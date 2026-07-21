"""Fit + OUT-OF-SAMPLE-VALIDATE a calibration model for signal Probabilità.

This is an *upgrade candidate* for the current per-detector base rate (the flat
``base_rate`` written by ``signal_detector_outcomes --emit-map``). The whole
point of this script is the VALIDATION DISCIPLINE, not the model: a single-name
technical hit-rate is a near-coin-flip, so the dominant risk is OVERFITTING a
weak signal. We therefore:

  1. Build a no-look-ahead labelled dataset by replaying the PRODUCTION
     detectors over a sampled universe + observation grid (reusing
     ``signal_detector_outcomes``' importable helpers — we do NOT edit that
     file, another agent references it).
  2. Fit two interpretable, regularised models — a per-detector PAVA isotonic
     map (Forza → P(hit), monotonic) and a single L2 logistic regression on
     [detector one-hot + factors + regime + horizon] (both pure numpy; sklearn
     is absent in this venv).
  3. Validate OUT OF SAMPLE two independent ways — split on DISJOINT stocks
     (so the model can't memorise a ticker) AND a TEMPORAL holdout (train old
     bars, test recent bars) — scoring Brier + log-loss + a reliability table
     against the BASELINE (the per-detector train-set base rate, i.e. exactly
     what the current artifact encodes).
  4. ADOPT the model ONLY IF it clears an explicit threshold on BOTH splits;
     otherwise REJECT and leave the artifact untouched (honesty over
     sophistication — the trade-playbook tbs% metric was data-rejected the same
     way this session).

REGIME feature: we use the *causal* ``close > EMA200`` (price vs its own 200d
EMA at the obs bar) — NOT the universe forward mean (which is forward-looking
and would leak the label's market component). EMA200 at bar i depends only on
bars ≤ i, so the dataset stays strictly no-look-ahead: the trailing window ends
at the obs bar; only the label looks forward.

Read-only on the DB (loads ohlcv + runs detectors). Writes the artifact +
prints the report ONLY with --emit-map (and only if the model is adopted).

USAGE
═════
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.fit_signal_calibration
      --sample N        eligible stocks to replay (default 300, matches artifact)
      --step N          bars between observation dates (default 42)
      --window N        trailing window fed to detect_signals (default 500)
      --min-bars N      require >= N bars of history (default 1000)
      --min-det-n N     min TRAIN signals for a detector to get its own isotonic
                        model (default 200; below this it falls back to base rate)
      --emit-map        if (and only if) the model is ADOPTED, write the upgraded
                        app/data/signal_calibration.json
      --seed N          RNG seed for the stock-disjoint split hash (default 0)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from loguru import logger

from app.indicators.ema import ema
from app.scripts.signal_detector_outcomes import _detector_horizon
from app.scripts.signal_factor_outcomes import (
    H_LONG,
    H_MED,
    H_SHORT,
    _load_universe,
    _universe_mean_fwd,
)
from app.signals.calibration_map import _DEFAULT_PATH
from app.signals.horizon import _PRIOR, classify_horizon
from app.signals.runner import detect_signals

# The report uses a few non-ASCII glyphs (Δ, →, box-drawing). The default
# Windows console is cp1252 and would UnicodeEncodeError on them — force UTF-8.
try:  # pragma: no cover - environment dependent
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

_HORIZONS = {"short": H_SHORT, "medium": H_MED, "long": H_LONG}
_HORIZON_NAME = {"short": 0, "medium": 1, "long": 2}  # for the logistic one-hot

# Adoption thresholds (explicit, stated up front).
#   - The model must beat the baseline on OOS Brier by >= this RELATIVE margin
#     on BOTH the stock-disjoint and the temporal holdout splits.
#   - It must not REGRESS log-loss on either split.
#   - Its reliability curve (predicted-bucket -> realised) must be monotone
#     non-decreasing on the stock-disjoint split (a calibrated model orders risk).
_ADOPT_REL_BRIER_GAIN = 0.02   # >= 2% relative Brier reduction
_RELIABILITY_BUCKETS = 10

# Deployment clamp: production Probabilità is clamped to [5, 95] (base._PROB_FLOOR
# / _PROB_CEIL). Models are EVALUATED with the same clamp so the OOS scores
# reflect how the model would actually be used — and so the isotonic tails
# (which PAVA can push to 0/1 on a sparse block) can't blow up log-loss with
# probabilities the live engine would never emit.
_CLAMP_LO, _CLAMP_HI = 0.05, 0.95


# ─────────────────────────────────────────────────────────────────────────────
#  Dataset
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Row:
    detector: str
    factors: dict[str, float]
    forza: float          # 0..1 (m.strength / 100)
    horizon: str          # short|medium|long
    regime: int           # +1 close>EMA200 else -1 (causal)
    label: int            # abs_hit (1 if close-to-close move went the signalled way)
    stock_id: int
    obs_idx: int          # global calendar index of the obs date (temporal split)


@dataclass
class Dataset:
    rows: list[Row] = field(default_factory=list)
    n_calls: int = 0

    def labels(self) -> np.ndarray:
        return np.array([r.label for r in self.rows], dtype=float)


def build_dataset(*, sample: int, step: int, window: int, min_bars: int) -> Dataset:
    """Replay the production detectors over a sampled universe + obs grid and
    emit one labelled Row per fired signal. No look-ahead: the detector window
    ends at the obs bar; only the abs_hit label looks forward (by the detector's
    horizon)."""
    from app.core.db import SessionLocal

    db = SessionLocal()
    ds = Dataset()
    try:
        logger.info(f"[fit] loading universe (sample={sample}) ...")
        universe = _load_universe(db, min_bars=min_bars, sample=sample)
        logger.info(f"[fit] {len(universe)} stocks")
        if not universe:
            return ds
        umean = _universe_mean_fwd(universe)
        date_to_idx = umean["_date_to_idx"]

        n_signals = 0
        for sidx, s in enumerate(universe):
            df = s.df
            c = s.closes
            n = len(c)
            # Causal regime: close vs its own EMA200 at each bar (EMA at bar i is
            # a function of bars <= i only → no look-ahead).
            ema200 = ema(df["close"].astype(float), 200).to_numpy(dtype="float64")
            for i in range(window, n - H_SHORT, step):
                win = df.iloc[i - window:i + 1].reset_index(drop=True)
                ds.n_calls += 1
                try:
                    matches = detect_signals(win)
                except Exception:  # noqa: BLE001
                    continue
                if not matches:
                    continue
                regime = 1 if (np.isfinite(ema200[i]) and c[i] > ema200[i]) else -1
                for m in matches:
                    h = _detector_horizon(m.name)
                    if i + h >= n or c[i] <= 0:
                        continue
                    fwd = c[i + h] / c[i] - 1.0
                    abs_hit = 1 if ((m.tone == "bull" and fwd > 0)
                                    or (m.tone == "bear" and fwd < 0)) else 0
                    hz = classify_horizon(m.name, m.chain)
                    ds.rows.append(Row(
                        detector=m.name,
                        factors={k: float(v) for k, v in m.factors.items()},
                        forza=float(m.strength) / 100.0,
                        horizon=hz if hz in _HORIZONS else _PRIOR.get(m.name, "medium"),
                        regime=regime,
                        label=abs_hit,
                        stock_id=s.stock_id,
                        obs_idx=date_to_idx.get(s.dates[i], -1),
                    ))
                    n_signals += 1
            if (sidx + 1) % 25 == 0:
                logger.info(f"[fit] {sidx + 1}/{len(universe)} stocks, "
                            f"{n_signals:,} signals so far")
        logger.info(f"[fit] {ds.n_calls:,} detect calls, {n_signals:,} signals")
        return ds
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Splits — disjoint stocks + temporal holdout
# ─────────────────────────────────────────────────────────────────────────────
def split_by_stock(rows: list[Row], seed: int) -> tuple[list[int], list[int]]:
    """TRAIN/TEST indices on DISJOINT stocks. A stock goes entirely to train or
    test by a stable hash of its id (so a ticker can't appear on both sides and
    leak). ~50/50 by stock count."""
    train, test = [], []
    for j, r in enumerate(rows):
        # Stable, seed-able hash bucket (avoid Python's salted hash()).
        h = (r.stock_id * 2654435761 + seed * 40503) & 0xFFFFFFFF
        (test if (h % 2 == 0) else train).append(j)
    return train, test


def split_temporal(rows: list[Row], frac: float = 0.7) -> tuple[list[int], list[int]]:
    """TRAIN = oldest `frac` of observation dates, TEST = most-recent (1-frac).
    Split on the obs calendar index so train precedes test in wall-clock time."""
    idxs = sorted(range(len(rows)), key=lambda j: rows[j].obs_idx)
    cut = int(len(idxs) * frac)
    return idxs[:cut], idxs[cut:]


# ─────────────────────────────────────────────────────────────────────────────
#  Baseline — per-detector TRAIN base rate (what the artifact encodes)
# ─────────────────────────────────────────────────────────────────────────────
def fit_baseline(rows: list[Row], train: list[int]) -> tuple[dict[str, float], float]:
    """Per-detector mean label on TRAIN (the constant base rate), plus the
    global mean as the fallback for detectors unseen in train."""
    by_det: dict[str, list[int]] = defaultdict(list)
    for j in train:
        by_det[rows[j].detector].append(rows[j].label)
    base = {d: float(np.mean(v)) for d, v in by_det.items()}
    glob = float(np.mean([rows[j].label for j in train])) if train else 0.5
    return base, glob


def predict_baseline(rows: list[Row], idxs: list[int],
                     base: dict[str, float], glob: float) -> np.ndarray:
    return np.array([base.get(rows[j].detector, glob) for j in idxs])


# ─────────────────────────────────────────────────────────────────────────────
#  Model 1 — per-detector PAVA isotonic (Forza -> P(hit))
# ─────────────────────────────────────────────────────────────────────────────
def pava(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pool-Adjacent-Violators isotonic regression. Returns (x_knots, y_fit)
    giving a monotone non-decreasing step function. x must be pre-sorted.

    Standard O(n) PAVA over weighted means: scan left→right, merge any block
    whose mean violates monotonicity with its left neighbour."""
    n = len(y)
    # Each block: [sum_wy, sum_w, value]; we also track block right-edges.
    val = y.astype(float).copy()
    wt = w.astype(float).copy()
    # Use index stacks for the merge.
    lvl_val: list[float] = []
    lvl_w: list[float] = []
    lvl_xend: list[float] = []
    for i in range(n):
        cur_v = val[i]
        cur_w = wt[i]
        cur_x = x[i]
        while lvl_val and lvl_val[-1] >= cur_v:
            # merge
            pw = lvl_w.pop()
            pv = lvl_val.pop()
            lvl_xend.pop()
            cur_v = (pv * pw + cur_v * cur_w) / (pw + cur_w)
            cur_w = pw + cur_w
        lvl_val.append(cur_v)
        lvl_w.append(cur_w)
        lvl_xend.append(cur_x)
    return np.array(lvl_xend), np.array(lvl_val)


