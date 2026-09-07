"""The confluence endpoint carried Forza under the legacy name.

`confluence_service` reads `$.strength` from the alert snapshot, falling back
to `$.confidence` for pre-split rows — so the value flowing through IS Forza.
It was then called `confidence` all the way out to the wire.

The frontend had already been written for the migration: `alerts.ts` declares
`strength?: number` as "the new primary" with `confidence` as "the legacy
fallback (transitional alias)", and `AlertsInsightCard` reads
`top.strength ?? top.confidence`. Since the field was never sent, that
expression sat permanently on its fallback while its comment asserted the
migration had happened.

CLAUDE.md records that `confidence` is a transitional alias of `strength`
being retired. So the fix is to finish the rename on the wire, not to delete
the frontend's expectation: emit `strength` as the primary and keep
`confidence` beside it so nothing reading the old name breaks.
"""
from app.schemas.confluence import ConfluenceComponentOut
from app.services.confluence_service import ConfluenceComponent


def _component(value: float = 72.5) -> ConfluenceComponent:
    return ConfluenceComponent(
        alert_id=1, rule_kind="signal:sr_flip", signal_name="sr_flip",
        confidence=value, tone="bull", horizon="medium", signal_date="2026-06-01",
    )


def test_the_component_exposes_forza_under_its_real_name():
    assert _component(72.5).strength == 72.5


def test_the_serialized_payload_carries_strength():
    out = ConfluenceComponentOut.model_validate(_component(72.5))
    assert out.strength == 72.5


def test_the_legacy_alias_is_still_sent_so_old_readers_keep_working():
    # Same number under both names — this is an alias, not a second metric.
    out = ConfluenceComponentOut.model_validate(_component(72.5))
    assert out.confidence == out.strength


def test_both_names_survive_a_round_trip_through_json():
    # Pydantic drops undeclared attributes, which is exactly how `strength`
    # went missing before: the dataclass had no such attribute to read.
    payload = ConfluenceComponentOut.model_validate(_component(64.0)).model_dump()
    assert payload["strength"] == 64.0
    assert payload["confidence"] == 64.0
