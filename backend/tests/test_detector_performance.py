"""Tests for the detector performance explorer (service + endpoint).

The service aggregates the `signal_outcomes` warehouse — here we seed outcome
rows DIRECTLY (the maturation pipeline that writes them is exercised end-to-end
in test_signal_drift_service.py; this suite tests the aggregation itself):

  - hit-rate math (absolute + market-neutral over the labeled subset only);
  - Forza banding (<60 / 60-74 / >=75, null → "n/d") incl. the boundaries;
  - null regime_at_signal → the "n/d" bucket;
  - the low_confidence honesty flag (n < min_n per cell, totals included);
  - archived alerts excluded;
  - meta coverage envelope (rows, detectors present vs 17, date range);
  - the read-only endpoint (auth + envelope shape + empty warehouse);
  - the replay segment (B4-5): artifact merge, read-time low_confidence,
    graceful degrade on missing/corrupt artifact, live cells untouched.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, SignalOutcome, Stock, User
from app.services import detector_performance_service as perf

# --------------------------------------------------------------------------- #
# Seeding helpers                                                             #
# --------------------------------------------------------------------------- #

_SEQ = {"n": 0}


@pytest.fixture(autouse=True)
def _no_replay_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the replay artifact at a nonexistent tmp file by default, so
    these tests stay deterministic even when a real artifact has been
    generated in the repo. Replay tests re-point it at a written file."""
    monkeypatch.setattr(perf, "_REPLAY_ARTIFACT", tmp_path / "replay_missing.json")


def _mk_outcome(
    db: Session,
    *,
    detector: str = "volume_breakout",
    tone: str = "bull",
    strength: int | None = 80,
    regime: str | None = "bull",
    abs_hit: int = 1,
    mkt_hit: int | None = 1,
    fwd_return: float = 0.05,
    signal_date: date = date(2026, 6, 1),
    archived: bool = False,
) -> SignalOutcome:
    """One warehouse row + its backing Alert/Stock (FK + archived-join)."""
    _SEQ["n"] += 1
    k = _SEQ["n"]
    stock = Stock(ticker=f"T{k}", exchange="TST", name=f"T{k}")
    db.add(stock)
    db.flush()
    alert = Alert(
        stock_id=stock.id,
        signal_name=detector,
        signal_date=signal_date,
        trigger_price=100.0,
        snapshot=json.dumps({"tone": tone, "strength": strength}),
    )
    if archived:
        alert.archived_at = datetime.now(UTC)
    db.add(alert)
    db.flush()
    row = SignalOutcome(
        alert_id=alert.id,
        stock_id=stock.id,
        detector=detector,
        signal_date=signal_date,
        tone=tone,
        horizon_days=21,
        entry_close=100.0,
        forward_close=100.0 * (1 + fwd_return),
        fwd_return=fwd_return,
        universe_mean_fwd=0.0 if mkt_hit is not None else None,
        mkt_neutral_excess=(fwd_return if mkt_hit is not None else None),
        abs_hit=abs_hit,
        mkt_neutral_hit=mkt_hit,
        regime_at_signal=regime,
        strength=strength,
        probability=55,
    )
    db.add(row)
    return row


def _cells_by_key(cells: list[dict]) -> dict[str, dict]:
    return {c["key"]: c for c in cells}


# --------------------------------------------------------------------------- #
# Aggregation math                                                            #
# --------------------------------------------------------------------------- #

def test_hit_rates_and_avg_fwd_return(db: Session):
    """4 rows: 3 abs hits (75%), market-neutral labeled on only 2 rows (1 hit
    → 50%), avg fwd_return = mean of the four ratios in percent."""
    _mk_outcome(db, abs_hit=1, mkt_hit=1, fwd_return=0.10)
    _mk_outcome(db, abs_hit=1, mkt_hit=0, fwd_return=0.02)
    _mk_outcome(db, abs_hit=1, mkt_hit=None, fwd_return=0.04)   # no benchmark
    _mk_outcome(db, abs_hit=0, mkt_hit=None, fwd_return=-0.04)  # no benchmark
    db.commit()

    out = perf.compute_detector_performance(db)
    assert len(out["detectors"]) == 1
    total = out["detectors"][0]["total"]
    assert total["key"] == "totale"
    assert total["n"] == 4
    assert total["abs_hit_rate"] == pytest.approx(75.0)
    # Market-neutral over the 2 labeled rows only — NOT diluted by the nulls.
    assert total["mkt_neutral_hit_rate"] == pytest.approx(50.0)
    assert total["avg_fwd_return"] == pytest.approx(3.0)  # (10+2+4-4)/4 %