@dataclass
class IsotonicModel:
    # Per detector: sorted x-knots + monotone y values (the step function); plus
    # the detector base rate as the fallback when Forza is below/above range.
    knots: dict[str, tuple[np.ndarray, np.ndarray]]
    base: dict[str, float]
    glob: float

    def predict_one(self, det: str, forza: float) -> float:
        km = self.knots.get(det)
        if km is None:
            return self.base.get(det, self.glob)
        xs, ys = km
        # Piecewise-constant-then-linear interpolation on the isotonic knots.
        return float(np.interp(forza, xs, ys, left=ys[0], right=ys[-1]))

    def predict(self, rows: list[Row], idxs: list[int]) -> np.ndarray:
        p = np.array([self.predict_one(rows[j].detector, rows[j].forza) for j in idxs])
        return np.clip(p, _CLAMP_LO, _CLAMP_HI)


def fit_isotonic(rows: list[Row], train: list[int], min_det_n: int,
                 base: dict[str, float], glob: float) -> IsotonicModel:
    by_det: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for j in train:
        by_det[rows[j].detector].append((rows[j].forza, rows[j].label))
    knots: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for det, pairs in by_det.items():
        if len(pairs) < min_det_n:
            continue
        pairs.sort(key=lambda p: p[0])
        x = np.array([p[0] for p in pairs], dtype=float)
        y = np.array([p[1] for p in pairs], dtype=float)
        w = np.ones_like(y)
        xs, ys = pava(x, y, w)
        if len(xs) < 2:   # degenerate (no monotone structure) → use base rate
            continue
        knots[det] = (xs, ys)
    return IsotonicModel(knots=knots, base=base, glob=glob)


