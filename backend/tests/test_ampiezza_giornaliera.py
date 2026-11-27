"""FA-188, ondata A: l'ampiezza di mercato si archivia giorno per giorno."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select

from app.models.ampiezza_giornaliera import UNIVERSO, AmpiezzaGiornaliera
from app.services import market_stats_service as ms

GLOBALE = {"stocks_total": 1018, "advancers": 738, "decliners": 271, "pct_above_ema50": 46.7,
           "pct_above_ema200": 49.5, "rsi_overbought_count": 27, "rsi_oversold_count": 26,
           "avg_change_pct": 0.86}
INDICI = [
    {"code": "SP500", "n": 503, "advancers": 400, "decliners": 100, "pct_above_ema50": 60.0,
     "pct_above_ema200": 55.0, "rsi_overbought_count": 10, "rsi_oversold_count": 3, "avg_change_pct": 1.1},
    {"code": "VUOTO", "n": 0},
]


def test_le_righe_sono_l_universo_e_gli_indici_con_titoli():
    righe = ms._righe_ampiezza(GLOBALE, INDICI, date(2026, 11, 27), datetime(2026, 11, 27, tzinfo=UTC))
    assert [r["ambito"] for r in righe] == [UNIVERSO, "SP500"]
    assert righe[0]["titoli"] == 1018 and righe[0]["sopra_ema200_pct"] == 49.5
    assert righe[1]["avanzano"] == 400


def test_la_seconda_scansione_del_giorno_sostituisce_la_prima(db):
    assert ms.archivia_ampiezza(db, GLOBALE, INDICI) == 2
    db.commit()
    assert ms.archivia_ampiezza(db, {**GLOBALE, "advancers": 1}, INDICI) == 2
    db.commit()
    righe = db.execute(select(AmpiezzaGiornaliera).where(AmpiezzaGiornaliera.ambito == UNIVERSO)).scalars().all()
    assert len(righe) == 1 and righe[0].avanzano == 1


def test_un_guasto_dell_archivio_non_tocca_lo_snapshot(db, monkeypatch):
    """Il savepoint: l'archivio fallisce, la sessione resta usabile."""
    monkeypatch.setattr(ms, "_righe_ampiezza", lambda *a: [{"giorno": None}])
    assert ms.archivia_ampiezza(db, GLOBALE, INDICI) == 0
    # la sessione e' ancora sana
    assert db.execute(select(AmpiezzaGiornaliera)).scalars().all() == []


def test_lo_snapshot_scrive_anche_l_archivio(db):
    ms.recompute_snapshot(db)
    righe = db.execute(select(AmpiezzaGiornaliera)).scalars().all()
    assert [r.ambito for r in righe] == [UNIVERSO]
