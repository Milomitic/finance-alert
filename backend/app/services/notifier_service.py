"""Telegram notifiers — daily digest + optional instant pushes.

Six send surfaces, all sharing the same bot/chat config + scrubbed logging:

1. `send_daily_digest`   — the 24h summary (cron `send_digest`, manual API).
2. `notify_signal_alerts` — OPTIONAL per-scan push of strong signals, gated on
   `settings.telegram_push_per_signal` + `telegram_push_min_strength`.
3. `notify_price_alerts`  — instant push when a price-target alert fires
   intraday (no flag: the user explicitly set the target, being told
   immediately is the whole point).
4. `notify_position_closed` — instant push when a tracked position auto-closes
   on a stop/target hit (same no-flag rationale as the price alerts).
5. `notify_scan_failed` — push when a scan run CRASHES to status='failed'
   (audit 2026-07-08 observability core). Gated on
   `settings.telegram_notify_health`; user-cancelled runs never notify.
6. `notify_health_transition` — push when the platform-health rollup
   transitions to degraded/outage. Called ONLY via
   `health_rollup.maybe_notify_transition` (which owns the state-change +
   6h-cooldown gating); same `telegram_notify_health` flag.
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


# ─── Salute piattaforma (audit 2026-07-08) ─────────────────────────────

# Rollup state → banner emoji + Italian label (mirrors the Salute page).
_HEALTH_STATE_EMOJI: dict[str, str] = {"degraded": "🟠", "outage": "🔴"}
_HEALTH_STATE_LABEL: dict[str, str] = {
    "degraded": "Servizi degradati",
    "outage": "Outage in corso",
}
# Max reasons enumerated in a health push message.
_HEALTH_REASONS_TOP_N = 8


def notify_scan_failed(run_id: int, error_message: str | None) -> PushResult:
    """Instant push when a scan run CRASHES to status='failed'.

    The 13F-crons audit showed failures died silently for months — a failed
    SCAN is the highest-value single event to surface because everything
    downstream (signals, scores, outcomes) depends on it. Gated on
    `settings.telegram_notify_health` (default ON) + Telegram config.
    Callers (scan_runner's crash path) treat this as best-effort — a
    Telegram problem must never mask the original scan error."""
    if not settings.telegram_notify_health:
        return PushResult(sent=False, reason="push_disabled")
    if not _telegram_enabled():
        logger.info("[notifier] scan-failed push skipped: Telegram disabled")
        return PushResult(sent=False, reason="telegram_disabled")

    detail = (error_message or "errore sconosciuto")[:500]
    lines = [
        f"❌ <b>Scan fallito</b> — run #{run_id}",
        "",
        f"Errore: {detail}",
        "",
        f"🔗 Dettagli: {settings.public_base_url}/health",
    ]
    text = _truncate("\n".join(lines))
    if not _send_telegram(text, what="scan-failed push"):
        return PushResult(sent=False, reason="http_error")
    logger.info(f"[notifier] scan-failed push sent for run #{run_id}")
    return PushResult(sent=True, reason="ok")


def notify_health_transition(overall: str, reasons: list[str]) -> bool:
    """Push the health-rollup TRANSITION to degraded/outage.

    Do NOT call directly from health readers — go through
    `health_rollup.maybe_notify_transition`, which owns the only-on-change +
    once-per-6h-per-state gating (this function would happily spam).
    Returns True when the message was delivered."""
    if not settings.telegram_notify_health:
        return False
    if not _telegram_enabled():
        logger.info("[notifier] health push skipped: Telegram disabled")
        return False

    emoji = _HEALTH_STATE_EMOJI.get(overall, "⚠️")
    label = _HEALTH_STATE_LABEL.get(overall, overall)
    lines = [f"{emoji} <b>Salute piattaforma: {label}</b>", ""]
    for r in reasons[:_HEALTH_REASONS_TOP_N]:
        lines.append(f"• {r}")
    if len(reasons) > _HEALTH_REASONS_TOP_N:
        lines.append(f"... e altri {len(reasons) - _HEALTH_REASONS_TOP_N} motivi.")
    lines.append("")
    lines.append(f"🔗 {settings.public_base_url}/health")

    text = _truncate("\n".join(lines))
    if not _send_telegram(text, what="health push"):
        return False
    logger.info(f"[notifier] health push sent: {overall} ({len(reasons)} reason(s))")
    return True


# Exit-reason → emoji for the position push. "manual" never notifies (the
# user clicked the button themselves) but keep a fallback for safety.
_EXIT_EMOJI: dict[str, str] = {"stop": "🛑", "target": "🎯"}
_EXIT_LABEL: dict[str, str] = {"stop": "stop", "target": "target", "manual": "chiusura manuale"}


def notify_position_closed(closed: list[tuple[Any, Stock]]) -> PushResult:
    """Instant push when tracked positions auto-close on a stop/target hit.

    `closed` = [(Position, Stock), ...] from position_service's hit detection.
    Same contract as `notify_price_alerts`: no opt-in flag by design (the user
    explicitly opened the position — being told it closed IS the feature),
    gated only on Telegram config; callers treat it as best-effort.
    """
    if not closed:
        return PushResult(sent=False, reason="no_alerts")
    if not _telegram_enabled():
        logger.info("[notifier] position push skipped: Telegram disabled")
        return PushResult(sent=False, reason="telegram_disabled")

    lines = ["📌 <b>Posizione chiusa</b>", ""]
    for pos, stock in closed[:PUSH_TOP_N]:
        emoji = _EXIT_EMOJI.get(pos.exit_reason or "", "•")
        reason = _EXIT_LABEL.get(pos.exit_reason or "", pos.exit_reason or "?")
        side = "Long" if pos.side == "long" else "Short"
        entry = float(pos.entry_price)
        line = f"{emoji} <b>{stock.ticker}</b> — {side} chiuso su {reason}"
        if pos.exit_price is not None and entry > 0:
            exit_p = float(pos.exit_price)
            sign = 1 if pos.side == "long" else -1
            pnl = sign * (exit_p - entry) / entry * 100.0
            line += (
                f" — entry {_fmt_price(entry)} → exit {_fmt_price(exit_p)}"
                f" ({pnl:+.1f}%)"
            )
        lines.append(line)
    if len(closed) > PUSH_TOP_N:
        lines.append(f"... e altre {len(closed) - PUSH_TOP_N}.")
    lines.append("")
    lines.append(f"🔗 {settings.public_base_url}/positions")

    text = _truncate("\n".join(lines))
    if not _send_telegram(text, what="position push"):
        return PushResult(sent=False, alerts_count=len(closed), reason="http_error")

    logger.info(f"[notifier] position push sent: {len(closed)} position(s)")
    return PushResult(sent=True, alerts_count=len(closed), reason="ok")
