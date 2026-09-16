"""Maturation of the signal_outcomes warehouse.

For every signal alert whose forward horizon has fully elapsed in stored
ohlcv_daily, write ONE labeled-outcome row (absolute hit + market-neutral skill
+ causal regime). This is the SINGLE source of truth for forward outcomes,
replacing the duplicated forward-hit logic across signal_drift_service /
signal_detector_outcomes / rule_performance_service.

No-look-ahead is structural: a row is created only once the forward bar exists,
and the regime is computed from data available AT the trigger bar.

Run incrementally at the end of a scan (mature_outcomes), or as a one-off
backfill (app.scripts.backfill_signal_outcomes). Idempotent: alerts that already
have an outcome row are skipped (unique alert_id).
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
from loguru import logger
from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from app.indicators.periods import FIXED_EMA_SLOW
from app.models import Alert, OhlcvDaily, SignalOutcome, Stock, StockSetup
from app.services.signal_drift_service import _horizon_days

# EMA span for the causal regime label at the trigger bar.
#: La EMA che definisce il regime causale. ⚠️ Era un 200 scritto a mano
#: mentre `FIXED_EMA_SLOW` esisteva ed era dichiarata fonte unica: la
#: costante viveva dentro un servizio e non era importabile da chi ne
#: aveva bisogno. Ora sta in un modulo foglia.
_REGIME_EMA = FIXED_EMA_SLOW


def _to_date(v: object) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, str) and len(v) >= 10:
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _snapshot_fields(snapshot: str | None) -> tuple[str | None, int | None, int | None]:
    """(tone, strength, probability) from an Alert.snapshot JSON blob."""
    try:
        s = json.loads(snapshot) if snapshot else {}
    except (ValueError, TypeError):
        return None, None, None
    tone = s.get("tone")
    st = s.get("strength")
    pr = s.get("probability")
    return (
        tone if tone in ("bull", "bear") else None,
        int(st) if isinstance(st, (int, float)) else None,
        int(pr) if isinstance(pr, (int, float)) else None,
    )


def _rows_to_arrays(
    rows: list[tuple[int, object, float]], keep: set[int] | None = None
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    by_stock: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for sid, d, c in rows:
        if keep is not None and sid not in keep:
            continue
        dd = _to_date(d)
        if dd is not None and c is not None:
            by_stock[sid].append((dd, float(c)))
    out: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for sid, seq in by_stock.items():
        ds = np.array([x[0] for x in seq], dtype=object)
        cs = np.array([x[1] for x in seq], dtype="float64")
        out[sid] = (ds, cs)
    return out


def _load_universe_closes(
    db: Session, *, since: date | None = None, exclude_etf: bool = False
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Per stock: (dates[], closes[]) ascending. Lightweight column select.

    `since` trims the load to `date >= since` for the market-neutral benchmark:
    the universe forward-mean at a trigger date pairs each bar positionally with
    the one H ahead, and trimming only the *pre-trigger* tail leaves that pairing
    (and every mean at a pending trigger date) numerically identical — while
    turning a full-table scan into a ~90-day slice on the incremental path.

    `exclude_etf` drops instrument_type='etf' stocks from the load: the
    market-neutral benchmark population must be COMPANIES only (a 3x leveraged
    ETF's ±10% days distort the universe forward-mean every signal is measured
    against). Per-stock series for an ETF's OWN alerts stay loadable via
    `_load_stock_closes` — only the benchmark population changes."""
    stmt = select(OhlcvDaily.stock_id, OhlcvDaily.date, OhlcvDaily.close)
    if since is not None:
        stmt = stmt.where(OhlcvDaily.date >= since)
    if exclude_etf:
        etf_ids = db.execute(
            select(Stock.id).where(Stock.instrument_type == "etf")
        ).scalars().all()
        if etf_ids:
            stmt = stmt.where(OhlcvDaily.stock_id.not_in(etf_ids))
    rows = db.execute(stmt.order_by(OhlcvDaily.stock_id, OhlcvDaily.date)).all()
    return _rows_to_arrays(rows)


