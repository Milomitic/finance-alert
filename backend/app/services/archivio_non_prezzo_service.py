"""Scrive l'archivio puntuale dei dati non-prezzo (`ArchivioNonPrezzo`).

Due passate, con costi molto diversi:

  fondamentali  NESSUNA chiamata di rete. Legge la cache dei fondamentali
                (L1, poi L2) e archivia cio' che contiene SOLO se e' stato
                scaricato dopo l'ultima riga archiviata: la cache si rinnova
                circa una volta a settimana per titolo (TTL 7 giorni, dentro la
                scansione notturna), e archiviare ogni notte la stessa copia
                moltiplicherebbe le righe senza aggiungere un fatto.
  opzioni       UNA catena per titolo USA, la prima scadenza ad almeno 7
                giorni: volatilita' implicita at-the-money di call e put,
                rapporti put/call di volume e open interest. Rete vera, quindi
                ha un tetto di tempo e si ferma al primo segno di limitazione.

⚠️ Nessuna delle due tocca un numero che il motore usa. Sono dati raccolti per
un modello che ancora non esiste, e la sola cosa che conta oggi e' che la
serie cominci — un consenso degli analisti di marzo non si puo' recuperare a
dicembre.
"""
from __future__ import annotations

import dataclasses
import json
import math
import time
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.models.archivio_non_prezzo import FONTE_FONDAMENTALI, FONTE_OPZIONI, ArchivioNonPrezzo

VERSIONE_FONDAMENTALI = "1"
VERSIONE_OPZIONI = "1"

#: Le parti della cache dei fondamentali che NON vengono dai prezzi. Il resto
#: (multipli, margini, bilanci) si ricostruisce dai rendiconti depositati.
#: Sul `Fundamentals`: analisti, stime della prossima trimestrale e dell'anno,
#: storia delle sorprese, insider.
_CAMPI_FONDAMENTALI: tuple[str, ...] = (
    "price_target", "analyst_ratings", "analyst_actions",
    "curr_fy_eps_estimate", "curr_fy_revenue_estimate",
    "next_eps_estimate", "next_revenue_estimate", "next_earnings_date", "earnings",
    "insiders",
)
#: Su `Fundamentals.micro` (da `Ticker.info`): consenso, stime, scoperto,
#: proprieta'.
_CAMPI_MICRO: tuple[str, ...] = (
    "recommendation_mean", "number_of_analyst_opinions",
    "eps_current_year", "eps_forward", "eps_growth_curr_fy", "revenue_growth_curr_fy",
    "shares_short", "short_ratio", "short_percent_of_float", "float_shares",
    "shares_outstanding", "held_percent_insiders", "held_percent_institutions",
)

#: Le azioni degli analisti si tengono solo degli ultimi 120 giorni: le piu'
#: vecchie sono gia' nelle righe precedenti, e ripeterle gonfierebbe ogni riga.
_AZIONI_GIORNI = 120


def _pulito(v):
    """JSON-sicuro: NaN e infiniti diventano None."""
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: _pulito(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_pulito(x) for x in v]
    return v


def estrai_fondamentali(f, *, oggi: date) -> dict:
    """Il sottoinsieme non-prezzo di un `Fundamentals`, versionato."""
    grezzo = dataclasses.asdict(f)
    micro = grezzo.get("micro") or {}
    out = {k: grezzo.get(k) for k in _CAMPI_FONDAMENTALI}
    out.update({k: micro.get(k) for k in _CAMPI_MICRO})
    soglia = (oggi - timedelta(days=_AZIONI_GIORNI)).isoformat()
    out["analyst_actions"] = [a for a in (out.get("analyst_actions") or [])
                              if str(a.get("date") or "")[:10] >= soglia]
    return {"versione": VERSIONE_FONDAMENTALI, **_pulito(out)}


def _inserisci(db: Session, **valori) -> bool:
    """ON CONFLICT DO NOTHING: due passate lo stesso giorno non si pestano, e
    su Postgres un doppione non lascia la sessione abortita."""
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    r = db.execute(insert(ArchivioNonPrezzo).values(**valori).on_conflict_do_nothing(
        index_elements=["stock_id", "fonte", "giorno"]))
    return bool(r.rowcount)


def _ultimo_osservato(db: Session, fonte: str) -> dict[int, datetime]:
    righe = db.execute(
        select(ArchivioNonPrezzo.stock_id, func.max(ArchivioNonPrezzo.osservato_il))
        .where(ArchivioNonPrezzo.fonte == fonte).group_by(ArchivioNonPrezzo.stock_id)
    ).all()
    out = {}
    for s, t in righe:
        if t is not None and t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        out[int(s)] = t
    return out


def archivia_fondamentali(db: Session, *, adesso: datetime | None = None) -> int:
    """Una riga per ogni titolo la cui cache e' piu' nuova dell'ultima archiviata."""
    from app.services import stock_fundamentals_service as fs

    adesso = adesso or datetime.now(UTC)
    ultimi = _ultimo_osservato(db, FONTE_FONDAMENTALI)
    scritte = 0
    for stock_id, ticker in db.execute(select(Stock.id, Stock.ticker)).all():
        try:
            f = fs.get_fundamentals_cached(db, ticker)
            if f is None or getattr(f, "error", None) or not getattr(f, "fetched_at", 0):
                continue
            osservato = datetime.fromtimestamp(float(f.fetched_at), tz=UTC)
            prima = ultimi.get(int(stock_id))
            if prima is not None and osservato <= prima:
                continue   # la stessa copia gia' archiviata
            dati = estrai_fondamentali(f, oggi=osservato.date())
            if _inserisci(db, stock_id=stock_id, fonte=FONTE_FONDAMENTALI,
                          giorno=osservato.date(), osservato_il=osservato,
                          dati=json.dumps(dati, default=str)):
                scritte += 1
        except Exception as exc:  # noqa: BLE001 — un titolo non ferma gli altri
            logger.debug(f"[archivio] fondamentali {ticker}: {exc}")
    db.commit()
    logger.info(f"[archivio] fondamentali: {scritte} righe nuove")
    return scritte


