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
    "bollinger_breakout": "Bollinger Breakout",
    # New desk/trader signals (replaced bollinger_squeeze)
    "adx_bullish_trend": "ADX Trend Forte ↑",
    "adx_bearish_trend": "ADX Trend Forte ↓",
    "gap_up": "Gap Up",
    "gap_down": "Gap Down",
    "mean_reversion_long": "Mean Reversion (long)",
    "mean_reversion_short": "Mean Reversion (short)",
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
    "bollinger_breakout": "Close outside Bollinger band (upper/lower/either)",
    "adx_bullish_trend": "ADX > threshold AND +DI > -DI (uptrend forte)",
    "adx_bearish_trend": "ADX > threshold AND -DI > +DI (downtrend forte)",
    "gap_up": "Open ≥ prev_close × (1 + threshold_pct) (gap rialzista)",
    "gap_down": "Open ≤ prev_close × (1 − threshold_pct) (gap ribassista)",
    "mean_reversion_long":
        "Close ≥ N σ sotto SMA(period) (estensione anomala al ribasso → bounce atteso)",
    "mean_reversion_short":
        "Close ≥ N σ sopra SMA(period) (estensione anomala al rialzo → fade atteso)",
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
