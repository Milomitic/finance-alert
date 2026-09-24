"""Active signal detectors for the current phase."""
from app.signals.detectors.adx_confirmation import AdxConfirmation
from app.signals.detectors.analyst_momentum import AnalystMomentum
from app.signals.detectors.candle_reversal import CandleReversal
from app.signals.detectors.chart_pattern import ChartPattern
from app.signals.detectors.gap_and_go import GapAndGo
from app.signals.detectors.hidden_divergence import HiddenDivergence
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
    HiddenDivergence(),
]


#: Detector che GIRANO ma non EMETTONO un alert proprio (2026-09-24).
#:
#: `adx_confirmation` e' anti-skill di direzione: 11.940 segnali nel replay
#: decennale, skill -0,051 R (t -3,21, q 0,02 dopo Benjamini-Hochberg su 22
#: celle), hit market-neutral 47,9%, e resta negativo anche con lo stop largo.
#: Non va INVERTITO — due punti sotto la moneta non sono un segnale da giocare
#: al contrario — ma non merita un alert. `docs/superpowers/specs/
#: 2026-09-23-studio-taratura-e-ml-findings.md` §5.
#:
#: ⚠️ Resta nell'elenco sopra di proposito, e il filtro sta nello SCAN, non nel
#: runner: gli studi rigiocano `detect_signals` e devono poterlo ancora
#: misurare, e l'evento su cui scatta (`adx_trend`) continua a comparire come
#: CONFERMA nella catena degli altri detector (`chain_enrichment`), che e' dove
#: lo studio dice che ha ancora un senso. Gli alert gia' emessi restano: sono
#: storia, e il magazzino degli esiti li misura.
NON_EMESSI: frozenset[str] = frozenset({"adx_confirmation"})
