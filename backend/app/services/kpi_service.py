"""KPI capture for engine monitoring (continuous improvement).

Append-only writes to `kpi_snapshots`:
  - `record_scan_kpis`   : called at scan end (per-scan health + signal pop).
  - `record_daily_rollup`: called by a daily cron (outcome calibration +
                           confluence + data quality), accumulating the
                           history the on-demand computations would discard.
Read helpers serve the monitoring panel (Phase B). All capture is best-effort
and must NEVER break the scan -- callers wrap in try/except.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Alert, KpiSnapshot

_CONF_BUCKETS = [(60, 70), (70, 80), (80, 90), (90, 101)]

# Below this many measured outcomes the historical calibration is too thin to
# trust -- mirrors the per-cell floor used by the frontend calibratedProbability.
_CALIB_MIN_N = 50
# Hours after which the latest scan is considered stale (daily cadence expected).
_SCAN_STALE_HOURS = 36


def _cbucket(c: float) -> str | None:
    for lo, hi in _CONF_BUCKETS:
        if lo <= c < hi:
            return f"{lo}-{hi - 1}"
    return None


def _active_signal_population(db: Session) -> dict:
    """Distribution of currently-active signal alerts by detector / tone /
    horizon / confidence bucket -- the live 'shape' of what the engine emits."""
    rows = db.execute(
        select(Alert.signal_name, Alert.snapshot)
        .where(Alert.signal_name.is_not(None), Alert.archived_at.is_(None))
    ).all()
    by_det: Counter = Counter()
    by_tone: Counter = Counter()
    by_hz: Counter = Counter()
    by_conf: Counter = Counter()
    for sname, snap in rows:
        by_det[sname] += 1
        try:
            d = json.loads(snap)
        except (ValueError, TypeError):
            d = {}
        if d.get("tone") in ("bull", "bear"):
            by_tone[d["tone"]] += 1
        if d.get("horizon") in ("short", "medium", "long"):
            by_hz[d["horizon"]] += 1
        c = d.get("confidence")
        if isinstance(c, (int, float)):
            b = _cbucket(c)
            if b:
                by_conf[b] += 1
    return {
        "total": len(rows), "by_detector": dict(by_det), "by_tone": dict(by_tone),
        "by_horizon": dict(by_hz), "by_confidence": dict(by_conf),
    }


def _data_sources() -> list[dict]:
    try:
        from app.services import data_source_metrics
        return [
            {"source": m.source, "op": m.op, "success": m.success,
             "failure": m.failure, "success_rate": m.success_rate, "health": m.health}
            for m in data_source_metrics.snapshot()
        ]
    except Exception:  # noqa: BLE001 - capture is best-effort
        return []


def record_scan_kpis(db: Session, run) -> None:
    """One `kind='scan'` row at scan end: scan health + signal population."""
    dur = None
    if run.completed_at and run.started_at:
        dur = (run.completed_at - run.started_at).total_seconds()
    metrics = {
        "scan_run_id": run.id, "trigger": run.trigger,
        "stocks_scanned": run.stocks_scanned, "stocks_skipped": run.stocks_skipped,
        "alerts_fired": run.alerts_fired,
        "duration_s": round(dur, 1) if dur is not None else None,
        "signals": _active_signal_population(db),
        "data_sources": _data_sources(),
    }
    db.add(KpiSnapshot(kind="scan", metrics=json.dumps(metrics)))
    db.commit()


def record_daily_rollup(db: Session, *, days: int = 365, window: int = 20) -> None:
    """One `kind='daily_rollup'` row: outcome calibration + confluence + data
    quality -- the accumulating history for trend/drift analysis."""
    from app.services import confluence_service
    from app.services.rule_performance_service import compute_calibration

    cal = compute_calibration(db, days=days, window=window)

    def buck(b) -> dict:
        return {"label": b.label, "count": b.count, "hit_rate": b.hit_rate, "mean_pct": b.mean_pct}

    clusters = confluence_service.compute_confluence(db)
    n = len(clusters)
    mh = sum(1 for c in clusters if c.multi_horizon)
    ct = sum(1 for c in clusters if c.contested)
    metrics = {
        "calibration": {
            "window": cal.window,
            "by_confidence": [buck(b) for b in cal.by_confidence],
            "by_horizon": [buck(b) for b in cal.by_horizon],
            "by_nature": [buck(b) for b in cal.by_nature],
        },
        "confluence": {
            "n_clusters": n,
            "multi_horizon_rate": round(mh / n, 3) if n else None,
            "contested_rate": round(ct / n, 3) if n else None,
        },
        "signals": _active_signal_population(db),
        "data_sources": _data_sources(),
    }
    db.add(KpiSnapshot(kind="daily_rollup", metrics=json.dumps(metrics)))
    db.commit()


def compute_flags(scans: list[dict], rollups: list[dict]) -> list[dict]:
    """Derive health flags for the monitoring panel from the recent KPI series.

    Pure over the passed-in lists (newest-first, as returned by `recent`). Each
    flag is `{level: error|warn|ok, code, title, detail}`. The result is sorted
    errors-first so the panel renders a triage list. Three flag families:
      1. scan freshness + sanity (latest scan row),
      2. data-source health (latest scan's per-source counters),
      3. calibration maturity (latest daily rollup).
    """
    flags: list[dict] = []

    # 1. Scan freshness + sanity --------------------------------------
    if not scans:
        flags.append({
            "level": "warn", "code": "no_scans",
            "title": "Nessuno scan recente",
            "detail": "Nessun KPI di scan nel periodo: il motore non ha girato o la cattura KPI non parte.",
        })
    else:
        latest = scans[0]
        m = latest.get("metrics", {})
        age_h: float | None = None
        try:
            ts = datetime.fromisoformat(latest["captured_at"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            age_h = (datetime.now(UTC) - ts).total_seconds() / 3600
        except (ValueError, KeyError, TypeError):
            age_h = None
        if age_h is not None and age_h > _SCAN_STALE_HOURS:
            flags.append({
                "level": "warn", "code": "scan_stale",
                "title": "Scan non recente",
                "detail": f"Ultimo scan ~{age_h:.0f}h fa (atteso giornaliero).",
            })
        scanned = m.get("stocks_scanned") or 0
        skipped = m.get("stocks_skipped") or 0
        if scanned == 0:
            flags.append({
                "level": "error", "code": "scan_empty",
                "title": "Ultimo scan a vuoto",
                "detail": "0 titoli analizzati nell'ultimo scan.",
            })
        tot = scanned + skipped
        if tot and skipped / tot > 0.5:
            flags.append({
                "level": "warn", "code": "high_skip",
                "title": "Molti titoli saltati",
                "detail": f"{skipped}/{tot} titoli saltati nell'ultimo scan ({skipped / tot * 100:.0f}%).",
            })

    # 2. Data-source health (latest scan's sources) ------------------
    src = (scans[0].get("metrics", {}).get("data_sources") if scans else None) or []
    for s in src:
        h = s.get("health")
        if h in ("down", "degraded"):
            sr = s.get("success_rate")
            srpct = f"{sr * 100:.0f}%" if isinstance(sr, (int, float)) else "n/d"
            flags.append({
                "level": "error" if h == "down" else "warn",
                "code": f"src_{s.get('source')}_{s.get('op')}",
                "title": f"Fonte {s.get('source')}/{s.get('op')}: {h}",
                "detail": f"Tasso di successo {srpct} ({s.get('success', 0)} ok / {s.get('failure', 0)} ko).",
            })

    # 3. Calibration maturity (latest rollup) ------------------------
    if not rollups:
        flags.append({
            "level": "warn", "code": "no_rollup",
            "title": "Nessun rollup giornaliero",
            "detail": "Il cron di calibrazione non ha ancora prodotto dati.",
        })
    else:
        cal = rollups[0].get("metrics", {}).get("calibration", {})
        total_n = sum((b.get("count") or 0) for b in (cal.get("by_confidence") or []))
        if total_n < _CALIB_MIN_N:
            flags.append({
                "level": "warn", "code": "calib_immature",
                "title": "Calibrazione immatura",
                "detail": (
                    f"Solo {total_n} esiti misurati (soglia {_CALIB_MIN_N}): "
                    "le probabilità storiche sono ancora poco affidabili."
                ),
            })

    if not flags:
        flags.append({
            "level": "ok", "code": "healthy",
            "title": "Tutto regolare",
            "detail": "Nessuna anomalia rilevata su scan, fonti dati e calibrazione.",
        })

    order = {"error": 0, "warn": 1, "ok": 2}
    flags.sort(key=lambda f: order.get(f["level"], 3))
    return flags


def recent(db: Session, *, kind: str, days: int = 90, limit: int = 200) -> list[dict]:
    """Time series for the monitoring panel: parsed snapshots, newest first."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(KpiSnapshot)
        .where(KpiSnapshot.kind == kind, KpiSnapshot.captured_at >= cutoff)
        .order_by(desc(KpiSnapshot.captured_at))
        .limit(limit)
    ).scalars().all()
    out = []
    for r in rows:
        try:
            m = json.loads(r.metrics)
        except (ValueError, TypeError):
            m = {}
        out.append({"id": r.id, "captured_at": r.captured_at.isoformat(), "scope": r.scope, "metrics": m})
    return out