# ─────────────────────────────────────────────────────────────────────────────
#  Model 2 — L2 logistic regression (numpy IRLS) on the full feature set
# ─────────────────────────────────────────────────────────────────────────────
# Factors that appear across detectors. Built dynamically from the dataset so we
# don't hard-code; gate factors (always 1.0) get dropped as zero-variance.
def _factor_vocab(rows: list[Row], idxs: list[int]) -> list[str]:
    keys: set[str] = set()
    for j in idxs:
        keys.update(rows[j].factors.keys())
    return sorted(keys)


@dataclass
class LogisticModel:
    detectors: list[str]
    factor_keys: list[str]
    feat_mean: np.ndarray
    feat_std: np.ndarray
    coef: np.ndarray         # includes intercept at [0]
    keep: np.ndarray         # bool mask of non-degenerate standardized columns

    def _design(self, rows: list[Row], idxs: list[int]) -> np.ndarray:
        det_idx = {d: i for i, d in enumerate(self.detectors)}
        nd = len(self.detectors)
        nf = len(self.factor_keys)
        # columns: [nd detector one-hot][nf factors][forza][regime][2 horizon one-hot]
        X = np.zeros((len(idxs), nd + nf + 1 + 1 + 2), dtype=float)
        for r_i, j in enumerate(idxs):
            r = rows[j]
            di = det_idx.get(r.detector)
            if di is not None:
                X[r_i, di] = 1.0
            for f_i, k in enumerate(self.factor_keys):
                X[r_i, nd + f_i] = r.factors.get(k, 0.0)
            X[r_i, nd + nf] = r.forza
            X[r_i, nd + nf + 1] = r.regime
            hz = _HORIZON_NAME.get(r.horizon, 1)
            if hz == 0:
                X[r_i, nd + nf + 2] = 1.0   # short
            elif hz == 2:
                X[r_i, nd + nf + 3] = 1.0   # long  (medium = reference)
        return X

    def predict(self, rows: list[Row], idxs: list[int]) -> np.ndarray:
        X = self._design(rows, idxs)
        Xs = (X - self.feat_mean) / self.feat_std
        Xs = Xs[:, self.keep]
        z = self.coef[0] + Xs @ self.coef[1:]
        return np.clip(1.0 / (1.0 + np.exp(-z)), _CLAMP_LO, _CLAMP_HI)


