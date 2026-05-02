# Fase 3C — Indicatori avanzati + regole composite + Rule Editor UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MACD/Bollinger/ATR/ADX indicators, six new atomic alert rules (volume/breakout/macd_cross/bollinger), AND/OR expression-tree composition with backward-compat scan path, and a `/rules` Rule Editor UI with tree builder + preview.

**Architecture:** Three independently shippable sub-phases — **3C-A** indicators+atomic rules (pure backend), **3C-B** expression-tree schema+evaluator+preview API (backend), **3C-C** React Rule Editor page (frontend). Backward compatibility is preserved by treating `Rule.expression` as nullable: existing rules keep using legacy `kind`+`params` path; rules with non-null `expression` use the new tree evaluator.

**Tech Stack:** pandas/numpy (indicators), FastAPI + SQLAlchemy 2.0 + Alembic (backend), pytest, React 19 + TanStack Query 5 + shadcn/ui (frontend). No new dependencies.

---

## File Structure

### Backend — new files

| Path | Responsibility |
|---|---|
| `backend/app/indicators/macd.py` | MACD line/signal/histogram |
| `backend/app/indicators/bb.py` | Bollinger bands + width helper |
| `backend/app/indicators/atr.py` | Wilder's ATR |
| `backend/app/indicators/adx.py` | ADX + ±DI |
| `backend/app/rules/volume_rules.py` | `VolumeSpikeRule` |
| `backend/app/rules/breakout_rules.py` | `BreakoutRule` |
| `backend/app/rules/macd_rules.py` | `MacdBullishCrossRule`, `MacdBearishCrossRule` |
| `backend/app/rules/bollinger_rules.py` | `BollingerSqueezeRule`, `BollingerBreakoutRule` |
| `backend/app/rules/composite.py` | `evaluate_expression`, `snapshot_expression`, `validate_expression`, `MAX_DEPTH`, `MAX_ATOMIC` |
| `backend/app/api/rule_catalog.py` | `GET /api/rules/catalog` (kind metadata) |
| `backend/app/api/rule_preview.py` | `POST /api/rules/preview` (evaluate against a stock) |
| `backend/alembic/versions/<auto>_add_rule_expression.py` | Migration adding `rules.expression` |
| `backend/tests/test_indicators_macd.py` | MACD tests |
| `backend/tests/test_indicators_bb.py` | Bollinger tests |
| `backend/tests/test_indicators_atr.py` | ATR tests |
| `backend/tests/test_indicators_adx.py` | ADX tests |
| `backend/tests/test_rules_volume.py` | Volume spike rule tests |
| `backend/tests/test_rules_breakout.py` | Breakout rule tests |
| `backend/tests/test_rules_macd.py` | MACD cross rules tests |
| `backend/tests/test_rules_bollinger.py` | Bollinger rules tests |
| `backend/tests/test_rules_composite.py` | Expression tree evaluator tests |
| `backend/tests/test_api_rule_catalog.py` | Catalog endpoint smoke |
| `backend/tests/test_api_rule_preview.py` | Preview endpoint tests |

### Backend — modified files

| Path | Change |
|---|---|
| `backend/app/models/rule.py` | Add `expression: Mapped[str \| None] = mapped_column(Text, nullable=True)` |
| `backend/app/rules/registry.py` | Register 6 new rule instances |
| `backend/app/schemas/rule.py` | Expand `_VALID_KINDS` with 6 new kinds; add `expression` field to `RuleCreate`/`RuleUpdate`/`RuleOut`; add validator that calls `validate_expression` |
| `backend/app/api/rules.py` | Persist/return `expression`; reject malformed via 422 |
| `backend/app/api/__init__.py` (or `main.py` router include) | Register `rule_catalog` and `rule_preview` routers |
| `backend/app/services/scan_service.py` | If `rule.expression` is non-null → use `evaluate_expression` + `snapshot_expression`; else legacy path |

### Frontend — new files

| Path | Responsibility |
|---|---|
| `frontend/src/api/rules.ts` (extend existing or new) | `listRules`, `createRule`, `updateRule`, `deleteRule`, `getRuleCatalog`, `previewRule` |
| `frontend/src/api/types.ts` (extend) | `Rule`, `RuleExpressionNode`, `RuleCatalogEntry`, `RulePreviewResponse` |
| `frontend/src/hooks/useRules.ts` | `useRules`, `useCreateRule`, `useUpdateRule`, `useDeleteRule` |
| `frontend/src/hooks/useRuleCatalog.ts` | TanStack Query w/ 5min stale time |
| `frontend/src/hooks/useRulePreview.ts` | mutation hook |
| `frontend/src/pages/RulesPage.tsx` | Page orchestrator |
| `frontend/src/components/rules/RulesTable.tsx` | List of existing rules |
| `frontend/src/components/rules/RuleEditorDialog.tsx` | Create/edit modal |
| `frontend/src/components/rules/ExpressionTree.tsx` | Recursive AND/OR tree builder |
| `frontend/src/components/rules/AtomicConditionForm.tsx` | Single-condition kind+params form |
| `frontend/src/components/rules/ExpressionPreview.tsx` | Test against ticker |

### Frontend — modified files

| Path | Change |
|---|---|
| `frontend/src/App.tsx` | Add `<Route path="/rules" element={<RulesPage />} />` |
| `frontend/src/components/Layout.tsx` | Flip `/rules` NAV entry `enabled: false → true` |

---

# 3C-A — Indicatori avanzati + 6 atomic rules (backend only)

### Task 1: MACD indicator

**Files:**
- Create: `backend/app/indicators/macd.py`
- Test: `backend/tests/test_indicators_macd.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_indicators_macd.py
"""Tests for MACD indicator."""
import math

import pandas as pd

from app.indicators.macd import macd


def test_macd_returns_three_series_same_length() -> None:
    s = pd.Series([100.0 + i * 0.5 for i in range(60)])
    line, signal, hist = macd(s)
    assert len(line) == len(signal) == len(hist) == 60


def test_macd_uptrend_line_above_signal_eventually() -> None:
    """In a steady uptrend, MACD line crosses above signal and stays positive."""
    s = pd.Series([100.0 + i * 1.0 for i in range(80)])
    line, signal, hist = macd(s)
    assert line.iloc[-1] > signal.iloc[-1]
    assert hist.iloc[-1] > 0


def test_macd_downtrend_line_below_signal() -> None:
    s = pd.Series([200.0 - i * 1.0 for i in range(80)])
    line, signal, _hist = macd(s)
    assert line.iloc[-1] < signal.iloc[-1]


def test_macd_warmup_yields_finite_after_slow_period() -> None:
    s = pd.Series([100.0 + i * 0.1 for i in range(60)])
    line, signal, hist = macd(s, fast=12, slow=26, signal=9)
    # By bar 50 all three should be finite numbers
    assert not math.isnan(line.iloc[50])
    assert not math.isnan(signal.iloc[50])
    assert not math.isnan(hist.iloc[50])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_indicators_macd.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.indicators.macd'`

- [ ] **Step 3: Implement MACD**

```python
# backend/app/indicators/macd.py
"""MACD: line = EMA(fast) - EMA(slow), signal = EMA(line, signal_period), histogram = line - signal."""
import pandas as pd


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram)."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    signal_line = line.ewm(span=signal, adjust=False).mean()
    histogram = line - signal_line
    return line, signal_line, histogram
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_indicators_macd.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/indicators/macd.py backend/tests/test_indicators_macd.py
git commit -m "feat(indicators): add MACD"
```

---

### Task 2: Bollinger Bands indicator

**Files:**
- Create: `backend/app/indicators/bb.py`
- Test: `backend/tests/test_indicators_bb.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_indicators_bb.py
"""Tests for Bollinger Bands."""
import pandas as pd

from app.indicators.bb import bb_width, bollinger


def test_bollinger_returns_three_series_same_length() -> None:
    s = pd.Series([100.0 + i * 0.5 for i in range(40)])
    upper, middle, lower = bollinger(s, period=20, k=2.0)
    assert len(upper) == len(middle) == len(lower) == 40


def test_bollinger_middle_equals_sma() -> None:
    s = pd.Series([float(v) for v in range(1, 31)])
    _u, middle, _l = bollinger(s, period=10, k=2.0)
    # SMA(10) of 21..30 = mean(21..30) = 25.5
    assert abs(middle.iloc[-1] - 25.5) < 1e-9


def test_bollinger_upper_above_lower_with_volatility() -> None:
    s = pd.Series([100.0, 110.0] * 25)  # zigzag -> nonzero stddev
    upper, _m, lower = bollinger(s, period=20, k=2.0)
    assert upper.iloc[-1] > lower.iloc[-1]


def test_bb_width_positive_with_volatility() -> None:
    s = pd.Series([100.0, 110.0] * 25)
    w = bb_width(s, period=20, k=2.0)
    assert w.iloc[-1] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_indicators_bb.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Bollinger**

```python
# backend/app/indicators/bb.py
"""Bollinger Bands: middle = SMA(period), upper/lower = middle ± k*stddev."""
import pandas as pd


def bollinger(
    close: pd.Series, period: int = 20, k: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, middle, lower)."""
    middle = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + k * std
    lower = middle - k * std
    return upper, middle, lower


def bb_width(close: pd.Series, period: int = 20, k: float = 2.0) -> pd.Series:
    """Width = (upper - lower) / middle. Used for squeeze detection."""
    upper, middle, lower = bollinger(close, period, k)
    return (upper - lower) / middle
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_indicators_bb.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/indicators/bb.py backend/tests/test_indicators_bb.py
git commit -m "feat(indicators): add Bollinger Bands"
```

---

### Task 3: ATR indicator

**Files:**
- Create: `backend/app/indicators/atr.py`
- Test: `backend/tests/test_indicators_atr.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_indicators_atr.py
"""Tests for Wilder's ATR."""
import pandas as pd

from app.indicators.atr import atr


def _ohlcv(highs: list[float], lows: list[float], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "open": closes,  # not used by ATR
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [0] * len(closes),
    })


def test_atr_constant_range_yields_constant_value() -> None:
    """If high-low is constant 1.0 and close = (high+low)/2, ATR -> 1.0."""
    n = 30
    highs = [101.0] * n
    lows = [100.0] * n
    closes = [100.5] * n
    df = _ohlcv(highs, lows, closes)
    result = atr(df, period=14)
    assert abs(result.iloc[-1] - 1.0) < 1e-9


