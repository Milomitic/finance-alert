"""Tests for alert_service.list_alerts sorting and filtering."""
import json
from datetime import date

from app.models import Alert, SignalOutcome, Stock
from app.services.alert_service import list_alerts


def _seed(db, ticker, price, conf, tone="bull"):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    db.add(
        Alert(
            stock_id=s.id,
            trigger_price=price,
            signal_date=date(2026, 5, 1),
            signal_name="volume_breakout",
            snapshot=json.dumps({"tone": tone, "confidence": conf, "chain": []}),
        )
    )
    db.commit()


def test_list_alerts_sort_by_price_and_confidence(db):
    _seed(db, "AAA", 10.0, 90)
    _seed(db, "BBB", 30.0, 50)
    _seed(db, "CCC", 20.0, 70)

    # sort by trigger_price asc
    items, _total, _more = list_alerts(db, sort_by="trigger_price", sort_dir="asc")
    assert [round(i["trigger_price"], 0) for i in items] == [10, 20, 30]

    # sort by confidence desc
    items, _, _ = list_alerts(db, sort_by="confidence", sort_dir="desc")
    assert [i["ticker"] for i in items] == ["AAA", "CCC", "BBB"]


# ── tone filter ──────────────────────────────────────────────────────────────

def test_filter_by_tone_bull(db):
    _seed(db, "BULL1", 10.0, 80, tone="bull")
    _seed(db, "BEAR1", 20.0, 60, tone="bear")
    _seed(db, "BULL2", 30.0, 40, tone="bull")

    items, total, _ = list_alerts(db, tone="bull")
    tickers = {i["ticker"] for i in items}
    assert tickers == {"BULL1", "BULL2"}
    assert total == 2


def test_filter_by_tone_bear(db):
    _seed(db, "BULL3", 10.0, 80, tone="bull")
    _seed(db, "BEAR2", 20.0, 60, tone="bear")

    items, total, _ = list_alerts(db, tone="bear")
    assert [i["ticker"] for i in items] == ["BEAR2"]
    assert total == 1


def test_filter_tone_no_match(db):
    _seed(db, "BULL4", 10.0, 80, tone="bull")

    items, total, _ = list_alerts(db, tone="bear")
    assert items == []
    assert total == 0


# ── confidence_min filter ────────────────────────────────────────────────────

def test_filter_by_confidence_min(db):
    _seed(db, "HIGH", 10.0, 85, tone="bull")
    _seed(db, "MID",  20.0, 70, tone="bull")
    _seed(db, "LOW",  30.0, 40, tone="bull")

    items, total, _ = list_alerts(db, confidence_min=70.0)
    tickers = {i["ticker"] for i in items}
    assert tickers == {"HIGH", "MID"}
    assert total == 2


def test_filter_by_confidence_min_exact_boundary(db):
    _seed(db, "EXACT", 10.0, 70, tone="bull")
    _seed(db, "BELOW", 20.0, 69, tone="bull")

    items, total, _ = list_alerts(db, confidence_min=70.0)
    assert [i["ticker"] for i in items] == ["EXACT"]
    assert total == 1


# ── combined tone + confidence_min ───────────────────────────────────────────

def test_filter_tone_and_confidence_combined(db):
    _seed(db, "A", 10.0, 90, tone="bull")
    _seed(db, "B", 20.0, 50, tone="bull")
    _seed(db, "C", 30.0, 90, tone="bear")

    items, total, _ = list_alerts(db, tone="bull", confidence_min=80.0)
    assert [i["ticker"] for i in items] == ["A"]
    assert total == 1


# ── outcome + horizon filters ────────────────────────────────────────────────

def _seed_with_outcome(db, ticker, *, horizon="short", abs_hit=None):
    """Signal alert with snapshot.horizon; abs_hit=None leaves it pending
    (no outcome row), 1/0 writes the matured SignalOutcome row."""
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    a = Alert(
        stock_id=s.id,
        trigger_price=10.0,
        signal_date=date(2026, 5, 1),
        signal_name="volume_breakout",
        snapshot=json.dumps({"tone": "bull", "strength": 70, "horizon": horizon}),
    )
    db.add(a)
    db.flush()
    if abs_hit is not None:
        db.add(SignalOutcome(
            alert_id=a.id, stock_id=s.id, detector="volume_breakout",
            signal_date=a.signal_date, tone="bull", horizon_days=10,
            entry_close=10.0, forward_close=11.0, fwd_return=0.1,
            abs_hit=abs_hit,
        ))
    db.commit()
    return a


def test_filter_by_outcome_hit_miss_pending(db):
    _seed_with_outcome(db, "HIT1", abs_hit=1)
    _seed_with_outcome(db, "MISS1", abs_hit=0)
    _seed_with_outcome(db, "PEND1", abs_hit=None)

    items, total, _ = list_alerts(db, outcome="hit")
    assert [i["ticker"] for i in items] == ["HIT1"] and total == 1

    items, total, _ = list_alerts(db, outcome="miss")
    assert [i["ticker"] for i in items] == ["MISS1"] and total == 1

    items, total, _ = list_alerts(db, outcome="pending")
    assert [i["ticker"] for i in items] == ["PEND1"] and total == 1


