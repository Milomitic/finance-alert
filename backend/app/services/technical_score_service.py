"""Continuous per-stock technical score.

Five price dimensions (trend, momentum, structure, volume) computed per stock,
plus a cross-sectional relative-strength percentile assigned in a finalize pass.
Persisted in technical_scores. Complementary to the fundamental StockScore.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta

import pandas as pd
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.indicators.adx import adx
from app.indicators.ema import ema
from app.indicators.macd import macd
from app.indicators.periods import FIXED_RSI_PERIOD
from app.indicators.rsi import rsi
from app.models import Alert, OhlcvDaily, Stock, TechnicalScore
from app.services import ohlcv_service

# Composite weights for the five price dimensions (must sum to 1.0).
_WEIGHTS = {
    "trend": 0.28,
    "momentum": 0.24,
    "rel_strength": 0.20,
    "structure": 0.16,
    "volume": 0.12,
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _ret(close: pd.Series, k: int) -> float | None:
    if k <= 0 or k >= len(close):
        return None
    base = float(close.iloc[-1 - k])
    return (float(close.iloc[-1]) / base - 1.0) if base else None


def _trend(close: pd.Series, ohlcv: pd.DataFrame) -> float:
    n = len(close)
    fast = ema(close, min(50, max(10, n // 4)))
    slow = ema(close, min(200, max(20, n // 2)))
    price = float(close.iloc[-1])
    f = float(fast.iloc[-1])
    s = float(slow.iloc[-1])
    pts = int(price > f) + int(f > s) + int(price > s)
    if n > 6:
        pts += int(float(slow.iloc[-1]) > float(slow.iloc[-6]))
    t01 = pts / 4.0
    adx_w = 0.5
    try:
        a, _, _ = adx(ohlcv, 14)
        adx_w = _clamp(float(a.dropna().iloc[-1]) / 40.0)
    except (IndexError, ValueError, TypeError) as e:
        # Narrowed from a bare `except Exception: pass`. These three ARE the
        # legitimate shortage: too few bars leaves the ADX series all-NaN, so
        # .iloc[-1] raises IndexError, and a non-finite value trips
        # ValueError/TypeError. Falling back to the neutral 0.5 weight is the
        # right answer for those.
        #
        # What must NOT be swallowed is a KeyError from `ohlcv["high"]` — that
        # means the frame arrived with the wrong shape, which is a defect, and
        # under the old blanket catch it silently rewrote every stock's Tecnico
        # score to the neutral weight instead of failing. A wrong score that
        # looks right is worse than a crash.
        #
        # debug, not warning: this runs once per stock across the ~1000-name
        # universe, and a per-stock warning would bury the log it lives in.
        logger.debug(f"[technical] ADX unavailable ({len(close)} bars): {e!r} — neutral weight")
    return _clamp(0.5 + (t01 - 0.5) * (0.6 + 0.4 * adx_w)) * 100.0


def _momentum(close: pd.Series) -> float:
    n = len(close)
    price = float(close.iloc[-1])
    # ⚠️ La disponibilita' dell'RSI si guarda sulla serie RIPULITA, non sul
    # numero di barre — esattamente come fa il MACD due righe sotto.
    #
    # La forma precedente era `if n > 15 else 50.0`, e non poteva funzionare
    # per due ragioni indipendenti. `_momentum` e' chiamata solo da
    # `partial_for`, che sbarra sotto le 30 barre: `n > 15` era quindi SEMPRE
    # vero e quel ripiego era codice morto. E il caso che accade davvero non e'
    # «poche barre» ma una serie PIATTA, dove guadagni e perdite sono entrambi
    # zero, l'RSI e' tutto NaN e `.iloc[-1]` su una serie vuota solleva
    # IndexError — raccolto dal `except Exception` di `partial_for`, che rende
    # None: il titolo spariva dalla lente Tecnico invece di ricevere un momento
    # neutro. Un ramo inerte che sembra coprire il caso e' peggio di nessun
    # ramo, perche' corrobora la convinzione che sia coperto.
    rd = rsi(close, FIXED_RSI_PERIOD).dropna()
    r = float(rd.iloc[-1]) if rd.size else 50.0
    _, _, hist = macd(close)
    hd = hist.dropna()
    h = float(hd.iloc[-1]) if hd.size else 0.0
    macd01 = (0.5 + 0.5 * math.tanh(h / (0.01 * price))) if price else 0.5
    rc = _ret(close, min(20, n - 1)) or 0.0
    roc01 = _clamp(0.5 + rc / 0.4)  # +20pct -> 1.0, -20pct -> 0.0
    return (r + macd01 * 100.0 + roc01 * 100.0) / 3.0


def _structure(ohlcv: pd.DataFrame, close: pd.Series) -> float:
    n = len(close)
    win = min(252, n)
    hi = float(ohlcv["high"].astype(float).iloc[-win:].max())
    lo = float(ohlcv["low"].astype(float).iloc[-win:].min())
    price = float(close.iloc[-1])
    rng = hi - lo
    pos = (price - lo) / rng if rng > 0 else 0.5
    return _clamp(pos) * 100.0


def _volume(ohlcv: pd.DataFrame, close: pd.Series) -> float:
    n = len(close)
    vol = ohlcv["volume"].astype(float)
    short = float(vol.iloc[-10:].mean()) if n >= 10 else float(vol.mean())
    long_avg = float(vol.iloc[-min(50, n):].mean())
    vratio = short / long_avg if long_avg > 0 else 1.0
    vtrend01 = _clamp(0.5 + (vratio - 1.0) * 0.5)
    k = min(20, n - 1)
    rec = ohlcv.iloc[-k:]
    d = rec["close"].astype(float).diff()
    rv = rec["volume"].astype(float)
    upv = float(rv[d > 0].sum())
    dnv = float(rv[d < 0].sum())
    ad01 = upv / (upv + dnv) if (upv + dnv) > 0 else 0.5
    return (0.5 * vtrend01 + 0.5 * ad01) * 100.0


def _blended_return(close: pd.Series) -> float | None:
    n = len(close)
    parts = [
        (0.4, _ret(close, min(63, n - 1))),
        (0.3, _ret(close, min(126, n - 1))),
        (0.3, _ret(close, min(252, n - 1))),
    ]
    num = 0.0
    wsum = 0.0
    for w, v in parts:
        if v is not None:
            num += w * v
            wsum += w
    return num / wsum if wsum > 0 else None


def partial_for(ohlcv: pd.DataFrame) -> dict | None:
    # Per-stock dimensions. Needs enough history; relative strength is added
    # later (cross-sectional). Returns None on too-short or malformed input.
    if ohlcv is None or len(ohlcv) < 30:
        return None
    try:
        close = ohlcv["close"].astype(float).reset_index(drop=True)
        return {
            "trend": _trend(close, ohlcv),
            "momentum": _momentum(close),
            "structure": _structure(ohlcv, close),
            "volume": _volume(ohlcv, close),
            "blended_return": _blended_return(close),
        }
    except Exception as e:  # noqa: BLE001 — per-stock isolation boundary
        # Deliberately broad: this is the boundary that stops ONE malformed
        # stock from killing a ~1000-name recompute. What it was missing is a
        # voice. Returning None silently means the stock simply has no
        # Tecnico score, which looks identical to "not computed yet" — so a
        # systematic frame-shape defect could drain the lens for a whole
        # slice of the universe with nothing anywhere to show for it.
        logger.debug(f"[technical] partial_for skipped ({len(ohlcv)} bars): {e!r}")
        return None


def _posture(composite: float) -> str:
    """Le tre bande della postura, col bordo INCLUSO.

    Proprietario unico. Questa riga era duplicata verbatim in `finalize` e in
    `recompute_one`: ritarare 66 o 40 in uno dei due avrebbe fatto disaccordare
    il pulsante «aggiorna» della pagina dettaglio dal ricalcolo di lotto, sullo
    stesso titolo e nella stessa schermata."""
    return "Forte" if composite >= 66 else "Neutro" if composite >= 40 else "Debole"


def _riga_tecnica(
    stock_id: int,
    dims: dict[str, float],
    *,
    blended_return: float | None,
    fac: dict | None,
    now: datetime,
) -> TechnicalScore:
    """La riga persistita, da un solo posto.

    ⚠️ Questo blocco esisteva in DUE copie — `finalize` e `recompute_one` — e
    la duplicazione ha gia' prodotto un guasto: quando `_recent_signal_facets`
    passo' da "confidence" a "strength" col taglio Forza/Probabilita', la copia
    in `finalize` fu aggiornata e questa no, cosi' ogni ricalcolo per un titolo
    con un segnale recente rendeva 500. Solo sui titoli CHE HANNO un segnale,
    cioe' quelli interessanti, e con 1.700 test verdi perche' nessuno
    percorreva il ramo `fac is not None`.

    La correzione di allora sistemo' la copia. Questa toglie la copia.

    I segnali restano la LORO lente (Forza / Probabilita'): il composito e'
    puro prezzo — la media pesata delle cinque dimensioni — e non viene spinto
    da loro. La Forza dell'ultimo segnale sopravvive solo come riferimento
    informativo nel campo `signals`."""
    composite = sum(_WEIGHTS[k] * dims[k] for k in _WEIGHTS)
    return TechnicalScore(
        stock_id=stock_id,
        composite=round(composite, 1),
        trend=round(dims["trend"], 1),
        momentum=round(dims["momentum"], 1),
        structure=round(dims["structure"], 1),
        volume=round(dims["volume"], 1),
        rel_strength=round(dims["rel_strength"], 1),
        # "strength", non "confidence": `_recent_signal_facets` rende
        # {"strength", "tone"} dal taglio Forza/Probabilita' in poi.
        signals=round(fac["strength"], 1) if fac is not None else None,
        posture=_posture(composite),
        computed_at=now,
        breakdown=json.dumps({
            "dims": {k: round(dims[k], 1) for k in dims},
            "blended_return": blended_return,
        }),
    )


def _recent_signal_facets(db: Session, stock_ids: list[int]) -> dict[int, dict]:
    # Best recent signal per stock (last 14 days): max-Forza alert with its
    # tone, parsed from the snapshot. Feeds the informational `signals` field.
    if not stock_ids:
        return {}
    cutoff = datetime.now(UTC) - timedelta(days=14)
    # ⚠️ `triggered_at` di proposito, non `emitted_at` (FA-100): qui «recente»
    # vuol dire VIVO, e un segnale nato tre settimane fa che l'ultima scansione
    # ha rivisto e' un segnale di adesso. Contare le nascite e' un'altra domanda.
    rows = db.execute(
        select(Alert.stock_id, Alert.snapshot).where(
            Alert.signal_name.isnot(None),
            Alert.triggered_at >= cutoff,
            Alert.stock_id.in_(stock_ids),
        )
    ).all()
    best: dict[int, tuple[float, str | None]] = {}
    for sid, snap in rows:
        try:
            d = json.loads(snap) if snap else {}
        except (json.JSONDecodeError, TypeError) as e:
            # Narrowed + logged. Skipping one corrupt snapshot is right, but
            # under a blanket silent catch a SYSTEMATIC corruption (a writer
            # bug, a truncated column) would drain this facet to empty with
            # no trace anywhere. debug because it is per-alert.
            logger.debug(f"[technical] snapshot alert stock_id={sid} illeggibile: {e!r}")
            continue
        # Snapshots carry "strength" since the Forza/Probabilità split;
        # "confidence" is the transitional legacy alias only present on
        # pre-split rows. Reading only "confidence" left this facet empty
        # for every post-split alert (0/938 rows populated) — coalesce
        # strength first, legacy confidence second. Same 0-100 scale.
        conf = d.get("strength")
        if not isinstance(conf, (int, float)):
            conf = d.get("confidence")
        if not isinstance(conf, (int, float)):
            continue
        cur = best.get(sid)
        if cur is None or conf > cur[0]:
            best[sid] = (float(conf), d.get("tone"))
    return {sid: {"strength": c, "tone": t} for sid, (c, t) in best.items()}


def forget(db: Session, stock_ids: list[int]) -> int:
    """Cancella il punteggio Tecnico dei titoli indicati. Rende quanti.

    ⚠️ Serve perche' `finalize` fa UPSERT e non cancella mai: smettere di
    valutare un titolo lascerebbe in piedi l'ultima riga calcolata, e per un
    titolo la cui serie si e' fermata quella riga e' il difetto peggiore che
    ci sia. Misurato in produzione il 2026-09-14, i dodici titoli morti
    stavano cosi':

        BK    composito 81,9  postura Forte  calcolato OGGI  ultima barra 10 lug
        CPRX  composito 81,2  postura Forte  calcolato OGGI  ultima barra 21 lug
        TERN  composito 81,0  postura Forte  calcolato OGGI  ultima barra 15 mag

    cioe' al **98esimo percentile** della classifica. Non e' un caso: una serie
    ferma ha volatilita' nulla e trend stabile, quindi produce un punteggio
    LUSINGHIERO. Un titolo morto non finisce in fondo alla classifica, finisce
    in cima — la stessa forma con cui TIT.MI, dopo un raggruppamento non
    riparato, divento' la forza relativa piu' alta dell'universo.

    ⚠️ Si CANCELLA invece di marcare: il punteggio Tecnico e' un'affermazione
    al PRESENTE («questo titolo e' Forte»), non uno storico — quello vive in
    `score_history` e resta intatto. Per un'affermazione al presente che non si
    puo' piu' sostenere, il valore onesto e' l'assenza.

    Riceve una lista ESPLICITA di id, mai «tutti quelli non in partials»: la
    scansione salta titoli anche per storia troppo corta, e una scansione
    parziale non ne guarda la maggior parte. Cancellare per esclusione
    svuoterebbe la classifica al primo scan ristretto.
    """
    if not stock_ids:
        return 0
    n = db.execute(
        delete(TechnicalScore).where(TechnicalScore.stock_id.in_(stock_ids))
    ).rowcount or 0
    if n:
        logger.info(f"[tecnico] {n} punteggi rimossi: la serie di quei titoli non avanza piu'")
    return n


def finalize(db: Session, partials: dict[int, dict]) -> int:
    # Assign relative-strength percentile from the blended returns, compute the
    # composite + posture, and upsert one technical_scores row per stock.
    if not partials:
        return 0
    rets = [
        (sid, p["blended_return"])
        for sid, p in partials.items()
        if p.get("blended_return") is not None
    ]
    rets.sort(key=lambda kv: kv[1])
    m = len(rets)
    rank: dict[int, float] = {}
    for i, (sid, _) in enumerate(rets):
        rank[sid] = (i / (m - 1) * 100.0) if m > 1 else 50.0
    facets = _recent_signal_facets(db, list(partials.keys()))
    now = datetime.now(UTC)
    count = 0
    for sid, p in partials.items():
        rel = rank.get(sid, 50.0)
        dims = {
            "trend": p["trend"],
            "momentum": p["momentum"],
            "structure": p["structure"],
            "volume": p["volume"],
            "rel_strength": rel,
        }
        db.merge(_riga_tecnica(
            sid, dims,
            blended_return=p.get("blended_return"),
            fac=facets.get(sid),
            now=now,
        ))
        count += 1
    return count


class SerieFerma(Exception):
    """Il titolo ha smesso di quotare: uno score tecnico sarebbe un'affermazione al
    presente su prezzi fermi (FA-071, FA-087). Distinta da «storico
    insufficiente», che per un titolo con anni di barre sarebbe una ragione falsa."""


def recompute_one(db: Session, stock_id: int) -> TechnicalScore | None:
    """Recompute ONE stock's technical score from stored OHLCV and upsert it.

    ⚠️ Rifiuta una serie FERMA sollevando `SerieFerma` (FA-087). La guardia di
    FA-071 sta nella scansione, e questo percorso non ci passa: il pulsante
    «aggiorna» della scheda Tecnico rimetteva in classifica un titolo morto,
    con la postura lusinghiera che una serie piatta produce, fino alla scansione
    seguente. Verificato con un test che senza la guardia rispondeva 200.

    Used by the per-card "refresh" button on the stock detail page when the
    scan-time score is missing or stale. Returns the persisted row, or None
    if there isn't enough stored history to compute the price dimensions.

    Difference vs `finalize`: the cross-sectional relative-strength percentile
    is NOT recomputed (that requires the whole universe). The previously-
    persisted `rel_strength` is reused; absent a prior row it defaults to the
    neutral 50th percentile. Everything else (the four price dims, the signals
    facet, composite + posture) is recomputed exactly as `finalize` does.
    """
    # Il predicato ha un proprietario solo (`ohlcv_service`): nessuna soglia qui.
    streak = db.execute(
        select(Stock.ohlcv_nodata_streak).where(Stock.id == stock_id)
    ).scalar_one_or_none()
    if ohlcv_service.series_is_stalled(streak):
        raise SerieFerma(
            "Serie prezzi ferma: il titolo non quota piu', quindi lo score tecnico "
            "non si ricalcola su prezzi vecchi."
        )
    rows = (
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock_id)
            .order_by(OhlcvDaily.date.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    rows = rows[-260:]
    ohlcv = pd.DataFrame(
        {
            "date": [r.date for r in rows],
            "open": [float(r.open) for r in rows],
            "high": [float(r.high) for r in rows],
            "low": [float(r.low) for r in rows],
            "close": [float(r.close) for r in rows],
            "volume": [int(r.volume) for r in rows],
        }
    )
    p = partial_for(ohlcv)
    if p is None:
        return None

    existing = db.execute(
        select(TechnicalScore).where(TechnicalScore.stock_id == stock_id).limit(1)
    ).scalars().first()
    rel = (
        existing.rel_strength
        if existing is not None and existing.rel_strength is not None
        else 50.0
    )
    dims = {
        "trend": p["trend"],
        "momentum": p["momentum"],
        "structure": p["structure"],
        "volume": p["volume"],
        "rel_strength": rel,
    }
    # ⚠️ La riga la costruisce `_riga_tecnica`, proprietario unico condiviso
    # con `finalize`. Il blocco era duplicato qui, e la duplicazione ha gia'
    # prodotto un 500 su questa esatta funzione: la ragione per cui non torna
    # e' strutturale, non una nota da ricordarsi.
    db.merge(_riga_tecnica(
        stock_id, dims,
        blended_return=p.get("blended_return"),
        fac=_recent_signal_facets(db, [stock_id]).get(stock_id),
        now=datetime.now(UTC),
    ))
    db.commit()
    return db.execute(
        select(TechnicalScore).where(TechnicalScore.stock_id == stock_id).limit(1)
    ).scalars().first()
