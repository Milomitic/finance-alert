"""Telegram notifiers — daily digest + optional instant pushes.

Three send surfaces, all sharing the same bot/chat config + scrubbed logging:

1. `send_daily_digest`   — the 24h summary (cron `send_digest`, manual API).
2. `notify_signal_alerts` — OPTIONAL per-scan push of strong signals, gated on
   `settings.telegram_push_per_signal` + `telegram_push_min_strength`.
3. `notify_price_alerts`  — instant push when a price-target alert fires
   intraday (no flag: the user explicitly set the target, being told
   immediately is the whole point).
"""
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Stock

# Maximum alerts to enumerate in the digest message body
DIGEST_TOP_N = 10
# Maximum alert lines in an instant push message
PUSH_TOP_N = 10
# Telegram message hard limit
TELEGRAM_MAX_LEN = 4000

# Italian display label per signal detector name.
# ⚠️ Ported from the frontend's SIGNAL_META map in
# `frontend/src/lib/alertMeta.ts` — that map is the source of truth for
# labels; keep the two in sync when a detector is added/renamed.
SIGNAL_LABELS: dict[str, str] = {
    "volume_breakout": "Volume Breakout",
    "trend_pullback": "Trend + Pullback",
    "rsi_divergence": "Divergenza RSI",
    "squeeze_expansion": "Squeeze + Espansione",
    "high52_momentum": "Massimo 52 settimane",
    "gap_and_go": "Gap and Go",
    "adx_confirmation": "Conferma ADX",
    "sr_flip": "Flip S/R",
    "structure_break": "Rottura struttura",
    "hidden_divergence": "Divergenza nascosta",
    "pead": "Drift post-utili",
    "analyst_momentum": "Momentum analisti",
    "macd_divergence": "Divergenza MACD",
    "oversold_reversal": "Inversione ipervenduto",
    "candle_reversal": "Inversione a candela",
    "insider_buy": "Acquisti insider",
    "chart_pattern": "Pattern grafico",
}

# Snapshot tone → emoji. Tone is per-alert (lives in the snapshot, not the
# kind) — mirrors the frontend's bull/bear chip coloring.
_TONE_EMOJI: dict[str, str] = {"bull": "🟢", "bear": "🔴"}


@dataclass
class DigestResult:
    sent: bool
    alerts_count: int = 0
    reason: str | None = None  # "ok" | "no_alerts" | "telegram_disabled" | "http_error"


@dataclass
class PushResult:
    sent: bool
    alerts_count: int = 0
    # "ok" | "push_disabled" | "telegram_disabled" | "no_alerts" | "http_error"
    reason: str | None = None


def _telegram_enabled() -> bool:
    return bool(settings.telegram_bot_token) and bool(settings.telegram_chat_id)


def _scrub_token(text: str) -> str:
    """Redact the bot token from any text destined for logs. httpx exception
    messages include the request URL — which embeds the token — so logging a
    raw `{e}` would leak the secret to disk AND the Salute live-log UI."""
    token = settings.telegram_bot_token
    return text.replace(token, "***") if token else text


