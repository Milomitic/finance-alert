"""Tests that signal alerts (rule_id=None, signal_name set) are counted in
dashboard stats and correctly labelled in the Telegram digest.

Phase 1c Task 3: surfaces that previously used an INNER join on Rule
(dropping NULL-rule rows) must include signal alerts and label their kind
as "signal:<name>", not NULL / "unknown".
"""
import json
from datetime import UTC, date, datetime, timedelta

from app.models import Alert, Stock
from app.services import stats_service
from app.services.notifier_service import build_digest_message


def _signal_alert(db, ticker="SIGSURF", d=date(2026, 5, 1)):
    s = Stock(ticker=ticker, exchange="NASDAQ", name="Sig Surf", country="US")
    db.add(s)
    db.flush()
    a = Alert(
        stock_id=s.id,
        trigger_price=10.0,
        signal_date=d,
        signal_name="volume_breakout",
        snapshot=json.dumps({"tone": "bull", "confidence": 80, "chain": []}),
    )
    # triggered_at defaults to now() via server_default; set it explicitly so
    # it lands inside the 30-day window used by get_alerts_by_day.
    a.triggered_at = datetime.now(UTC) - timedelta(hours=1)
    db.add(a)
    db.commit()
    return s, a


# ---------------------------------------------------------------------------
# stats_service: get_alerts_by_day
# ---------------------------------------------------------------------------

def test_alerts_by_day_counts_signal_alerts(db):
    _signal_alert(db)
    points = stats_service.get_alerts_by_day(db)   # signature: (db, days=30)
    total = sum(p.count for p in points)
    assert total >= 1

    kinds = set()
    for p in points:
        kinds.update(p.by_kind.keys())
    assert any(k.startswith("signal:") for k in kinds), (
        f"Expected a 'signal:*' key in by_kind but got: {kinds}"
    )


def test_alerts_by_day_signal_kind_is_signal_prefixed(db):
    _signal_alert(db, ticker="SIGSURF2")
    points = stats_service.get_alerts_by_day(db, days=30)
    all_kinds: set[str] = set()
    for p in points:
        all_kinds.update(p.by_kind.keys())
    assert "signal:volume_breakout" in all_kinds, (
        f"Expected 'signal:volume_breakout' in kinds but got: {all_kinds}"
    )
    assert "unknown" not in all_kinds, "Signal alert kind must not be 'unknown'"


# ---------------------------------------------------------------------------
# stats_service: get_top_stocks
# ---------------------------------------------------------------------------

def test_top_stocks_counts_signal_alerts(db):
    s, _ = _signal_alert(db, ticker="SIGSURF3")
    top = stats_service.get_top_stocks(db, days=30, limit=10)
    tickers = [t.ticker for t in top]
    assert "SIGSURF3" in tickers, (
        f"Signal-only stock not in top_stocks: {tickers}"
    )


# ---------------------------------------------------------------------------
# notifier_service: build_digest_message
# ---------------------------------------------------------------------------

def test_digest_labels_signal_alert_not_unknown(db):
    _, alert = _signal_alert(db, ticker="SIGDIG")
    text = build_digest_message(db, [alert])
    assert "unknown" not in text, (
        f"Digest must not label signal alert as 'unknown'. Got:\n{text}"
    )
    # Since the B3-2 rewrite the digest maps signal names to friendly Italian
    # labels (mirroring frontend/src/lib/alertMeta.ts SIGNAL_META).
    assert "SIGDIG" in text
    assert "Volume Breakout" in text, (
        f"Digest must reference the signal kind via its label. Got:\n{text}"
    )
