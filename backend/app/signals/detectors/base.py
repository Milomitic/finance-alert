"""Detector contract + SignalMatch + temporal-sequence helpers."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Protocol

import pandas as pd

from app.signals.context import SignalContext
from app.signals.events import Event


# frozen=True makes the fields immutable but NOT hashable — chain/invalidation/
# factors are mutable containers. Don't put SignalMatch in a set or use it as a
# dict key; it is meant to be iterated and serialised to JSON.
@dataclass(frozen=True)
class SignalMatch:
    name: str
    tone: str                       # "bull" | "bear"
    signal_date: str                # ISO — date of the chain's last event
    chain: list[dict]               # [{date, label, detail}]
    invalidation: dict | None       # {"level": float, "reason": str}
    factors: dict[str, float] = field(default_factory=dict)
    annotations: dict = field(default_factory=lambda: {"levels": [], "points": []})
    # Two-score model (confidence redesign): Forza = pattern strength
    # (score_v2 over per-factor curves), Probabilità = empirical hit-rate "di
    # accadimento" (calibration_map). Default to neutral so un-migrated
    # detectors keep working during the incremental migration.
    strength: int = 0               # "Forza" 0..100
    probability: int = 50           # "Probabilità" 0..100


class SignalDetector(Protocol):
    name: str
    tone: str
    sources: list[str]
    min_bars: int
    def detect(
        self, events: list[Event], ohlcv: pd.DataFrame, ctx: SignalContext,
    ) -> SignalMatch | None: ...


def _d(iso: str) -> _date:
    return _date.fromisoformat(iso[:10])


def find_after(
    events: list[Event], type_: str, *, after: str, within_days: int,
    direction: str | None = None,
) -> Event | None:
    """First event of `type_` (and optional `direction`) strictly after
    `after` and within `within_days` calendar days. Events assumed
    date-sorted ascending."""
    a = _d(after)
    for e in events:
        if e.type != type_:
            continue
        if direction is not None and e.direction != direction:
            continue
        ed = _d(e.date)
        if ed <= a:
            continue
        if (ed - a).days <= within_days:
            return e
    return None


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def soft01(x: float, ref: float) -> float:
    """Saturating strength score in [0, 1) that NEVER reaches 1.0.

    Replaces the old `clamp01(x / ref)` for magnitude-style "strength" factors.
    The hard clamp pinned every reading >= ref to exactly 1.0, so a merely-
    sufficient signal and an extreme one scored identically — the main reason
    so many alerts maxed out at confidence 100. This curve keeps a gradient:

        x = ref      -> 0.80   (meets the old "full" bar: strong, not maxed)
        x = 2*ref    -> 0.89
        x = 4*ref    -> 0.94
        x -> inf     -> 1.0    (asymptote, never reached)
        x = ref/2    -> 0.67   (sub-threshold readings fall off faster)

    So two signals that both used to hit 1.0 now separate by their real
    magnitude, and the factor can never on its own force a perfect score."""
    if x <= 0 or ref <= 0:
        return 0.0
    return x / (x + 0.25 * ref)


# ── Per-factor calibration curves (confidence redesign, Phase A) ─────────────
# These replace the global soft01/clamp01 shaping. Each factor is mapped onto
# the curve that fits its NATURE, with anchor points placed at data-grounded raw
# values (from app.scripts.signal_factor_outcomes — the raw level at which the
# realised forward hit-rate crosses 52/56/60%). This makes a factor reach the
# top of its range only when its underlying parameter genuinely predicts, not
# merely when it's statistically rare.

# Asymptote shared by `concave`: the top of a factor's contribution. Set to 0.99
# (not 1.0) and approached only for EXTREME raw values — so a genuine "monster"
# factor can carry the combined score toward 99, while 100 stays unreachable.
_CONCAVE_CEIL = 0.99
# Contribution at the `a88` anchor (kept at 0.88 so the sub-monster band is
# unchanged); the saturating tail rises from here toward _CONCAVE_CEIL.
_CONCAVE_A88 = 0.88


def concave(x: float, anchors: tuple[float, float, float, float]) -> float:
    """Piecewise-linear-then-saturating curve in [0, 0.92) for bounded
    "strength" magnitude factors (candle body/range, breakout %, EMA spread, …).

    anchors = (a45, a75, a88, ceil): the RAW factor values that should map to
    contributions 0.45 / 0.75 / 0.88, plus `ceil` setting the decay scale of the
    saturating tail. Semantics: contribution 0.88 == "the parameter is at the
    level that empirically predicts" (not "the 99th percentile of rarity").

    Shape:
        x <= 0      -> 0.0
        0  .. a45   -> linear up to 0.45
        a45 .. a75  -> linear up to 0.75
        a75 .. a88  -> linear up to 0.88
        x  >  a88   -> 0.92 - 0.04*exp(-(x-a88)/(ceil-a88))   (asymptote 0.92)
    The tail is continuous at (a88, 0.88) and approaches but never reaches 0.92.
    """
    a45, a75, a88, ceil = anchors
    if x <= 0 or a45 <= 0:
        return 0.0
    if x <= a45:
        return 0.45 * (x / a45)
    if x <= a75 and a75 > a45:
        return 0.45 + 0.30 * (x - a45) / (a75 - a45)
    if x <= a88 and a88 > a75:
        return 0.75 + 0.13 * (x - a75) / (a88 - a75)
    scale = (ceil - a88) if ceil > a88 else max(a88, 1e-9)
    # Tail rises from (a88, _CONCAVE_A88) toward the _CONCAVE_CEIL asymptote.
    # Keep the gap strictly positive: for extreme x the exp underflows to 0.0,
    # which would let the curve touch the asymptote exactly. The epsilon
    # preserves the "never quite reaches the ceiling" invariant in float math.
    gap = max((_CONCAVE_CEIL - _CONCAVE_A88) * math.exp(-(x - a88) / scale), 1e-9)
    return _CONCAVE_CEIL - gap


def log_saturate(x: float, ceil: float, target: float = 0.85) -> float:
    """Logarithmic saturation in [0, 1] for UNBOUNDED ratio factors (volume vs
    average, very large gaps). Linear in log-space: equal multiplicative steps
    give equal contribution steps, matching how a 10x vs 5x volume "feels".

        f(x) = target * ln(1+x) / ln(1+ceil),  clamped to 1.0
        f(0) = 0 ;  f(ceil) = target ;  f keeps rising past ceil toward 1.0.

    `ceil` is the raw value deemed "strong" (maps to `target`, default 0.85); a
    genuine monster beyond it still earns extra credit up to 1.0."""
    if x <= 0 or ceil <= 0:
        return 0.0
    return min(1.0, target * math.log1p(x) / math.log1p(ceil))


def trend_maturity_factor(age: int | None) -> float:
    """Backtest-derived favorability of a trend-following entry by trend age
    (bars since the EMA50/EMA200 cross). Forward 21d returns peaked mid-life
    (~120-250 bars) and were weakest for very young (<60) and mature (250+)
    trends, so this factor is non-monotonic by design."""
    if age is None:
        return 0.6
    if age < 60:
        return 0.5
    if age < 120:
        return 0.7
    if age < 250:
        return 1.0
    return 0.35


# Top-of-scale reserve. The raw weighted mean is passed through unchanged up
# to _CONF_KNEE; above it, [_CONF_KNEE, 1.0] is linearly compressed into
# [_CONF_KNEE, _CONF_MAX]. So a "perfect" factor set tops out at _CONF_MAX
# (95) — never 100, which is treated as theoretical, unreachable perfection —
# and strong-but-not-perfect signals spread across the upper band instead of
# all pinning at 100. Leaving the sub-knee region untouched keeps the emission
# floor (settings.signal_min_confidence = 60) unaffected: no signal that used
# to qualify is silently dropped by the reshape.
_CONF_KNEE = 0.72
_CONF_MAX = 0.95


def score(factors: dict[str, float], weights: dict[str, float]) -> int:
    """Weighted mean of [0,1] factors, with the top of the scale reserved
    (see _CONF_KNEE / _CONF_MAX), returned as a 0..100 int."""
    num = sum(clamp01(factors.get(k, 0.0)) * w for k, w in weights.items())
    den = sum(weights.values()) or 1.0
    raw = num / den
    if raw > _CONF_KNEE:
        raw = _CONF_KNEE + (_CONF_MAX - _CONF_KNEE) * (raw - _CONF_KNEE) / (1.0 - _CONF_KNEE)
    return round(100.0 * raw)


# Combiner v2 (confidence redesign). Detectors opt in one at a time; until then
# they keep calling score(). The soft-min cap replaces the global knee: instead
# of compressing the TOP of the weighted mean, it bounds the result by the
# WEAKEST strength factor, so confidence can't be manufactured by a saturated
# context factor riding over a mediocre one ("mediocrity laundering").
_V2_DELTA = 0.12          # how far strong factors may lift the score past the weakest
_V2_GUARDRAIL = 0.99      # top clamp: 99 reachable only by exceptional signals; 100 never


def score_v2(
    factors: dict[str, float],
    weights: dict[str, float],
    strength_keys: set[str],
    *,
    delta: float = _V2_DELTA,
    guardrail: float = _V2_GUARDRAIL,
) -> int:
    """Weighted mean of [0,1] factors, capped by a soft-min over the detector's
    STRENGTH factors, returned as a 0..100 int.

        arith  = Σ(f_i·w_i) / Σ(w_i)                      # all weighted factors
        m      = min(f_i for i in strength_keys present)  # genuine strength only
        score  = min(arith, m + delta, guardrail)

    `strength_keys` lists the factors that represent real signal strength;
    context modulators (trend_alignment, trend_maturity) are deliberately
    EXCLUDED so their weakness isn't double-counted (it already lives in their
    floor) — they contribute additively via `arith` but never pull the cap.
    A score ≥ 0.85 therefore requires every strength factor ≥ 0.85−delta."""
    num = sum(clamp01(factors.get(k, 0.0)) * w for k, w in weights.items())
    den = sum(weights.values()) or 1.0
    arith = num / den
    strengths = [
        clamp01(factors[k]) for k in strength_keys if k in weights and k in factors
    ]
    if strengths:
        arith = min(arith, min(strengths) + delta)
    return round(100.0 * min(arith, guardrail))


# ── Probabilità ("di accadimento") — empirical occurrence likelihood ─────────
# Unlike Forza (pattern strength), Probabilità is grounded in REALISED outcomes:
# a detector's historical absolute directional hit-rate (base rate) plus small,
# bounded per-factor adjustments where a factor measurably shifts the odds. See
# docs/superpowers/specs/2026-05-28-signal-strength-probability-split-design.md.
_PROB_MAX_ADJ = 8.0       # cap on the summed factor adjustments (base rate dominates)
_PROB_FLOOR = 5.0
_PROB_CEIL = 95.0


def interp_adjustment(raw: float, points: list[tuple[float, float]]) -> float:
    """Piecewise-linear lookup of a factor's raw value into (raw, adjustment)
    points. Below the first point → first adj; above the last → last adj;
    between → linear. Empty → 0.0. Points need not be pre-sorted."""
    if not points:
        return 0.0
    pts = sorted(points)
    if raw <= pts[0][0]:
        return pts[0][1]
    if raw >= pts[-1][0]:
        return pts[-1][1]
    for i in range(1, len(pts)):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i]
        if raw <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (raw - x0) / (x1 - x0)
    return pts[-1][1]


def probability_from_factors(
    base_rate: float,
    factors: dict[str, float],
    adj_table: dict[str, list[tuple[float, float]]],
    *,
    max_total_adj: float = _PROB_MAX_ADJ,
    floor: float = _PROB_FLOOR,
    ceil: float = _PROB_CEIL,
) -> int:
    """Probabilità as a 0..100 int: detector `base_rate` + a bounded sum of
    per-factor adjustments, clamped to [floor, ceil].

    `adj_table` maps a factor key to its (raw, adjustment) interpolation points;
    factors absent from the table contribute 0. The summed adjustment is capped
    at ±`max_total_adj` so the empirically-measured detector base rate dominates
    (the marginal-factor study showed most per-factor effects are small)."""
    total = 0.0
    for k, raw in factors.items():
        pts = adj_table.get(k)
        if pts:
            total += interp_adjustment(raw, pts)
    total = max(-max_total_adj, min(max_total_adj, total))
    return round(max(floor, min(ceil, base_rate + total)))
