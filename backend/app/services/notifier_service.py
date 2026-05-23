"""Telegram digest notifier — single daily summary message."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Rule, Stock
from app.services.alert_service import derive_rule_kind

# Maximum alerts to enumerate in the message body
DIGEST_TOP_N = 10
# Telegram message hard limit
TELEGRAM_MAX_LEN = 4000

# Display labels for each rule kind (Italian)
RULE_LABELS: dict[str, str] = {
    "rsi_oversold": "RSI Oversold",
    "rsi_overbought": "RSI Overbought",
    "golden_cross": "Golden Cross",
    "death_cross": "Death Cross",
}

# Emoji per kind
RULE_EMOJIS: dict[str, str] = {
    "rsi_oversold": "🟢",
    "rsi_overbought": "🔴",
    "golden_cross": "⚡",
    "death_cross": "⚠️",
}


@dataclass
class DigestResult:
    sent: bool
    alerts_count: int = 0
    reason: str | None = None  # "ok" | "no_alerts" | "telegram_disabled" | "http_error"


def _telegram_enabled() -> bool:
    return bool(settings.telegram_bot_token) and bool(settings.telegram_chat_id)


def _fetch_alerts_last_24h(db: Session) -> list[Alert]:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    return list(
        db.execute(
            select(Alert)
            .where(Alert.triggered_at > cutoff)
            .order_by(Alert.triggered_at.desc())
        )
        .scalars()
        .all()
    )


def build_digest_message(db: Session, alerts: list[Alert]) -> str:
    """Format the digest as Telegram HTML."""
    n = len(alerts)
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Group counts by kind
    rule_ids = {a.rule_id for a in alerts}
    rules_by_id = {
        r.id: r
        for r in db.execute(select(Rule).where(Rule.id.in_(rule_ids))).scalars().all()
    }
    counts: dict[str, int] = {}
    for a in alerts:
        rule = rules_by_id.get(a.rule_id)
        kind = derive_rule_kind(rule.kind if rule else None, a.signal_name) or "unknown"
        counts[kind] = counts.get(kind, 0) + 1

    # Per-stock lookup
    stock_ids = {a.stock_id for a in alerts}
    stocks_by_id = {
        s.id: s
        for s in db.execute(select(Stock).where(Stock.id.in_(stock_ids))).scalars().all()
    }

    lines = [f"🔔 <b>Finance Alert — Digest del {today}</b>", ""]
    lines.append(f"<b>{n} alert</b> nelle ultime 24h:")
    lines.append("")
    lines.append("<b>Per regola:</b>")
    for kind, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        label = RULE_LABELS.get(kind, kind)
        lines.append(f"• {label}: {count}")
    lines.append("")
    top = alerts[:DIGEST_TOP_N]
    lines.append(f"<b>Top {len(top)} alert per timestamp:</b>")
    for a in top:
        rule = rules_by_id.get(a.rule_id)
        kind = derive_rule_kind(rule.kind if rule else None, a.signal_name) or "unknown"
        emoji = RULE_EMOJIS.get(kind, "•")
        label = RULE_LABELS.get(kind, kind)
        stock = stocks_by_id.get(a.stock_id)
        ticker = stock.ticker if stock else f"#{a.stock_id}"
        ts = a.triggered_at.strftime("%H:%M")
        lines.append(f"{emoji} {ticker} — {label} (${a.trigger_price}) — {ts}")

    if n > DIGEST_TOP_N:
        lines.append(f"... e altri {n - DIGEST_TOP_N}.")

    lines.append("")
    lines.append(f"🔗 Vedi tutti: {settings.public_base_url}/alerts")

    text = "\n".join(lines)
    if len(text) > TELEGRAM_MAX_LEN:
        text = text[: TELEGRAM_MAX_LEN - 12] + "\n... [tronca]"
    return text


def send_daily_digest(db: Session) -> DigestResult:
    """Build and send the digest of the last 24 hours of alerts."""
    if not _telegram_enabled():
        logger.info("[notifier] digest skipped: Telegram disabled (no token or chat_id)")
        return DigestResult(sent=False, reason="telegram_disabled")

    alerts = _fetch_alerts_last_24h(db)
    if not alerts:
        logger.info("[notifier] digest skipped: no alerts in last 24h")
        return DigestResult(sent=False, reason="no_alerts")

    text = build_digest_message(db, alerts)

    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"[notifier] Telegram digest send failed: {e}")
        return DigestResult(sent=False, alerts_count=len(alerts), reason="http_error")

    logger.info(f"[notifier] digest sent: {len(alerts)} alerts")
    return DigestResult(sent=True, alerts_count=len(alerts), reason="ok")
