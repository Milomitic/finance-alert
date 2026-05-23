"""Active signal detectors for the current phase."""
from app.signals.detectors.trend_pullback import TrendPullback
from app.signals.detectors.volume_breakout import VolumeBreakout

DETECTORS = [VolumeBreakout(), TrendPullback()]
