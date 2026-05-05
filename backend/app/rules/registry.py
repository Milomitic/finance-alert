"""Registry mapping rule kind -> instance."""
from app.rules.adx_rules import AdxBearishTrendRule, AdxBullishTrendRule
from app.rules.base import Rule
from app.rules.bollinger_rules import BollingerBreakoutRule
from app.rules.breakout_rules import BreakoutRule
from app.rules.cross_rules import DeathCrossRule, GoldenCrossRule
from app.rules.gap_rules import GapDownRule, GapUpRule
from app.rules.macd_rules import MacdBearishCrossRule, MacdBullishCrossRule
from app.rules.mean_reversion_rules import (
    MeanReversionLongRule,
    MeanReversionShortRule,
)
from app.rules.rsi_rules import RsiOverboughtRule, RsiOversoldRule
from app.rules.volume_rules import VolumeSpikeRule

# bollinger_squeeze was retired — see Alembic migration
# `47c2035665bd_drop_bollinger_squeeze_rules`. The category was replaced by
# the more actionable desk/trader signals below: ADX trend strength, gap
# up/down, mean reversion. BollingerBreakoutRule stays because it's a
# directional signal (long/short on band breakouts).
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
        BollingerBreakoutRule(),
        AdxBullishTrendRule(),
        AdxBearishTrendRule(),
        GapUpRule(),
        GapDownRule(),
        MeanReversionLongRule(),
        MeanReversionShortRule(),
    ]
}


def get_rule(kind: str) -> Rule:
    if kind not in RULES:
        raise KeyError(f"Unknown rule kind: {kind}")
    return RULES[kind]
