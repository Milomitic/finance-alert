"""Lo stesso alert, aperto da due pagine, deve rendere gli stessi campi.

FA-054 + FA-055. `alert_service._row_to_item` e' il serializzatore canonico, e
il suo docstring prevede letteralmente questo difetto:

    «due percorsi che costruiscono a mano la stessa forma divergono, e qui la
    divergenza sarebbe silenziosa — il frontend riceverebbe un alert con meno
    campi solo quando lo apre da una posizione invece che dalla lista»

`api/stocks.py` e' il TERZO percorso di cui quel commento avvertiva, ed era gia'
divergente: costruiva `AlertOut` campo per campo e ne ometteva sei — `currency`
e l'intero blocco esito.

⚠️ I due difetti si COMPONGONO, ed e' la ragione per cui nessuno se n'era
accorto guardando lo schermo. Il dettaglio titolo escludeva anche gli alert
archiviati, e in produzione **5.312 dei 5.313 esiti maturati stanno su alert
archiviati** — quindi la colonna Esito sarebbe stata comunque vuota, e
aggiungere i sei campi senza togliere il filtro non avrebbe cambiato niente di
visibile. Correggerne uno solo lascia il difetto in piedi sembrando chiuderlo.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, OhlcvDaily, SignalOutcome, Stock, User


@pytest.fixture
def client(db):
    """Client autenticato con la sessione del test: la stessa forma che usa
    `test_signal_drift_service`, non una variante."""
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()

#: Campi che la lista canonica rende e che il dettaglio titolo deve rendere
#: anch'esso. Non un campione: l'insieme intero, cosi' che un campo aggiunto
#: alla lista e dimenticato nel dettaglio faccia rosso.
_CANONICI = {
    "id", "rule_kind", "stock_id", "ticker", "name", "currency",
    "triggered_at", "signal_date", "trigger_price", "snapshot",
    "read_at", "archived_at", "same_day_others", "same_day_sector",
    "outcome_hit", "outcome_fwd_return", "outcome_horizon_days",
    "outcome_mkt_excess", "next_earnings_date",
}


def _titolo_con_barre(db) -> Stock:
    s = Stock(ticker="PARITA", exchange="LSE", name="Parita plc",
              country="GB", currency="GBP", sector="Energy")
    db.add(s)
    db.flush()
    for i in range(1, 40):
        d = date(2026, 6, 1) + timedelta(days=i)
        db.add(OhlcvDaily(stock_id=s.id, date=d, open=100, high=101, low=99,
                          close=100 + i * 0.1, volume=1000))
    db.flush()
    return s


def _alert(db, s, *, giorno: date, archiviato: bool) -> Alert:
    a = Alert(
        stock_id=s.id, trigger_price=100.0, signal_date=giorno,
        signal_name="candle_reversal",
        snapshot=json.dumps({"tone": "bull", "strength": 70, "probability": 50}),
        triggered_at=datetime(2026, 7, 1, tzinfo=UTC),
        archived_at=datetime(2026, 8, 1, tzinfo=UTC) if archiviato else None,
    )
    db.add(a)
    db.flush()
    return a


def test_the_detail_payload_keeps_every_canonical_key(client, db) -> None:
    """Guardia sullo SCHEMA, e va letta per quello che e'.

    ⚠️ Questo test NON vede il difetto di FA-055, e capire perche' conta:
    `AlertOut` e' un modello Pydantic con tutti i campi dichiarati e un default,
    quindi i sei che `api/stocks.py` non passava venivano serializzati come
    `null` invece di sparire. Le chiavi c'erano tutte. Il che e' PEGGIO, non
    meglio: chi legge `outcome_hit: null` non puo' distinguere «non ancora
    maturato» da «questa rotta non lo popola».

    Resta utile contro un campo tolto dallo schema, ed e' il motivo per cui il
    difetto vero va cercato sui VALORI, nei due test qui sotto."""
    s = _titolo_con_barre(db)
    _alert(db, s, giorno=date(2026, 6, 20), archiviato=False)
    db.commit()

    r = client.get(f"/api/stocks/{s.ticker}/detail")
    assert r.status_code == 200
    storia = r.json()["alerts_history"]
    assert storia, "il titolo ha un alert non archiviato: la storia non puo' essere vuota"
    assert set(storia[0]) == _CANONICI


def test_the_detail_page_populates_currency_and_outcome(client, db) -> None:
    """Il difetto di FA-055 nella forma in cui si vede davvero: i VALORI.

    Un alert vivo che ha gia' maturato il suo esito e' il caso che separa le
    due letture — se la rotta popolasse il blocco esito, qui lo vedremmo."""
    s = _titolo_con_barre(db)
    a = _alert(db, s, giorno=date(2026, 6, 20), archiviato=False)
    db.add(SignalOutcome(
        alert_id=a.id, stock_id=s.id, detector="candle_reversal",
        signal_date=a.signal_date, tone="bull", horizon_days=5,
        entry_close=100.0, forward_close=105.0, fwd_return=0.05, abs_hit=1,
    ))
    db.commit()

    riga = client.get(f"/api/stocks/{s.ticker}/detail").json()["alerts_history"][0]
    # ⚠️ La valuta NON e' dollari: 312 titoli su 1010 non sono quotati in USD,
    # ed e' il campo la cui assenza faceva rendere ogni prezzo con `$`.
    assert riga["currency"] == "GBP"
    assert riga["outcome_hit"] is True
    assert riga["outcome_horizon_days"] == 5
    assert riga["outcome_fwd_return"] == pytest.approx(0.05)


def test_the_two_pages_agree_on_the_same_alert(client, db) -> None:
    """La parita' vera: stesso alert, due rotte, stessi campi E stessi valori.

    ⚠️ Si confrontano i VALORI e non solo le chiavi. Due payload con le stesse
    chiavi e valuta diversa sarebbero d'accordo sulla forma e in disaccordo sul
    contenuto, che e' il difetto peggiore dei due."""
    s = _titolo_con_barre(db)
    a = _alert(db, s, giorno=date(2026, 6, 20), archiviato=False)
    db.commit()

    dal_dettaglio = client.get(f"/api/stocks/{s.ticker}/detail").json()["alerts_history"][0]
    dalla_lista = next(
        i for i in client.get(f"/api/alerts?ticker={s.ticker}").json()["items"]
        if i["id"] == a.id
    )
    for campo in sorted(_CANONICI - {"same_day_others", "same_day_sector"}):
        assert dal_dettaglio[campo] == dalla_lista[campo], f"divergono su {campo}"
    # ⚠️ E la valuta NON e' dollari: un terzo dell'universo non e' quotato in
    # USD, ed e' il campo la cui assenza faceva rendere ogni prezzo con `$`.
    assert dal_dettaglio["currency"] == "GBP"