def test_atr_increasing_volatility_increases() -> None:
    n = 30
    highs = [100.0 + i * 0.5 for i in range(n)]
    lows = [99.0 - i * 0.5 for i in range(n)]
    closes = [99.5 + i * 0.0 for i in range(n)]
    df = _ohlcv(highs, lows, closes)
    result = atr(df, period=14)
    # ATR after warmup should be >> 1
    assert result.iloc[-1] > 5.0


def test_atr_warmup_returns_nan() -> None:
    df = _ohlcv([101.0, 102.0], [99.0, 100.0], [100.0, 101.0])
    result = atr(df, period=14)
    assert pd.isna(result.iloc[0])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_indicators_atr.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ATR**

```python
# backend/app/indicators/atr.py
"""Wilder's ATR. True Range = max(high-low, |high-prev_close|, |low-prev_close|).
Smoothed with Wilder's RMA (ewm alpha=1/period)."""
import pandas as pd


def atr(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_indicators_atr.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/indicators/atr.py backend/tests/test_indicators_atr.py
git commit -m "feat(indicators): add ATR"
```

---

### Task 4: ADX indicator

**Files:**
- Create: `backend/app/indicators/adx.py`
- Test: `backend/tests/test_indicators_adx.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_indicators_adx.py
"""Tests for ADX + ±DI."""
import pandas as pd

from app.indicators.adx import adx


def _ohlcv(highs: list[float], lows: list[float], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [0] * len(closes),
    })


def test_adx_strong_uptrend_high_adx_plus_di_dominates() -> None:
    n = 60
    highs = [100.0 + i * 1.0 for i in range(n)]
    lows = [99.0 + i * 1.0 for i in range(n)]
    closes = [99.5 + i * 1.0 for i in range(n)]
    df = _ohlcv(highs, lows, closes)
    a, p, m = adx(df, period=14)
    assert a.iloc[-1] > 25.0
    assert p.iloc[-1] > m.iloc[-1]


def test_adx_strong_downtrend_minus_di_dominates() -> None:
    n = 60
    highs = [200.0 - i * 1.0 for i in range(n)]
    lows = [199.0 - i * 1.0 for i in range(n)]
    closes = [199.5 - i * 1.0 for i in range(n)]
    df = _ohlcv(highs, lows, closes)
    a, p, m = adx(df, period=14)
    assert a.iloc[-1] > 25.0
    assert m.iloc[-1] > p.iloc[-1]


def test_adx_returns_three_same_length_series() -> None:
    n = 30
    df = _ohlcv([101.0] * n, [99.0] * n, [100.0] * n)
    a, p, m = adx(df, period=14)
    assert len(a) == len(p) == len(m) == n
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_indicators_adx.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ADX**

```python
# backend/app/indicators/adx.py
"""Wilder's ADX with +DI / -DI. Standard formula."""
import pandas as pd

from app.indicators.atr import atr


def adx(ohlcv: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (adx, plus_di, minus_di)."""
    high = ohlcv["high"]
    low = ohlcv["low"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move.fillna(0.0)
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move.fillna(0.0)

    atr_series = atr(ohlcv, period)
    smooth_plus_dm = plus_dm.ewm(alpha=1.0 / period, adjust=False).mean()
    smooth_minus_dm = minus_dm.ewm(alpha=1.0 / period, adjust=False).mean()

    plus_di = 100.0 * (smooth_plus_dm / atr_series)
    minus_di = 100.0 * (smooth_minus_dm / atr_series)

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, pd.NA)
    adx_series = dx.ewm(alpha=1.0 / period, adjust=False).mean()

    return adx_series, plus_di, minus_di
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_indicators_adx.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/indicators/adx.py backend/tests/test_indicators_adx.py
git commit -m "feat(indicators): add ADX"
```

---

### Task 5: Volume Spike rule

**Files:**
- Create: `backend/app/rules/volume_rules.py`
- Test: `backend/tests/test_rules_volume.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_rules_volume.py
"""Tests for VolumeSpikeRule."""
import pandas as pd

from app.rules.volume_rules import VolumeSpikeRule


def _ohlcv(volumes: list[int]) -> pd.DataFrame:
    n = len(volumes)
    return pd.DataFrame({
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.0] * n,
        "volume": volumes,
    })


def test_volume_spike_true_when_today_above_threshold_x_avg() -> None:
    rule = VolumeSpikeRule()
    vols = [1000] * 20 + [3000]  # today = 3x avg
    df = _ohlcv(vols)
    assert rule.evaluate(df, {"window": 20, "threshold": 2.0}) is True


def test_volume_spike_false_when_today_below_threshold() -> None:
    rule = VolumeSpikeRule()
    vols = [1000] * 20 + [1500]
    df = _ohlcv(vols)
    assert rule.evaluate(df, {"window": 20, "threshold": 2.0}) is False


def test_volume_spike_kind_and_defaults() -> None:
    r = VolumeSpikeRule()
    assert r.kind == "volume_spike"
    assert r.default_params == {"window": 20, "threshold": 2.0}


def test_volume_spike_snapshot_has_ratio() -> None:
    rule = VolumeSpikeRule()
    vols = [1000] * 20 + [3000]
    df = _ohlcv(vols)
    snap = rule.snapshot(df, {"window": 20, "threshold": 2.0})
    assert "ratio" in snap and snap["ratio"] >= 2.9
    assert snap["window"] == 20
    assert snap["threshold"] == 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_rules_volume.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement VolumeSpikeRule**

```python
# backend/app/rules/volume_rules.py
"""Volume-based rules: VolumeSpikeRule."""
from typing import Any

import pandas as pd


class VolumeSpikeRule:
    kind = "volume_spike"
    default_params = {"window": 20, "threshold": 2.0}

    def _ratio(self, ohlcv: pd.DataFrame, window: int) -> float | None:
        if len(ohlcv) < window + 1:
            return None
        prior = ohlcv["volume"].iloc[-(window + 1):-1]
        avg = float(prior.mean())
        if avg <= 0:
            return None
        today = float(ohlcv["volume"].iloc[-1])
        return today / avg

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        window = int(params.get("window", 20))
        threshold = float(params.get("threshold", 2.0))
        r = self._ratio(ohlcv, window)
        return r is not None and r > threshold

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        window = int(params.get("window", 20))
        threshold = float(params.get("threshold", 2.0))
        r = self._ratio(ohlcv, window)
        return {
            "ratio": None if r is None else round(r, 3),
            "window": window,
            "threshold": threshold,
        }
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_rules_volume.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/rules/volume_rules.py backend/tests/test_rules_volume.py
git commit -m "feat(rules): add VolumeSpikeRule"
```

---

### Task 6: Breakout rule

**Files:**
- Create: `backend/app/rules/breakout_rules.py`
- Test: `backend/tests/test_rules_breakout.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_rules_breakout.py
"""Tests for BreakoutRule."""
import pandas as pd

from app.rules.breakout_rules import BreakoutRule


def _ohlcv_close(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": [0] * n,
    })


def test_breakout_true_when_close_exceeds_period_max_excluding_today() -> None:
    rule = BreakoutRule()
    closes = [100.0] * 20 + [105.0]  # today breaks above prior max(100)
    df = _ohlcv_close(closes)
    assert rule.evaluate(df, {"period": 20}) is True


def test_breakout_false_when_close_below_or_equal_to_period_max() -> None:
    rule = BreakoutRule()
    closes = [100.0] * 20 + [100.0]
    df = _ohlcv_close(closes)
    assert rule.evaluate(df, {"period": 20}) is False


def test_breakout_kind_and_defaults() -> None:
    r = BreakoutRule()
    assert r.kind == "breakout"
    assert r.default_params == {"period": 20}


def test_breakout_snapshot_has_prior_max() -> None:
    rule = BreakoutRule()
    closes = [100.0] * 20 + [105.0]
    df = _ohlcv_close(closes)
    snap = rule.snapshot(df, {"period": 20})
    assert snap["prior_max"] == 100.0
    assert snap["close"] == 105.0
    assert snap["period"] == 20
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_rules_breakout.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement BreakoutRule**

```python
# backend/app/rules/breakout_rules.py
"""Breakout rule: today's close breaks above prior `period` close max."""
from typing import Any

import pandas as pd


class BreakoutRule:
    kind = "breakout"
    default_params = {"period": 20}

    def _prior_max(self, ohlcv: pd.DataFrame, period: int) -> float | None:
        if len(ohlcv) < period + 1:
            return None
        return float(ohlcv["close"].iloc[-(period + 1):-1].max())

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 20))
        prior_max = self._prior_max(ohlcv, period)
        if prior_max is None:
            return False
        return float(ohlcv["close"].iloc[-1]) > prior_max

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 20))
        prior_max = self._prior_max(ohlcv, period)
        close = float(ohlcv["close"].iloc[-1])
        return {
            "close": round(close, 4),
            "prior_max": None if prior_max is None else round(prior_max, 4),
            "period": period,
        }
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_rules_breakout.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/rules/breakout_rules.py backend/tests/test_rules_breakout.py
git commit -m "feat(rules): add BreakoutRule"
```

---

### Task 7: MACD cross rules

**Files:**
- Create: `backend/app/rules/macd_rules.py`
- Test: `backend/tests/test_rules_macd.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_rules_macd.py
"""Tests for MACD cross rules."""
import pandas as pd

from app.rules.macd_rules import MacdBearishCrossRule, MacdBullishCrossRule


def test_macd_bullish_cross_kind() -> None:
    assert MacdBullishCrossRule().kind == "macd_bullish_cross"
    assert MacdBearishCrossRule().kind == "macd_bearish_cross"


def test_macd_bullish_cross_defaults() -> None:
    assert MacdBullishCrossRule().default_params == {"fast": 12, "slow": 26, "signal": 9}


def test_macd_bullish_cross_true_when_line_crosses_above_signal() -> None:
    """Build a series where MACD line crosses signal upward at the last bar."""
    # Long downtrend then sharp reversal — last bar should produce a bullish cross
    s = [100.0 - i * 1.0 for i in range(50)] + [50.0 + i * 5.0 for i in range(15)]
    df = pd.DataFrame({"close": s, "open": s, "high": s, "low": s, "volume": [0] * len(s)})
    rule = MacdBullishCrossRule()
    # We assert at least one bullish cross occurs in the final region by sweeping
    crossed = False
    for end in range(55, len(s) + 1):
        sub = df.iloc[:end]
        if rule.evaluate(sub, {}):
            crossed = True
            break
    assert crossed