def _parse_snapshot(alert: Alert) -> dict[str, Any]:
    """Alert.snapshot is a JSON text column; degrade to {} on any garbage."""
    try:
        data = json.loads(alert.snapshot or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def _alert_label(alert: Alert, snap: dict[str, Any]) -> str:
    """Human label for an alert. Signal alerts map via SIGNAL_LABELS with a
    graceful raw-name fallback (never a KeyError on a future detector);
    price-target alerts derive the direction arrow from the snapshot."""
    if alert.signal_name:
        return SIGNAL_LABELS.get(alert.signal_name, alert.signal_name)
    direction = snap.get("direction")
    if direction == "above":
        return "Price target ↑"
    if direction == "below":
        return "Price target ↓"
    return "Price alert"


def _alert_emoji(alert: Alert, snap: dict[str, Any]) -> str:
    tone = snap.get("tone")
    if isinstance(tone, str) and tone in _TONE_EMOJI:
        return _TONE_EMOJI[tone]
    # Price alerts carry no tone — derive from the crossing direction
    # (above = broke UP through target = bullish; below = bearish).
    direction = snap.get("direction")
    if direction == "above":
        return "🟢"
    if direction == "below":
        return "🔴"
    return "•"


def _snapshot_strength(snap: dict[str, Any]) -> float | None:
    """Forza from the snapshot. `confidence` is the transitional alias of
    `strength` (legacy alerts) — same fallback the alert_service sort uses."""
    for key in ("strength", "confidence"):
        v = snap.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _forza_prob(snap: dict[str, Any]) -> str:
    """'Forza 82% · Prob. 54%' — empty string when the snapshot has neither."""
    parts: list[str] = []
    s = _snapshot_strength(snap)
    if s is not None:
        parts.append(f"Forza {round(s)}%")
    p = snap.get("probability")
    if isinstance(p, (int, float)):
        parts.append(f"Prob. {round(p)}%")
    return " · ".join(parts)


def _fmt_price(value: Any) -> str:
    """Compact price rendering (trigger_price is Numeric(12,4) → Decimal)."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _truncate(text: str) -> str:
    if len(text) > TELEGRAM_MAX_LEN:
        return text[: TELEGRAM_MAX_LEN - 12] + "\n... [tronca]"
    return text


def _send_telegram(text: str, *, what: str) -> bool:
    """POST one HTML message to the configured chat. Returns success.
    Errors are logged (token-scrubbed) — callers treat False as http_error."""
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
        return True
    except httpx.HTTPError as e:
        logger.error(f"[notifier] Telegram {what} send failed: {_scrub_token(str(e))}")
        return False


def _stocks_by_id(db: Session, alerts: list[Alert]) -> dict[int, Stock]:
    stock_ids = {a.stock_id for a in alerts}
    if not stock_ids:
        return {}
    return {
        s.id: s
        for s in db.execute(select(Stock).where(Stock.id.in_(stock_ids))).scalars().all()
    }


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
    """Format the digest as Telegram HTML — grouped by signal label, with
    per-alert tone emoji + Forza/Probabilità when the snapshot carries them."""
    n = len(alerts)
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Group counts by human label (signal detectors and price targets share
    # the same label machinery, so unknown names degrade to the raw name).
    counts: dict[str, int] = {}
    for a in alerts:
        label = _alert_label(a, _parse_snapshot(a))
        counts[label] = counts.get(label, 0) + 1

    stocks_by_id = _stocks_by_id(db, alerts)

    lines = [f"🔔 <b>Finance Alert — Digest del {today}</b>", ""]
    lines.append(f"<b>{n} alert</b> nelle ultime 24h:")
    lines.append("")
    lines.append("<b>Per segnale:</b>")
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"• {label}: {count}")
    lines.append("")
    top = alerts[:DIGEST_TOP_N]
    lines.append(f"<b>Top {len(top)} alert per timestamp:</b>")
    for a in top:
        snap = _parse_snapshot(a)
        emoji = _alert_emoji(a, snap)
        label = _alert_label(a, snap)
        stock = stocks_by_id.get(a.stock_id)
        ticker = stock.ticker if stock else f"#{a.stock_id}"
        ts = a.triggered_at.strftime("%H:%M")
        metrics = _forza_prob(snap)
        line = f"{emoji} {ticker} — {label} ({_fmt_price(a.trigger_price)})"
        if metrics:
            line += f" — {metrics}"
        line += f" — {ts}"
        lines.append(line)

    if n > DIGEST_TOP_N:
        lines.append(f"... e altri {n - DIGEST_TOP_N}.")

    lines.append("")
    lines.append(f"🔗 Vedi tutti: {settings.public_base_url}/alerts")

    return _truncate("\n".join(lines))


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

    if not _send_telegram(text, what="digest"):
        return DigestResult(sent=False, alerts_count=len(alerts), reason="http_error")

    logger.info(f"[notifier] digest sent: {len(alerts)} alerts")
    return DigestResult(sent=True, alerts_count=len(alerts), reason="ok")


def notify_signal_alerts(db: Session, alerts: list[Alert]) -> PushResult:
    """OPTIONAL instant push for the signal alerts of a completed scan.

    Gated on `settings.telegram_push_per_signal` (default OFF) + Telegram
    being configured. Only alerts whose snapshot Forza (strength, with the
    transitional `confidence` fallback) >= `telegram_push_min_strength` are
    included — ONE compact message, strongest first, max PUSH_TOP_N lines
    + "e altri N". Callers must treat this as best-effort (the scan_runner
    wraps it in try/except): a Telegram failure never fails the scan.
    """
    if not settings.telegram_push_per_signal:
        return PushResult(sent=False, reason="push_disabled")
    if not _telegram_enabled():
        logger.info("[notifier] signal push skipped: Telegram disabled")
        return PushResult(sent=False, reason="telegram_disabled")

    threshold = float(settings.telegram_push_min_strength)
    strong: list[tuple[float, Alert, dict[str, Any]]] = []
    for a in alerts:
        if not a.signal_name:
            continue  # price alerts have their own instant push
        snap = _parse_snapshot(a)
        s = _snapshot_strength(snap)
        if s is not None and s >= threshold:
            strong.append((s, a, snap))
    if not strong:
        return PushResult(sent=False, reason="no_alerts")

    strong.sort(key=lambda t: -t[0])
    stocks_by_id = _stocks_by_id(db, [a for _, a, _ in strong])

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    lines = [f"⚡ <b>Segnali forti — scan del {now}</b>", ""]
    for _, a, snap in strong[:PUSH_TOP_N]:
        stock = stocks_by_id.get(a.stock_id)
        ticker = stock.ticker if stock else f"#{a.stock_id}"
        label = _alert_label(a, snap)
        metrics = _forza_prob(snap)
        line = f"{_alert_emoji(a, snap)} <b>{ticker}</b> — {label} ({_fmt_price(a.trigger_price)})"
        if metrics:
            line += f" — {metrics}"
        lines.append(line)
    if len(strong) > PUSH_TOP_N:
        lines.append(f"... e altri {len(strong) - PUSH_TOP_N}.")
    lines.append("")
    lines.append(f"🔗 {settings.public_base_url}/alerts")

    text = _truncate("\n".join(lines))
    if not _send_telegram(text, what="signal push"):
        return PushResult(sent=False, alerts_count=len(strong), reason="http_error")

    logger.info(f"[notifier] signal push sent: {len(strong)} strong alert(s)")
    return PushResult(sent=True, alerts_count=len(strong), reason="ok")


def notify_price_alerts(fired: list[tuple[Alert, Stock]]) -> PushResult:
    """Instant push for intraday price-target crossings.

    No opt-in flag by design: a price alert is an explicit user-set trigger —
    immediate notification IS the feature. Only gated on Telegram config.
    Best-effort like the other senders: callers swallow exceptions.
    """
    if not fired:
        return PushResult(sent=False, reason="no_alerts")
    if not _telegram_enabled():
        logger.info("[notifier] price push skipped: Telegram disabled")
        return PushResult(sent=False, reason="telegram_disabled")

    lines = ["🎯 <b>Price target raggiunto</b>", ""]
    for a, stock in fired[:PUSH_TOP_N]:
        snap = _parse_snapshot(a)
        arrow = "↑" if snap.get("direction") == "above" else "↓"
        target = _fmt_price(snap.get("target"))
        lines.append(
            f"{_alert_emoji(a, snap)} <b>{stock.ticker}</b> — target {target} {arrow} — "
            f"prezzo {_fmt_price(a.trigger_price)}"
        )
    if len(fired) > PUSH_TOP_N:
        lines.append(f"... e altri {len(fired) - PUSH_TOP_N}.")
    lines.append("")
    lines.append(f"🔗 {settings.public_base_url}/alerts")

    text = _truncate("\n".join(lines))
    if not _send_telegram(text, what="price push"):
        return PushResult(sent=False, alerts_count=len(fired), reason="http_error")

    logger.info(f"[notifier] price push sent: {len(fired)} alert(s)")
    return PushResult(sent=True, alerts_count=len(fired), reason="ok")