def test_filter_outcome_pending_excludes_legacy_rows(db):
    """A legacy/price alert (no signal_name/signal_date) never matures, so it
    must NOT read as 'pending' — pending means 'in maturazione'."""
    s = Stock(ticker="LEGCY", exchange="NASDAQ", name="Legacy", country="US")
    db.add(s)
    db.flush()
    db.add(Alert(stock_id=s.id, trigger_price=5.0, snapshot=json.dumps({"rsi": 28})))
    db.commit()
    _seed_with_outcome(db, "PEND2", abs_hit=None)

    items, total, _ = list_alerts(db, outcome="pending")
    assert [i["ticker"] for i in items] == ["PEND2"] and total == 1


def test_filter_by_horizon(db):
    _seed_with_outcome(db, "SHRT", horizon="short")
    _seed_with_outcome(db, "MEDM", horizon="medium")
    _seed_with_outcome(db, "LONG", horizon="long")

    items, total, _ = list_alerts(db, horizon="medium")
    assert [i["ticker"] for i in items] == ["MEDM"] and total == 1

    # Combined with outcome: nothing matured yet → hit+medium is empty.
    items, total, _ = list_alerts(db, horizon="medium", outcome="hit")
    assert items == [] and total == 0


# ── l'ordine della lista: il giorno in cui il segnale e' COMPARSO ───────────
#
# ⚠️ Ordinare su `triggered_at` vuol dire ordinare sull'ULTIMA REVISIONE: un
# segnale che persiste viene rivisto a ogni scansione, quindi torna in cima
# ogni giorno a prescindere da quando e' nato. Misurato in produzione il
# 2026-09-22: 7.296 alert su 8.910 hanno almeno una revisione, uno ne conta
# 167. La lista mostra il giorno di nascita, quindi ci si ordina sopra.

def _seed_emissione(db, ticker, *, prima_emissione: str | None, ultima_revisione: str):
    from datetime import UTC, datetime

    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    snap = {"tone": "bull", "confidence": 70, "chain": []}
    if prima_emissione is not None:
        snap["first_emitted_at"] = prima_emissione
    db.add(Alert(
        stock_id=s.id, trigger_price=100.0, signal_date=date(2026, 5, 1),
        signal_name="volume_breakout", snapshot=json.dumps(snap),
        triggered_at=datetime.fromisoformat(ultima_revisione).replace(tzinfo=UTC),
    ))
    db.commit()


def test_la_lista_si_ordina_sul_giorno_in_cui_l_alert_e_COMPARSO(db):
    # VECCHIO nasce prima e viene rivisto oggi; NUOVO nasce ieri e non e' mai
    # stato rivisto. Sull'ultima revisione VECCHIO starebbe davanti.
    _seed_emissione(db, "VECCHIO", prima_emissione="2026-05-02T23:30:00+00:00",
                    ultima_revisione="2026-05-20T23:30:00")
    _seed_emissione(db, "NUOVO", prima_emissione="2026-05-19T23:30:00+00:00",
                    ultima_revisione="2026-05-19T23:30:00")

    items, _, _ = list_alerts(db, sort_by="emissione", sort_dir="desc")
    assert [i["ticker"] for i in items] == ["NUOVO", "VECCHIO"]

    # Controllo negativo: sull'altro campo l'ordine si INVERTE. Senza, il test
    # sopra sarebbe vero anche di un ordinamento che non distingue i due campi.
    items, _, _ = list_alerts(db, sort_by="triggered_at", sort_dir="desc")
    assert [i["ticker"] for i in items] == ["VECCHIO", "NUOVO"]


def test_un_alert_senza_prima_emissione_si_ordina_sul_campo_vecchio(db):
    """I 116 alert (1,3%) che precedono il campo: il ripiego li tiene nella
    lista al posto giusto invece di spingerli tutti in fondo."""
    _seed_emissione(db, "LEGACY", prima_emissione=None,
                    ultima_revisione="2026-05-21T23:30:00")
    _seed_emissione(db, "RECENTE", prima_emissione="2026-05-19T23:30:00+00:00",
                    ultima_revisione="2026-05-19T23:30:00")

    items, _, _ = list_alerts(db, sort_by="emissione", sort_dir="desc")
    assert [i["ticker"] for i in items] == ["LEGACY", "RECENTE"]


def test_l_ordine_predefinito_e_quello_dell_emissione(db):
    _seed_emissione(db, "VECCHIO", prima_emissione="2026-05-02T23:30:00+00:00",
                    ultima_revisione="2026-05-20T23:30:00")
    _seed_emissione(db, "NUOVO", prima_emissione="2026-05-19T23:30:00+00:00",
                    ultima_revisione="2026-05-19T23:30:00")

    items, _, _ = list_alerts(db)
    assert [i["ticker"] for i in items] == ["NUOVO", "VECCHIO"]