def test_mkt_neutral_rate_is_none_when_never_labeled(db: Session):
    """All rows without a market-neutral label → None, not a misleading 0."""
    _mk_outcome(db, mkt_hit=None)
    _mk_outcome(db, mkt_hit=None)
    db.commit()

    total = perf.compute_detector_performance(db)["detectors"][0]["total"]
    assert total["mkt_neutral_hit_rate"] is None


def test_strength_banding_boundaries(db: Session):
    """59 → <60; 60 and 74 → 60-74; 75 → >=75; null → n/d."""
    _mk_outcome(db, strength=59, abs_hit=1)
    _mk_outcome(db, strength=60, abs_hit=0)
    _mk_outcome(db, strength=74, abs_hit=1)
    _mk_outcome(db, strength=75, abs_hit=1)
    _mk_outcome(db, strength=None, abs_hit=0)
    db.commit()

    row = perf.compute_detector_performance(db)["detectors"][0]
    bands = _cells_by_key(row["by_strength"])
    assert set(bands.keys()) == {"<60", "60-74", ">=75", "n/d"}
    assert bands["<60"]["n"] == 1
    assert bands["60-74"]["n"] == 2
    assert bands["60-74"]["abs_hit_rate"] == pytest.approx(50.0)
    assert bands[">=75"]["n"] == 1
    assert bands["n/d"]["n"] == 1
    # Fixed order for stable UI columns.
    assert [c["key"] for c in row["by_strength"]] == ["<60", "60-74", ">=75", "n/d"]


def test_null_regime_goes_to_nd_bucket(db: Session):
    _mk_outcome(db, regime="bull")
    _mk_outcome(db, regime="bear")
    _mk_outcome(db, regime=None)
    db.commit()

    row = perf.compute_detector_performance(db)["detectors"][0]
    regimes = _cells_by_key(row["by_regime"])
    assert set(regimes.keys()) == {"bull", "bear", "n/d"}
    assert regimes["n/d"]["n"] == 1


def test_tone_breakdown_splits_bull_bear(db: Session):
    _mk_outcome(db, tone="bull", abs_hit=1)
    _mk_outcome(db, tone="bull", abs_hit=1)
    _mk_outcome(db, tone="bear", abs_hit=0)
    db.commit()

    row = perf.compute_detector_performance(db)["detectors"][0]
    tones = _cells_by_key(row["by_tone"])
    assert tones["bull"]["n"] == 2
    assert tones["bull"]["abs_hit_rate"] == pytest.approx(100.0)
    assert tones["bear"]["n"] == 1
    assert tones["bear"]["abs_hit_rate"] == pytest.approx(0.0)


def test_low_confidence_flag_per_cell(db: Session):
    """35 bull + 5 bear rows: the total and the bull cell clear min_n=30, the
    bear cell (n=5) is flagged low_confidence — the honesty guardrail is per
    CELL, not per detector."""
    for _ in range(35):
        _mk_outcome(db, tone="bull")
    for _ in range(5):
        _mk_outcome(db, tone="bear")
    db.commit()

    row = perf.compute_detector_performance(db)["detectors"][0]
    assert row["total"]["n"] == 40
    assert row["total"]["low_confidence"] is False
    tones = _cells_by_key(row["by_tone"])
    assert tones["bull"]["low_confidence"] is False
    assert tones["bear"]["low_confidence"] is True


def test_min_n_parameter_moves_the_flag(db: Session):
    for _ in range(10):
        _mk_outcome(db)
    db.commit()

    assert perf.compute_detector_performance(db, min_n=30)["detectors"][0][
        "total"]["low_confidence"] is True
    assert perf.compute_detector_performance(db, min_n=5)["detectors"][0][
        "total"]["low_confidence"] is False


