"""Tests for alert_service.list_alerts sorting and filtering."""
import json
from datetime import date

import pytest

from app.models import Alert, Stock
from app.services.alert_service import list_alerts


def _seed(db, ticker, price, conf, tone="bull"):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    db.add(
        Alert(
            stock_id=s.id,
            trigger_price=price,
            signal_date=date(2026, 5, 1),
            signal_name="volume_breakout",
            snapshot=json.dumps({"tone": tone, "confidence": conf, "chain": []}),
        )
    )
    db.commit()


def test_list_alerts_sort_by_price_and_confidence(db):
    _seed(db, "AAA", 10.0, 90)
    _seed(db, "BBB", 30.0, 50)
    _seed(db, "CCC", 20.0, 70)

    # sort by trigger_price asc
    items, _total, _more = list_alerts(db, sort_by="trigger_price", sort_dir="asc")
    assert [round(i["trigger_price"], 0) for i in items] == [10, 20, 30]

    # sort by confidence desc
    items, _, _ = list_alerts(db, sort_by="confidence", sort_dir="desc")
    assert [i["ticker"] for i in items] == ["AAA", "CCC", "BBB"]


# ── tone filter ──────────────────────────────────────────────────────────────

def test_filter_by_tone_bull(db):
    _seed(db, "BULL1", 10.0, 80, tone="bull")
    _seed(db, "BEAR1", 20.0, 60, tone="bear")
    _seed(db, "BULL2", 30.0, 40, tone="bull")

    items, total, _ = list_alerts(db, tone="bull")
    tickers = {i["ticker"] for i in items}
    assert tickers == {"BULL1", "BULL2"}
    assert total == 2


def test_filter_by_tone_bear(db):
    _seed(db, "BULL3", 10.0, 80, tone="bull")
    _seed(db, "BEAR2", 20.0, 60, tone="bear")

    items, total, _ = list_alerts(db, tone="bear")
    assert [i["ticker"] for i in items] == ["BEAR2"]
    assert total == 1


def test_filter_tone_no_match(db):
    _seed(db, "BULL4", 10.0, 80, tone="bull")

    items, total, _ = list_alerts(db, tone="bear")
    assert items == []
    assert total == 0


# ── confidence_min filter ────────────────────────────────────────────────────

def test_filter_by_confidence_min(db):
    _seed(db, "HIGH", 10.0, 85, tone="bull")
    _seed(db, "MID",  20.0, 70, tone="bull")
    _seed(db, "LOW",  30.0, 40, tone="bull")

    items, total, _ = list_alerts(db, confidence_min=70.0)
    tickers = {i["ticker"] for i in items}
    assert tickers == {"HIGH", "MID"}
    assert total == 2


def test_filter_by_confidence_min_exact_boundary(db):
    _seed(db, "EXACT", 10.0, 70, tone="bull")
    _seed(db, "BELOW", 20.0, 69, tone="bull")

    items, total, _ = list_alerts(db, confidence_min=70.0)
    assert [i["ticker"] for i in items] == ["EXACT"]
    assert total == 1


# ── combined tone + confidence_min ───────────────────────────────────────────

def test_filter_tone_and_confidence_combined(db):
    _seed(db, "A", 10.0, 90, tone="bull")
    _seed(db, "B", 20.0, 50, tone="bull")
    _seed(db, "C", 30.0, 90, tone="bear")

    items, total, _ = list_alerts(db, tone="bull", confidence_min=80.0)
    assert [i["ticker"] for i in items] == ["A"]
    assert total == 1
