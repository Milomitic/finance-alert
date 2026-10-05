"""Il portafoglio eToro dell'utente nell'app (FA-124).

`sincronizza` legge il conto e aggiorna le tre tabelle di `app.models.etoro`.
Il job lo chiama ogni 10 minuti (`sincronizza_etoro`). Quattro chiamate al
massimo per giro, contro le 60 al minuto che eToro concede.

Quattro regole, ognuna con la sua ragione:

1. **P/L, margine ed esposizione sono di eToro.** Arrivano da
   `unrealizedPnL` nella valuta del conto (USD). Con leva, CFD e cambio la
   formula e' loro (`pnlVersion`): una copia locale divergerebbe in silenzio.
2. **Una posizione si chiude quando lo storico lo conferma**, col prezzo e il
   profitto veri. Sparire dalla lettura non basta: una risposta parziale o un
   ritardo dello storico chiuderebbero posizioni ancora aperte. Dopo 24 ore di
   assenza senza conferma si chiude dichiarandolo («non_trovata»).
3. **Una risposta senza `clientPortfolio.positions` e' un errore, non un conto
   vuoto.** Altrimenti un guasto di eToro chiuderebbe ogni posizione.
4. **L'abbinamento al catalogo e' automatico solo se e' sicuro.** Simbolo
   identico E nome compatibile; un candidato meno sicuro aspetta una conferma
   e non entra fra i «tuoi titoli». Un abbinamento sbagliato sembra giusto:
   metterebbe una posizione sul titolo sbagliato, con le novita', i promemoria
   e le notifiche di un'altra societa'. Meglio un titolo non abbinato e
   dichiarato.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import UpstreamError, UpstreamUnavailable
from app.models import Stock
from app.models.etoro import EtoroConto, EtoroPosizione, EtoroStrumento
from app.services import etoro_client
from app.services.sec_13f_scraper import normalize_issuer_name

ROMA = ZoneInfo("Europe/Rome")

AUTOMATICO = "automatico"
MANUALE = "manuale"
DA_CONFERMARE = "da_confermare"
ASSENTE = "assente"
ABBINAMENTI = (AUTOMATICO, MANUALE, DA_CONFERMARE, ASSENTE)

#: settlementTypeID di eToro.
REGOLAMENTI: dict[int, str] = {0: "cfd", 1: "reale", 2: "swap", 3: "crypto_margine", 4: "future"}
ALTRO = "altro"

STOP = "stop"
TARGET = "target"
CHIUSA = "chiusa"
NON_TROVATA = "non_trovata"
MOTIVI = (STOP, TARGET, CHIUSA, NON_TROVATA)

#: Dopo quanto un'assenza senza conferma dello storico diventa una chiusura.
ATTESA_STORICO = timedelta(hours=24)
#: Una chiusura e' «a stop» o «a target» se il prezzo e' entro questo scarto.
_TOLLERANZA_LIVELLO = 0.005
#: Lo storico accetta al massimo un anno meno un giorno.
_STORICO_MAX = timedelta(days=364)
_PAGINE_STORICO = 10
_RIGHE_PAGINA = 100
#: Ogni quanto si rilegge l'anagrafica di uno strumento gia' noto.
_ANAGRAFICA_VECCHIA = timedelta(days=7)

_PNL = "/api/v1/trading/info/real/pnl"
_STRUMENTI = "/api/v2/market-data/instruments"
_STORICO = "/api/v1/trading/info/trade/history"
_AGGREGATO = "/api/v1/trading/info/aggregate-portfolio"


@dataclass
class Esito:
    saltata: str | None = None
    aperte: int = 0
    nuove: int = 0
    chiuse: list[int] = field(default_factory=list)
    strumenti_nuovi: int = 0
    da_confermare: int = 0
    conto_aggiornato: bool = False


# ─── Lettura delle risposte ─────────────────────────────────────────────────


def _ts(v: Any) -> datetime | None:
    if not v or not isinstance(v, str):
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _livello(rate: Any, disattivato: Any) -> float | None:
    """Stop o target: None se disattivato su eToro o se vale zero."""
    if disattivato is True:
        return None
    x = _num(rate)
    return x if x and x > 0 else None


def posizioni_della_risposta(dati: Any) -> list[dict]:
    """Le posizioni aperte, dirette e da copy trading. Una risposta senza
    `clientPortfolio.positions` solleva: non e' un conto vuoto (regola 3)."""
    cp = dati.get("clientPortfolio") if isinstance(dati, dict) else None
    if not isinstance(cp, dict) or not isinstance(cp.get("positions"), list):
        raise UpstreamUnavailable(
            "eToro: risposta senza clientPortfolio.positions", source="etoro", op="portafoglio"
        )
    out = [p for p in cp["positions"] if isinstance(p, dict)]
    for m in cp.get("mirrors") or []:
        if isinstance(m, dict):
            out.extend(p for p in (m.get("positions") or []) if isinstance(p, dict))
    return out


