import json
from datetime import UTC, date, datetime

import pandas as pd

from app.models import Alert, SignalOutcome, Stock
from app.signals.signal_scan_service import evaluate_signals


def _confirmed_df():
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                 "close": 110, "volume": 4000})
    return pd.DataFrame(rows)


def _confirmed_then_stale_df():
    """The breakout fires on 2026-05-01, then 10 calmer bars follow so that
    bar's signal_date is ~10 days behind the latest bar."""
    df = _confirmed_df()
    extra = pd.DataFrame([
        {"date": f"2026-05-{d:02d}", "open": 110, "high": 110.5, "low": 109.5,
         "close": 110, "volume": 1000} for d in range(2, 12)
    ])
    return pd.concat([df, extra], ignore_index=True)


def test_stale_signal_skipped_by_recency_guard(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_max_age_days", 3)
    s = Stock(ticker="STALE_BO", exchange="NASDAQ", name="Stale", country="US")
    db.add(s); db.flush()
    evaluate_signals(db, s, _confirmed_then_stale_df())
    db.commit()
    # The breakout's signal_date (2026-05-01) is 10 days before the last bar
    # (2026-05-11) -> older than max_age=3 -> the volume_breakout is skipped.
    vb = db.query(Alert).filter(Alert.stock_id == s.id,
                                Alert.signal_name == "volume_breakout").first()
    assert vb is None


def test_recent_signal_kept_with_large_max_age(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_max_age_days", 365)
    s = Stock(ticker="FRESH_BO", exchange="NASDAQ", name="Fresh", country="US")
    db.add(s); db.flush()
    evaluate_signals(db, s, _confirmed_then_stale_df())
    db.commit()
    vb = db.query(Alert).filter(Alert.stock_id == s.id,
                                Alert.signal_name == "volume_breakout").first()
    assert vb is not None   # 10 days <= 365 -> kept


def test_creates_signal_alert_above_threshold(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_follow_through", False)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_trend_alignment", False)
    s = Stock(ticker="BRK_SIG", exchange="NASDAQ", name="BO Co", country="US")
    db.add(s); db.flush()
    n = evaluate_signals(db, s, _confirmed_df())
    db.commit()
    assert n >= 1  # at least volume_breakout fires; other detectors may also fire
    a = db.query(Alert).filter(Alert.stock_id == s.id,
                               Alert.signal_name == "volume_breakout").first()
    assert a is not None and a.signal_date == date(2026, 5, 1)


def test_dedup_same_signal_date(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_follow_through", False)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_trend_alignment", False)
    s = Stock(ticker="BRK_SIG2", exchange="NASDAQ", name="BO2", country="US")
    db.add(s); db.flush()
    df = _confirmed_df()
    first_run = evaluate_signals(db, s, df)
    assert first_run >= 1  # at least volume_breakout fires; other detectors may also fire
    db.commit()
    assert evaluate_signals(db, s, df) == 0   # same (stock, name, signal_date) -> skip
    db.commit()


def test_below_threshold_not_emitted(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 101)
    s = Stock(ticker="BRK_SIG3", exchange="NASDAQ", name="BO3", country="US")
    db.add(s); db.flush()
    assert evaluate_signals(db, s, _confirmed_df()) == 0


# --- Cooldown + refresh dedup ---------------------------------------------

def _relax(monkeypatch, *, cooldown=14):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_follow_through", False)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_trend_alignment", False)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_dedup_cooldown_days", cooldown)


def _seed_prior(db, stock, *, signal_date, tone="bull", price=50.0, archived=False,
                first_emitted=None):
    """Pre-existing volume_breakout alert to exercise the cooldown branch.
    `first_emitted` (ISO string) stamps snapshot.first_emitted_at so the
    chain-lifetime cap can be exercised on a seeded chain."""
    snap = {"tone": tone, "confidence": 70}
    if first_emitted is not None:
        snap["first_emitted_at"] = first_emitted
    a = Alert(
        stock_id=stock.id, trigger_price=price, signal_date=signal_date,
        signal_name="volume_breakout",
        snapshot=json.dumps(snap),
        archived_at=datetime.now(UTC) if archived else None,
    )
    db.add(a); db.flush()
    return a


def _seed_outcome(db, alert):
    """Matured SignalOutcome row for `alert` (freeze post-esito substrate)."""
    db.add(SignalOutcome(
        alert_id=alert.id, stock_id=alert.stock_id, detector=alert.signal_name,
        signal_date=alert.signal_date, tone="bull", horizon_days=10,
        entry_close=50.0, forward_close=55.0, fwd_return=0.1, abs_hit=1,
    ))
    db.flush()


def _vb_rows(db, stock):
    return db.query(Alert).filter(
        Alert.stock_id == stock.id, Alert.signal_name == "volume_breakout",
    ).all()


def test_cooldown_refreshes_existing_alert_in_place(db, monkeypatch):
    """A new detection within the cooldown window of an active same-signal alert
    refreshes it (price + dates) instead of inserting a near-duplicate."""
    _relax(monkeypatch)
    s = Stock(ticker="CD_REFRESH", exchange="NASDAQ", name="Cd", country="US")
    db.add(s); db.flush()
    prior = _seed_prior(db, s, signal_date=date(2026, 4, 28), price=50.0)
    db.commit()
    evaluate_signals(db, s, _confirmed_df())  # volume_breakout signal_date 2026-05-01
    db.commit()
    rows = _vb_rows(db, s)
    assert len(rows) == 1                       # refreshed, not duplicated
    assert rows[0].id == prior.id
    assert rows[0].signal_date == date(2026, 5, 1)   # anchor moved forward
    assert float(rows[0].trigger_price) == 110.0     # refreshed to last close
    # Provenance: the refresh is a post-creation amendment → amended_at is set,
    # and the ORIGINAL emission time is preserved (the seeded prior had no
    # first_emitted_at, so it falls back to the prior's triggered_at).
    snap = json.loads(rows[0].snapshot)
    assert snap.get("amended_at") is not None
    assert snap.get("first_emitted_at") is not None
    assert (snap.get("amend_count") or 0) >= 1


def test_new_alert_pins_first_emitted_at_without_amendment(db, monkeypatch):
    """A freshly-created alert carries first_emitted_at and is NOT marked amended."""
    _relax(monkeypatch)
    s = Stock(ticker="PROV_NEW", exchange="NASDAQ", name="Prov", country="US")
    db.add(s); db.flush()
    evaluate_signals(db, s, _confirmed_df())
    db.commit()
    a = db.query(Alert).filter(Alert.stock_id == s.id,
                               Alert.signal_name == "volume_breakout").first()
    snap = json.loads(a.snapshot)
    assert snap.get("first_emitted_at") is not None
    assert "amended_at" not in snap


def test_cooldown_respects_archived_alert(db, monkeypatch):
    """An archived same-signal alert within the window suppresses re-creation:
    the next scan must not resurrect what the user archived."""
    _relax(monkeypatch)
    s = Stock(ticker="CD_ARCH", exchange="NASDAQ", name="Cd", country="US")
    db.add(s); db.flush()
    prior = _seed_prior(db, s, signal_date=date(2026, 4, 28), price=50.0, archived=True)
    db.commit()
    evaluate_signals(db, s, _confirmed_df())
    db.commit()
    rows = _vb_rows(db, s)
    assert len(rows) == 1                       # not resurrected
    assert rows[0].id == prior.id
    assert rows[0].archived_at is not None      # left archived, untouched
    assert float(rows[0].trigger_price) == 50.0  # not refreshed


# --- Freeze post-esito ------------------------------------------------------

def test_matured_prior_is_frozen_and_new_row_inserted(db, monkeypatch):
    """Once the prior alert's outcome matured, the refresh must NOT amend it:
    the Esito describes the frozen bar. The re-detection inserts a NEW row."""
    _relax(monkeypatch)
    s = Stock(ticker="CD_FROZEN", exchange="NASDAQ", name="Cd", country="US")
    db.add(s); db.flush()
    prior = _seed_prior(db, s, signal_date=date(2026, 4, 28), price=50.0)
    _seed_outcome(db, prior)
    db.commit()
    evaluate_signals(db, s, _confirmed_df())  # volume_breakout signal_date 2026-05-01
    db.commit()
    rows = _vb_rows(db, s)
    assert len(rows) == 2                            # new row, prior NOT refreshed
    frozen = next(r for r in rows if r.id == prior.id)
    assert frozen.signal_date == date(2026, 4, 28)   # anchor frozen
    assert float(frozen.trigger_price) == 50.0       # price frozen
    assert "amended_at" not in json.loads(frozen.snapshot)
    fresh = next(r for r in rows if r.id != prior.id)
    assert fresh.signal_date == date(2026, 5, 1)     # the re-detection, own row
    assert "amended_at" not in json.loads(fresh.snapshot)


def test_same_bar_redetected_after_maturation_creates_nothing(db, monkeypatch):
    """Re-reading the SAME event after its outcome matured is not a new event.

    The defect this closes (FA-051) was 668 excess rows across 9,034 alerts —
    7.4% of the warehouse, 596 of them identical to the cent. The freeze guard
    dropped out of the WHOLE dedup block once the outcome existed, so the
    detection fell through to the insert arm and minted a row on every SCAN
    pass — not every day: CPRX collected 8 in a single day, all at 31.49.

    The freeze itself stays and is right: the Esito describes the frozen bar
    and price, and amending them would make the outcome column lie. What was
    wrong is that freezing meant "insert instead of amend" rather than "do
    nothing"."""
    _relax(monkeypatch)
    s = Stock(ticker="CD_SAMEDAY", exchange="NASDAQ", name="Cd", country="US")
    db.add(s); db.flush()
    # Same bar the volume_breakout in _confirmed_df() stamps.
    prior = _seed_prior(db, s, signal_date=date(2026, 5, 1), price=50.0)
    _seed_outcome(db, prior)
    db.commit()
    evaluate_signals(db, s, _confirmed_df())
    db.commit()
    rows = _vb_rows(db, s)
    assert len(rows) == 1                        # no new row
    assert rows[0].id == prior.id
    assert rows[0].signal_date == date(2026, 5, 1)
    assert float(rows[0].trigger_price) == 50.0  # frozen, not refreshed
    assert "amended_at" not in json.loads(rows[0].snapshot)


def test_rescanning_the_same_matured_event_is_idempotent(db, monkeypatch):
    """FA-051's closure criterion, in the shape the defect actually took: the
    scan runs several times a day and each pass added a row. Three passes must
    leave exactly one."""
    _relax(monkeypatch)
    s = Stock(ticker="CD_IDEMP", exchange="NASDAQ", name="Cd", country="US")
    db.add(s); db.flush()
    prior = _seed_prior(db, s, signal_date=date(2026, 5, 1), price=50.0)
    _seed_outcome(db, prior)
    db.commit()
    for _ in range(3):
        evaluate_signals(db, s, _confirmed_df())
        db.commit()
    assert len(_vb_rows(db, s)) == 1


def test_unmatured_prior_still_amended(db, monkeypatch):
    """No outcome row yet → the living-setup refresh amends in place as before
    (the other side of the freeze boundary)."""
    _relax(monkeypatch)
    s = Stock(ticker="CD_LIVE", exchange="NASDAQ", name="Cd", country="US")
    db.add(s); db.flush()
    prior = _seed_prior(db, s, signal_date=date(2026, 4, 28), price=50.0)
    db.commit()
    evaluate_signals(db, s, _confirmed_df())
    db.commit()
    rows = _vb_rows(db, s)
    assert len(rows) == 1 and rows[0].id == prior.id
    assert rows[0].signal_date == date(2026, 5, 1)   # amended forward


# --- Chain lifetime cap -------------------------------------------------------

def test_chain_dies_past_lifetime_cap(db, monkeypatch):
    """A chain older than signal_chain_max_age_days stops refreshing: no amend
    AND no new row — the persistent condition must not re-arm the cooldown
    forever."""
    _relax(monkeypatch)
    monkeypatch.setattr(
        "app.signals.signal_scan_service.settings.signal_chain_max_age_days", 28)
    s = Stock(ticker="CD_CAP", exchange="NASDAQ", name="Cd", country="US")
    db.add(s); db.flush()
    # sig_date will be 2026-05-01; first emitted 2026-04-02 → 29 days > 28.
    prior = _seed_prior(db, s, signal_date=date(2026, 4, 28), price=50.0,
                        first_emitted="2026-04-02T09:00:00+00:00")
    db.commit()
    evaluate_signals(db, s, _confirmed_df())
    db.commit()
    rows = _vb_rows(db, s)
    assert len(rows) == 1 and rows[0].id == prior.id   # chain died: no new row
    assert rows[0].signal_date == date(2026, 4, 28)    # not amended either
    assert float(rows[0].trigger_price) == 50.0


def test_chain_still_refreshes_at_exact_cap(db, monkeypatch):
    """Boundary: (signal_date - first_emitted) == cap days is NOT past the cap
    (strictly greater kills the chain) → refresh proceeds."""
    _relax(monkeypatch)
    monkeypatch.setattr(
        "app.signals.signal_scan_service.settings.signal_chain_max_age_days", 28)
    s = Stock(ticker="CD_CAP_OK", exchange="NASDAQ", name="Cd", country="US")
    db.add(s); db.flush()
    # sig_date 2026-05-01; first emitted 2026-04-03 → exactly 28 days.
    prior = _seed_prior(db, s, signal_date=date(2026, 4, 28), price=50.0,
                        first_emitted="2026-04-03T09:00:00+00:00")
    db.commit()
    evaluate_signals(db, s, _confirmed_df())
    db.commit()
    rows = _vb_rows(db, s)
    assert len(rows) == 1 and rows[0].id == prior.id
    assert rows[0].signal_date == date(2026, 5, 1)     # amended forward
    snap = json.loads(rows[0].snapshot)
    assert snap.get("first_emitted_at") == "2026-04-03T09:00:00+00:00"  # preserved


def test_new_alert_after_cooldown_gap(db, monkeypatch):
    """A detection long after the prior one (outside the window) is a genuinely
    new occurrence -> a fresh alert is inserted."""
    _relax(monkeypatch)
    s = Stock(ticker="CD_GAP", exchange="NASDAQ", name="Cd", country="US")
    db.add(s); db.flush()
    _seed_prior(db, s, signal_date=date(2026, 1, 1), price=50.0)  # ~120d before
    db.commit()
    evaluate_signals(db, s, _confirmed_df())
    db.commit()
    rows = _vb_rows(db, s)
    assert len(rows) == 2                       # old + new (gap exceeds cooldown)


def test_setup_records_the_evaluated_bar_with_its_levels(db, monkeypatch):
    from app.models import StockSetup
    from app.signals.setups.base import SetupMatch

    stock = Stock(ticker="SNAPSHOT", exchange="KRX", name="Snapshot", currency="KRW")
    db.add(stock)
    db.flush()
    match = SetupMatch(detector="trend_pullback", tone="bull", proximity=0.8,
                       missing="waiting", factors={"trend_strength": 0.9}, annotations={"levels": [{"label": "EMA50", "price": 111}]})
    monkeypatch.setattr("app.signals.signal_scan_service.detect_signals_and_setups",
                        lambda *args, **kwargs: ([], [match]))
    bars = _confirmed_df()
    evaluate_signals(db, stock, bars)
    db.flush()
    row = db.query(StockSetup).filter_by(stock_id=stock.id).one()
    first_id, opening_bar = row.id, row.first_seen_bar
    assert json.loads(row.annotations_json)["evaluation"] == {
        "bar_date": "2026-05-01", "close": 110.0, "currency": "KRW",
    }
    # A later evaluation updates its snapshot, not the episode's opening bar.
    bars.loc[bars.index[-1], ["date", "close"]] = ["2026-05-02", 109]
    evaluate_signals(db, stock, bars)
    db.flush()
    assert row.id == first_id and row.first_seen_bar == opening_bar
    annotations = json.loads(row.annotations_json)
    assert annotations["evaluation"]["bar_date"] == "2026-05-02"
    assert annotations["evaluation"]["close"] == 109
    assert annotations["levels"] == match.annotations["levels"]
    assert "evaluation" not in match.annotations
# ─── Il PREZZO della prima emissione, conservato come l'istante ────────────
#
# ⚠️ Un alert e' una riga viva: finche' il segnale persiste, ogni scansione lo
# rivede e riscrive `trigger_price` con la chiusura corrente. Misurato in
# produzione il 2026-09-18: 80% degli alert ha almeno una revisione, uno ne ha
# 103, e nel 18% dei casi il prezzo mostrato dista oltre il 2% dalla chiusura
# della barra del segnale. Su FICO il box «prezzo trigger» diceva 985,39, che
# e' la chiusura dell'11 settembre, accanto a una data segnale del 4 — mentre
# la chiusura vera del 4 era 932,26.
#
# `first_emitted_at` gia' conservava l'ISTANTE della prima emissione; il
# PREZZO di quel momento non era conservato da nessuna parte, e una volta
# sovrascritto non era piu' recuperabile dall'alert. Ora lo e'.

def test_un_alert_nuovo_conserva_il_prezzo_della_prima_emissione(db, monkeypatch):
    _relax(monkeypatch)
    s = Stock(ticker="PREZZO_NEW", exchange="NASDAQ", name="Prezzo", country="US")
    db.add(s); db.flush()
    evaluate_signals(db, s, _confirmed_df())
    db.commit()

    a = db.query(Alert).filter(Alert.stock_id == s.id,
                               Alert.signal_name == "volume_breakout").first()
    snap = json.loads(a.snapshot)
    assert snap.get("first_price") == float(a.trigger_price)


def test_una_revisione_NON_sovrascrive_il_prezzo_della_prima_emissione(db, monkeypatch):
    """⚠️ Il test che chiude il difetto.

    `trigger_price` avanza con la revisione — ed e' voluto, perche' descrive il
    segnale vivo — ma il prezzo a cui l'alert e' COMPARSO non deve muoversi:
    e' l'ingresso che il magazzino misura e quello su cui il piano a schermo
    dovrebbe poggiare. Due numeri diversi che oggi erano lo stesso campo.
    """
    _relax(monkeypatch)
    s = Stock(ticker="PREZZO_AMEND", exchange="NASDAQ", name="Prezzo", country="US")
    db.add(s); db.flush()
    prior = _seed_prior(db, s, signal_date=date(2026, 4, 28), price=50.0)
    snap0 = json.loads(prior.snapshot)
    snap0["first_price"] = 50.0
    snap0["first_emitted_at"] = "2026-04-28T21:00:00+00:00"
    prior.snapshot = json.dumps(snap0)
    db.commit()

    evaluate_signals(db, s, _confirmed_df())   # chiusura corrente 110.0
    db.commit()

    riga = _vb_rows(db, s)[0]
    snap = json.loads(riga.snapshot)
    assert float(riga.trigger_price) == 110.0, "il prezzo del segnale vivo deve avanzare"
    assert snap.get("first_price") == 50.0, (
        "la revisione ha sovrascritto il prezzo della prima emissione"
    )
    assert snap.get("first_emitted_at") == "2026-04-28T21:00:00+00:00"


def test_una_revisione_su_un_alert_storico_senza_first_price_non_ne_inventa_uno(
    db, monkeypatch,
):
    """Gli alert che precedono il campo non ricevono il prezzo di OGGI spacciato
    per quello della prima emissione: resta assente, e il ricalcolo storico lo
    riempie dalla barra giusta."""
    _relax(monkeypatch)
    s = Stock(ticker="PREZZO_LEGACY", exchange="NASDAQ", name="Prezzo", country="US")
    db.add(s); db.flush()
    _seed_prior(db, s, signal_date=date(2026, 4, 28), price=50.0)
    db.commit()

    evaluate_signals(db, s, _confirmed_df())
    db.commit()

    snap = json.loads(_vb_rows(db, s)[0].snapshot)
    assert "first_price" not in snap
