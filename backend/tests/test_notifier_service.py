"""Tests for Telegram digest notifier."""
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Rule, Stock
from app.services.notifier_service import (
    DigestResult,
    build_digest_message,
    send_daily_digest,
)


def _seed_for_digest(db: Session) -> tuple[Stock, Rule, Alert]:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc.")
    db.add(stock)
    db.commit()
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    alert = Alert(
        rule_id=rule.id,
        stock_id=stock.id,
        trigger_price=182.50,
        snapshot='{"rsi": 28.4, "period": 14, "threshold": 30}',
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return stock, rule, alert


def test_send_digest_skipped_when_no_token(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    _seed_for_digest(db)
    result = send_daily_digest(db)
    assert isinstance(result, DigestResult)
    assert result.sent is False
    assert result.reason == "telegram_disabled"


def test_send_digest_skipped_when_no_alerts(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "FAKE_TOKEN")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    # No alerts in DB
    result = send_daily_digest(db)
    assert result.sent is False
    assert result.reason == "no_alerts"


def test_send_digest_calls_telegram_when_alerts_present(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "FAKE_TOKEN")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    _seed_for_digest(db)

    with patch("app.services.notifier_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None, status_code=200)
        result = send_daily_digest(db)

    assert result.sent is True
    assert result.alerts_count == 1
    assert mock_post.called
    call_kwargs = mock_post.call_args.kwargs
    assert "json" in call_kwargs
    assert call_kwargs["json"]["chat_id"] == "12345"
    assert "AAPL" in call_kwargs["json"]["text"]


def test_build_digest_message_contains_summary_and_top_alerts(db: Session) -> None:
    stock, rule, alert = _seed_for_digest(db)
    message = build_digest_message(db, [alert])
    assert "AAPL" in message
    assert "RSI Oversold" in message
    assert "Finance Alert" in message
