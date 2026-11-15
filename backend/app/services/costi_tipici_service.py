"""I costi tipici di eToro e l'attesa dei piani al netto (FA-142).

Il pannello Motore dice l'attesa dei piani in R. Un'attesa di +0,05 R puo'
sparire nei costi: la commissione e' circa lo 0,15% del nozionale per lato
(misurato il 2026-11-15, uguale su AAPL e UCG.MI), e su uno stop al 2% vale
gia' 0,15 R andata e ritorno. Il costo in R dipende dalla distanza dello
stop, quindi lo stesso costo pesa molto di piu' sui piani brevi.

Le misure vengono da un preventivo di eToro in SOLA LETTURA
(`etoro_catalogo_service.costi`), una volta a settimana:

- un preventivo long a leva 1 per ogni titolo negoziabile: commissione e
  spread, che cambiano da titolo a titolo;
- per ogni valuta, un preventivo long e uno short alla leva tipica del conto:
  la notte dipende dal tasso della valuta, non dal titolo.

⚠️ Tre ipotesi, dichiarate perche' il preventivo non le copre:

1. La chiusura costa quanto l'apertura in commissione. Il preventivo descrive
   solo l'apertura; una stima che le ignorasse sarebbe ottimista.
2. Le notti sono i giorni di CALENDARIO fra ingresso e uscita: il venerdi'
   eToro addebita il fine settimana, cioe' tre notti, e contare sabato e
   domenica come notti normali da' la stessa somma.
3. A leva 1 nessuna notte: eToro non ne addebita (misurato, long e short).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CostoTipico, EtoroCatalogo, EtoroPosizione, Stock

#: Il nozionale del preventivo, in USD: le frazioni non ne dipendono.
IMPORTO = 1000.0
#: La leva se il conto non ne ha ancora una tipica.
LEVA_PREDEFINITA = 5
#: Pausa fra due preventivi: sono ~1.000 chiamate a settimana.
PAUSA_S = 0.5
#: Dopo tanti fallimenti di fila il job si ferma: probabilmente un limite.
FALLIMENTI_MAX = 5


def leva_tipica(db: Session) -> int:
    """La mediana delle leve sopra 1 delle posizioni eToro, aperte e chiuse."""
    leve = [int(v) for v in db.execute(
        select(EtoroPosizione.leva).where(EtoroPosizione.leva > 1)).scalars() if v]
    return int(round(median(leve))) if leve else LEVA_PREDEFINITA


@dataclass(frozen=True)
class Costo:
    commissione_pct: float
    spread_pct: float
    notte_long_pct: float | None
    notte_short_pct: float | None


def costo_in_r(
    *, costo: Costo, ingresso: float, r: float, lato: str, notti: int, con_leva: bool,
) -> float | None:
    """Il costo di un trade in multipli di R. None se manca un dato. Pura.

    Frazione del nozionale: due commissioni, uno spread, e le notti solo con
    leva. Diviso per la distanza dello stop come frazione del prezzo."""
    if ingresso <= 0 or r <= 0:
        return None
    pct = 2 * costo.commissione_pct + costo.spread_pct
    if con_leva and notti > 0:
        notte = costo.notte_long_pct if lato == "long" else costo.notte_short_pct
        if notte is None:
            return None
        pct += notti * notte
    return pct / (r / ingresso)


def _frazioni(voci, leva: int) -> dict[str, float]:
    nozionale = IMPORTO * leva
    somma: dict[str, float] = {}
    for v in voci:
        if v.importo_usd is None:
            continue
        somma[v.tipo] = somma.get(v.tipo, 0.0) + v.importo_usd / nozionale
    return somma


def aggiorna(
    db: Session, *, adesso: datetime | None = None, pausa: float = PAUSA_S,
    preventivo: Callable | None = None,
) -> dict[str, int]:
    """Rifa' la tabella. `preventivo` e' `etoro_catalogo_service.costi`,
    sostituibile nei test."""
    if preventivo is None:
        from app.services.etoro_catalogo_service import costi as preventivo  # noqa: PLC0415
    adesso = adesso or datetime.now(UTC)
    leva = leva_tipica(db)
    righe = db.execute(
        select(Stock.id, Stock.ticker, Stock.currency, Stock.ohlcv_in_pounds)
        .join(EtoroCatalogo, EtoroCatalogo.stock_id == Stock.id)
        .order_by(Stock.ticker)
    ).all()
    out = {"titoli": len(righe), "scritti": 0, "falliti": 0, "valute": 0}
    notti: dict[str, tuple[float | None, float | None]] = {}
    di_fila = 0
    for sid, ticker, valuta, _sterline in righe:
        chiave_valuta = (valuta or "?").upper()
        try:
            base = preventivo(db, ticker, lato="long", leva=1, importo=IMPORTO, stop=None)
            if chiave_valuta not in notti:
                lungo = preventivo(db, ticker, lato="long", leva=leva, importo=IMPORTO, stop=1e-6)
                corto = preventivo(db, ticker, lato="short", leva=leva, importo=IMPORTO, stop=1e12)
                notti[chiave_valuta] = (
                    _frazioni(lungo.voci, leva).get("overnightFee") if lungo else None,
                    _frazioni(corto.voci, leva).get("overnightFee") if corto else None,
                )
                out["valute"] += 1
            di_fila = 0
        except Exception as exc:  # noqa: BLE001 — un titolo non ferma gli altri
            out["falliti"] += 1
            di_fila += 1
            logger.warning(f"[costi] preventivo {ticker} fallito: {exc}")
            if di_fila >= FALLIMENTI_MAX:
                logger.warning("[costi] troppi fallimenti di fila: mi fermo")
                break
            continue
        if base is None:
            continue
        f = _frazioni(base.voci, 1)
        if "transactionFee" not in f:
            continue
        nl, ns = notti.get(chiave_valuta, (None, None))
        valori = dict(
            commissione_pct=f.get("transactionFee", 0.0) + f.get("sdrt", 0.0),
            spread_pct=f.get("marketSpread", 0.0) + f.get("markup", 0.0),
            notte_long_pct=nl, notte_short_pct=ns, leva=leva, valuta=chiave_valuta,
            aggiornato_il=adesso,
        )
        riga = db.get(CostoTipico, sid)
        if riga is None:
            db.add(CostoTipico(stock_id=sid, **valori))
        else:
            for k, v in valori.items():
                setattr(riga, k, v)
        out["scritti"] += 1
        if pausa:
            time.sleep(pausa)
    db.commit()
    logger.info(f"[costi] costi tipici aggiornati: {out}")
    return out


def per_titolo(db: Session) -> tuple[dict[int, Costo], int | None]:
    """{stock_id: Costo} e la leva a cui sono misurate le notti."""
    out: dict[int, Costo] = {}
    leve = set()
    for c in db.execute(select(CostoTipico)).scalars():
        out[c.stock_id] = Costo(c.commissione_pct, c.spread_pct, c.notte_long_pct,
                                c.notte_short_pct)
        leve.add(c.leva)
    return out, (max(leve) if leve else None)