def fit_logistic(rows: list[Row], train: list[int], *, l2: float = 1.0,
                 iters: int = 50) -> LogisticModel:
    detectors = sorted({rows[j].detector for j in train})
    factor_keys = _factor_vocab(rows, train)
    model = LogisticModel(detectors=detectors, factor_keys=factor_keys,
                          feat_mean=np.zeros(1), feat_std=np.ones(1),
                          coef=np.zeros(1), keep=np.ones(1, dtype=bool))
    X = model._design(rows, train)
    y = np.array([rows[j].label for j in train], dtype=float)

    mean = X.mean(axis=0)
    std = X.std(axis=0)
    keep = std > 1e-9            # drop zero-variance cols (constant gate factors)
    std_safe = np.where(keep, std, 1.0)
    Xs = (X - mean) / std_safe
    Xs = Xs[:, keep]

    n, p = Xs.shape
    Xb = np.hstack([np.ones((n, 1)), Xs])      # intercept column
    beta = np.zeros(p + 1)
    # L2 penalty applied to all but the intercept.
    pen = np.full(p + 1, l2)
    pen[0] = 0.0
    for _ in range(iters):
        z = Xb @ beta
        mu = 1.0 / (1.0 + np.exp(-z))
        Wd = np.clip(mu * (1.0 - mu), 1e-6, None)
        # IRLS / Newton step with ridge: (XᵀWX + λI) Δ = Xᵀ(y-μ) - λβ
        grad = Xb.T @ (y - mu) - pen * beta
        H = (Xb.T * Wd) @ Xb + np.diag(pen)
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H, grad, rcond=None)[0]
        beta = beta + step
        if np.max(np.abs(step)) < 1e-7:
            break

    model.feat_mean = mean
    model.feat_std = std_safe
    model.coef = beta
    model.keep = keep
    return model