def _load_stock_closes(
    db: Session, stock_ids: set[int]
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Full-history (dates[], closes[]) for ONLY the given stocks. Used for the
    per-alert entry/forward/trigger lookups and the causal regime EMA200 — which
    needs each stock's COMPLETE series to converge, so it cannot be windowed.
    On the incremental scan path `stock_ids` is just the handful of stocks whose
    alerts matured this cycle; on the one-off backfill it is the whole universe."""
    if not stock_ids:
        return {}
    stmt = select(OhlcvDaily.stock_id, OhlcvDaily.date, OhlcvDaily.close)
    # SQLite caps bound params at 999. Past that (backfill: pending == universe)
    # skip the IN clause and load all rows, then keep only the wanted stocks.
    load_all = len(stock_ids) > 900
    if not load_all:
        stmt = stmt.where(OhlcvDaily.stock_id.in_(stock_ids))
    rows = db.execute(stmt.order_by(OhlcvDaily.stock_id, OhlcvDaily.date)).all()
    return _rows_to_arrays(rows, keep=stock_ids if load_all else None)


# A date needs at least this many stocks before its benchmark means anything.
# Same floor as the conditional-screen replay: a median over three names is
# not a market.
_MIN_UNIVERSE_PER_DATE = 10


def _universe_fwd_medians(
    closes_by_stock: dict[int, tuple[np.ndarray, np.ndarray]], horizon: int
) -> dict[date, float]:
    """{trigger_date: MEDIAN H-day-forward return across the universe}.

    THE MEDIAN, NOT THE MEAN, and the distinction is the whole point of this
    function. Cross-sectional forward returns are right-skewed, so under zero
    skill P(beat the mean) is BELOW 50% — measured on this universe: 47.4% at
    H=5, 45.3% at H=21, 42.2% at H=63. A bull signal therefore starts from ~45
    and a bear signal from ~55 before any skill exists, so the zero point of
    `mkt_neutral_hit` moves with tone and horizon and the bias is larger than
    the effect being measured (the whole engine spans 45.7-52.0).

    This is invariant #3 in CLAUDE.md — the lesson of the trend_pullback
    artifact, which a whole conditional-screen grid had to be discarded over.
    `conditional_screen_replay._universe_fwd_medians` honoured it; this path,
    which is what actually reaches the user through `calibration_map.skill`
    and the honesty tags, used the mean. The invariant's regression test lived
    only in `test_conditional_screen.py`, i.e. only on the path that already
    obeyed it.

    Collected per date rather than accumulated: a median needs the whole
    distribution, so the fancy-add trick the mean used does not apply.
    """
    by_date: dict[date, list[float]] = defaultdict(list)
    for ds, cs in closes_by_stock.values():
        if len(cs) <= horizon:
            continue
        c0 = cs[:-horizon]
        cH = cs[horizon:]
        ok = c0 > 0
        rets = cH[ok] / c0[ok] - 1.0
        # ⚠️ `strict=True`, non False. I due lati sono filtrati dalla STESSA
        # maschera `ok`, quindi hanno lunghezza uguale per costruzione e
        # `strict` oggi non ha niente da rilevare — ma se quell'invariante si
        # rompe, `False` TRONCA in silenzio e il riferimento di mercato viene
        # calcolato su meno osservazioni di quante ce ne siano, senza che
        # niente lo dica. `True` lo trasforma in un errore.
        #
        # Nessun test puo' distinguere le due forme finche' l'invariante
        # regge: il mutante che le scambia resta in EQUIVALENTI, con la
        # ragione. E' un miglioramento, non una lacuna chiusa.
        for d, r in zip(np.asarray(ds, dtype=object)[:-horizon][ok], rets, strict=True):
            by_date[d].append(float(r))
    return {
        d: float(np.median(v))
        for d, v in by_date.items()
        if len(v) >= _MIN_UNIVERSE_PER_DATE
    }


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    """Causal EWM (pandas-equivalent) over a 1-D array."""
    alpha = 2.0 / (span + 1.0)
    # ⚠️ `zeros_like`, non `empty_like`. La funzione riempie ogni indice, quindi
    # `empty_like` sarebbe corretta — ma se un giorno smette di riempirli tutti,
    # l'uscita non e' un valore sbagliato: e' memoria non inizializzata, cioe'
    # un risultato che a volte coincide per caso con quello giusto. La sonda di
    # mutazione l'ha dimostrato: spostando `out[0]` a `out[1]` il test che
    # confronta con pandas PASSAVA, tre volte su tre, perche' il blocco appena
    # liberato conteneva gia' il valore atteso.
    # Il costo e' nullo in proporzione: azzerare 20 KB vale ~1% del ciclo Python
    # interpretato qui sotto.
    out = np.zeros_like(values)
    acc = values[0]
    out[0] = acc
    for i in range(1, len(values)):
        acc = alpha * values[i] + (1 - alpha) * acc
        out[i] = acc
    return out


def _trigger_index(dates: np.ndarray, signal_date: date) -> int | None:
    """First bar index at/after signal_date (None if signal_date is past EOD)."""
    for i, d in enumerate(dates):
        if d >= signal_date:
            return i
    return None


def _benchmark_medians(
    db: Session, first_trigger: date, horizons: set[int]
) -> dict[int, dict[date, float]]:
    """Il riferimento di mercato per ogni orizzonte: {orizzonte: {data: mediana}}.

    Proprietario unico del perimetro del riferimento — solo societa' (ETF
    esclusi, vedi `_load_universe_closes`) e solo la finestra che i trigger in
    attesa raggiungono. Alert ed eventi di conversione dei setup lo leggono da
    qui: una seconda copia potrebbe smettere di escludere gli ETF e i due
    esiti dello stesso segnale non sarebbero piu' confrontabili.

    This is the load that used to scan the entire 2.4M-row table at every
    scan end."""
    uni_closes = _load_universe_closes(
        db, since=first_trigger - timedelta(days=10), exclude_etf=True
    )
    return {h: _universe_fwd_medians(uni_closes, h) for h in horizons}


@dataclass(frozen=True)
class Label:
    trigger_index: int
    entry: float
    forward_close: float
    fwd_return: float
    abs_hit: int
    universe_median: float | None
    mkt_excess: float | None
    mkt_hit: int | None


def _label(
    series: tuple[np.ndarray, np.ndarray] | None,
    signal_date: date,
    tone: str,
    horizon: int,
    medians_by_h: dict[int, dict[date, float]],
) -> Label | None:
    """L'etichetta d'esito di UN evento (titolo, barra, verso, orizzonte).

    Proprietario unico: la usano sia gli alert (`mature_outcomes`) sia gli
    eventi di conversione dei setup (`mature_setup_outcomes`). Due copie della
    stessa aritmetica divergono al primo ritocco, e qui la divergenza farebbe
    dire cose diverse alle due pagine sullo stesso segnale.

    None quando l'orizzonte non e' ancora trascorso o la barra manca."""
    if series is None:
        return None
    dates, cs = series
    ti = _trigger_index(dates, signal_date)
    if ti is None:
        return None
    fi = ti + horizon
    if fi >= len(cs):
        return None  # horizon not yet elapsed → not matured
    entry = float(cs[ti])
    if entry <= 0:
        return None
    fwd_close = float(cs[fi])
    fwd_ret = fwd_close / entry - 1.0
    abs_hit = 1 if ((tone == "bull" and fwd_ret > 0) or (tone == "bear" and fwd_ret < 0)) else 0
    uni_median = medians_by_h.get(horizon, {}).get(dates[ti])
    mkt_excess = mkt_hit = None
    if uni_median is not None:
        excess = fwd_ret - uni_median
        mkt_excess = excess if tone == "bull" else -excess
        mkt_hit = 1 if mkt_excess > 0 else 0
    return Label(ti, entry, fwd_close, fwd_ret, abs_hit, uni_median, mkt_excess, mkt_hit)


def _maturable_alert_ids(db: Session, conditions: tuple) -> set[int]:
    """Gli alert in attesa il cui orizzonte e' GIA' trascorso nelle barre salvate.

    ⚠️ E' la stessa condizione che `_label` verifica, detta in SQL: la barra
    del trigger e' la prima con `date >= signal_date`, e l'esito esiste se da
    li' in poi ci sono almeno H+1 barre (`ti + H < len`). Quindi filtrare qui
    non cambia nessun esito — cambia soltanto quante serie si caricano. Un
    alert senza barre dopo la sua data conta zero e resta fuori, che e'
    esattamente il caso delle serie ferme.

    Una query aggregata sulla chiave primaria `(stock_id, date)`, non una per
    alert. L'orizzonte dipende dal detector, quindi il confronto si fa qui."""
    righe = db.execute(
        select(Alert.id, Alert.signal_name, func.count(OhlcvDaily.date))
        .join(
            OhlcvDaily,
            and_(
                OhlcvDaily.stock_id == Alert.stock_id,
                OhlcvDaily.date >= Alert.signal_date,
            ),
        )
        .where(*conditions)
        .group_by(Alert.id, Alert.signal_name)
    ).all()
    return {aid for aid, name, n in righe if n >= _horizon_days(name) + 1}


