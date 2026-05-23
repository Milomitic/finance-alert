"""Continuous per-stock technical score.

Five price dimensions (trend, momentum, structure, volume) computed per stock,
plus a cross-sectional relative-strength percentile assigned in a finalize pass.
Persisted in technical_scores. Complementary to the fundamental StockScore.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.indicators.adx import adx
from app.indicators.ema import ema
from app.indicators.macd import macd
from app.indicators.rsi import rsi
from app.models import TechnicalScore

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
    except Exception:
        pass
    return _clamp(0.5 + (t01 - 0.5) * (0.6 + 0.4 * adx_w)) * 100.0


def _momentum(close: pd.Series) -> float:
    n = len(close)
    price = float(close.iloc[-1])
    r = float(rsi(close, 14).dropna().iloc[-1]) if n > 15 else 50.0
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
    except Exception:
        return None


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
    now = datetime.now(timezone.utc)
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
        composite = sum(_WEIGHTS[k] * dims[k] for k in _WEIGHTS)
        posture = "Forte" if composite >= 66 else "Neutro" if composite >= 40 else "Debole"
        db.merge(TechnicalScore(
            stock_id=sid,
            composite=round(composite, 1),
            trend=round(dims["trend"], 1),
            momentum=round(dims["momentum"], 1),
            structure=round(dims["structure"], 1),
            volume=round(dims["volume"], 1),
            rel_strength=round(rel, 1),
            signals=None,
            posture=posture,
            computed_at=now,
            breakdown=json.dumps({
                "dims": {k: round(dims[k], 1) for k in dims},
                "blended_return": p.get("blended_return"),
            }),
        ))
        count += 1
    return count