_L2_GRID = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0)


def fit_logistic_cv(rows: list[Row], train: list[int], *, seed: int = 0) -> LogisticModel:
    """Select the L2 strength by K-fold CV WITHIN the training rows (no test
    leakage), minimising mean validation log-loss, then refit on all of `train`
    at the chosen λ. For a near-coin-flip signal the right λ is what stops the
    model from chasing noise — picking it on a held-in fold is the honest way."""
    if len(train) < 200:
        return fit_logistic(rows, train)
    rng = np.random.default_rng(seed)
    folds = rng.integers(0, 5, size=len(train))
    best_l2, best_ll = _L2_GRID[0], float("inf")
    for l2 in _L2_GRID:
        lls = []
        for k in range(5):
            tr = [train[i] for i in range(len(train)) if folds[i] != k]
            va = [train[i] for i in range(len(train)) if folds[i] == k]
            if not va or not tr:
                continue
            m = fit_logistic(rows, tr, l2=l2)
            p = m.predict(rows, va)
            yv = np.array([rows[j].label for j in va], dtype=float)
            lls.append(log_loss(p, yv))
        mean_ll = float(np.mean(lls)) if lls else float("inf")
        if mean_ll < best_ll:
            best_ll, best_l2 = mean_ll, l2
    return fit_logistic(rows, train, l2=best_l2)


# ─────────────────────────────────────────────────────────────────────────────
#  Metrics
# ─────────────────────────────────────────────────────────────────────────────
def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    pc = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def reliability(p: np.ndarray, y: np.ndarray, n_buckets: int = _RELIABILITY_BUCKETS):
    """Return list of (pred_mean, obs_mean, n) per equal-width probability bucket
    (only non-empty buckets)."""
    out = []
    edges = np.linspace(p.min(), p.max() + 1e-12, n_buckets + 1) if p.size else [0, 1]
    for b in range(len(edges) - 1):
        lo, hi = edges[b], edges[b + 1]
        sel = (p >= lo) & (p < hi) if b < len(edges) - 2 else (p >= lo) & (p <= hi)
        if not sel.any():
            continue
        out.append((float(p[sel].mean()), float(y[sel].mean()), int(sel.sum())))
    return out


def reliability_monotone(rel) -> bool:
    """Is realised hit-rate non-decreasing across predicted buckets (allowing a
    small tolerance for noise in sparse buckets)?"""
    ys = [obs for _, obs, n in rel if n >= 30]
    return all(ys[i] <= ys[i + 1] + 0.02 for i in range(len(ys) - 1))


# ─────────────────────────────────────────────────────────────────────────────
#  Evaluation harness
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_split(name: str, rows: list[Row], train: list[int], test: list[int],
                   *, min_det_n: int) -> dict:
    base, glob = fit_baseline(rows, train)
    iso = fit_isotonic(rows, train, min_det_n, base, glob)
    log = fit_logistic_cv(rows, train)

    y = np.array([rows[j].label for j in test], dtype=float)
    p_base = predict_baseline(rows, test, base, glob)
    p_iso = iso.predict(rows, test)
    p_log = log.predict(rows, test)

    res = {
        "name": name,
        "n_train": len(train),
        "n_test": len(test),
        "test_pos_rate": float(y.mean()),
        "baseline": {"brier": brier(p_base, y), "logloss": log_loss(p_base, y)},
        "isotonic": {"brier": brier(p_iso, y), "logloss": log_loss(p_iso, y),
                     "reliability": reliability(p_iso, y)},
        "logistic": {"brier": brier(p_log, y), "logloss": log_loss(p_log, y),
                     "reliability": reliability(p_log, y)},
        "_models": {"base": base, "glob": glob, "iso": iso, "log": log},
    }
    return res


def _rel_gain(model_brier: float, base_brier: float) -> float:
    return (base_brier - model_brier) / base_brier if base_brier > 0 else 0.0


def print_reliability(label: str, rel) -> None:
    print(f"    {label} reliability (pred → realised):")
    print(f"      {'pred%':>8}{'real%':>8}{'n':>9}")
    for pm, om, n in rel:
        print(f"      {pm*100:>8.1f}{om*100:>8.1f}{n:>9,}")


