"""Three stock leaderboards for the Esplora landing section.

WHAT THESE ARE, AND WHAT THEY ARE NOT
─────────────────────────────────────
They are ATTENTION rankings: three different questions about the same universe,
each answered from data already computed. They are not forecasts, and this
module must never be extended into one without a study behind it.

That is not caution for its own sake. The score-IC backtest (39 quarterly
cross-sections, 20,217 observations, `app/data/score_ic_report.json`) found no
statistically significant IC for the Qualità composite on forward returns, and
a NEGATIVE market-neutral decile spread at longer horizons. The conditional
screen (729,830 signals, 5 horizons) found nothing that changes detector skill.
Six studies, six nulls — documented in CLAUDE.md. Ranking by these numbers is
a way to decide WHERE TO LOOK, and the UI says so out loud.

THE THREE LENSES
────────────────
`analysts`  — where the sell side is positive AND sees room. NOT ranked by raw
              upside: see `_analyst_rank` for the measurement that showed why.
`combined`  — strong on Qualità AND Tecnico. Uses a soft minimum, not an
              average, for the same reason signal Forza does: averaging lets a
              90 on one lens carry a 30 on the other, which is exactly the
              stock neither lens is recommending.
`signals`   — where the engine has been firing bullish lately. The NET count,
              because 20 bull against 18 bear is not the same story as 20
              against 1, and the raw total tells neither.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db_json import json_text
from app.core.visibility import visible_country_clause
from app.models import Alert, Stock, StockScore, TechnicalScore
from app.signals.detectors.base import clamp01, log_saturate

# An analyst consensus needs enough voices to mean anything. yfinance reports
# `recommendation_mean` off however many analysts cover the name, and a single
# enthusiastic boutique produces a 1.0 that reads like unanimity.
MIN_ANALYST_OPINIONS = 5

# yfinance scale: 1 = Strong Buy … 5 = Sell, 3 = Hold. Above this the consensus
# is not positive enough for "the sell side likes it" to be a fair summary.
MAX_RECOMMENDATION_MEAN = 2.5

# A target more than this far above the price is a stale figure or a
# pre-collapse leftover far more often than a real call. Dropped rather than
# shown, same rule as the dividend-yield ceiling in `percent_units`. Measured
# on the live cache: 4 names of 917 sit above it, up to +231%.
MAX_PLAUSIBLE_UPSIDE_PCT = 150.0

# Window for the signals board. Long enough to survive a quiet week, short
# enough that "lately" is still true.
SIGNAL_WINDOW_DAYS = 30

# `log_saturate` reference points — the raw value that counts as "strong".
_UPSIDE_REF_PCT = 25.0   # a 25% target gap is a substantial call
_COVERAGE_REF = 20.0     # 20 analysts is a well-covered name

# Weights for the analyst rank. Room to run leads, but cannot win alone.
_W_ROOM = 0.45
_W_CONVICTION = 0.35
_W_COVERAGE = 0.20


@dataclass(frozen=True)
class LeaderRow:
    ticker: str
    name: str | None
    sector: str | None
    quality: float | None
    technical: float | None
    # Board-specific headline number, already in display units. Named
    # generically because each board explains its own in the UI.
    value: float
    # Supporting detail, board-specific and optional.
    detail: str | None = None
    signals_bull: int = 0
    signals_bear: int = 0
    detectors_bull: int = 0
    analysts: int | None = None
    recommendation: float | None = None
    upside_pct: float | None = None
    target: float | None = None
    last_close: float | None = None


def soft_min(a: float, b: float, *, slack: float = 12.0) -> float:
    """Combined lens score: the weaker lens, allowed a bounded lift from the
    stronger one.

    A plain average lets 90/30 read as 60 — a stock neither lens likes,
    presented as middling. A hard minimum ignores that 80/78 is genuinely
    better than 80/60. `min + slack` capped by the mean keeps both readings:
    the floor decides, the ceiling rewards agreement. Same shape as the
    `score_v2` soft-min already used for signal Forza.
    """
    return min((a + b) / 2.0, min(a, b) + slack)


def upside_pct(target: float | None, price: float | None) -> float | None:
    """Percent gap from price to consensus target, or None if not usable.

    Both numbers come from the SAME fundamentals payload (`price_target.mean`
    and `price_target.current`), deliberately: pairing a live price with a
    day-old target would compute a gap that neither source ever stated.
    """
    if target is None or price is None:
        return None
    try:
        t, p = float(target), float(price)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None
    up = (t - p) / p * 100.0
    if up <= 0 or up > MAX_PLAUSIBLE_UPSIDE_PCT:
        return None
    return up


def _analyst_rank(up_pct: float, recommendation: float, n_analysts: float) -> float:
    """0..100 ordering score for the analyst board.

    WHY NOT JUST SORT BY UPSIDE. Measured on the live cache (917 names with a
    full analyst record), ranking by raw target gap returns APLD +144%,
    CRVS +138%, NTLA +137%, ONDS +122%, USAR +120% — microcap biotech, crypto
    miners and defence-tech, several covered by 7-8 analysts. That board is a
    volatility filter wearing an analyst costume: a wide target gap is mostly a
    statement about how uncertain the name is, not about how much the sell side
    likes it. The user asked for picks "in base alle valutazioni degli
    analisti", so the ranking has to reflect the opinion, not its variance.

    Three components, each saturating so no single one can run away with it:
      room       — the target gap, log-saturating (a 100% gap is a bigger call
                   than 25%, but not four times bigger)
      conviction — how positive the consensus is: 1.0 (Strong Buy) → 1.0,
                   3.0 (Hold) → 0.0
      coverage   — how many analysts stand behind it, log-saturating
    """
    room = log_saturate(up_pct, _UPSIDE_REF_PCT)
    conviction = clamp01((3.0 - recommendation) / 2.0)
    coverage = log_saturate(n_analysts, _COVERAGE_REF)
    return round(
        100.0 * (_W_ROOM * room + _W_CONVICTION * conviction + _W_COVERAGE * coverage), 1
    )


def _base_rows(db: Session) -> dict[int, tuple[Stock, float | None, float | None]]:
    """Every visible stock with whatever lens scores it has.

    One query rather than per-board queries: the three boards rank the same
    population three ways, and re-reading it three times would triple the cost
    of a page that renders in one shot.
    """
    q = (
        select(Stock, StockScore.composite, TechnicalScore.composite)
        .outerjoin(StockScore, StockScore.stock_id == Stock.id)
        .outerjoin(TechnicalScore, TechnicalScore.stock_id == Stock.id)
        .where(visible_country_clause())
    )
    return {s.id: (s, q_, t_) for s, q_, t_ in db.execute(q).all()}


@dataclass
class _SignalTally:
    bull: int = 0
    bear: int = 0
    # Distinct bullish detectors. Ten fires of one detector is one thing
    # happening repeatedly; three different detectors agreeing is three things.
    bull_detectors: set[str] | None = None


def _signal_counts(db: Session, *, days: int = SIGNAL_WINDOW_DAYS) -> dict[int, _SignalTally]:
    """Bull/bear counts per stock over the window, archived excluded.

    Tone lives INSIDE `Alert.snapshot` (a JSON text column) — there is no
    `alerts.tone` column. Read it with the dialect-portable `json_text` helper,
    the same way `alert_service` filters by tone, so this works on SQLite
    locally and Postgres in production.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    tone_col = json_text(Alert.snapshot, "tone")
    rows = db.execute(
        select(Alert.stock_id, tone_col, Alert.signal_name, func.count(Alert.id))
        .where(Alert.triggered_at >= since, Alert.archived_at.is_(None))
        .group_by(Alert.stock_id, tone_col, Alert.signal_name)
    ).all()

    out: dict[int, _SignalTally] = {}
    for stock_id, tone, signal_name, n in rows:
        tally = out.setdefault(stock_id, _SignalTally(bull_detectors=set()))
        count = int(n or 0)
        if tone == "bull":
            tally.bull += count
            if signal_name and tally.bull_detectors is not None:
                tally.bull_detectors.add(signal_name)
        elif tone == "bear":
            tally.bear += count
    return out