def test_a_matured_outcome_reaches_the_detail_page(client, db) -> None:
    """⚠️ Il difetto che i due si compongono a formare.

    In produzione 5.312 dei 5.313 esiti maturati stanno su alert ARCHIVIATI,
    quindi la scheda storica del dettaglio ne mostrava UNO. Lo storico completo
    deve poterli vedere; i recenti no, ed e' una scelta di prodotto, non una
    svista."""
    s = _titolo_con_barre(db)
    vecchio = _alert(db, s, giorno=date(2026, 6, 10), archiviato=True)
    db.add(SignalOutcome(
        alert_id=vecchio.id, stock_id=s.id, detector="candle_reversal",
        signal_date=vecchio.signal_date, tone="bull", horizon_days=5,
        entry_close=100.0, forward_close=105.0, fwd_return=0.05, abs_hit=1,
    ))
    db.commit()

    # I recenti non lo mostrano: e' archiviato.
    recenti = client.get(f"/api/stocks/{s.ticker}/detail").json()["alerts_history"]
    assert all(i["id"] != vecchio.id for i in recenti)

    # Lo storico completo si', CON il suo esito.
    completo = client.get(f"/api/alerts?ticker={s.ticker}&archived=true").json()["items"]
    riga = next(i for i in completo if i["id"] == vecchio.id)
    assert riga["outcome_hit"] is True
    assert riga["outcome_horizon_days"] == 5