def test_macd_bearish_cross_true_when_line_crosses_below_signal() -> None:
    s = [100.0 + i * 1.0 for i in range(50)] + [150.0 - i * 5.0 for i in range(15)]
    df = pd.DataFrame({"close": s, "open": s, "high": s, "low": s, "volume": [0] * len(s)})
    rule = MacdBearishCrossRule()
    crossed = False
    for end in range(55, len(s) + 1):
        sub = df.iloc[:end]
        if rule.evaluate(sub, {}):
            crossed = True
            break
    assert crossed


def test_macd_snapshot_has_line_signal_hist() -> None:
    s = [100.0 + i * 0.5 for i in range(60)]
    df = pd.DataFrame({"close": s, "open": s, "high": s, "low": s, "volume": [0] * len(s)})
    snap = MacdBullishCrossRule().snapshot(df, {})
    assert "line" in snap and "signal" in snap and "hist" in snap
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_rules_macd.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement MACD cross rules**

```python
# backend/app/rules/macd_rules.py
"""MACD bullish/bearish cross rules."""
from typing import Any

import pandas as pd

from app.indicators.macd import macd


def _last_two(ohlcv: pd.DataFrame, params: dict[str, Any]) -> tuple[float, float, float, float] | None:
    fast = int(params.get("fast", 12))
    slow = int(params.get("slow", 26))
    signal = int(params.get("signal", 9))
    line, sig, _hist = macd(ohlcv["close"], fast=fast, slow=slow, signal=signal)
    if len(line) < 2 or pd.isna(line.iloc[-2:]).any() or pd.isna(sig.iloc[-2:]).any():
        return None
    return float(line.iloc[-2]), float(line.iloc[-1]), float(sig.iloc[-2]), float(sig.iloc[-1])


def _snapshot(ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
    fast = int(params.get("fast", 12))
    slow = int(params.get("slow", 26))
    signal = int(params.get("signal", 9))
    line, sig, hist = macd(ohlcv["close"], fast=fast, slow=slow, signal=signal)
    last_line = line.iloc[-1]
    last_sig = sig.iloc[-1]
    last_hist = hist.iloc[-1]
    return {
        "line": None if pd.isna(last_line) else round(float(last_line), 4),
        "signal": None if pd.isna(last_sig) else round(float(last_sig), 4),
        "hist": None if pd.isna(last_hist) else round(float(last_hist), 4),
        "fast": fast,
        "slow": slow,
        "signal_period": signal,
    }


class MacdBullishCrossRule:
    kind = "macd_bullish_cross"
    default_params = {"fast": 12, "slow": 26, "signal": 9}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        pair = _last_two(ohlcv, params)
        if pair is None:
            return False
        line_prev, line_now, sig_prev, sig_now = pair
        return line_prev <= sig_prev and line_now > sig_now

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        return _snapshot(ohlcv, params)


class MacdBearishCrossRule:
    kind = "macd_bearish_cross"
    default_params = {"fast": 12, "slow": 26, "signal": 9}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        pair = _last_two(ohlcv, params)
        if pair is None:
            return False
        line_prev, line_now, sig_prev, sig_now = pair
        return line_prev >= sig_prev and line_now < sig_now

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        return _snapshot(ohlcv, params)
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_rules_macd.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/rules/macd_rules.py backend/tests/test_rules_macd.py
git commit -m "feat(rules): add MACD bullish/bearish cross rules"
```

---

### Task 8: Bollinger rules

**Files:**
- Create: `backend/app/rules/bollinger_rules.py`
- Test: `backend/tests/test_rules_bollinger.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_rules_bollinger.py
"""Tests for Bollinger squeeze and breakout rules."""
import pandas as pd

from app.rules.bollinger_rules import BollingerBreakoutRule, BollingerSqueezeRule


def test_bollinger_squeeze_kind_defaults() -> None:
    r = BollingerSqueezeRule()
    assert r.kind == "bollinger_squeeze"
    assert r.default_params == {"period": 20, "k": 2.0, "lookback": 50, "percentile": 0.20}


def test_bollinger_breakout_kind_defaults() -> None:
    r = BollingerBreakoutRule()
    assert r.kind == "bollinger_breakout"
    assert r.default_params == {"period": 20, "k": 2.0, "direction": "either"}


def test_bollinger_squeeze_true_when_width_in_low_percentile() -> None:
    """Volatile early then very calm late -> last bar's width should be in bottom 20%."""
    early = [100.0 + (i % 2) * 10.0 for i in range(80)]  # zigzag wide
    late = [105.0] * 20  # flat
    closes = early + late
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerSqueezeRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "lookback": 50, "percentile": 0.20}) is True


def test_bollinger_squeeze_false_when_width_normal() -> None:
    closes = [100.0 + (i % 2) * 5.0 for i in range(80)]
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerSqueezeRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "lookback": 50, "percentile": 0.20}) is False


def test_bollinger_breakout_upper_true_when_close_above_upper() -> None:
    closes = [100.0] * 30 + [200.0]  # huge spike on last bar
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerBreakoutRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "direction": "upper"}) is True


def test_bollinger_breakout_lower_true_when_close_below_lower() -> None:
    closes = [100.0] * 30 + [10.0]
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerBreakoutRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "direction": "lower"}) is True


def test_bollinger_breakout_either_matches_any_side() -> None:
    closes = [100.0] * 30 + [200.0]
    df = pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [0] * len(closes)})
    rule = BollingerBreakoutRule()
    assert rule.evaluate(df, {"period": 20, "k": 2.0, "direction": "either"}) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_rules_bollinger.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement Bollinger rules**

```python
# backend/app/rules/bollinger_rules.py
"""Bollinger Bands rules: squeeze (low-volatility) and breakout (close outside band)."""
from typing import Any

import pandas as pd

from app.indicators.bb import bb_width, bollinger


class BollingerSqueezeRule:
    kind = "bollinger_squeeze"
    default_params = {"period": 20, "k": 2.0, "lookback": 50, "percentile": 0.20}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 20))
        k = float(params.get("k", 2.0))
        lookback = int(params.get("lookback", 50))
        percentile = float(params.get("percentile", 0.20))
        widths = bb_width(ohlcv["close"], period=period, k=k)
        recent = widths.iloc[-lookback:].dropna()
        if len(recent) < lookback // 2:
            return False
        last = recent.iloc[-1]
        if pd.isna(last):
            return False
        threshold = recent.quantile(percentile)
        return float(last) <= float(threshold)

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 20))
        k = float(params.get("k", 2.0))
        lookback = int(params.get("lookback", 50))
        percentile = float(params.get("percentile", 0.20))
        widths = bb_width(ohlcv["close"], period=period, k=k)
        last = widths.iloc[-1]
        recent = widths.iloc[-lookback:].dropna()
        threshold = float(recent.quantile(percentile)) if len(recent) else None
        return {
            "width": None if pd.isna(last) else round(float(last), 6),
            "threshold": None if threshold is None else round(threshold, 6),
            "period": period,
            "k": k,
            "lookback": lookback,
            "percentile": percentile,
        }


class BollingerBreakoutRule:
    kind = "bollinger_breakout"
    default_params = {"period": 20, "k": 2.0, "direction": "either"}

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        period = int(params.get("period", 20))
        k = float(params.get("k", 2.0))
        direction = str(params.get("direction", "either"))
        upper, _mid, lower = bollinger(ohlcv["close"], period=period, k=k)
        u = upper.iloc[-1]
        l = lower.iloc[-1]
        c = float(ohlcv["close"].iloc[-1])
        if pd.isna(u) or pd.isna(l):
            return False
        if direction == "upper":
            return c > float(u)
        if direction == "lower":
            return c < float(l)
        return c > float(u) or c < float(l)

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        period = int(params.get("period", 20))
        k = float(params.get("k", 2.0))
        direction = str(params.get("direction", "either"))
        upper, _mid, lower = bollinger(ohlcv["close"], period=period, k=k)
        return {
            "close": round(float(ohlcv["close"].iloc[-1]), 4),
            "upper": None if pd.isna(upper.iloc[-1]) else round(float(upper.iloc[-1]), 4),
            "lower": None if pd.isna(lower.iloc[-1]) else round(float(lower.iloc[-1]), 4),
            "direction": direction,
            "period": period,
            "k": k,
        }
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_rules_bollinger.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/rules/bollinger_rules.py backend/tests/test_rules_bollinger.py
git commit -m "feat(rules): add Bollinger squeeze and breakout rules"
```

---

### Task 9: Register new rules in RULES registry + expand schema kind whitelist

**Files:**
- Modify: `backend/app/rules/registry.py`
- Modify: `backend/app/schemas/rule.py:7`

- [ ] **Step 1: Write failing test**

```python
# Append to backend/tests/test_rules_registry.py (or create if no equivalent test exists)
def test_registry_contains_all_3c_rules() -> None:
    from app.rules.registry import RULES
    expected = {
        "rsi_oversold", "rsi_overbought", "golden_cross", "death_cross",
        "volume_spike", "breakout",
        "macd_bullish_cross", "macd_bearish_cross",
        "bollinger_squeeze", "bollinger_breakout",
    }
    assert expected.issubset(set(RULES.keys()))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_rules_registry.py::test_registry_contains_all_3c_rules -v
```
Expected: FAIL with `AssertionError`

- [ ] **Step 3: Update registry**

Replace `backend/app/rules/registry.py` contents with:

```python
"""Registry mapping rule kind -> instance."""
from app.rules.base import Rule
from app.rules.bollinger_rules import BollingerBreakoutRule, BollingerSqueezeRule
from app.rules.breakout_rules import BreakoutRule
from app.rules.cross_rules import DeathCrossRule, GoldenCrossRule
from app.rules.macd_rules import MacdBearishCrossRule, MacdBullishCrossRule
from app.rules.rsi_rules import RsiOverboughtRule, RsiOversoldRule
from app.rules.volume_rules import VolumeSpikeRule

RULES: dict[str, Rule] = {
    r.kind: r
    for r in [
        RsiOversoldRule(),
        RsiOverboughtRule(),
        GoldenCrossRule(),
        DeathCrossRule(),
        VolumeSpikeRule(),
        BreakoutRule(),
        MacdBullishCrossRule(),
        MacdBearishCrossRule(),
        BollingerSqueezeRule(),
        BollingerBreakoutRule(),
    ]
}


