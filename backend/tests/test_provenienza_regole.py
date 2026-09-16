"""Ogni osservazione nuova dice con quali regole e' nata; lo storico dice di no.

Negli 8.554 alert del motore nessuno snapshot portava una versione: una
modifica al motore mescolava in silenzio le popolazioni. Questi test fissano
che la versione si SCRIVE, e che lo storico resti dichiaratamente senza.
"""
import ast
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from app.core import provenance
from app.models import Alert, OhlcvDaily, SignalOutcome, Stock, StockSetup
from app.models.stock_setup import CONVERSION_LEGACY, STATUS_ACTIVE, STATUS_CONVERTED
from app.services import detector_performance_service, setup_service
from app.services import signal_outcome_service as sos
from app.signals.signal_scan_service import evaluate_signals


def test_il_modulo_e_una_foglia_e_le_versioni_entrano_nelle_colonne() -> None:
    albero = ast.parse(Path(provenance.__file__).read_text(encoding="utf-8"))
    importati = [
        n.module if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(albero) if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [None])
    ]
    assert all(not (m or "").startswith("app") for m in importati), importati
    lunghezza = SignalOutcome.__table__.c["method_version"].type.length
    for v in (provenance.EMISSION_RULES_VERSION, provenance.SETUP_CONVERSION_VERSION,
              provenance.OUTCOME_METHOD_VERSION):
        assert v and len(v) <= lunghezza
    assert StockSetup.__table__.c["conversion_version"].type.length >= len(
        provenance.SETUP_CONVERSION_VERSION)


def test_lo_snapshot_di_un_alert_porta_regole_e_build(db, monkeypatch) -> None:
    base = "app.signals.signal_scan_service.settings."
    monkeypatch.setattr(base + "signal_min_confidence", 0)
    monkeypatch.setattr(base + "signal_require_follow_through", False)
    monkeypatch.setattr(base + "signal_require_trend_alignment", False)
    monkeypatch.setattr(base + "signal_max_age_days", 365)
    monkeypatch.setenv("GIT_SHA", "abc1234")
    s = Stock(ticker="PROVA", exchange="NYSE", name="P", country="US")
    db.add(s)
    db.flush()
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                 "close": 110, "volume": 4000})
    assert evaluate_signals(db, s, pd.DataFrame(rows)) >= 1
    for a in db.execute(select(Alert).where(Alert.stock_id == s.id)).scalars():
        prov = json.loads(a.snapshot)["provenance"]
        assert prov == {"emission": provenance.EMISSION_RULES_VERSION, "build": "abc1234"}


def test_senza_build_la_chiave_resta_e_dice_none(monkeypatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    assert provenance.emission_stamp()["build"] is None


def test_la_riga_d_esito_porta_il_metodo(db, monkeypatch) -> None:
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 2)
    s = Stock(ticker="PROVB", exchange="NYSE", name="P", country="US")
    db.add(s)
    db.flush()
    for i in range(6):
        d = date(2026, 1, 5) + timedelta(days=i)
        db.add(OhlcvDaily(stock_id=s.id, date=d, open=10, high=10, low=10,
                          close=10 + i, volume=1))
    db.add(Alert(stock_id=s.id, signal_name="x", signal_date=date(2026, 1, 5),
                 trigger_price=10, snapshot=json.dumps({"tone": "bull"})))
    db.commit()
    assert sos.mature_outcomes(db) == 1
    riga = db.execute(select(SignalOutcome)).scalar_one()
    assert riga.method_version == provenance.OUTCOME_METHOD_VERSION