def mature_outcomes(db: Session, *, commit: bool = True) -> int:
    """Write outcome rows for newly-matured signal alerts. Returns rows added."""
    # Anti-join in SQL: only alerts WITHOUT an outcome row come back. The old
    # shape loaded every signal alert + every outcome alert_id into Python and
    # set-differenced them — O(all history) per scan. NOT EXISTS resolves as a
    # point probe per alert on the unique ix_signal_outcomes_alert index, and
    # already-matured alerts never leave the database.
    in_attesa = (
        Alert.signal_name.is_not(None),
        Alert.signal_date.is_not(None),
        ~exists(select(SignalOutcome.id).where(SignalOutcome.alert_id == Alert.id)),
    )
    pending = list(db.execute(select(Alert).where(*in_attesa)).scalars())
    n_pending = len(pending)
    # ⚠️ Solo quelli che POSSONO maturare. Misurato il 2026-09-16: 3.724 alert
    # in attesa su 932 titoli, e oltre 900 titoli `_load_stock_closes` legge
    # l'INTERA tabella (2,48M righe) a ogni fine scansione — per scoprire, un
    # alert alla volta, che l'orizzonte non e' trascorso. 48 di quei titoli
    # hanno la serie ferma e non matureranno mai.
    maturabili = _maturable_alert_ids(db, in_attesa)
    pending = [a for a in pending if a.id in maturabili]
    if not pending:
        logger.info(f"[signal-outcomes] matured 0 new alerts ({n_pending} pending, 0 maturable)")
        return 0

    # Per-alert exact series (entry/forward/trigger + regime EMA200) for ONLY
    # the pending stocks — a handful on the incremental scan path. Full history
    # because the EMA needs a long warmup to converge to the same value the
    # backfill path produces.
    pending_sids = {a.stock_id for a in pending}
    closes = _load_stock_closes(db, pending_sids)

    # Universe market-neutral benchmark: companies only (ETFs excluded — see
    # _load_universe_closes), and only the date window the pending triggers
    # reach (exact — see _load_universe_closes). This is the load that used
    # to scan the entire 2.4M-row table at every scan end.
    medians_by_h = _benchmark_medians(
        db,
        min(a.signal_date for a in pending),
        {_horizon_days(a.signal_name) for a in pending},
    )
    ema_cache: dict[int, np.ndarray] = {}

    added = 0
    for a in pending:
        tone, strength, probability = _snapshot_fields(a.snapshot)
        if tone is None:
            continue
        H = _horizon_days(a.signal_name)
        lab = _label(closes.get(a.stock_id), a.signal_date, tone, H, medians_by_h)
        if lab is None:
            continue
        ti, cs = lab.trigger_index, closes[a.stock_id][1]

        # Causal regime: close vs EMA200 at the trigger bar.
        regime = None
        if a.stock_id not in ema_cache:
            ema_cache[a.stock_id] = _ema(cs, _REGIME_EMA) if len(cs) else np.array([])
        ema_arr = ema_cache[a.stock_id]
        if ti < len(ema_arr) and ema_arr[ti] > 0:
            regime = "bull" if cs[ti] > ema_arr[ti] else "bear"

        db.add(SignalOutcome(
            alert_id=a.id, stock_id=a.stock_id, detector=a.signal_name,
            signal_date=a.signal_date, tone=tone, horizon_days=H,
            entry_close=lab.entry, forward_close=lab.forward_close,
            fwd_return=lab.fwd_return,
            universe_mean_fwd=lab.universe_median, mkt_neutral_excess=lab.mkt_excess,
            abs_hit=lab.abs_hit, mkt_neutral_hit=lab.mkt_hit, regime_at_signal=regime,
            strength=strength, probability=probability,
        ))
        added += 1

    if commit and added:
        db.commit()
    logger.info(
        f"[signal-outcomes] matured {added} new alerts "
        f"({n_pending} pending, {len(pending)} maturable)"
    )
    return added