# ─── Abbinamento al catalogo ────────────────────────────────────────────────


def _varianti(simbolo: str) -> set[str]:
    s = simbolo.strip().upper()
    out = {s}
    # Classi di azioni: eToro «BRK.B», il catalogo «BRK-B». Solo con UNA lettera
    # dopo il punto, perche' «.MI» o «.HK» sono borse e non classi.
    m = re.fullmatch(r"([A-Z0-9]+)\.([A-Z])", s)
    if m:
        out.add(f"{m.group(1)}-{m.group(2)}")
    # Gli ETF americani su eToro portano «.US» (misurato il 2026-10-05:
    # «LABU.US» contro «NUGT» e «SOXL» senza): il catalogo non ha suffisso.
    if s.endswith(".US") and len(s) > 3:
        out.add(s[:-3])
    return out


def nomi_compatibili(a: str | None, b: str | None) -> bool:
    """Due nomi della stessa societa'? Uguali dopo la normalizzazione, uno
    prefisso dell'altro, o la stessa prima parola significativa."""
    na, nb = normalize_issuer_name(a or ""), normalize_issuer_name(b or "")
    if not na or not nb:
        return False
    if na == nb or na.startswith(nb) or nb.startswith(na):
        return True
    # «Super Micro Computer» contro «Supermicro»: gli spazi non fanno la societa'.
    ca, cb = na.replace(" ", ""), nb.replace(" ", "")
    if min(len(ca), len(cb)) >= 5 and (ca.startswith(cb) or cb.startswith(ca)):
        return True
    return na.split()[0] == nb.split()[0] and len(na.split()[0]) >= 3


def abbina(db: Session, simbolo: str | None, nome: str | None) -> tuple[int | None, int | None, str]:
    """(stock_id, candidato_stock_id, stato). Regola 4 del modulo."""
    if not simbolo:
        return None, None, ASSENTE
    righe = db.execute(
        select(Stock.id, Stock.name).where(func.upper(Stock.ticker).in_(_varianti(simbolo)))
    ).all()
    if not righe:
        return None, None, ASSENTE
    compatibili = [sid for sid, n in righe if nomi_compatibili(nome, n)]
    if len(compatibili) == 1:
        return compatibili[0], None, AUTOMATICO
    return None, (compatibili or [righe[0][0]])[0], DA_CONFERMARE


#: L'endpoint degli strumenti rende al massimo 100 risultati per pagina: si
#: chiede a lotti di 100 id, e le watchlist ne portano centinaia (FA-125).
_LOTTO_STRUMENTI = 100


def aggiorna_strumenti(db: Session, ids: set[int], adesso: datetime) -> int:
    """Anagrafica e abbinamento degli strumenti dati. Rende quanti sono nuovi."""
    noti = {s.instrument_id: s for s in db.execute(
        select(EtoroStrumento).where(EtoroStrumento.instrument_id.in_(ids))
    ).scalars()}
    da_leggere = sorted(
        i for i in ids if i not in noti or adesso - _aware(noti[i].aggiornato_il) > _ANAGRAFICA_VECCHIA
    )
    anagrafica: dict[int, dict] = {}
    for i in range(0, len(da_leggere), _LOTTO_STRUMENTI):
        lotto = da_leggere[i:i + _LOTTO_STRUMENTI]
        dati = etoro_client.get(
            _STRUMENTI, op="strumenti",
            params={"instrumentsIds": ",".join(str(x) for x in lotto), "pageSize": _LOTTO_STRUMENTI},
        )
        for r in (dati.get("results") if isinstance(dati, dict) else None) or []:
            if isinstance(r, dict) and isinstance(r.get("instrumentId"), int):
                anagrafica[r["instrumentId"]] = r
    nuovi = 0
    for iid in da_leggere:
        r = anagrafica.get(iid, {})
        s = noti.get(iid)
        if s is None:
            s = EtoroStrumento(instrument_id=iid, abbinamento=ASSENTE, aggiornato_il=adesso)
            db.add(s)
            nuovi += 1
        s.simbolo = (r.get("symbol") or s.simbolo or None)
        s.nome = (r.get("displayName") or s.nome or None)
        s.tipo = (r.get("type") or s.tipo or None)
        s.exchange_id = r.get("exchangeId", s.exchange_id)
        s.aggiornato_il = adesso
        # Una conferma dell'utente non si rifa' da sola.
        if s.abbinamento != MANUALE:
            s.stock_id, s.candidato_stock_id, s.abbinamento = abbina(db, s.simbolo, s.nome)
    db.flush()
    return nuovi