def get_rule(kind: str) -> Rule:
    if kind not in RULES:
        raise KeyError(f"Unknown rule kind: {kind}")
    return RULES[kind]
```

- [ ] **Step 4: Update `_VALID_KINDS` in schema**

In `backend/app/schemas/rule.py`, replace line 7:

```python
_VALID_KINDS = {
    "rsi_oversold", "rsi_overbought", "golden_cross", "death_cross",
    "volume_spike", "breakout",
    "macd_bullish_cross", "macd_bearish_cross",
    "bollinger_squeeze", "bollinger_breakout",
    "composite",  # used by 3C-B for expression-based rules
}
```

- [ ] **Step 5: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_rules_registry.py -v
```
Expected: PASS (including new test)

- [ ] **Step 6: Commit**

```bash
git add backend/app/rules/registry.py backend/app/schemas/rule.py backend/tests/test_rules_registry.py
git commit -m "feat(rules): register 6 new atomic kinds in RULES + schema whitelist"
```

---

### Task 10: Rule catalog endpoint

**Files:**
- Create: `backend/app/api/rule_catalog.py`
- Modify: `backend/app/main.py` (router include)
- Test: `backend/tests/test_api_rule_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_api_rule_catalog.py
"""Tests for /api/rules/catalog endpoint."""
from fastapi.testclient import TestClient


def test_catalog_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/rules/catalog")
    assert resp.status_code == 401


def test_catalog_returns_all_kinds(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/api/rules/catalog", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    kinds = {entry["kind"] for entry in body}
    expected = {
        "rsi_oversold", "rsi_overbought", "golden_cross", "death_cross",
        "volume_spike", "breakout",
        "macd_bullish_cross", "macd_bearish_cross",
        "bollinger_squeeze", "bollinger_breakout",
    }
    assert expected.issubset(kinds)


def test_catalog_entry_shape(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/api/rules/catalog", headers=auth_headers)
    body = resp.json()
    for entry in body:
        assert "kind" in entry and "label" in entry and "default_params" in entry
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_api_rule_catalog.py -v
```
Expected: FAIL with 404 (route not registered)

- [ ] **Step 3: Implement catalog endpoint**

```python
# backend/app/api/rule_catalog.py
"""Rule catalog: enumerate available rule kinds for UI builder."""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models import User
from app.rules.registry import RULES

router = APIRouter(prefix="/api/rules", tags=["rules"])

_LABELS: dict[str, str] = {
    "rsi_oversold": "RSI Oversold",
    "rsi_overbought": "RSI Overbought",
    "golden_cross": "Golden Cross (SMA)",
    "death_cross": "Death Cross (SMA)",
    "volume_spike": "Volume Spike",
    "breakout": "Breakout (close > prior N-day max)",
    "macd_bullish_cross": "MACD Bullish Cross",
    "macd_bearish_cross": "MACD Bearish Cross",
    "bollinger_squeeze": "Bollinger Squeeze",
    "bollinger_breakout": "Bollinger Breakout",
}

_DESCRIPTIONS: dict[str, str] = {
    "rsi_oversold": "RSI(period) < threshold",
    "rsi_overbought": "RSI(period) > threshold",
    "golden_cross": "SMA(fast) crosses above SMA(slow)",
    "death_cross": "SMA(fast) crosses below SMA(slow)",
    "volume_spike": "Today's volume / SMA(volume, window) > threshold",
    "breakout": "Today's close > max(close[-period:-1])",
    "macd_bullish_cross": "MACD line crosses above signal line",
    "macd_bearish_cross": "MACD line crosses below signal line",
    "bollinger_squeeze": "Bollinger width in lowest percentile of recent lookback",
    "bollinger_breakout": "Close outside Bollinger band (upper/lower/either)",
}


@router.get("/catalog")
def get_catalog(_user: User = Depends(get_current_user)) -> list[dict]:
    out = []
    for kind, rule_obj in RULES.items():
        out.append({
            "kind": kind,
            "label": _LABELS.get(kind, kind),
            "description": _DESCRIPTIONS.get(kind, ""),
            "default_params": rule_obj.default_params,
        })
    return out
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py`, find the section where routers are included (e.g., `app.include_router(rules.router)`) and add:

```python
from app.api import rule_catalog
# ...
app.include_router(rule_catalog.router)
```

- [ ] **Step 5: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_api_rule_catalog.py -v
```
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/rule_catalog.py backend/app/main.py backend/tests/test_api_rule_catalog.py
git commit -m "feat(api): add /api/rules/catalog endpoint"
```

---

### Task 11: 3C-A smoke verification

**Files:** none (manual smoke)

- [ ] **Step 1: Run full backend suite**

```bash
cd backend && python -m pytest -q
```
Expected: All tests passing (~180+ original + ~25 new = ~205+)

- [ ] **Step 2: Manual API smoke (optional)**

Start the dev server and POST a new rule with one of the new kinds:

```bash
# In a separate shell:
curl -X POST http://localhost:8000/api/rules \
     -H "Content-Type: application/json" \
     -H "Cookie: session=..." \
     -d '{"kind":"volume_spike","params":{"window":20,"threshold":2.0},"enabled":true}'
```
Expected: 201 Created with new rule body.

- [ ] **Step 3: 3C-A summary commit**

```bash
git commit --allow-empty -m "chore: 3C-A complete (4 indicators + 6 atomic rules + catalog endpoint)"
```

---

# 3C-B — Composition schema + evaluator + preview API (backend only)

### Task 12: Add `Rule.expression` column + Alembic migration

**Files:**
- Modify: `backend/app/models/rule.py`
- Create: `backend/alembic/versions/<auto>_add_rule_expression.py`

- [ ] **Step 1: Add the field to the model**

In `backend/app/models/rule.py`, after the `params` field (line 26), add:

