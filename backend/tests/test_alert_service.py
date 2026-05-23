"""Tests for alert_service.list_alerts sorting."""
import json
from datetime import date

import pytest

from app.models import Alert, Stock
from app.services.alert_service import list_alerts


def _seed(db, ticker, price, conf):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    db.add(
        Alert(
            stock_id=s.id,
            trigger_price=price,
            signal_date=date(2026, 5, 1),
            signal_name="volume_breakout",
            snapshot=json.dumps({"tone": "bull", "confidence": conf, "chain": []}),
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