def _fundamentals_cache() -> dict:
    """The in-process fundamentals cache, hydrated if still cold.

    The analyst board reads `price_target` out of L1. On a freshly booted pod
    L1 can be empty for a few seconds until some other consumer triggers
    hydration — which would render the board empty and look like "no analyst
    coverage" rather than "cache not warm yet". Hydrating explicitly costs one
    query and removes that failure mode. See the two-tier cache note in
    CLAUDE.md.
    """
    from app.services.stock_fundamentals_service import _CACHE, hydrate_l1_from_db

    if not _CACHE:
        try:
            hydrate_l1_from_db()
        except Exception:  # pragma: no cover - never block the page on the cache
            pass
    return _CACHE


def build_leaderboards(db: Session, *, limit: int = 6) -> dict[str, list[LeaderRow]]:
    """The three boards, computed from one pass over the universe."""
    base = _base_rows(db)
    signals = _signal_counts(db)
    cache = _fundamentals_cache()

    analysts: list[LeaderRow] = []
    combined: list[LeaderRow] = []
    signal_rows: list[LeaderRow] = []

    for stock_id, (stock, quality, technical) in base.items():
        tally = signals.get(stock_id) or _SignalTally(bull_detectors=set())
        bull, bear = tally.bull, tally.bear
        n_det = len(tally.bull_detectors or ())
        q = float(quality) if quality is not None else None
        t = float(technical) if technical is not None else None
        common = {
            "ticker": stock.ticker,
            "name": stock.name,
            "sector": stock.sector,
            "quality": q,
            "technical": t,
            "signals_bull": bull,
            "signals_bear": bear,
            "detectors_bull": n_det,
        }

        # ── combined: both lenses, floor-driven ────────────────────────────
        if q is not None and t is not None:
            combined.append(LeaderRow(
                **common,
                value=round(soft_min(q, t), 1),
                detail=f"Qualità {q:.0f} · Tecnico {t:.0f}",
            ))

        # ── signals: net bullish activity ──────────────────────────────────
        if bull > bear:
            detail = f"{bull} rialzisti · {bear} ribassisti"
            if n_det > 1:
                detail += f" · {n_det} detector diversi"
            signal_rows.append(LeaderRow(**common, value=float(bull - bear), detail=detail))

        # ── analysts: positive consensus with room left ────────────────────
        fund = cache.get(stock.ticker)
        if fund is None:
            continue
        micro = getattr(fund, "micro", None)
        pt = getattr(fund, "price_target", None)
        if micro is None or pt is None:
            continue
        n_op = getattr(micro, "number_of_analyst_opinions", None)
        rec = getattr(micro, "recommendation_mean", None)
        if n_op is None or rec is None:
            continue
        if n_op < MIN_ANALYST_OPINIONS or rec > MAX_RECOMMENDATION_MEAN:
            continue
        up = upside_pct(pt.mean, pt.current)
        if up is None:
            continue
        analysts.append(LeaderRow(
            **common,
            value=_analyst_rank(up, float(rec), float(n_op)),
            detail=f"consenso {rec:.1f} · {int(n_op)} analisti",
            analysts=int(n_op),
            recommendation=round(float(rec), 2),
            upside_pct=round(up, 1),
            target=round(float(pt.mean), 2),
            last_close=round(float(pt.current), 2),
        ))

    def top(rows: list[LeaderRow]) -> list[LeaderRow]:
        # Ties broken by ticker so the order is stable between requests rather
        # than following whatever the query happened to return.
        return sorted(rows, key=lambda r: (-r.value, r.ticker))[:limit]

    return {
        "analysts": top(analysts),
        "combined": top(combined),
        "signals": top(signal_rows),
    }
