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
