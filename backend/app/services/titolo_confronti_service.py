"""Il dettaglio titolo messo a confronto: con i pari e con le proprie
trimestrali (FA-156).

Tutto descrittivo e tutto dalle cache o dal database: nessuna chiamata di rete.

**I pari.** I sei titoli della stessa INDUSTRIA piu' vicini per
capitalizzazione in dollari (FA-026: ordinare in valuta nativa metteva in testa
dieci coreani). Se l'industria ne ha meno di `MIN_INDUSTRIA` si allarga al
settore, e la risposta lo dice: un confronto su due titoli non e' un
confronto.

**Le reazioni alle trimestrali.** Per ogni trimestrale passata con l'utile
riportato: il movimento della seduta di reazione e quello a 5 sedute, accanto
alla sorpresa. La seduta di reazione dipende dall'ora dell'annuncio
(`earnings_session_timing`):

    pre       la seduta del giorno stesso, contro la chiusura precedente
    after     la seduta del giorno dopo, contro la chiusura del giorno stesso
    ignota    dalla chiusura del giorno prima a quella del giorno dopo, e la
              riga lo dichiara: due sedute invece di una

⚠️ Non e' una previsione della prossima reazione, e lo schermo lo dice: e'
quanto si e' mosso il titolo, cioe' la misura di quanto rischio porta la data.
"""
from __future__ import annotations

import math
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock, StockScore, TechnicalScore
from app.services import fx_service
from app.services import stock_fundamentals_service as sfs
from app.services.earnings_session_timing import classify_session_timing

PARI = 6
MIN_INDUSTRIA = 3
SEDUTE_3M = 63


def _cap_usd(s: Stock) -> float | None:
    if not s.market_cap or s.market_cap <= 0:
        return None
    if (s.currency or "USD").upper() == "USD":
        return float(s.market_cap)
    try:
        return fx_service.to_usd(float(s.market_cap), s.currency)
    except Exception:  # noqa: BLE001 — un cambio mancante toglie il titolo, non la risposta
        return None


def _rendimento_3m(db: Session, stock_id: int) -> float | None:
    chiusure = [float(c) for c in db.execute(
        select(OhlcvDaily.close).where(OhlcvDaily.stock_id == stock_id)
        .order_by(OhlcvDaily.date.desc()).limit(SEDUTE_3M + 1)
    ).scalars()]
    if len(chiusure) <= SEDUTE_3M or chiusure[-1] <= 0:
        return None
    return chiusure[0] / chiusure[-1] - 1.0


def _riga(db: Session, s: Stock, cap: float | None, qualita: dict, tecnico: dict) -> dict:
    f = sfs._CACHE.get(s.ticker)
    micro = f.micro if f is not None else None
    return {
        "ticker": s.ticker, "nome": s.name, "cap_usd": cap,
        "qualita": qualita.get(s.id), "tecnico": tecnico.get(s.id),
        "pe": getattr(micro, "trailing_pe", None),
        "pe_forward": getattr(micro, "forward_pe", None),
        "crescita_ricavi": getattr(micro, "revenue_growth", None),
        "rendimento_3m": _rendimento_3m(db, s.id),
    }


def pari(db: Session, ticker: str) -> dict | None:
    """{base, industria|settore, righe: [il titolo, poi i pari]}. None se il
    titolo non esiste."""
    s = db.execute(select(Stock).where(Stock.ticker == ticker).limit(1)).scalars().first()
    if s is None:
        return None
    base, valore = "industria", s.industry
    candidati: list[Stock] = []
    if s.industry:
        candidati = list(db.execute(select(Stock).where(
            Stock.industry == s.industry, Stock.id != s.id, Stock.instrument_type != "etf",
        )).scalars())
    if len(candidati) < MIN_INDUSTRIA and s.sector:
        base, valore = "settore", s.sector
        candidati = list(db.execute(select(Stock).where(
            Stock.sector == s.sector, Stock.id != s.id, Stock.instrument_type != "etf",
        )).scalars())
    mia = _cap_usd(s)
    con_cap = [(c, _cap_usd(c)) for c in candidati]
    con_cap = [(c, k) for c, k in con_cap if k]
    if mia:
        con_cap.sort(key=lambda ck: abs(math.log(ck[1] / mia)))
    else:
        con_cap.sort(key=lambda ck: -ck[1])
    scelti = con_cap[:PARI]
    ids = [s.id] + [c.id for c, _ in scelti]
    qualita = dict(db.execute(select(StockScore.stock_id, StockScore.composite)
                              .where(StockScore.stock_id.in_(ids))).all())
    tecnico = dict(db.execute(select(TechnicalScore.stock_id, TechnicalScore.composite)
                              .where(TechnicalScore.stock_id.in_(ids))).all())
    righe = [_riga(db, s, mia, qualita, tecnico)]
    righe += [_riga(db, c, k, qualita, tecnico) for c, k in scelti]
    return {"base": base, "gruppo": valore, "righe": righe}