```python
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Generate the migration**

```bash
cd backend && alembic revision --autogenerate -m "add rule expression"
```

This creates `backend/alembic/versions/<hash>_add_rule_expression.py`. Verify its contents:

```python
def upgrade() -> None:
    with op.batch_alter_table("rules") as batch_op:
        batch_op.add_column(sa.Column("expression", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("rules") as batch_op:
        batch_op.drop_column("expression")
```

If autogenerate produced extra noise, hand-edit to match the above.

- [ ] **Step 3: Apply migration**

```bash
cd backend && alembic upgrade head
```
Expected: `Running upgrade ... -> <hash>, add rule expression`

- [ ] **Step 4: Verify by running existing tests**

```bash
cd backend && python -m pytest tests/test_api_rules.py -v
```
Expected: All existing rules tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/rule.py backend/alembic/versions/
git commit -m "feat(db): add nullable Rule.expression column"
```

---

### Task 13: Composition evaluator module

**Files:**
- Create: `backend/app/rules/composite.py`
- Test: `backend/tests/test_rules_composite.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_rules_composite.py
"""Tests for composite expression evaluator."""
import pandas as pd
import pytest

from app.rules.composite import (
    MAX_ATOMIC,
    MAX_DEPTH,
    evaluate_expression,
    snapshot_expression,
    validate_expression,
)


def _ohlcv_oversold() -> pd.DataFrame:
    closes = [100.0 - i * 0.5 for i in range(40)]
    return pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [1000] * 40})


def _ohlcv_overbought() -> pd.DataFrame:
    closes = [100.0 + i * 0.5 for i in range(40)]
    return pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [1000] * 40})


def test_atomic_evaluates_via_registry() -> None:
    expr = {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}}
    assert evaluate_expression(expr, _ohlcv_oversold()) is True
    assert evaluate_expression(expr, _ohlcv_overbought()) is False


def test_and_returns_true_only_if_all_children_true() -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "rsi_overbought", "params": {"period": 14, "threshold": 70}},
        ],
    }
    # oversold series: rsi_oversold=True, rsi_overbought=False -> AND=False
    assert evaluate_expression(expr, _ohlcv_oversold()) is False


def test_or_returns_true_if_any_child_true() -> None:
    expr = {
        "op": "or",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "rsi_overbought", "params": {"period": 14, "threshold": 70}},
        ],
    }
    assert evaluate_expression(expr, _ohlcv_oversold()) is True


def test_nested_and_or_evaluates_correctly() -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {
                "op": "or",
                "children": [
                    {"op": "atomic", "kind": "rsi_overbought", "params": {"period": 14, "threshold": 70}},
                    {"op": "atomic", "kind": "volume_spike", "params": {"window": 5, "threshold": 0.0}},
                ],
            },
        ],
    }
    # oversold=True AND (overbought=False OR volume_spike with threshold 0 = True)
    assert evaluate_expression(expr, _ohlcv_oversold()) is True


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="Unknown rule kind"):
        evaluate_expression({"op": "atomic", "kind": "totally_made_up", "params": {}}, _ohlcv_oversold())


def test_invalid_op_raises() -> None:
    with pytest.raises(ValueError, match="Invalid expression op"):
        evaluate_expression({"op": "xor", "children": []}, _ohlcv_oversold())


def test_validate_rejects_too_deep() -> None:
    """Build a tree with depth = MAX_DEPTH+1."""
    leaf = {"op": "atomic", "kind": "rsi_oversold", "params": {}}
    expr = leaf
    for _ in range(MAX_DEPTH + 1):
        expr = {"op": "and", "children": [expr]}
    with pytest.raises(ValueError, match="depth"):
        validate_expression(expr)


def test_validate_rejects_too_many_atomic() -> None:
    leaves = [{"op": "atomic", "kind": "rsi_oversold", "params": {}} for _ in range(MAX_ATOMIC + 1)]
    expr = {"op": "and", "children": leaves}
    with pytest.raises(ValueError, match="atomic"):
        validate_expression(expr)


def test_validate_accepts_well_formed() -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {}},
            {"op": "atomic", "kind": "volume_spike", "params": {}},
        ],
    }
    validate_expression(expr)  # should not raise


def test_snapshot_mirrors_tree_with_atomic_snapshots() -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "volume_spike", "params": {"window": 20, "threshold": 2.0}},
        ],
    }
    snap = snapshot_expression(expr, _ohlcv_oversold())
    assert snap["op"] == "and"
    assert len(snap["children"]) == 2
    assert snap["children"][0]["op"] == "atomic"
    assert "snapshot" in snap["children"][0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_rules_composite.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement composite module**

```python
# backend/app/rules/composite.py
"""Composite expression tree evaluator (AND/OR/atomic)."""
from typing import Any

import pandas as pd

from app.rules.registry import RULES

MAX_DEPTH = 5
MAX_ATOMIC = 8


def evaluate_expression(node: dict, ohlcv: pd.DataFrame) -> bool:
    """Walk tree; True iff the expression evaluates True on the last OHLCV bar."""
    op = node.get("op")
    if op == "atomic":
        kind = node.get("kind")
        if kind not in RULES:
            raise ValueError(f"Unknown rule kind in expression: {kind}")
        return RULES[kind].evaluate(ohlcv, node.get("params", {}))
    if op == "and":
        children = node.get("children") or []
        return all(evaluate_expression(c, ohlcv) for c in children)
    if op == "or":
        children = node.get("children") or []
        return any(evaluate_expression(c, ohlcv) for c in children)
    raise ValueError(f"Invalid expression op: {op!r}")


def snapshot_expression(node: dict, ohlcv: pd.DataFrame) -> dict:
    """Mirror the tree, attaching `.snapshot` and `.matched` to each atomic node."""
    op = node.get("op")
    if op == "atomic":
        kind = node.get("kind")
        params = node.get("params", {})
        if kind not in RULES:
            return {"op": "atomic", "kind": kind, "params": params, "error": "unknown_kind"}
        rule_obj = RULES[kind]
        try:
            matched = rule_obj.evaluate(ohlcv, params)
            snap = rule_obj.snapshot(ohlcv, params)
        except Exception as e:  # noqa: BLE001
            return {"op": "atomic", "kind": kind, "params": params, "error": str(e)}
        return {"op": "atomic", "kind": kind, "params": params, "matched": matched, "snapshot": snap}
    children = [snapshot_expression(c, ohlcv) for c in (node.get("children") or [])]
    matched = all(c.get("matched", False) for c in children) if op == "and" else any(c.get("matched", False) for c in children)
    return {"op": op, "matched": matched, "children": children}


def validate_expression(node: Any, *, max_depth: int = MAX_DEPTH, max_atomic: int = MAX_ATOMIC) -> None:
    """Raise ValueError if tree violates structural constraints."""
    if not isinstance(node, dict):
        raise ValueError("Expression node must be an object")

    def walk(n: Any, depth: int, counter: dict[str, int]) -> None:
        if depth > max_depth:
            raise ValueError(f"Expression depth exceeds {max_depth}")
        if not isinstance(n, dict):
            raise ValueError("Expression node must be an object")
        op = n.get("op")
        if op == "atomic":
            counter["atomic"] += 1
            if counter["atomic"] > max_atomic:
                raise ValueError(f"Too many atomic conditions (max {max_atomic})")
            kind = n.get("kind")
            if kind not in RULES:
                raise ValueError(f"Unknown rule kind: {kind}")
            return
        if op in ("and", "or"):
            children = n.get("children")
            if not isinstance(children, list) or not children:
                raise ValueError(f"'{op}' node must have non-empty children list")
            for c in children:
                walk(c, depth + 1, counter)
            return
        raise ValueError(f"Invalid expression op: {op!r}")

    walk(node, depth=1, counter={"atomic": 0})
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_rules_composite.py -v
```
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/rules/composite.py backend/tests/test_rules_composite.py
git commit -m "feat(rules): add composite expression evaluator (AND/OR/atomic)"
```

---

### Task 14: Wire composite evaluator into scan_service

**Files:**
- Modify: `backend/app/services/scan_service.py:154-203`

- [ ] **Step 1: Write failing test**

```python
# Append to backend/tests/test_scan_service.py (or create test_scan_service_composite.py)
"""Tests scan_service uses Rule.expression when present."""
import json

import pandas as pd
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Rule, Stock
from app.services.scan_service import scan_universe


def test_scan_uses_expression_when_present(db: Session) -> None:
    # Seed a stock + downward OHLCV (RSI oversold)
    s = Stock(ticker="EXPRTEST.MI", name="Test", index_code="FTSEMIB", exchange="BIT", currency="EUR")
    db.add(s)
    db.commit()
    db.refresh(s)
    from datetime import date, timedelta
    base = date(2025, 1, 1)
    closes = [100.0 - i * 0.5 for i in range(40)]
    for i, c in enumerate(closes):
        db.add(OhlcvDaily(stock_id=s.id, date=base + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1000))
    # Composite expression: RSI oversold AND volume_spike with threshold 0 (always true)
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "volume_spike", "params": {"window": 5, "threshold": 0.0}},
        ],
    }
    rule = Rule(
        kind="composite",
        params="{}",
        expression=json.dumps(expr),
        enabled=True,
    )
    db.add(rule)
    db.commit()
    result = scan_universe(db)
    assert result.alerts_fired >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_scan_service.py::test_scan_uses_expression_when_present -v
```
Expected: FAIL (current code ignores `expression`).

- [ ] **Step 3: Modify scan_service**

In `backend/app/services/scan_service.py`:

(a) At the top, after the existing imports add:

```python
from app.rules.composite import evaluate_expression, snapshot_expression
```

(b) Modify `_load_global_rules` to also include rules with non-null expression (kind unique already, but safe). It already returns all `watchlist_id IS NULL` rules — no change needed.

(c) In the per-stock loop (lines ~154-205), replace the rule-evaluation block to handle expression rules. Replace this block:

```python
        for kind in global_rules:
            resolved = _resolve_effective_rule(stock.id, kind, global_rules, tier2)
            if resolved is None:
                continue
            global_rule, eff_params = resolved
            rule_obj = RULES.get(kind)
            if rule_obj is None:
                continue
            try:
                new_eval = rule_obj.evaluate(ohlcv, eff_params)
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[scan] eval crashed for stock={stock.ticker} kind={kind}: {e}")
                continue
```

with:

```python
        for kind, candidate_global in global_rules.items():
            global_rule = candidate_global
            if not global_rule.enabled:
                continue
            # Composite (expression) rules: ignore Tier-2 overrides; expression is the source of truth
            if global_rule.expression:
                try:
                    expr = json.loads(global_rule.expression)
                    new_eval = evaluate_expression(expr, ohlcv)
                except Exception as e:  # noqa: BLE001
                    logger.exception(f"[scan] composite eval crashed stock={stock.ticker} rule_id={global_rule.id}: {e}")
                    continue
                eff_params = {}
                rule_obj = None  # signals "use composite snapshot below"
            else:
                resolved = _resolve_effective_rule(stock.id, kind, global_rules, tier2)
                if resolved is None:
                    continue
                global_rule, eff_params = resolved
                rule_obj = RULES.get(kind)
                if rule_obj is None:
                    continue
                try:
                    new_eval = rule_obj.evaluate(ohlcv, eff_params)
                except Exception as e:  # noqa: BLE001
                    logger.exception(f"[scan] eval crashed for stock={stock.ticker} kind={kind}: {e}")
                    continue
```

(d) Where snapshots are computed (the two `snapshot = rule_obj.snapshot(...)` lines), replace each with:

```python
                    if rule_obj is not None:
                        snapshot = rule_obj.snapshot(ohlcv, eff_params)
                    else:
                        snapshot = snapshot_expression(json.loads(global_rule.expression), ohlcv)
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_scan_service.py -v
```
Expected: All scan_service tests pass including the new one.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scan_service.py backend/tests/test_scan_service.py
git commit -m "feat(scan): evaluate Rule.expression when present (backward-compat with kind path)"
```

---

### Task 15: Extend rule schemas + API to accept expression

**Files:**
- Modify: `backend/app/schemas/rule.py`
- Modify: `backend/app/api/rules.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to backend/tests/test_api_rules.py
import json


def test_create_rule_with_expression(client, auth_headers):
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "volume_spike", "params": {"window": 20, "threshold": 2.0}},
        ],
    }
    resp = client.post(
        "/api/rules",
        headers=auth_headers,
        json={"kind": "composite", "params": {}, "enabled": True, "expression": expr},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["expression"] == expr


def test_create_rule_with_invalid_expression_returns_422(client, auth_headers):
    expr = {"op": "and", "children": [{"op": "atomic", "kind": "DOES_NOT_EXIST", "params": {}}]}
    resp = client.post(
        "/api/rules",
        headers=auth_headers,
        json={"kind": "composite", "params": {}, "enabled": True, "expression": expr},
    )
    assert resp.status_code == 422


def test_create_rule_with_too_deep_expression_returns_422(client, auth_headers):
    leaf = {"op": "atomic", "kind": "rsi_oversold", "params": {}}
    expr = leaf
    for _ in range(6):
        expr = {"op": "and", "children": [expr]}
    resp = client.post(
        "/api/rules",
        headers=auth_headers,
        json={"kind": "composite", "params": {}, "enabled": True, "expression": expr},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_api_rules.py -v -k "expression"
```
Expected: FAIL with 422 for the valid case (because schema doesn't know `expression` yet).

- [ ] **Step 3: Update schemas**

Replace `backend/app/schemas/rule.py` contents with:

```python
"""Rules request/response schemas."""
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_VALID_KINDS = {
    "rsi_oversold", "rsi_overbought", "golden_cross", "death_cross",
    "volume_spike", "breakout",
    "macd_bullish_cross", "macd_bearish_cross",
    "bollinger_squeeze", "bollinger_breakout",
    "composite",
}


class RuleBase(BaseModel):
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    expression: dict[str, Any] | None = None

    @field_validator("kind")
    @classmethod
    def kind_must_be_known(cls, v: str) -> str:
        if v not in _VALID_KINDS:
            raise ValueError(f"unknown rule kind: {v}")
        return v

    @model_validator(mode="after")
    def expression_structure_valid(self) -> "RuleBase":
        if self.expression is None:
            return self
        # Lazy import to avoid circular at module load
        from app.rules.composite import validate_expression
        try:
            validate_expression(self.expression)
        except ValueError as e:
            raise ValueError(str(e)) from e
        return self


class RuleCreate(RuleBase):
    watchlist_id: int | None = None


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    params: dict[str, Any] | None = None
    expression: dict[str, Any] | None = None

    @model_validator(mode="after")
    def expression_structure_valid(self) -> "RuleUpdate":
        if self.expression is None:
            return self
        from app.rules.composite import validate_expression
        try:
            validate_expression(self.expression)
        except ValueError as e:
            raise ValueError(str(e)) from e
        return self


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    watchlist_id: int | None
    kind: str
    params: dict[str, Any]
    enabled: bool
    expression: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("params", mode="before")
    @classmethod
    def parse_params(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, str):
            return json.loads(v) if v else {}
        return v or {}

    @field_validator("expression", mode="before")
    @classmethod
    def parse_expression(cls, v: Any) -> dict[str, Any] | None:
        if v is None:
            return None
        if isinstance(v, str):
            return json.loads(v) if v else None
        return v
```

- [ ] **Step 4: Update API to persist expression**

In `backend/app/api/rules.py`:

(a) Update `_to_out` to include expression:

```python
def _to_out(r: Rule) -> RuleOut:
    return RuleOut(
        id=r.id,
        watchlist_id=r.watchlist_id,
        kind=r.kind,
        params=json.loads(r.params or "{}"),
        enabled=r.enabled,
        expression=json.loads(r.expression) if r.expression else None,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
```

(b) Update `create_rule` to persist expression:

```python
    r = Rule(
        watchlist_id=payload.watchlist_id,
        kind=payload.kind,
        params=json.dumps(payload.params),
        enabled=payload.enabled,
        expression=json.dumps(payload.expression) if payload.expression else None,
    )
```

(c) Update `patch_rule` to allow expression updates. Add right before `db.commit()`:

```python
    if payload.expression is not None:
        r.expression = json.dumps(payload.expression)
```

- [ ] **Step 5: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_api_rules.py -v
```
Expected: All pass including the 3 new expression tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/rule.py backend/app/api/rules.py backend/tests/test_api_rules.py
git commit -m "feat(api): rules CRUD accepts and validates expression tree"
```

---

### Task 16: Rule preview endpoint

**Files:**
- Create: `backend/app/api/rule_preview.py`
- Modify: `backend/app/main.py` (router include)
- Test: `backend/tests/test_api_rule_preview.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_api_rule_preview.py
"""Tests for /api/rules/preview endpoint."""
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock


def _seed_oversold_stock(db: Session, ticker: str = "PVTEST.MI") -> int:
    s = Stock(ticker=ticker, name="Preview Test", index_code="FTSEMIB", exchange="BIT", currency="EUR")
    db.add(s)
    db.commit()
    db.refresh(s)
    base = date(2025, 1, 1)
    for i in range(40):
        c = 100.0 - i * 0.5
        db.add(OhlcvDaily(stock_id=s.id, date=base + timedelta(days=i),
                          open=c, high=c, low=c, close=c, volume=1000))
    db.commit()
    return s.id


def test_preview_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/rules/preview", json={"ticker": "X", "expression": {"op": "atomic", "kind": "rsi_oversold", "params": {}}})
    assert resp.status_code == 401


def test_preview_returns_matched_for_oversold(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    _seed_oversold_stock(db, "PVTEST.MI")
    resp = client.post(
        "/api/rules/preview",
        headers=auth_headers,
        json={
            "ticker": "PVTEST.MI",
            "expression": {"op": "atomic", "kind": "rsi_oversold",
                           "params": {"period": 14, "threshold": 30}},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is True
    assert body["snapshot"]["op"] == "atomic"
    assert "snapshot" in body["snapshot"]


def test_preview_unknown_ticker_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/rules/preview",
        headers=auth_headers,
        json={
            "ticker": "DOES_NOT_EXIST",
            "expression": {"op": "atomic", "kind": "rsi_oversold", "params": {}},
        },
    )
    assert resp.status_code == 404


def test_preview_invalid_expression_returns_422(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    _seed_oversold_stock(db, "PVTEST2.MI")
    resp = client.post(
        "/api/rules/preview",
        headers=auth_headers,
        json={
            "ticker": "PVTEST2.MI",
            "expression": {"op": "atomic", "kind": "DOES_NOT_EXIST", "params": {}},
        },
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_api_rule_preview.py -v
```
Expected: FAIL with 404 (route not registered).

- [ ] **Step 3: Implement preview endpoint**

```python
# backend/app/api/rule_preview.py
"""POST /api/rules/preview — evaluate an expression against a single stock's OHLCV."""
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import OhlcvDaily, Stock, User
from app.rules.composite import evaluate_expression, snapshot_expression, validate_expression

router = APIRouter(prefix="/api/rules", tags=["rules"])


class PreviewRequest(BaseModel):
    ticker: str
    expression: dict[str, Any]


class PreviewResponse(BaseModel):
    matched: bool
    snapshot: dict[str, Any]


def _load_ohlcv(db: Session, stock_id: int, limit: int = 252) -> pd.DataFrame | None:
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
    rows = rows[-limit:]
    return pd.DataFrame({
        "open": [float(r.open) for r in rows],
        "high": [float(r.high) for r in rows],
        "low": [float(r.low) for r in rows],
        "close": [float(r.close) for r in rows],
        "volume": [int(r.volume) for r in rows],
    })


@router.post(
    "/preview",
    response_model=PreviewResponse,
    dependencies=[Depends(require_json)],
)
def preview_rule(
    payload: PreviewRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PreviewResponse:
    try:
        validate_expression(payload.expression)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    stock = db.execute(select(Stock).where(Stock.ticker == payload.ticker)).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {payload.ticker}")
    ohlcv = _load_ohlcv(db, stock.id)
    if ohlcv is None or len(ohlcv) < 2:
        return PreviewResponse(matched=False, snapshot={"error": "insufficient data"})
    try:
        matched = evaluate_expression(payload.expression, ohlcv)
        snap = snapshot_expression(payload.expression, ohlcv)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PreviewResponse(matched=matched, snapshot=snap)
```

- [ ] **Step 4: Register router**

In `backend/app/main.py` add:

```python
from app.api import rule_preview
# ...
app.include_router(rule_preview.router)
```

- [ ] **Step 5: Verify tests pass**

```bash
cd backend && python -m pytest tests/test_api_rule_preview.py -v
```
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/rule_preview.py backend/app/main.py backend/tests/test_api_rule_preview.py
git commit -m "feat(api): add POST /api/rules/preview"
```

---

### Task 17: 3C-B summary commit + full backend suite

- [ ] **Step 1: Run full backend suite**

```bash
cd backend && python -m pytest -q
```
Expected: ~210+ passed.

- [ ] **Step 2: Summary commit**

```bash
git commit --allow-empty -m "chore: 3C-B complete (expression schema + evaluator + preview API)"
```

---

# 3C-C — Rule Editor UI (frontend only)

### Task 18: API client + types for rules

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify or create: `frontend/src/api/rules.ts`

- [ ] **Step 1: Add types**

In `frontend/src/api/types.ts`, add (next to other API types):

```typescript
export type RuleExpressionAtomic = {
  op: "atomic";
  kind: string;
  params: Record<string, unknown>;
};

export type RuleExpressionComposite = {
  op: "and" | "or";
  children: RuleExpressionNode[];
};

export type RuleExpressionNode = RuleExpressionAtomic | RuleExpressionComposite;

export interface Rule {
  id: number;
  watchlist_id: number | null;
  kind: string;
  params: Record<string, unknown>;
  enabled: boolean;
  expression: RuleExpressionNode | null;
  created_at: string;
  updated_at: string;
}

export interface RuleCatalogEntry {
  kind: string;
  label: string;
  description: string;
  default_params: Record<string, unknown>;
}

export interface RulePreviewSnapshotAtomic {
  op: "atomic";
  kind: string;
  params: Record<string, unknown>;
  matched?: boolean;
  snapshot?: Record<string, unknown>;
  error?: string;
}

export interface RulePreviewSnapshotComposite {
  op: "and" | "or";
  matched: boolean;
  children: RulePreviewSnapshotNode[];
}

export type RulePreviewSnapshotNode =
  | RulePreviewSnapshotAtomic
  | RulePreviewSnapshotComposite;

export interface RulePreviewResponse {
  matched: boolean;
  snapshot: RulePreviewSnapshotNode;
}
```

- [ ] **Step 2: Add API client functions**

Create or extend `frontend/src/api/rules.ts`:

```typescript
import { apiFetch } from "@/api/client";
import type {
  Rule,
  RuleCatalogEntry,
  RuleExpressionNode,
  RulePreviewResponse,
} from "@/api/types";

export interface RuleCreatePayload {
  watchlist_id?: number | null;
  kind: string;
  params?: Record<string, unknown>;
  enabled?: boolean;
  expression?: RuleExpressionNode | null;
}

export interface RuleUpdatePayload {
  enabled?: boolean;
  params?: Record<string, unknown>;
  expression?: RuleExpressionNode | null;
}

export async function listRules(watchlistId?: number): Promise<Rule[]> {
  const qs = watchlistId !== undefined ? `?watchlist_id=${watchlistId}` : "";
  return apiFetch<Rule[]>(`/api/rules${qs}`);
}

export async function createRule(payload: RuleCreatePayload): Promise<Rule> {
  return apiFetch<Rule>("/api/rules", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateRule(id: number, payload: RuleUpdatePayload): Promise<Rule> {
  return apiFetch<Rule>(`/api/rules/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function deleteRule(id: number): Promise<void> {
  await apiFetch<void>(`/api/rules/${id}`, { method: "DELETE" });
}

export async function getRuleCatalog(): Promise<RuleCatalogEntry[]> {
  return apiFetch<RuleCatalogEntry[]>("/api/rules/catalog");
}

export async function previewRule(
  ticker: string,
  expression: RuleExpressionNode,
): Promise<RulePreviewResponse> {
  return apiFetch<RulePreviewResponse>("/api/rules/preview", {
    method: "POST",
    body: JSON.stringify({ ticker, expression }),
  });
}
```

> **Note:** If `frontend/src/api/client.ts` exposes a different helper (e.g. `apiPost`, `apiGet`), adapt the calls. Check the file first.

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npm run build
```
Expected: build succeeds (no usages yet, just declarations).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/rules.ts
git commit -m "feat(rules-ui): add Rule types + API client functions"
```

---

### Task 19: TanStack Query hooks for rules

**Files:**
- Create: `frontend/src/hooks/useRules.ts`
- Create: `frontend/src/hooks/useRuleCatalog.ts`
- Create: `frontend/src/hooks/useRulePreview.ts`

- [ ] **Step 1: Implement useRules hook**

```typescript
// frontend/src/hooks/useRules.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type RuleCreatePayload,
  type RuleUpdatePayload,
  createRule,
  deleteRule,
  listRules,
  updateRule,
} from "@/api/rules";

export const RULES_KEY = (watchlistId?: number) => ["rules", watchlistId ?? "global"] as const;

export function useRules(watchlistId?: number) {
  return useQuery({
    queryKey: RULES_KEY(watchlistId),
    queryFn: () => listRules(watchlistId),
  });
}

export function useCreateRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RuleCreatePayload) => createRule(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });
}

export function useUpdateRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: RuleUpdatePayload }) =>
      updateRule(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });
}

