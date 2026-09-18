"""L'elenco degli esiti di piano, un segnale per riga.

Il magazzino `plan_outcomes` esisteva da due giorni e si vedeva solo
AGGREGATO per detector, dentro un pannello chiuso di Diagnostica. Cioe' la
domanda che l'utente si fa davanti a un segnale — «il target e' arrivato?» —
non aveva risposta a schermo, mentre il dato era in tabella.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, PlanOutcome, Stock, User
from app.services.plan_performance_service import elenco_esiti_piano


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _titolo(db: Session, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc.", country="US")
    db.add(s)
    db.flush()
    return s


def _esito(
    db: Session, stock: Stock, *, esito: str = "tp1", risolto: str = "2026-03-10",
    detector: str = "sr_flip", tono: str = "bull", r_mult: float = 2.0,
    stop_hit: str | None = None, tp1_hit: str | None = "2026-03-10",
) -> PlanOutcome:
    a = Alert(stock_id=stock.id, signal_name=detector,
              signal_date=date(2026, 3, 1),
              triggered_at=datetime(2026, 3, 1, tzinfo=UTC),
              trigger_price=100.0, snapshot="{}")
    db.add(a)
    db.flush()
    riga = PlanOutcome(
        alert_id=a.id, stock_id=stock.id, detector=detector,
        signal_date=date(2026, 3, 1), tone=tono, horizon_days=21,
        entry_date=date(2026, 3, 2), entry=100.0, stop=96.0, tp1=108.0, tp2=112.0,
        r=4.0, esito=esito, resolved_date=date.fromisoformat(risolto),
        bars_to_outcome=6, r_multiple=r_mult, mae_r=0.3, mfe_r=2.1,
        tp2_reached=False,
        stop_hit_date=date.fromisoformat(stop_hit) if stop_hit else None,
        tp1_hit_date=date.fromisoformat(tp1_hit) if tp1_hit else None,
        tp2_hit_date=None, source="emesso", method_version="2",
        matured_at=datetime.now(UTC),
    )
    db.add(riga)
    db.flush()
    return riga


def test_una_riga_per_segnale_col_titolo_accanto(db: Session) -> None:
    s = _titolo(db, "AAA")
    _esito(db, s)

    dati = elenco_esiti_piano(db)

    assert dati["total"] == 1
    riga = dati["items"][0]
    assert riga["ticker"] == "AAA"
    assert riga["esito"] == "tp1"
    assert riga["r_multiple"] == pytest.approx(2.0)


def test_le_gambe_escono_GREZZE_non_una_conclusione(db: Session) -> None:
    """⚠️ Il caso che da' senso all'intera vista: stop colpito PRIMA di un
    target poi arrivato lo stesso. L'esito dice -1R ed e' giusto, la posizione
    era chiusa; le due date dicono l'altra meta', cioe' che lo stop era troppo
    stretto e il trade aveva ragione.

    L'API rende le date, non un booleano `stop_troppo_stretto`: una
    conclusione congelata qui vivrebbe in due posti il giorno che qualcuno la
    affina.
    """
    s = _titolo(db, "BBB")
    _esito(db, s, esito="stop", r_mult=-1.0,
           stop_hit="2026-03-05", tp1_hit="2026-03-18")

    riga = elenco_esiti_piano(db)["items"][0]

    assert riga["stop_hit_date"] == date(2026, 3, 5)
    assert riga["tp1_hit_date"] == date(2026, 3, 18)
    assert riga["esito"] == "stop"
    assert "stop_troppo_stretto" not in riga


def test_il_riassunto_conta_la_POPOLAZIONE_non_la_pagina(db: Session) -> None:
    """Questo progetto ha gia' stampato «50 setup chiusi» sopra una lista di
    795, e conteggi di chip presi dalle righe ricevute invece che dal server.
    Un numero che cambia con la dimensione della pagina non e' un conteggio."""
    s = _titolo(db, "CCC")
    for i in range(5):
        _esito(db, s, risolto=f"2026-03-{10 + i:02d}")

    dati = elenco_esiti_piano(db, limit=2)

    assert len(dati["items"]) == 2
    assert dati["total"] == 5
    assert dati["has_more"] is True
    assert dati["summary"]["n"] == 5
    assert dati["summary"]["esiti"]["tp1"] == 5


def test_i_piu_recenti_per_primi_per_data_di_CHIUSURA(db: Session) -> None:
    # Un segnale vecchio che ha toccato il target ieri e' una notizia di ieri:
    # l'ordine e' sulla risoluzione, non sullo scatto.
    s = _titolo(db, "DDD")
    _esito(db, s, risolto="2026-03-04")
    _esito(db, s, risolto="2026-03-20")

    date_rese = [r["resolved_date"] for r in elenco_esiti_piano(db)["items"]]

    assert date_rese == [date(2026, 3, 20), date(2026, 3, 4)]


def test_i_filtri_restringono_anche_il_riassunto(db: Session) -> None:
    s = _titolo(db, "EEE")
    _esito(db, s, esito="tp1", r_mult=2.0)
    _esito(db, s, esito="stop", r_mult=-1.0, detector="gap_and_go")

    solo_stop = elenco_esiti_piano(db, esito="stop")

    assert solo_stop["total"] == 1
    assert solo_stop["summary"]["n"] == 1
    assert solo_stop["summary"]["expectancy_r"] == pytest.approx(-1.0)
    # Controllo negativo: senza filtro il riassunto vede entrambe, quindi il
    # test sopra non e' vero per caso.
    assert elenco_esiti_piano(db)["summary"]["n"] == 2


def test_un_filtro_che_non_seleziona_niente_non_ha_un_attesa(db: Session) -> None:
    """Zero righe non hanno un'attesa. Stampare 0,00 R sarebbe
    un'affermazione, non un'assenza."""
    _titolo(db, "FFF")

    dati = elenco_esiti_piano(db, ticker="FFF")

    assert dati["total"] == 0
    assert dati["summary"] is None


# ─── L'endpoint ────────────────────────────────────────────────────────────

def test_la_rotta_letterale_non_e_scambiata_per_un_id(client: TestClient, db: Session) -> None:
    """⚠️ `/plan-outcomes` sta PRIMA di `/{alert_id}`. Dichiarata dopo, FastAPI
    proverebbe a leggerla come un intero e risponderebbe 422 — un guasto che
    si presenta come «l'elenco non carica» e si diagnostica altrove."""
    s = _titolo(db, "GGG")
    _esito(db, s)
    db.commit()

    r = client.get("/api/alerts/plan-outcomes")

    assert r.status_code == 200
    assert r.json()["items"][0]["ticker"] == "GGG"


def test_un_esito_inventato_e_un_400_che_dice_quali_esistono(client: TestClient) -> None:
    r = client.get("/api/alerts/plan-outcomes?esito=vinto")

    assert r.status_code == 400
    assert "tp1" in r.json()["detail"]