def reazioni_trimestrali(db: Session, ticker: str) -> dict | None:
    """{righe: [...], mediana_assoluta_pct}. None se il titolo non esiste."""
    s = db.execute(select(Stock).where(Stock.ticker == ticker).limit(1)).scalars().first()
    if s is None:
        return None
    f = sfs._CACHE.get(ticker)
    passate = [e for e in (f.earnings if f is not None else []) if e.eps_reported is not None]
    barre = db.execute(
        select(OhlcvDaily.date, OhlcvDaily.close).where(OhlcvDaily.stock_id == s.id)
        .order_by(OhlcvDaily.date)
    ).all()
    date_ = [d if isinstance(d, date) else date.fromisoformat(str(d)[:10]) for d, _ in barre]
    chiusure = [float(c) for _, c in barre]

    def indice_da(g: date) -> int | None:
        """La prima barra in data g o dopo."""
        for i, d in enumerate(date_):
            if d >= g:
                return i
        return None

    righe = []
    for e in passate:
        try:
            g = date.fromisoformat(str(e.date)[:10])
        except ValueError:
            continue
        i = indice_da(g)
        if i is None or i == 0:
            continue
        quando = classify_session_timing(e.time_utc, s.country)
        stesso = date_[i] == g
        if quando == "pre":
            prima, reazione = i - 1, i
        elif quando == "after":
            prima, reazione = (i, i + 1) if stesso else (i - 1, i)
        else:
            prima, reazione = i - 1, (i + 1 if stesso else i)
        if reazione >= len(chiusure) or chiusure[prima] <= 0:
            continue
        cinque = reazione + 4
        righe.append({
            "data": g.isoformat(), "quando": quando,
            "sorpresa_pct": e.surprise_pct,
            "reazione_pct": chiusure[reazione] / chiusure[prima] - 1.0,
            "cinque_sedute_pct": (chiusure[cinque] / chiusure[prima] - 1.0)
            if cinque < len(chiusure) else None,
            "due_sedute": quando is None and stesso,
        })
    righe.sort(key=lambda r: r["data"], reverse=True)
    assolute = sorted(abs(r["reazione_pct"]) for r in righe)
    mediana = None
    if assolute:
        m = len(assolute) // 2
        mediana = assolute[m] if len(assolute) % 2 else (assolute[m - 1] + assolute[m]) / 2
    return {"righe": righe, "mediana_assoluta_pct": mediana}


# ─── Che cosa ha mosso il punteggio Qualità ────────────────────────────────

FINESTRE_PUNTEGGIO = (30, 90)


def variazione_punteggio(db: Session, ticker: str, *, oggi: date | None = None) -> dict | None:
    """Per 30 e 90 giorni: il composito Qualità di allora e di adesso, e il
    contributo di ciascun pilastro alla differenza.

    Il composito e' la media pesata dei pilastri PRESENTI
    (`score_service.common.PILLAR_WEIGHTS`), quindi il contributo di un
    pilastro e' peso / somma dei pesi presenti x la sua variazione. Quello che
    resta — un pilastro comparso o sparito, una riscalatura trasversale — e'
    `altro`, e si dichiara invece di spalmarlo sui pilastri.
    """
    import json  # noqa: PLC0415
    from datetime import timedelta  # noqa: PLC0415

    from app.models import ScoreHistory  # noqa: PLC0415
    from app.services.score_service.common import PILLAR_WEIGHTS  # noqa: PLC0415

    s = db.execute(select(Stock).where(Stock.ticker == ticker).limit(1)).scalars().first()
    if s is None:
        return None
    storia = db.execute(
        select(ScoreHistory.captured_on, ScoreHistory.composite, ScoreHistory.pillars)
        .where(ScoreHistory.stock_id == s.id, ScoreHistory.lens == "qualita")
        .order_by(ScoreHistory.captured_on)
    ).all()
    out: dict = {"finestre": []}
    if not storia:
        return out
    ultimo_giorno, ultimo_comp, ultimi_pil = storia[-1]
    ultimi = json.loads(ultimi_pil or "{}")
    for giorni in FINESTRE_PUNTEGGIO:
        limite = (oggi or ultimo_giorno) - timedelta(days=giorni)
        prima = [r for r in storia if r[0] <= limite]
        if not prima:
            continue
        g0, c0, p0 = prima[-1]
        vecchi = json.loads(p0 or "{}")
        comuni = [p for p in PILLAR_WEIGHTS
                  if ultimi.get(p) is not None and vecchi.get(p) is not None]
        peso = sum(PILLAR_WEIGHTS[p] for p in comuni)
        contributi = [
            {"pilastro": p, "da": vecchi[p], "a": ultimi[p],
             "contributo": PILLAR_WEIGHTS[p] / peso * (ultimi[p] - vecchi[p])}
            for p in comuni
        ] if peso else []
        contributi.sort(key=lambda c: abs(c["contributo"]), reverse=True)
        delta = ultimo_comp - c0
        out["finestre"].append({
            "giorni": giorni, "dal": g0.isoformat(), "al": ultimo_giorno.isoformat(),
            "da": c0, "a": ultimo_comp, "delta": delta, "contributi": contributi,
            "altro": delta - sum(c["contributo"] for c in contributi),
        })
    return out
