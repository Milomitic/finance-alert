"""Registry mapping rule kind -> instance."""
from app.rules.base import Rule
from app.rules.cross_rules import DeathCrossRule, GoldenCrossRule
from app.rules.rsi_rules import RsiOverboughtRule, RsiOversoldRule

RULES: dict[str, Rule] = {
    r.kind: r
    for r in [RsiOversoldRule(), RsiOverboughtRule(), GoldenCrossRule(), DeathCrossRule()]
}


def get_rule(kind: str) -> Rule:
    if kind not in RULES:
        raise KeyError(f"Unknown rule kind: {kind}")
    return RULES[kind]