def mature_setup_outcomes(db: Session, *, commit: bool = True) -> int:
    """Matura l'esito dell'EVENTO che ha convertito ogni setup.

    ⚠️ Non l'esito dell'alert puntato. L'alert e' un'entita' viva: la scansione
    ne aggiorna data e prezzo finche' la condizione tiene, e in produzione 71
    conversioni su 334 puntavano a un alert la cui data era scivolata fino a 28
    giorni oltre la conversione. Il suo esito misurerebbe un altro momento.

    Due popolazioni:

    - con `converted_signal_date` (conversioni registrate, e le storiche il cui
      alert non fu mai rivisto): etichettate da QUELLA barra, con `_label`, la
      stessa aritmetica del magazzino;
    - storiche SENZA data d'evento: si accetta l'esito gia' nel magazzino solo
      se misura una barra non successiva al giorno della conversione, cioe' un
      momento che la conversione poteva conoscere. Altrimenti restano senza
      esito, e `conversion_stats` le conta come non misurabili.

    Le riconciliate non hanno data e non vengono toccate. Idempotente: una riga
    con `outcome_matured_at` non si ricalcola.
    """
    now = datetime.now(UTC)
    added = 0

    dated = list(db.execute(
        select(StockSetup).where(
            StockSetup.status == "converted",
            StockSetup.outcome_matured_at.is_(None),
            StockSetup.converted_signal_date.is_not(None),
            StockSetup.converted_tone.in_(("bull", "bear")),
        )
    ).scalars())
    if dated:
        closes = _load_stock_closes(db, {r.stock_id for r in dated})
        medians_by_h = _benchmark_medians(
            db,
            min(r.converted_signal_date for r in dated),
            {_horizon_days(r.detector) for r in dated},
        )
        for r in dated:
            H = _horizon_days(r.detector)
            lab = _label(
                closes.get(r.stock_id), r.converted_signal_date, r.converted_tone,
                H, medians_by_h,
            )
            if lab is None:
                continue
            r.outcome_signal_date = r.converted_signal_date
            r.outcome_horizon_days = H
            r.outcome_fwd_return = lab.fwd_return
            r.outcome_mkt_neutral_excess = lab.mkt_excess
            r.outcome_mkt_neutral_hit = lab.mkt_hit
            r.outcome_matured_at = now
            added += 1

    undated = db.execute(
        select(StockSetup, SignalOutcome)
        .join(SignalOutcome, SignalOutcome.alert_id == StockSetup.converted_alert_id)
        .where(
            StockSetup.status == "converted",
            StockSetup.outcome_matured_at.is_(None),
            StockSetup.converted_signal_date.is_(None),
            StockSetup.conversion_source == "legacy",
            StockSetup.resolved_at.is_not(None),
        )
    ).all()
    for r, o in undated:
        resolved = r.resolved_at
        if o.signal_date > resolved.date():
            continue  # misura un momento successivo alla conversione
        r.outcome_signal_date = o.signal_date
        r.outcome_horizon_days = o.horizon_days
        r.outcome_fwd_return = o.fwd_return
        r.outcome_mkt_neutral_excess = o.mkt_neutral_excess
        r.outcome_mkt_neutral_hit = o.mkt_neutral_hit
        r.outcome_matured_at = now
        added += 1

    if commit and added:
        db.commit()
    logger.info(f"[setup-outcomes] matured {added} conversion events")
    return added