def report(res_stock: dict, res_time: dict) -> None:
    print(f"\n{'#'*78}")
    print("#  SIGNAL-PROBABILITÀ CALIBRATION — OUT-OF-SAMPLE VALIDATION")
    print(f"{'#'*78}")
    for res in (res_stock, res_time):
        print(f"\n{'='*78}\n  SPLIT: {res['name']}   "
              f"train={res['n_train']:,}  test={res['n_test']:,}  "
              f"test pos-rate={res['test_pos_rate']*100:.1f}%\n{'='*78}")
        b = res["baseline"]
        print(f"  {'model':<12}{'Brier':>10}{'log-loss':>12}{'ΔBrier rel':>14}")
        print(f"  {'baseline':<12}{b['brier']:>10.5f}{b['logloss']:>12.5f}{'—':>14}")
        for key in ("isotonic", "logistic"):
            m = res[key]
            g = _rel_gain(m["brier"], b["brier"])
            print(f"  {key:<12}{m['brier']:>10.5f}{m['logloss']:>12.5f}{g*100:>+13.2f}%")
        print()
        print_reliability("isotonic", res["isotonic"]["reliability"])
        print_reliability("logistic", res["logistic"]["reliability"])


def decide(res_stock: dict, res_time: dict) -> tuple[str | None, str]:
    """Return (winner_key | None, rationale). winner_key in {isotonic, logistic}
    if a model clears the bar on BOTH splits; else None (reject)."""
    lines = []
    winner = None
    for key in ("isotonic", "logistic"):
        gains, ll_ok, _all_ok = [], True, True
        for res in (res_stock, res_time):
            b = res["baseline"]
            m = res[key]
            g = _rel_gain(m["brier"], b["brier"])
            gains.append(g)
            if m["logloss"] > b["logloss"] + 1e-9:
                ll_ok = False
        mono = reliability_monotone(res_stock[key]["reliability"])
        clears = (min(gains) >= _ADOPT_REL_BRIER_GAIN) and ll_ok and mono
        lines.append(
            f"  {key}: stock ΔBrier {gains[0]*100:+.2f}%, temporal ΔBrier "
            f"{gains[1]*100:+.2f}%, log-loss not-worse={ll_ok}, "
            f"stock-split reliability monotone={mono} → "
            f"{'CLEARS' if clears else 'fails'} (need ≥{_ADOPT_REL_BRIER_GAIN*100:.0f}% "
            f"on BOTH splits + no log-loss regression + monotone)")
        if clears and winner is None:
            winner = key
    return winner, "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Artifact write (only on adoption)
# ─────────────────────────────────────────────────────────────────────────────
def _refit_full(rows: list[Row], min_det_n: int):
    """Refit the chosen model on ALL rows (train+test) for production use — OOS
    validation already happened; the shipped model should use every observation.
    Returns (base, glob, iso, log)."""
    allidx = list(range(len(rows)))
    base, glob = fit_baseline(rows, allidx)
    iso = fit_isotonic(rows, allidx, min_det_n, base, glob)
    log = fit_logistic_cv(rows, allidx)
    return base, glob, iso, log


def write_artifact(winner: str, rows: list[Row], ds: Dataset, min_det_n: int,
                   *, sample: int, path: Path, prev_path: Path) -> None:
    base, glob, iso, log = _refit_full(rows, min_det_n)
    # Carry forward the previous artifact's per-detector metadata (horizon_days,
    # n, mkt-neutral diagnostics) where present.
    prev = {}
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8")).get("detectors", {})
    except (OSError, ValueError):
        prev = {}

    n_by_det: dict[str, int] = defaultdict(int)
    for r in rows:
        n_by_det[r.detector] += 1

    detectors: dict[str, dict] = {}
    for det in sorted(n_by_det, key=lambda d: -n_by_det[d]):
        rec = dict(prev.get(det, {}))
        rec["base_rate"] = round(base.get(det, glob) * 100)
        rec["horizon_days"] = rec.get("horizon_days", _detector_horizon(det))
        rec["n"] = n_by_det[det]
        if winner == "isotonic" and det in iso.knots:
            xs, ys = iso.knots[det]
            # Down-sample knots to a compact, monotone (x,y) set in PERCENT.
            rec["model"] = {
                "kind": "isotonic_forza",
                "x": [round(float(v), 4) for v in xs],
                "y": [round(float(v) * 100, 2) for v in ys],
            }
        detectors[det] = rec

    payload: dict = {
        "version": "2026-05-29-fit",
        "generated_by": "app.scripts.fit_signal_calibration",
        "base_rate_metric": "close_to_close_abs_hit",
        "model_kind": winner,
        "universe_stocks": sample,
        "signals": len(rows),
        "horizons": {"short": H_SHORT, "medium": H_MED, "long": H_LONG},
        "detectors": detectors,
        "factor_adjustments": {},
    }
    if winner == "logistic":
        payload["logistic_model"] = _serialize_logistic(log)

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n  [emit-map] ADOPTED '{winner}' → wrote {path} "
          f"({len(detectors)} detectors, {len(rows):,} signals)\n")