def test_archived_alerts_excluded(db: Session):
    _mk_outcome(db, abs_hit=1)
    _mk_outcome(db, abs_hit=0, archived=True)
    db.commit()

    out = perf.compute_detector_performance(db)
    total = out["detectors"][0]["total"]
    assert total["n"] == 1                       # the archived row is invisible
    assert total["abs_hit_rate"] == pytest.approx(100.0)
    assert out["meta"]["total_rows"] == 1


def test_detectors_sorted_by_total_n_desc(db: Session):
    for _ in range(3):
        _mk_outcome(db, detector="small_det")
    for _ in range(7):
        _mk_outcome(db, detector="big_det")
    db.commit()

    out = perf.compute_detector_performance(db)
    assert [d["detector"] for d in out["detectors"]] == ["big_det", "small_det"]


def test_meta_coverage_envelope(db: Session):
    _mk_outcome(db, detector="volume_breakout", signal_date=date(2026, 3, 10))
    _mk_outcome(db, detector="sr_flip", signal_date=date(2026, 6, 20))
    db.commit()

    meta = perf.compute_detector_performance(db)["meta"]
    assert meta["total_rows"] == 2
    assert meta["n_detectors"] == 2
    assert meta["n_detectors_universe"] == 17    # the full detector universe
    assert meta["date_min"] == "2026-03-10"
    assert meta["date_max"] == "2026-06-20"
    assert meta["min_n"] == 30
    assert "computed_at" in meta


def test_empty_warehouse(db: Session):
    out = perf.compute_detector_performance(db)
    assert out["detectors"] == []
    assert out["meta"]["total_rows"] == 0
    assert out["meta"]["n_detectors"] == 0
    assert out["meta"]["date_min"] is None
    assert out["meta"]["date_max"] is None
    # No replay artifact → segment absent, honestly flagged.
    assert out["meta"]["replay_available"] is False
    assert out["replay"] is None


# --------------------------------------------------------------------------- #
# Replay segment (B4-5 artifact merge)                                        #
# --------------------------------------------------------------------------- #