def _aware(d: datetime) -> datetime:
    """SQLite rende datetime senza fuso anche da colonne `timezone=True`."""
    return d if d.tzinfo else d.replace(tzinfo=UTC)


# ─── Posizioni ──────────────────────────────────────────────────────────────


def _applica(row: EtoroPosizione, p: dict, adesso: datetime) -> None:
    pnl = p.get("unrealizedPnL") if isinstance(p.get("unrealizedPnL"), dict) else {}
    row.instrument_id = int(p["instrumentID"])
    row.mirror_id = p.get("mirrorID") or None
    row.lato = "long" if p.get("isBuy", True) else "short"
    row.leva = int(p.get("leverage") or 1)
    row.regolamento = REGOLAMENTI.get(p.get("settlementTypeID"), ALTRO)
    row.aperta_il = _ts(p.get("openDateTime")) or row.aperta_il or adesso
    row.prezzo_apertura = float(p["openRate"])
    row.unita = float(p.get("units") or 0.0)
    row.importo_usd = float(p.get("amount") or 0.0)
    row.investimento_iniziale_usd = _num(p.get("initialAmountInDollars"))
    row.stop = _livello(p.get("stopLossRate"), p.get("isNoStopLoss"))
    row.target = _livello(p.get("takeProfitRate"), p.get("isNoTakeProfit"))
    row.trailing = bool(p.get("isTslEnabled"))
    row.commissioni_usd = _num(p.get("totalFees"))
    row.pnl_usd = _num(pnl.get("pnL"))
    row.margine_usd = _num(pnl.get("marginInAccountCurrency"))
    row.esposizione_usd = _num(pnl.get("exposureInAccountCurrency"))
    row.prezzo_corrente = _num(pnl.get("closeRate"))
    row.pnl_il = _ts(pnl.get("timestamp")) or adesso
    row.vista_il = adesso


def motivo_chiusura(prezzo: float | None, stop: float | None, target: float | None) -> str:
    """«stop» o «target» se la chiusura e' a quel livello, altrimenti «chiusa»."""
    if prezzo is None:
        return CHIUSA
    for livello, motivo in ((stop, STOP), (target, TARGET)):
        if livello and abs(prezzo - livello) / livello <= _TOLLERANZA_LIVELLO:
            return motivo
    return CHIUSA


def _storico(dal: date) -> dict[int, dict]:
    """Le operazioni chiuse da `dal`, per positionId. Al massimo
    `_PAGINE_STORICO` pagine: il giro dopo riprende da dove serve."""
    out: dict[int, dict] = {}
    for pagina in range(1, _PAGINE_STORICO + 1):
        dati = etoro_client.get(
            _STORICO, op="storico",
            params={"minDate": dal.isoformat(), "page": pagina, "pageSize": _RIGHE_PAGINA},
        )
        # La specifica dichiara una lista; un oggetto con la lista dentro si
        # accetta lo stesso, perche' un cambio di forma non chiuda niente.
        if isinstance(dati, list):
            righe = dati
        elif isinstance(dati, dict):
            righe = dati.get("trades") or dati.get("items") or []
        else:
            righe = []
        for r in righe:
            if isinstance(r, dict) and isinstance(r.get("positionId"), int):
                out[r["positionId"]] = r
        if len(righe) < _RIGHE_PAGINA:
            break
    return out


def _chiudi(row: EtoroPosizione, r: dict | None, adesso: datetime) -> None:
    if r is None:
        row.chiusa_il = _aware(row.vista_il)
        row.motivo_chiusura = NON_TROVATA
        return
    row.chiusa_il = _ts(r.get("closeTimestamp")) or adesso
    row.prezzo_chiusura = _num(r.get("closeRate"))
    row.profitto_netto_usd = _num(r.get("netProfit"))
    row.motivo_chiusura = motivo_chiusura(
        row.prezzo_chiusura,
        _num(r.get("stopLossRate")) or row.stop,
        _num(r.get("takeProfitRate")) or row.target,
    )