def _serialize_logistic(log: LogisticModel) -> dict:
    return {
        "kind": "l2_logistic",
        "detectors": log.detectors,
        "factor_keys": log.factor_keys,
        "feat_mean": [float(v) for v in log.feat_mean],
        "feat_std": [float(v) for v in log.feat_std],
        "keep": [bool(v) for v in log.keep],
        "coef": [float(v) for v in log.coef],
        "feature_layout": ["detector_onehot", "factors", "forza", "regime",
                           "horizon_short", "horizon_long"],
    }


# ─────────────────────────────────────────────────────────────────────────────
def run(*, sample: int, step: int, window: int, min_bars: int, min_det_n: int,
        emit_map: bool, seed: int) -> None:
    ds = build_dataset(sample=sample, step=step, window=window, min_bars=min_bars)
    if len(ds.rows) < 1000:
        print(f"Only {len(ds.rows)} rows — too few to validate. Aborting.")
        return
    rows = ds.rows

    # Feature list (reported).
    fk = _factor_vocab(rows, list(range(len(rows))))
    dets = sorted({r.detector for r in rows})
    print(f"\nDataset: {len(rows):,} labelled signals over {len(dets)} detectors, "
          f"{ds.n_calls:,} detect calls.")
    print(f"Overall abs-hit rate: {ds.labels().mean()*100:.1f}%")
    print("Features:")
    print(f"  - detector (categorical, {len(dets)} levels): {dets}")
    print(f"  - factors (per-detector strength/context, {len(fk)}): {fk}")
    print("  - forza (Forza/100, continuous)")
    print("  - regime (causal: +1 close>EMA200 else -1)")
    print("  - horizon (short/medium/long)")
    print("  - label: abs_hit (1 if close-to-close move went the signalled way)")

    tr_s, te_s = split_by_stock(rows, seed)
    tr_t, te_t = split_temporal(rows)
    res_stock = evaluate_split("DISJOINT STOCKS", rows, tr_s, te_s, min_det_n=min_det_n)
    res_time = evaluate_split("TEMPORAL HOLDOUT (old→recent)", rows, tr_t, te_t,
                              min_det_n=min_det_n)

    report(res_stock, res_time)

    winner, rationale = decide(res_stock, res_time)
    print(f"\n{'='*78}\n  ADOPTION DECISION\n{'='*78}")
    print(rationale)
    if winner is None:
        print("\n  → REJECT: no model clears the OOS bar on both splits. "
              "Leaving the artifact as-is (per-detector base rate).")
        return

    print(f"\n  → ADOPT: '{winner}' clears the bar on both splits.")
    if emit_map:
        write_artifact(winner, rows, ds, min_det_n, sample=sample,
                       path=_DEFAULT_PATH, prev_path=_DEFAULT_PATH)
    else:
        print("  (run with --emit-map to write the artifact.)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--step", type=int, default=42)
    ap.add_argument("--window", type=int, default=500)
    ap.add_argument("--min-bars", type=int, default=1000)
    ap.add_argument("--min-det-n", type=int, default=200)
    ap.add_argument("--emit-map", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    run(sample=args.sample, step=args.step, window=args.window, min_bars=args.min_bars,
        min_det_n=args.min_det_n, emit_map=args.emit_map, seed=args.seed)