export function useDeleteRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });
}
```

- [ ] **Step 2: Implement useRuleCatalog**

```typescript
// frontend/src/hooks/useRuleCatalog.ts
import { useQuery } from "@tanstack/react-query";

import { getRuleCatalog } from "@/api/rules";

export function useRuleCatalog() {
  return useQuery({
    queryKey: ["rules", "catalog"],
    queryFn: getRuleCatalog,
    staleTime: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 3: Implement useRulePreview**

```typescript
// frontend/src/hooks/useRulePreview.ts
import { useMutation } from "@tanstack/react-query";

import { previewRule } from "@/api/rules";
import type { RuleExpressionNode } from "@/api/types";

export function useRulePreview() {
  return useMutation({
    mutationFn: ({ ticker, expression }: { ticker: string; expression: RuleExpressionNode }) =>
      previewRule(ticker, expression),
  });
}
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useRules.ts frontend/src/hooks/useRuleCatalog.ts frontend/src/hooks/useRulePreview.ts
git commit -m "feat(rules-ui): add TanStack hooks (rules CRUD + catalog + preview)"
```

---

### Task 20: AtomicConditionForm component

**Files:**
- Create: `frontend/src/components/rules/AtomicConditionForm.tsx`

- [ ] **Step 1: Implement form**

```tsx
// frontend/src/components/rules/AtomicConditionForm.tsx
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useRuleCatalog } from "@/hooks/useRuleCatalog";
import type { RuleExpressionAtomic } from "@/api/types";

interface Props {
  value: RuleExpressionAtomic;
  onChange: (next: RuleExpressionAtomic) => void;
}

export function AtomicConditionForm({ value, onChange }: Props) {
  const catalog = useRuleCatalog();

  if (catalog.isLoading || !catalog.data) {
    return <div className="text-xs text-muted-foreground">Caricamento catalog…</div>;
  }

  const entry = catalog.data.find((c) => c.kind === value.kind);

  function handleKindChange(newKind: string) {
    const newEntry = catalog.data?.find((c) => c.kind === newKind);
    onChange({
      op: "atomic",
      kind: newKind,
      params: { ...(newEntry?.default_params ?? {}) },
    });
  }

  function handleParamChange(paramKey: string, raw: string) {
    const numeric = Number(raw);
    const next = Number.isFinite(numeric) && raw.trim() !== "" ? numeric : raw;
    onChange({
      op: "atomic",
      kind: value.kind,
      params: { ...value.params, [paramKey]: next },
    });
  }

  return (
    <div className="flex flex-col gap-2 p-3 border rounded-md bg-muted/30">
      <div className="flex items-center gap-2">
        <Label className="text-xs w-20">Condizione</Label>
        <Select value={value.kind} onValueChange={handleKindChange}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {catalog.data.map((c) => (
              <SelectItem key={c.kind} value={c.kind}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {entry && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(entry.default_params).map(([k, defVal]) => (
            <div key={k} className="flex items-center gap-1">
              <Label className="text-[11px] text-muted-foreground">{k}</Label>
              <Input
                className="h-7 text-xs w-24"
                value={String(value.params[k] ?? defVal)}
                onChange={(e) => handleParamChange(k, e.target.value)}
              />
            </div>
          ))}
        </div>
      )}
      {entry?.description && (
        <div className="text-[11px] text-muted-foreground">{entry.description}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/rules/AtomicConditionForm.tsx
git commit -m "feat(rules-ui): add AtomicConditionForm component"
```

---

### Task 21: ExpressionTree recursive component

**Files:**
- Create: `frontend/src/components/rules/ExpressionTree.tsx`

- [ ] **Step 1: Implement recursive tree**

```tsx
// frontend/src/components/rules/ExpressionTree.tsx
import { Plus, X } from "lucide-react";

import type {
  RuleExpressionAtomic,
  RuleExpressionComposite,
  RuleExpressionNode,
} from "@/api/types";
import { AtomicConditionForm } from "@/components/rules/AtomicConditionForm";
import { Button } from "@/components/ui/button";

const MAX_DEPTH = 5;
const MAX_ATOMIC = 8;

function countAtomic(node: RuleExpressionNode): number {
  if (node.op === "atomic") return 1;
  return node.children.reduce((sum, c) => sum + countAtomic(c), 0);
}

function defaultAtomic(): RuleExpressionAtomic {
  return { op: "atomic", kind: "rsi_oversold", params: { period: 14, threshold: 30 } };
}

interface Props {
  node: RuleExpressionNode;
  rootNode: RuleExpressionNode;
  depth: number;
  onChange: (next: RuleExpressionNode) => void;
  onRemove?: () => void;
}

export function ExpressionTree({ node, rootNode, depth, onChange, onRemove }: Props) {
  const totalAtomic = countAtomic(rootNode);
  const canAddChild = depth < MAX_DEPTH && totalAtomic < MAX_ATOMIC;

  if (node.op === "atomic") {
    return (
      <div className="relative flex items-start gap-1">
        <div className="flex-1">
          <AtomicConditionForm value={node} onChange={(next) => onChange(next)} />
        </div>
        {onRemove && (
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0 mt-3" onClick={onRemove}>
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    );
  }

  const composite = node as RuleExpressionComposite;

  function updateChild(idx: number, child: RuleExpressionNode) {
    const next = { ...composite, children: [...composite.children] };
    next.children[idx] = child;
    onChange(next);
  }

  function removeChild(idx: number) {
    const next = { ...composite, children: composite.children.filter((_, i) => i !== idx) };
    if (next.children.length === 0) {
      // Replace empty composite with a single atomic to avoid invalid trees
      onChange(defaultAtomic());
      return;
    }
    onChange(next);
  }

  function addAtomicChild() {
    const next = { ...composite, children: [...composite.children, defaultAtomic()] };
    onChange(next);
  }

  function addCompositeChild(op: "and" | "or") {
    const next = {
      ...composite,
      children: [...composite.children, { op, children: [defaultAtomic()] } as RuleExpressionComposite],
    };
    onChange(next);
  }

  function flipOp() {
    onChange({ ...composite, op: composite.op === "and" ? "or" : "and" });
  }

  return (
    <div className="border-l-2 border-primary/40 pl-3 py-2 relative">
      <div className="flex items-center gap-2 mb-2">
        <Button variant="outline" size="sm" className="h-6 text-xs px-2" onClick={flipOp}>
          {composite.op.toUpperCase()}
        </Button>
        {onRemove && (
          <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={onRemove}>
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {composite.children.map((child, idx) => (
          <ExpressionTree
            key={idx}
            node={child}
            rootNode={rootNode}
            depth={depth + 1}
            onChange={(next) => updateChild(idx, next)}
            onRemove={() => removeChild(idx)}
          />
        ))}
      </div>
      <div className="flex gap-2 mt-2">
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={addAtomicChild}
          disabled={!canAddChild}
        >
          <Plus className="h-3 w-3 mr-1" /> Condizione
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => addCompositeChild("and")}
          disabled={!canAddChild}
        >
          <Plus className="h-3 w-3 mr-1" /> AND
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => addCompositeChild("or")}
          disabled={!canAddChild}
        >
          <Plus className="h-3 w-3 mr-1" /> OR
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/rules/ExpressionTree.tsx
git commit -m "feat(rules-ui): add ExpressionTree recursive component"
```

---

### Task 22: ExpressionPreview component

**Files:**
- Create: `frontend/src/components/rules/ExpressionPreview.tsx`

- [ ] **Step 1: Implement preview**

```tsx
// frontend/src/components/rules/ExpressionPreview.tsx
import { useState } from "react";

import type { RuleExpressionNode } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRulePreview } from "@/hooks/useRulePreview";

interface Props {
  expression: RuleExpressionNode;
}

export function ExpressionPreview({ expression }: Props) {
  const [ticker, setTicker] = useState("AAPL");
  const preview = useRulePreview();

  function handleTest() {
    preview.mutate({ ticker: ticker.trim().toUpperCase(), expression });
  }

  return (
    <div className="flex flex-col gap-2 p-3 border rounded-md bg-muted/20">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Anteprima su ticker:</span>
        <Input
          className="h-7 w-24 text-sm"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
        />
        <Button size="sm" className="h-7" onClick={handleTest} disabled={preview.isPending}>
          {preview.isPending ? "Test…" : "Test"}
        </Button>
      </div>
      {preview.error && (
        <div className="text-xs text-red-600">
          {preview.error instanceof Error ? preview.error.message : "Errore"}
        </div>
      )}
      {preview.data && (
        <div className="text-xs">
          <div className="font-semibold">
            Risultato: {preview.data.matched ? "✓ Scatta" : "✗ Non scatta"}
          </div>
          <pre className="mt-1 p-2 bg-background border rounded text-[10px] overflow-auto max-h-40">
            {JSON.stringify(preview.data.snapshot, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/rules/ExpressionPreview.tsx
git commit -m "feat(rules-ui): add ExpressionPreview component"
```

---

### Task 23: RuleEditorDialog modal

**Files:**
- Create: `frontend/src/components/rules/RuleEditorDialog.tsx`

- [ ] **Step 1: Implement modal**

```tsx
// frontend/src/components/rules/RuleEditorDialog.tsx
import { useState } from "react";

import type { Rule, RuleExpressionNode } from "@/api/types";
import { ExpressionPreview } from "@/components/rules/ExpressionPreview";
import { ExpressionTree } from "@/components/rules/ExpressionTree";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useCreateRule, useUpdateRule } from "@/hooks/useRules";

const DEFAULT_EXPRESSION: RuleExpressionNode = {
  op: "and",
  children: [
    { op: "atomic", kind: "rsi_oversold", params: { period: 14, threshold: 30 } },
  ],
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rule: Rule | null;
}

export function RuleEditorDialog({ open, onOpenChange, rule }: Props) {
  const isEdit = rule !== null;
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [expression, setExpression] = useState<RuleExpressionNode>(
    rule?.expression ?? DEFAULT_EXPRESSION,
  );
  const createMut = useCreateRule();
  const updateMut = useUpdateRule();
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setError(null);
    try {
      if (isEdit && rule) {
        await updateMut.mutateAsync({
          id: rule.id,
          payload: { enabled, expression },
        });
      } else {
        await createMut.mutateAsync({
          watchlist_id: null,
          kind: "composite",
          params: {},
          enabled,
          expression,
        });
      }
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore salvataggio");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Modifica regola" : "Nuova regola"}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Label className="text-sm">Attiva</Label>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
          <div>
            <Label className="text-sm font-semibold">Condizioni</Label>
            <div className="mt-2">
              <ExpressionTree
                node={expression}
                rootNode={expression}
                depth={1}
                onChange={setExpression}
              />
            </div>
          </div>
          <ExpressionPreview expression={expression} />
          {error && <div className="text-sm text-red-600">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Annulla
          </Button>
          <Button onClick={handleSave} disabled={createMut.isPending || updateMut.isPending}>
            Salva
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

> **Note:** This assumes shadcn `Dialog`, `Switch`, `Label` components exist. If `Switch` is missing, run `npx shadcn-ui@latest add switch dialog label` (use the same shadcn version already in the repo — check `components.json`).

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: build succeeds. If it fails on missing `Switch` import, install via shadcn before retrying.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/rules/RuleEditorDialog.tsx frontend/src/components/ui/
git commit -m "feat(rules-ui): add RuleEditorDialog modal"
```

---

### Task 24: RulesTable component

**Files:**
- Create: `frontend/src/components/rules/RulesTable.tsx`

- [ ] **Step 1: Implement table**

```tsx
// frontend/src/components/rules/RulesTable.tsx
import { Pencil, Trash2 } from "lucide-react";

import type { Rule, RuleExpressionNode } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useDeleteRule, useUpdateRule } from "@/hooks/useRules";

function describeExpression(expr: RuleExpressionNode | null, kind: string): string {
  if (expr === null) return kind;
  if (expr.op === "atomic") return expr.kind;
  return `${expr.op.toUpperCase()} (${expr.children.length} cond.)`;
}

interface Props {
  rules: Rule[];
  onEdit: (rule: Rule) => void;
}

export function RulesTable({ rules, onEdit }: Props) {
  const updateMut = useUpdateRule();
  const deleteMut = useDeleteRule();

  if (rules.length === 0) {
    return (
      <div className="text-sm text-muted-foreground p-6 text-center border rounded-md">
        Nessuna regola configurata. Clicca "+ Nuova regola" per crearne una.
      </div>
    );
  }

  return (
    <table className="w-full text-sm border rounded-md">
      <thead className="bg-muted/50 text-xs">
        <tr>
          <th className="px-3 py-2 text-left">Stato</th>
          <th className="px-3 py-2 text-left">Tipo</th>
          <th className="px-3 py-2 text-left">Condizioni</th>
          <th className="px-3 py-2 text-right">Azioni</th>
        </tr>
      </thead>
      <tbody>
        {rules.map((r) => (
          <tr key={r.id} className="border-t">
            <td className="px-3 py-2">
              <Switch
                checked={r.enabled}
                onCheckedChange={(checked) =>
                  updateMut.mutate({ id: r.id, payload: { enabled: checked } })
                }
              />
            </td>
            <td className="px-3 py-2">{r.kind}</td>
            <td className="px-3 py-2 text-xs text-muted-foreground">
              {describeExpression(r.expression, r.kind)}
            </td>
            <td className="px-3 py-2 text-right">
              <Button variant="ghost" size="sm" onClick={() => onEdit(r)}>
                <Pencil className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  if (confirm("Eliminare questa regola?")) {
                    deleteMut.mutate(r.id);
                  }
                }}
              >
                <Trash2 className="h-4 w-4 text-red-600" />
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/rules/RulesTable.tsx
git commit -m "feat(rules-ui): add RulesTable component"
```

---

### Task 25: RulesPage orchestrator + routing + sidebar enable

**Files:**
- Create: `frontend/src/pages/RulesPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx:23`

- [ ] **Step 1: Implement RulesPage**

```tsx
// frontend/src/pages/RulesPage.tsx
import { Plus } from "lucide-react";
import { useState } from "react";

import type { Rule } from "@/api/types";
import { RuleEditorDialog } from "@/components/rules/RuleEditorDialog";
import { RulesTable } from "@/components/rules/RulesTable";
import { Button } from "@/components/ui/button";
import { useRules } from "@/hooks/useRules";

export default function RulesPage() {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Rule | null>(null);
  const rules = useRules();

  function handleNew() {
    setEditing(null);
    setOpen(true);
  }

  function handleEdit(rule: Rule) {
    setEditing(rule);
    setOpen(true);
  }

  return (
    <div className="flex flex-col gap-4 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Regole alert</h2>
          <p className="text-sm text-muted-foreground">
            Componi condizioni AND/OR e visualizza in anteprima i match su uno stock.
          </p>
        </div>
        <Button onClick={handleNew}>
          <Plus className="h-4 w-4 mr-2" /> Nuova regola
        </Button>
      </div>
      {rules.isLoading ? (
        <div className="text-sm text-muted-foreground">Caricamento…</div>
      ) : rules.error ? (
        <div className="text-sm text-red-600">
          Errore: {rules.error instanceof Error ? rules.error.message : "sconosciuto"}
        </div>
      ) : (
        <RulesTable rules={rules.data ?? []} onEdit={handleEdit} />
      )}
      <RuleEditorDialog open={open} onOpenChange={setOpen} rule={editing} />
    </div>
  );
}
```

- [ ] **Step 2: Add route in App.tsx**

In `frontend/src/App.tsx`, add the import and route:

```tsx
import RulesPage from "@/pages/RulesPage";
```

then inside the protected `<Route>` block (after the `/stocks/:ticker` line):

```tsx
        <Route path="/rules" element={<RulesPage />} />
```

- [ ] **Step 3: Enable sidebar entry**

In `frontend/src/components/Layout.tsx`, line 23, change:

```tsx
  { to: "/rules", label: "Regole", icon: Sliders, enabled: false },
```

to:

```tsx
  { to: "/rules", label: "Regole", icon: Sliders, enabled: true },
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/RulesPage.tsx frontend/src/App.tsx frontend/src/components/Layout.tsx
git commit -m "feat(rules-ui): mount /rules page and enable sidebar entry"
```

---

### Task 26: 3C-C smoke + ARCHITECTURE doc update

**Files:**
- Modify: `ARCHITECTURE.md` (append a Fase 3C section)

- [ ] **Step 1: Manual E2E smoke**

Start backend + frontend dev servers. In browser:

1. Login → click "Regole" in sidebar → page loads, shows existing rules (or empty)
2. Click "+ Nuova regola" → modal opens with default AND tree containing 1 RSI Oversold condition
3. Click "+ Condizione" inside the AND → second atomic appears
4. Change one condition's kind to `volume_spike`
5. Set ticker to a known stock (e.g. `AAPL`), click "Test" → preview shows `{matched, snapshot}` JSON
6. Click "Salva" → modal closes, table refreshes with new row
7. Toggle the switch to disable → row updates without errors
8. Click delete (trash) → confirm → row removed

- [ ] **Step 2: Update ARCHITECTURE.md**

Append a new section to `ARCHITECTURE.md`:

```markdown
## Fase 3C — Indicatori avanzati + regole composite + Rule Editor (2026-05-02)

### Backend additions

- 4 nuovi indicatori: MACD, Bollinger Bands, ATR, ADX (in `app/indicators/`)
- 6 nuove regole atomiche: volume_spike, breakout, macd_bullish_cross, macd_bearish_cross, bollinger_squeeze, bollinger_breakout
- `Rule.expression` (Text nullable): se valorizzato, prende precedenza su `kind`+`params`
- `app/rules/composite.py`: `evaluate_expression`, `snapshot_expression`, `validate_expression` (max depth 5, max 8 atomic)
- Endpoints: `GET /api/rules/catalog`, `POST /api/rules/preview`
- `scan_service` instrada le regole con `expression` non-null al composite evaluator (backward-compat preservato)

### Frontend additions

- Nuova pagina `/rules` con `RulesPage` orchestrator
- Componenti in `components/rules/`: `RulesTable`, `RuleEditorDialog`, `ExpressionTree`, `AtomicConditionForm`, `ExpressionPreview`
- Hooks: `useRules`, `useRuleCatalog`, `useRulePreview`
- Sidebar entry "Regole" attivata
```

- [ ] **Step 3: Commit + push**

```bash
git add ARCHITECTURE.md
git commit -m "docs: ARCHITECTURE updated with Fase 3C summary"
git push
```

- [ ] **Step 4: 3C-C summary commit**

```bash
git commit --allow-empty -m "chore: 3C-C complete (Rule Editor UI shipped)"
```

---

## Self-Review Notes

**Spec coverage:** every spec section maps to tasks:
- §5 schema → Task 12
- §6 indicators → Tasks 1–4
- §7 atomic rules → Tasks 5–8 + Task 9 registry
- §8 composite evaluator + scan_service wiring → Tasks 13–14
- §9 API surface → Tasks 10 (catalog), 15 (CRUD with expression), 16 (preview)
- §10 frontend → Tasks 18–25
- §11 decomposition (3C-A/B/C) → mirrored as section headers
- §12 error handling → covered by tests (422 for invalid expression, 404 for ticker, "insufficient data" snapshot)
- §13 testing → ~30 new tests across Tasks 1–16
- §14 DoD → Task 11 (3C-A), 17 (3C-B), 26 (3C-C)

**Type consistency check:** `RuleExpressionNode`, `RuleExpressionAtomic`, `RuleExpressionComposite` declared once in Task 18 and used identically in Tasks 19–25. Backend `evaluate_expression`, `snapshot_expression`, `validate_expression`, `MAX_DEPTH=5`, `MAX_ATOMIC=8` declared in Task 13 and used identically in Tasks 14–16.

**Placeholder scan:** none found; every step has concrete code or commands.
