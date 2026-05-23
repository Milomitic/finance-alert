"""Active signal detectors for the current phase."""
from app.signals.detectors.adx_confirmation import AdxConfirmation
from app.signals.detectors.analyst_momentum import AnalystMomentum
from app.signals.detectors.candle_reversal import CandleReversal
from app.signals.detectors.chart_pattern import ChartPattern
from app.signals.detectors.gap_and_go import GapAndGo
from app.signals.detectors.high52_momentum import High52Momentum
from app.signals.detectors.insider_buy import InsiderBuy
from app.signals.detectors.macd_divergence import MacdDivergence
from app.signals.detectors.oversold_reversal import OversoldReversal
from app.signals.detectors.pead import Pead
from app.signals.detectors.rsi_divergence import RsiDivergence
from app.signals.detectors.squeeze_expansion import SqueezeExpansion
from app.signals.detectors.sr_flip import SRFlip
from app.signals.detectors.structure_break import StructureBreak
from app.signals.detectors.trend_pullback import TrendPullback
from app.signals.detectors.volume_breakout import VolumeBreakout

DETECTORS = [
    VolumeBreakout(),
    TrendPullback(),
    RsiDivergence(),
    SqueezeExpansion(),
    High52Momentum(),
    OversoldReversal(),
    SRFlip(),
    StructureBreak(),
    MacdDivergence(),
    GapAndGo(),
    AdxConfirmation(),
    CandleReversal(),
    Pead(),
    AnalystMomentum(),
    InsiderBuy(),
    ChartPattern(),
]
