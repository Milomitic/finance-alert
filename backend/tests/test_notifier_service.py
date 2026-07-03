"""Tests for the Telegram notifiers — digest labels, per-signal push gates."""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Stock
from app.services.notifier_service import (
    DigestResult,
    PushResult,
    SIGNAL_LABELS,
    build_digest_message,
    notify_price_alerts,
    notify_signal_alerts,
    send_daily_digest,
)


def _mk_stock(db: Session, ticker: str = "AAPL") -> Stock:
    stock = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc.")
    db.add(stock)
    db.commit()
    return stock


def _mk_signal_alert(
    db: Session,
    stock: Stock,
    *,
    signal_name: str = "volume_breakout",
    strength: float | None = 82,
    probability: float | None = 54,
    tone: str = "bull",
    price: float = 182.50,
) -> Alert:
    snap: dict = {"tone": tone, "chain": []}
    if strength is not None:
        snap["strength"] = strength
    if probability is not None:
        snap["probability"] = probability
    alert = Alert(
        signal_name=signal_name,
        stock_id=stock.id,
        trigger_price=price,
        snapshot=json.dumps(snap),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def _seed_for_digest(db: Session) -> tuple[Stock, Alert]:
    stock = _mk_stock(db)
    return stock, _mk_signal_alert(db, stock)


# ─── send_daily_digest gates ─────────────────────────────────────────────


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


# ─── build_digest_message: signal labels ─────────────────────────────────


def test_build_digest_message_uses_italian_signal_labels(db: Session) -> None:
    stock, alert = _seed_for_digest(db)
    message = build_digest_message(db, [alert])
    assert "AAPL" in message
    assert "Volume Breakout" in message          # mapped label, not raw name
    assert "signal:" not in message              # no raw kind strings
    assert "Finance Alert" in message


def test_build_digest_message_no_legacy_rule_kinds(db: Session) -> None:
    """The 4 legacy rule kinds are gone — a modern detector set must never
    surface them nor fall through to 'unknown'."""
    stock = _mk_stock(db, "MSFT")
    alerts = [
        _mk_signal_alert(db, stock, signal_name="trend_pullback", tone="bull"),
        _mk_signal_alert(db, stock, signal_name="macd_divergence", tone="bear"),
    ]
    message = build_digest_message(db, alerts)
    assert "Trend + Pullback" in message
    assert "Divergenza MACD" in message
    for legacy in ("RSI Oversold", "RSI Overbought", "Golden Cross", "Death Cross"):
        assert legacy not in message
    assert "unknown" not in message


def test_build_digest_message_all_17_detectors_have_labels() -> None:
    """The python map must cover the frontend's 17 detectors (alertMeta.ts)."""
    expected = {
        "volume_breakout", "trend_pullback", "rsi_divergence", "squeeze_expansion",
        "high52_momentum", "gap_and_go", "adx_confirmation", "sr_flip",
        "structure_break", "hidden_divergence", "pead", "analyst_momentum",
        "macd_divergence", "oversold_reversal", "candle_reversal", "insider_buy",
        "chart_pattern",
    }
    assert set(SIGNAL_LABELS) == expected


def test_build_digest_message_unknown_signal_falls_back_to_raw_name(db: Session) -> None:
    """A future detector unknown to the map degrades to its raw name — never
    a KeyError."""
    stock = _mk_stock(db, "NVDA")
    alert = _mk_signal_alert(db, stock, signal_name="quantum_flux_reversal")
    message = build_digest_message(db, [alert])
    assert "quantum_flux_reversal" in message
    assert "NVDA" in message


def test_build_digest_message_includes_forza_and_probabilita(db: Session) -> None:
    stock = _mk_stock(db, "AMD")
    alert = _mk_signal_alert(db, stock, strength=82, probability=54)
    message = build_digest_message(db, [alert])
    assert "Forza 82%" in message
    assert "Prob. 54%" in message


def test_build_digest_message_tone_emoji(db: Session) -> None:
    stock = _mk_stock(db, "TSLA")
    bull = _mk_signal_alert(db, stock, tone="bull")
    bear = _mk_signal_alert(db, stock, tone="bear", signal_name="macd_divergence")
    message = build_digest_message(db, [bull, bear])
    assert "🟢" in message
    assert "🔴" in message


def test_build_digest_message_price_alert_label(db: Session) -> None:
    """Price-target alerts (signal_name=None) get a directional label from
    the snapshot instead of a raw/None kind."""
    stock = _mk_stock(db, "INTC")
    alert = Alert(
        stock_id=stock.id,
        trigger_price=101.0,
        snapshot=json.dumps({"direction": "above", "target": 100.0}),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    message = build_digest_message(db, [alert])
    assert "Price target ↑" in message


def test_build_digest_message_tolerates_garbage_snapshot(db: Session) -> None:
    stock = _mk_stock(db, "IBM")
    alert = Alert(
        signal_name="volume_breakout",
        stock_id=stock.id,
        trigger_price=10.0,
        snapshot="not-json{{{",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    message = build_digest_message(db, [alert])  # must not raise
    assert "Volume Breakout" in message


# ─── notify_signal_alerts: flag + threshold gates ────────────────────────


def _push_env(monkeypatch: pytest.MonkeyPatch, *, enabled: bool = True, min_strength: int = 75) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "FAKE_TOKEN")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    monkeypatch.setattr(settings, "telegram_push_per_signal", enabled)
    monkeypatch.setattr(settings, "telegram_push_min_strength", min_strength)


def test_notify_signal_alerts_disabled_by_default(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _push_env(monkeypatch, enabled=False)
    stock = _mk_stock(db)
    alert = _mk_signal_alert(db, stock, strength=99)
    with patch("app.services.notifier_service.httpx.post") as mock_post:
        result = notify_signal_alerts(db, [alert])
    assert isinstance(result, PushResult)
    assert result.sent is False
    assert result.reason == "push_disabled"
    assert not mock_post.called


def test_notify_signal_alerts_requires_telegram_config(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    monkeypatch.setattr(settings, "telegram_push_per_signal", True)
    stock = _mk_stock(db)
    alert = _mk_signal_alert(db, stock, strength=99)
    result = notify_signal_alerts(db, [alert])
    assert result.sent is False
    assert result.reason == "telegram_disabled"


def test_notify_signal_alerts_respects_strength_threshold(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _push_env(monkeypatch, min_strength=75)
    stock = _mk_stock(db)
    weak = _mk_signal_alert(db, stock, strength=60)
    with patch("app.services.notifier_service.httpx.post") as mock_post:
        result = notify_signal_alerts(db, [weak])
    assert result.sent is False
    assert result.reason == "no_alerts"
    assert not mock_post.called


def test_notify_signal_alerts_sends_strong_alerts(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _push_env(monkeypatch, min_strength=75)
    stock = _mk_stock(db)
    weak = _mk_signal_alert(db, stock, strength=60)
    strong = _mk_signal_alert(db, stock, strength=88, signal_name="squeeze_expansion")
    with patch("app.services.notifier_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None, status_code=200)
        result = notify_signal_alerts(db, [weak, strong])
    assert result.sent is True
    assert result.alerts_count == 1  # only the strong one
    text = mock_post.call_args.kwargs["json"]["text"]
    assert "AAPL" in text
    assert "Squeeze + Espansione" in text
    assert "Forza 88%" in text
    # The weak alert's kind must not appear
    assert "Volume Breakout" not in text


def test_notify_signal_alerts_legacy_confidence_counts_as_strength(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`confidence` is the transitional alias of `strength` — a legacy
    snapshot with only confidence must still pass the threshold gate."""
    _push_env(monkeypatch, min_strength=75)
    stock = _mk_stock(db)
    alert = Alert(
        signal_name="trend_pullback",
        stock_id=stock.id,
        trigger_price=50.0,
        snapshot=json.dumps({"confidence": 80, "tone": "bull"}),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    with patch("app.services.notifier_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None, status_code=200)
        result = notify_signal_alerts(db, [alert])
    assert result.sent is True
    assert result.alerts_count == 1


def test_notify_signal_alerts_batches_with_e_altri(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _push_env(monkeypatch, min_strength=75)
    stock = _mk_stock(db)
    alerts = [_mk_signal_alert(db, stock, strength=80 + i % 15) for i in range(13)]
    with patch("app.services.notifier_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None, status_code=200)
        result = notify_signal_alerts(db, alerts)
    assert result.sent is True
    assert result.alerts_count == 13
    text = mock_post.call_args.kwargs["json"]["text"]
    assert mock_post.call_count == 1  # ONE message, not 13
    assert "e altri 3" in text


def test_notify_signal_alerts_http_error_reported_not_raised(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx as _httpx
    _push_env(monkeypatch)
    stock = _mk_stock(db)
    alert = _mk_signal_alert(db, stock, strength=90)
    with patch(
        "app.services.notifier_service.httpx.post",
        side_effect=_httpx.ConnectError("boom"),
    ):
        result = notify_signal_alerts(db, [alert])  # must not raise
    assert result.sent is False
    assert result.reason == "http_error"


# ─── notify_price_alerts ─────────────────────────────────────────────────


def test_notify_price_alerts_sends_when_configured(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "FAKE_TOKEN")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    stock = _mk_stock(db, "AMZN")
    alert = Alert(
        stock_id=stock.id,
        trigger_price=101.25,
        snapshot=json.dumps({"direction": "above", "target": 100.0, "source": "intraday"}),
    )
    db.add(alert)
    db.commit()
    with patch("app.services.notifier_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None, status_code=200)
        result = notify_price_alerts([(alert, stock)])
    assert result.sent is True
    text = mock_post.call_args.kwargs["json"]["text"]
    assert "AMZN" in text
    assert "target 100" in text
    assert "↑" in text


def test_notify_price_alerts_skipped_when_telegram_disabled(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    stock = _mk_stock(db, "GOOG")
    alert = Alert(stock_id=stock.id, trigger_price=10.0, snapshot="{}")
    db.add(alert)
    db.commit()
    with patch("app.services.notifier_service.httpx.post") as mock_post:
        result = notify_price_alerts([(alert, stock)])
    assert result.sent is False
    assert result.reason == "telegram_disabled"
    assert not mock_post.called


# ─── scan_runner wiring: push at scan end ────────────────────────────────


def _fake_scan_factory(db: Session, stock: Stock, *, strength: float = 90):
    """scan_universe stand-in that fires one strong signal alert mid-scan."""
    from app.services.scan_service import ScanResult

    def fake_scan(db2, on_progress=None, progress_every=5, cancel_check=None):
        _mk_signal_alert(db2, stock, strength=strength)
        return ScanResult(stocks_scanned=1, stocks_skipped=0, alerts_fired=1, states_updated=0)

    return fake_scan


def test_scan_runner_pushes_new_signal_alerts(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import scan_runner

    _push_env(monkeypatch, min_strength=75)
    stock = _mk_stock(db, "PUSHW")
    monkeypatch.setattr(scan_runner, "scan_universe", _fake_scan_factory(db, stock))

    with patch("app.services.notifier_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None, status_code=200)
        run = scan_runner.run_tracked_scan(db, trigger="manual")

    assert run.status == "success"
    assert mock_post.called
    text = mock_post.call_args.kwargs["json"]["text"]
    assert "PUSHW" in text
    assert "Volume Breakout" in text


def test_scan_runner_no_push_when_flag_disabled(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import notifier_service, scan_runner

    _push_env(monkeypatch, enabled=False)
    stock = _mk_stock(db, "NOPUSH")
    monkeypatch.setattr(scan_runner, "scan_universe", _fake_scan_factory(db, stock))
    called = {"n": 0}
    monkeypatch.setattr(
        notifier_service, "notify_signal_alerts",
        lambda db2, alerts: called.__setitem__("n", called["n"] + 1),
    )
    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"
    assert called["n"] == 0  # flag off → baseline never captured → no call


def test_scan_runner_push_failure_is_non_fatal(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import notifier_service, scan_runner

    _push_env(monkeypatch)
    stock = _mk_stock(db, "BOOMP")
    monkeypatch.setattr(scan_runner, "scan_universe", _fake_scan_factory(db, stock))
    monkeypatch.setattr(
        notifier_service, "notify_signal_alerts",
        lambda db2, alerts: (_ for _ in ()).throw(RuntimeError("telegram down")),
    )
    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"  # a Telegram crash must never fail the scan
