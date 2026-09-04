"""The data-health gauges behind the "Finance-Alert · Salute" dashboard.

Two properties matter and neither is obvious from reading the code:

1. They must NEVER raise. They run at the end of a scan that has already
   committed real alerts, so a failed metrics refresh must not turn a
   successful scan into a failed one.
2. A failed query must leave the PREVIOUS reading standing rather than writing
   a false zero. A gauge that drops to 0 on error looks exactly like "the
   problem went away", which is worse than no gauge.
"""
from sqlalchemy import text

from app.core import app_metrics


def _value(gauge, **labels):
    g = gauge.labels(**labels) if labels else gauge
    return g._value.get()


class TestDataHealthGauges:
    def test_it_populates_from_a_real_session(self, db):
        app_metrics.refresh_data_health_gauges(db)
        # The catalogue count is the one gauge with no dependency on there
        # being any market data at all.
        assert _value(app_metrics.CATALOG_STOCKS) >= 0

    def test_api_key_gauges_are_strictly_0_or_1(self, db):
        app_metrics.refresh_data_health_gauges(db)
        for provider in ("fred", "finnhub", "marketaux"):
            v = _value(app_metrics.API_KEY_CONFIGURED, provider=provider)
            assert v in (0.0, 1.0), f"{provider}={v}"

    def test_a_broken_database_does_not_raise(self):
        """The whole point of the isolation: one unusable session must produce
        log lines, not an exception reaching the scan."""
        class _Dead:
            def execute(self, *a, **k):
                raise RuntimeError("database is gone")

        app_metrics.refresh_data_health_gauges(_Dead())   # must not raise

    def test_a_broken_query_leaves_the_previous_value_alone(self):
        app_metrics.CATALOG_STOCKS.set(999.0)

        class _Dead:
            def execute(self, *a, **k):
                raise RuntimeError("boom")

        app_metrics.refresh_data_health_gauges(_Dead())
        assert _value(app_metrics.CATALOG_STOCKS) == 999.0


class TestBasisBreakGauge:
    def test_it_counts_and_returns(self, db):
        n = app_metrics.refresh_basis_breaks_gauge(db)
        assert n is None or n >= 0
        if n is not None:
            assert _value(app_metrics.BASIS_BREAKS) == float(n)

    def test_failure_returns_none_and_keeps_the_old_reading(self):
        app_metrics.BASIS_BREAKS.set(7.0)

        class _Dead:
            def execute(self, *a, **k):
                raise RuntimeError("boom")

        assert app_metrics.refresh_basis_breaks_gauge(_Dead()) is None
        assert _value(app_metrics.BASIS_BREAKS) == 7.0

    def test_it_sees_a_break_that_is_actually_there(self, db):
        """Guards the wiring, not the detector (which has its own tests): a
        20:1 drop with volume moving inversely must be counted."""
        from app.models import Stock

        s = Stock(ticker="ZZTEST", name="T", exchange="TEST", currency="USD")
        db.add(s)
        db.flush()
        rows = []
        for i in range(40):
            px, vol = (100.0, 1_000) if i < 20 else (5.0, 20_000)
            rows.append(
                {"sid": s.id, "d": f"2026-01-{i + 1:02d}", "c": px, "v": vol})
        for r in rows:
            db.execute(
                text("INSERT INTO ohlcv_daily (stock_id, date, open, high, low, close, volume)"
                     " VALUES (:sid, :d, :c, :c, :c, :c, :v)"), r)
        db.flush()
        n = app_metrics.refresh_basis_breaks_gauge(db)
        assert n is not None and n >= 1
