"""`finance_alert_data_age_days` dice giorni VERI anche su SQLite.

Le tre eta' erano SQL Postgres: `CURRENT_DATE - MAX(date)` e
`MAX(triggered_at)::date`. Su SQLite — sviluppo e gate CI, dove il log lo
stampava a ogni avvio — il cast `::` falliva e la sottrazione fra due
stringhe-data rendeva zero. Zero giorni e' la lettura piu' tranquillizzante
possibile di un dato fermo.
"""

from datetime import UTC, datetime, timedelta

from loguru import logger

from app.core import app_metrics
from app.models import Alert, OhlcvDaily, Stock


def _eta(dataset: str) -> float:
    return app_metrics.DATA_AGE_DAYS.labels(dataset=dataset)._value.get()


def test_le_eta_sono_giorni_veri_su_sqlite(db):
    oggi = datetime.now(UTC).date()
    s = Stock(ticker="ETA", exchange="NASDAQ", name="Eta", country="US")
    db.add(s)
    db.flush()
    db.add(OhlcvDaily(stock_id=s.id, date=oggi - timedelta(days=3),
                      open=1, high=1, low=1, close=1, volume=1))
    db.add(Alert(stock_id=s.id, signal_name="trend_pullback", trigger_price=1.0,
                 snapshot="{}", signal_date=oggi - timedelta(days=3),
                 triggered_at=datetime.now(UTC) - timedelta(days=2)))
    db.commit()
    # Una sentinella: il gauge e' globale al processo, e un valore lasciato da
    # un altro test renderebbe vere le asserzioni sotto senza che girasse nulla.
    for d in ("ohlcv_daily", "alerts", "macro_observations"):
        app_metrics.DATA_AGE_DAYS.labels(dataset=d).set(-1)

    righe: list[str] = []
    sink = logger.add(lambda m: righe.append(str(m)), level="WARNING")
    try:
        app_metrics.refresh_data_health_gauges(db)
    finally:
        logger.remove(sink)

    assert _eta("ohlcv_daily") == 3.0
    assert _eta("alerts") == 2.0
    assert not [r for r in righe if "age refresh failed" in r], righe
    # ⚠️ Una tabella vuota non scrive un'eta': zero direbbe «dato di oggi».
    assert _eta("macro_observations") == -1