def test_conversione_ed_esito_del_setup_portano_la_versione(db) -> None:
    s = Stock(ticker="PROVC", exchange="NYSE", name="P", country="US")
    db.add(s)
    db.flush()
    row = StockSetup(stock_id=s.id, detector="d", tone="bull", proximity=0.8,
                     convenience=70, missing="-", status=STATUS_ACTIVE, shortlisted=True,
                     first_seen_at=datetime(2026, 9, 1, tzinfo=UTC),
                     last_seen_at=datetime(2026, 9, 1, tzinfo=UTC),
                     first_seen_bar=date(2026, 9, 1))
    a = Alert(stock_id=s.id, signal_name="d", signal_date=date(2026, 9, 3),
              trigger_price=1, snapshot=json.dumps({"tone": "bull"}))
    db.add_all([row, a])
    db.flush()
    setup_service.convert_setups_for_event(db, a, signal_date=date(2026, 9, 3),
                                           tone="bull", price=1.0)
    assert row.conversion_version == provenance.SETUP_CONVERSION_VERSION

    # Uno storico: la versione della conversione non esiste, e lo si conta come tale.
    db.add(StockSetup(stock_id=s.id, detector="e", tone="bull", proximity=0.8,
                      convenience=70, missing="-", status=STATUS_CONVERTED,
                      shortlisted=True, conversion_source=CONVERSION_LEGACY,
                      first_seen_at=datetime(2026, 8, 1, tzinfo=UTC),
                      last_seen_at=datetime(2026, 8, 1, tzinfo=UTC),
                      resolved_at=datetime(2026, 8, 5, tzinfo=UTC)))
    db.commit()
    assert setup_service.conversion_stats(db)["conversion_versions"] == {
        provenance.SETUP_CONVERSION_VERSION: 1, "non registrata": 1,
    }


def test_l_esito_storico_copiato_dal_magazzino_eredita_il_suo_metodo(db) -> None:
    s = Stock(ticker="PROVD", exchange="NYSE", name="P", country="US")
    db.add(s)
    db.flush()
    a = Alert(stock_id=s.id, signal_name="d", signal_date=date(2026, 8, 30),
              trigger_price=1, snapshot=json.dumps({"tone": "bull"}))
    db.add(a)
    db.flush()
    # Riga del magazzino maturata prima che il metodo si scrivesse: NULL.
    db.add(SignalOutcome(alert_id=a.id, stock_id=s.id, detector="d",
                         signal_date=date(2026, 8, 30), tone="bull", horizon_days=21,
                         entry_close=1, forward_close=1.1, fwd_return=0.1, abs_hit=1,
                         mkt_neutral_hit=1))
    row = StockSetup(stock_id=s.id, detector="d", tone="bull", proximity=0.8,
                     convenience=70, missing="-", status=STATUS_CONVERTED, shortlisted=True,
                     conversion_source=CONVERSION_LEGACY, converted_alert_id=a.id,
                     first_seen_at=datetime(2026, 8, 20, tzinfo=UTC),
                     last_seen_at=datetime(2026, 8, 20, tzinfo=UTC),
                     resolved_at=datetime(2026, 9, 1, tzinfo=UTC))
    db.add(row)
    db.commit()
    assert sos.mature_setup_outcomes(db) == 1
    # Non gli si attribuisce il metodo di oggi.
    assert row.outcome_matured_at is not None
    assert row.outcome_method_version is None


def test_le_prestazioni_contano_gli_esiti_per_metodo(db) -> None:
    s = Stock(ticker="PROVE", exchange="NYSE", name="P", country="US")
    db.add(s)
    db.flush()
    for i, versione in enumerate([None, None, provenance.OUTCOME_METHOD_VERSION]):
        a = Alert(stock_id=s.id, signal_name="d", signal_date=date(2026, 8, 1),
                  trigger_price=1, snapshot="{}")
        db.add(a)
        db.flush()
        db.add(SignalOutcome(alert_id=a.id, stock_id=s.id, detector="d",
                             signal_date=date(2026, 8, 1) + timedelta(days=i), tone="bull",
                             horizon_days=21, entry_close=1, forward_close=1.1,
                             fwd_return=0.1, abs_hit=1, mkt_neutral_hit=1,
                             method_version=versione))
    db.commit()
    meta = detector_performance_service.compute_detector_performance(db)["meta"]
    assert meta["method_versions"] == {"non registrata": 2, provenance.OUTCOME_METHOD_VERSION: 1}