def _write_replay_artifact(path: Path, *, n_total: int = 120) -> dict:
    """A minimal valid artifact: one 63d detector with a thin bear cell."""
    def cell(key: str, n: int, hit: float = 55.0) -> dict:
        return {"key": key, "n": n, "abs_hit_rate": hit,
                "mkt_neutral_hit_rate": 49.0, "avg_fwd_return": 1.5}

    payload = {
        "version": "1",
        "generated_by": "app.scripts.backfill_replay_outcomes",
        "source": "replay",
        "generated_at": "2026-07-01T00:00:00+00:00",
        "params": {"years": 10.0, "step": 42, "window": 500},
        "universe_stocks": 300,
        "n_signals": n_total,
        "date_min": "2016-07-04",
        "date_max": "2026-03-15",
        "detectors": {
            "trend_pullback": {
                "total": cell("totale", n_total),
                "by_regime": [cell("bull", n_total - 10), cell("bear", 10)],
                "by_tone": [cell("bull", n_total)],
                "by_strength": [cell("60-74", n_total - 5), cell(">=75", 5)],
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_replay_segment_merged_with_read_time_low_confidence(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    artifact = tmp_path / "replay.json"
    _write_replay_artifact(artifact)
    monkeypatch.setattr(perf, "_REPLAY_ARTIFACT", artifact)
    _mk_outcome(db, detector="volume_breakout")  # one live row, untouched
    db.commit()

    out = perf.compute_detector_performance(db)
    # Live side untouched by the replay merge.
    assert [d["detector"] for d in out["detectors"]] == ["volume_breakout"]
    assert out["meta"]["total_rows"] == 1
    assert out["meta"]["replay_available"] is True

    r = out["replay"]
    assert r["n_signals"] == 120
    assert r["generated_at"] == "2026-07-01T00:00:00+00:00"
    assert r["date_min"] == "2016-07-04"
    assert r["params"]["years"] == 10.0
    row = r["detectors"][0]
    assert row["detector"] == "trend_pullback"
    # low_confidence stamped at read time against min_n (default 30).
    assert row["total"]["n"] == 120
    assert row["total"]["low_confidence"] is False
    regimes = _cells_by_key(row["by_regime"])
    assert regimes["bear"]["n"] == 10
    assert regimes["bear"]["low_confidence"] is True
    bands = _cells_by_key(row["by_strength"])
    assert bands[">=75"]["low_confidence"] is True


def test_replay_low_confidence_follows_min_n(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    artifact = tmp_path / "replay.json"
    _write_replay_artifact(artifact, n_total=120)
    monkeypatch.setattr(perf, "_REPLAY_ARTIFACT", artifact)

    out = perf.compute_detector_performance(db, min_n=200)
    assert out["replay"]["detectors"][0]["total"]["low_confidence"] is True


def test_corrupt_or_empty_replay_artifact_degrades_gracefully(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    artifact = tmp_path / "replay.json"
    artifact.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(perf, "_REPLAY_ARTIFACT", artifact)
    out = perf.compute_detector_performance(db)
    assert out["meta"]["replay_available"] is False
    assert out["replay"] is None

    # Valid JSON but no detectors → same degrade (nothing to render).
    artifact.write_text(json.dumps({"detectors": {}}), encoding="utf-8")
    out = perf.compute_detector_performance(db)
    assert out["meta"]["replay_available"] is False
    assert out["replay"] is None


# --------------------------------------------------------------------------- #
# Endpoint                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_detector_performance_endpoint_requires_auth():
    c = TestClient(app, raise_server_exceptions=True)
    r = c.get("/api/platform/detector-performance")
    assert r.status_code in (401, 403)


def test_detector_performance_endpoint_shape_empty(client: TestClient):
    """Empty warehouse → 200 with an honest zeroed meta, not a 404/500."""
    r = client.get("/api/platform/detector-performance")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"meta", "detectors", "replay"}
    assert body["detectors"] == []
    assert body["meta"]["total_rows"] == 0
    assert body["meta"]["n_detectors_universe"] == 17
    assert body["meta"]["replay_available"] is False
    assert body["replay"] is None


def test_detector_performance_endpoint_returns_replay_segment(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """The replay block passes response_model validation end-to-end."""
    artifact = tmp_path / "replay.json"
    _write_replay_artifact(artifact)
    monkeypatch.setattr(perf, "_REPLAY_ARTIFACT", artifact)

    r = client.get("/api/platform/detector-performance")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["replay_available"] is True
    row = body["replay"]["detectors"][0]
    assert row["detector"] == "trend_pullback"
    assert set(row["total"].keys()) == {
        "key", "n", "abs_hit_rate", "mkt_neutral_hit_rate",
        "avg_fwd_return", "low_confidence",
    }


def test_detector_performance_endpoint_returns_cube(client: TestClient, db: Session):
    for _ in range(31):
        _mk_outcome(db, tone="bull", strength=80, regime="bull")
    _mk_outcome(db, tone="bear", strength=55, regime=None)
    db.commit()

    r = client.get("/api/platform/detector-performance")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["total_rows"] == 32
    row = body["detectors"][0]
    assert set(row.keys()) == {
        "detector", "total", "by_regime", "by_tone", "by_strength",
    }
    assert set(row["total"].keys()) == {
        "key", "n", "abs_hit_rate", "mkt_neutral_hit_rate",
        "avg_fwd_return", "low_confidence",
    }
    regimes = {c["key"]: c for c in row["by_regime"]}
    assert regimes["n/d"]["n"] == 1
    assert regimes["n/d"]["low_confidence"] is True
    bands = {c["key"]: c for c in row["by_strength"]}
    assert bands[">=75"]["n"] == 31
    assert bands[">=75"]["low_confidence"] is False
    assert bands["<60"]["n"] == 1


def test_detector_performance_endpoint_validates_min_n(client: TestClient):
    assert client.get("/api/platform/detector-performance?min_n=0").status_code == 422
