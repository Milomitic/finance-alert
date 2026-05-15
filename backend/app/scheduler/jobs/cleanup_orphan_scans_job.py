"""Job APScheduler: chiude le ScanRun 'running' senza heartbeat da troppo tempo.

Estrae la logica già usata in main.py:_cleanup_orphan_scans (che gira solo
al boot) in una funzione invocabile anche periodicamente. Threshold: 5 min
senza heartbeat ⇒ il worker è morto/bloccato, marca 'failed'.

Idempotente: zero orfani ⇒ no-op silenzioso.
"""
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select

from app.models import ScanRun

# Heartbeat threshold. 5 min copre con margine il caso peggiore di un
# fetch yfinance lento + scan grosso (scan_universe pulsa il progress
# ogni 0.5s via progress_pulse).
_STALE_AFTER_MINUTES = 5


def run_cleanup_orphan_scans() -> int:
    """Chiude le ScanRun running con heartbeat stale. Restituisce il count
    di righe chiuse (utile per test e log)."""
    # Local import so monkeypatching in tests propagates correctly.
    from app.core.db import SessionLocal  # noqa: PLC0415

    cutoff = datetime.now(UTC) - timedelta(minutes=_STALE_AFTER_MINUTES)
    closed = 0
    with SessionLocal() as db:
        stale = db.execute(
            select(ScanRun).where(
                ScanRun.status == "running",
                ScanRun.last_progress_at < cutoff,
            )
        ).scalars().all()
        if not stale:
            return 0
        now = datetime.now(UTC)
        for r in stale:
            # Normalize tz before subtracting (DB may return naive datetimes
            # depending on SQLite driver behavior).
            ref = r.last_progress_at
            if ref is not None and ref.tzinfo is None:
                ref = ref.replace(tzinfo=UTC)
            elapsed = int((now - (ref or now)).total_seconds() / 60)
            r.status = "failed"
            r.phase = None
            r.error_message = (
                f"Scan terminato dal cleanup periodico (heartbeat fermo da "
                f"~{elapsed}min)."
            )
            r.completed_at = now
            closed += 1
        db.commit()
        logger.warning(
            f"[orphan_cleanup] closed {closed} stale ScanRun(s) "
            f"(ids={[r.id for r in stale]})"
        )
    return closed