# ─── opzioni ───────────────────────────────────────────────────────────────

def e_usa(ticker: str) -> bool:
    """Le opzioni quotate su Yahoo sono quelle USA: niente suffisso di borsa
    (`.L`, `.MI`, `.HK`...) e niente indici."""
    return bool(ticker) and "." not in ticker and not ticker.startswith("^")


def _iv_atm(tabella, prezzo: float) -> float | None:
    """La volatilita' implicita dello strike piu' vicino al prezzo."""
    if tabella is None or len(tabella) == 0 or "strike" not in tabella or "impliedVolatility" not in tabella:
        return None
    t = tabella[tabella["impliedVolatility"] > 0]
    if len(t) == 0:
        return None
    riga = t.iloc[(t["strike"] - prezzo).abs().argsort().iloc[0]]
    iv = float(riga["impliedVolatility"])
    return iv if math.isfinite(iv) else None


def _somma(tabella, col: str) -> float:
    if tabella is None or col not in tabella:
        return 0.0
    v = float(tabella[col].fillna(0).sum())
    return v if math.isfinite(v) else 0.0


def estrai_opzioni(calls, puts, *, prezzo: float, scadenza: str, oggi: date) -> dict:
    """Il riassunto di una catena: IV ATM, rapporti put/call, scadenza."""
    vc, vp = _somma(calls, "volume"), _somma(puts, "volume")
    oc, op_ = _somma(calls, "openInterest"), _somma(puts, "openInterest")
    return _pulito({
        "versione": VERSIONE_OPZIONI,
        "scadenza": scadenza,
        "giorni": (date.fromisoformat(scadenza) - oggi).days,
        "prezzo": prezzo,
        "iv_atm_call": _iv_atm(calls, prezzo),
        "iv_atm_put": _iv_atm(puts, prezzo),
        "put_call_volume": vp / vc if vc > 0 else None,
        "put_call_oi": op_ / oc if oc > 0 else None,
        "open_interest": oc + op_,
    })


def _catena(ticker: str, oggi: date):
    """(scadenza, calls, puts) della prima scadenza ad almeno 7 giorni, o None."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    scadenze = [s for s in (t.options or []) if (date.fromisoformat(s) - oggi).days >= 7]
    if not scadenze:
        return None
    c = t.option_chain(scadenze[0])
    return scadenze[0], c.calls, c.puts


def archivia_opzioni(
    db: Session, *, adesso: datetime | None = None, tetto_s: float = 40 * 60,
    pausa_s: float = 0.3, catena=None,
) -> int:
    """Una riga per titolo USA per giorno. Si ferma al tetto di tempo, al
    breaker di yfinance aperto, o dopo 20 errori di fila."""
    from app.services import yfinance_health

    adesso = adesso or datetime.now(UTC)
    oggi = adesso.date()
    catena = catena or _catena
    fatti = {s for (s,) in db.execute(
        select(ArchivioNonPrezzo.stock_id).where(
            ArchivioNonPrezzo.fonte == FONTE_OPZIONI, ArchivioNonPrezzo.giorno == oggi))}
    ultima_chiusura = dict(db.execute(
        select(OhlcvDaily.stock_id, func.max(OhlcvDaily.date)).group_by(OhlcvDaily.stock_id)).all())
    t0, scritte, errori = time.monotonic(), 0, 0
    for stock_id, ticker in db.execute(select(Stock.id, Stock.ticker).order_by(Stock.id)).all():
        if not e_usa(ticker) or stock_id in fatti or stock_id not in ultima_chiusura:
            continue
        if time.monotonic() - t0 > tetto_s:
            logger.info("[archivio] opzioni: tetto di tempo raggiunto")
            break
        if yfinance_health.is_open():
            logger.warning("[archivio] opzioni: breaker yfinance aperto, mi fermo")
            break
        prezzo = db.execute(select(OhlcvDaily.close).where(
            OhlcvDaily.stock_id == stock_id, OhlcvDaily.date == ultima_chiusura[stock_id])).scalar()
        try:
            risposta = catena(ticker, oggi)
            errori = 0
        except Exception as exc:  # noqa: BLE001 — una catena non ferma le altre
            errori += 1
            if yfinance_health.is_rate_limit_error(exc):
                yfinance_health.record_failure(f"opzioni {ticker}: {exc}")
                logger.warning("[archivio] opzioni: limitazione di Yahoo, mi fermo")
                break
            if errori >= 20:
                logger.warning(f"[archivio] opzioni: 20 errori di fila, mi fermo ({exc})")
                break
            continue
        if risposta is not None and prezzo:
            scadenza, calls, puts = risposta
            dati = estrai_opzioni(calls, puts, prezzo=float(prezzo), scadenza=scadenza, oggi=oggi)
            if _inserisci(db, stock_id=stock_id, fonte=FONTE_OPZIONI, giorno=oggi,
                          osservato_il=adesso, dati=json.dumps(dati)):
                scritte += 1
                if scritte % 50 == 0:
                    db.commit()
        if pausa_s:
            time.sleep(pausa_s)
    db.commit()
    logger.info(f"[archivio] opzioni: {scritte} righe in {time.monotonic() - t0:.0f}s")
    return scritte