def _registra_chiusure(db: Session, viste: set[int], adesso: datetime) -> list[int]:
    scomparse = list(db.execute(
        select(EtoroPosizione).where(
            EtoroPosizione.chiusa_il.is_(None), EtoroPosizione.position_id.notin_(viste or {-1})
        )
    ).scalars())
    if not scomparse:
        return []
    dal = max(
        min(_aware(r.aperta_il) for r in scomparse).astimezone(UTC).date(),
        (adesso - _STORICO_MAX).date(),
    )
    storico = _storico(dal)
    chiuse: list[int] = []
    for row in scomparse:
        r = storico.get(row.position_id)
        if r is None and adesso - _aware(row.vista_il) < ATTESA_STORICO:
            continue  # lo storico di eToro puo' arrivare in ritardo: si riprova
        _chiudi(row, r, adesso)
        chiuse.append(row.position_id)
    return chiuse


# ─── Conto ──────────────────────────────────────────────────────────────────


def mezzanotte_di_roma_utc(adesso: datetime) -> datetime:
    """L'inizio di «oggi» per chi usa l'app, in UTC: cio' che `dailyCutoffUtc` vuole."""
    locale = adesso.astimezone(ROMA)
    return locale.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def _aggiorna_conto(db: Session, credito: float | None, adesso: datetime) -> bool:
    conto = db.get(EtoroConto, 1)
    if conto is None:
        conto = EtoroConto(id=1, aggiornato_il=adesso)
        db.add(conto)
    conto.credito_usd = credito
    conto.aggiornato_il = adesso
    try:
        dati = etoro_client.get(_AGGREGATO, op="portafoglio", params={
            "pnlLevel": "DailyPnl",
            "dailyCutoffUtc": mezzanotte_di_roma_utc(adesso).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    except UpstreamError as e:
        # Il totale e' un di piu': le posizioni restano aggiornate.
        logger.warning(f"[etoro] totali del conto non letti: {e}")
        return False
    tot = dati.get("accountTotals") if isinstance(dati, dict) else None
    if not isinstance(tot, dict):
        return False
    conto.valuta = (dati.get("accountCurrency") or None)
    conto.valore_totale = _num(tot.get("accountTotalValue"))
    conto.pnl_aperto = _num(tot.get("accountCurrentPnl"))
    conto.guadagno_giorno = _num(tot.get("dailyGainAccountCurrency"))
    conto.guadagno_giorno_pct = _num(tot.get("dailyGainAccountCurrencyPercent"))
    return True


# ─── La sincronizzazione ────────────────────────────────────────────────────


def sincronizza(db: Session, *, adesso: datetime | None = None) -> Esito:
    if not etoro_client.configurato():
        return Esito(saltata="non configurato")
    adesso = adesso or datetime.now(UTC)
    dati = etoro_client.get(_PNL, op="portafoglio")
    posizioni = posizioni_della_risposta(dati)  # solleva prima di toccare il db
    esito = Esito()
    ids = {int(p["instrumentID"]) for p in posizioni if isinstance(p.get("instrumentID"), int)}
    if ids:
        esito.strumenti_nuovi = aggiorna_strumenti(db, ids, adesso)

    viste: set[int] = set()
    for p in posizioni:
        pid = p.get("positionID")
        if not isinstance(pid, int) or not isinstance(p.get("instrumentID"), int) or p.get("openRate") is None:
            continue
        row = db.get(EtoroPosizione, pid)
        if row is None:
            row = EtoroPosizione(position_id=pid, notificata=False)
            db.add(row)
            esito.nuove += 1
        _applica(row, p, adesso)
        viste.add(pid)
    db.flush()
    esito.aperte = len(viste)
    esito.chiuse = _registra_chiusure(db, viste, adesso)
    cp = dati.get("clientPortfolio") or {}
    esito.conto_aggiornato = _aggiorna_conto(db, _num(cp.get("credit")), adesso)
    esito.da_confermare = len(da_decidere(db))
    db.commit()
    return esito


# ─── Letture per l'API e per gli altri servizi ──────────────────────────────


def stock_id_aperti():
    """I titoli del catalogo con una posizione eToro aperta: per `rilevanza_service`."""
    return (
        select(EtoroStrumento.stock_id)
        .join(EtoroPosizione, EtoroPosizione.instrument_id == EtoroStrumento.instrument_id)
        .where(EtoroPosizione.chiusa_il.is_(None), EtoroStrumento.stock_id.is_not(None))
    )


def pct_sul_margine(pnl: float | None, margine: float | None) -> float | None:
    if pnl is None or not margine:
        return None
    return pnl / margine * 100.0


def stop_sul_margine(lato: str, prezzo_apertura: float, stop: float | None, leva: int) -> float | None:
    """Quanto del margine si perde se scatta lo stop, in %: la distanza dello
    stop dal prezzo d'apertura moltiplicata per la leva. Negativo = perdita.
    Non conta commissioni e cambio: e' la geometria, non il conto."""
    if stop is None or prezzo_apertura <= 0:
        return None
    mossa = (stop - prezzo_apertura) / prezzo_apertura
    if lato == "short":
        mossa = -mossa
    return mossa * leva * 100.0


def da_notificare(db: Session) -> list[tuple[EtoroPosizione, EtoroStrumento, Stock | None]]:
    righe = db.execute(
        select(EtoroPosizione, EtoroStrumento)
        .join(EtoroStrumento, EtoroStrumento.instrument_id == EtoroPosizione.instrument_id)
        .where(EtoroPosizione.chiusa_il.is_not(None), EtoroPosizione.notificata.is_(False))
        .order_by(EtoroPosizione.chiusa_il)
    ).all()
    out = []
    for pos, s in righe:
        stock = db.get(Stock, s.stock_id) if s.stock_id else None
        out.append((pos, s, stock))
    return out


def segna_notificate(db: Session, position_ids: list[int]) -> None:
    for pid in position_ids:
        row = db.get(EtoroPosizione, pid)
        if row is not None:
            row.notificata = True
    db.commit()


#: I tipi eToro per cui un'assenza dal catalogo chiede una decisione. Crypto,
#: materie prime e indici fuori catalogo lo sono per natura e non chiedono niente.
AZIONARI = frozenset({"Stocks", "ETF"})


def _in_posizione():
    return select(EtoroPosizione.instrument_id).where(EtoroPosizione.chiusa_il.is_(None))


def da_decidere(db: Session) -> list[EtoroStrumento]:
    """Gli strumenti IN POSIZIONE che aspettano l'utente: prima i candidati
    incerti, poi gli azionari senza corrispondenza. Proprietario unico della
    regola: il client la riceve gia' applicata, nella stessa risposta del
    portafoglio. Solo le posizioni aperte: le watchlist portano 173 titoli
    fuori catalogo (2026-10-06), che qui sarebbero una lista illeggibile."""
    righe = db.execute(
        select(EtoroStrumento).where(
            EtoroStrumento.instrument_id.in_(_in_posizione()),
            (EtoroStrumento.abbinamento == DA_CONFERMARE)
            | ((EtoroStrumento.abbinamento == ASSENTE) & EtoroStrumento.tipo.in_(AZIONARI)),
        )
    ).scalars().all()
    return sorted(righe, key=lambda s: (s.abbinamento != DA_CONFERMARE, s.simbolo or ""))


def watchlist_da_confermare(db: Session) -> list[EtoroStrumento]:
    """Dalle watchlist, i candidati incerti (simbolo nel catalogo, nome
    diverso): pochi e decidibili a colpo d'occhio, a differenza degli assenti."""
    righe = db.execute(
        select(EtoroStrumento).where(
            EtoroStrumento.in_watchlist.is_(True),
            EtoroStrumento.abbinamento == DA_CONFERMARE,
            EtoroStrumento.instrument_id.notin_(_in_posizione()),
        )
    ).scalars().all()
    return sorted(righe, key=lambda s: s.simbolo or "")


def conferma_abbinamento(db: Session, instrument_id: int, ticker: str | None) -> EtoroStrumento:
    """L'utente decide: un ticker del catalogo, o nessuno («non e' nel catalogo»)."""
    s = db.get(EtoroStrumento, instrument_id)
    if s is None:
        raise LookupError(f"strumento eToro {instrument_id} sconosciuto")
    if ticker:
        sid = db.execute(
            select(Stock.id).where(func.upper(Stock.ticker) == ticker.strip().upper()).limit(1)
        ).scalars().first()
        if sid is None:
            raise ValueError(f"{ticker} non e' nel catalogo")
        s.stock_id = sid
    else:
        s.stock_id = None
    s.candidato_stock_id = None
    s.abbinamento = MANUALE
    db.commit()
    return s
