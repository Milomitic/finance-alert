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
    chiusa: bool | None = True,
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
        tp2_hit_date=None, method_version="2",
        matured_at=datetime.now(UTC), legs_window_complete=chiusa,
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


def test_l_elenco_mostra_le_finestre_aperte_ma_il_riassunto_no(db: Session) -> None:
    """⚠️ Due domande diverse, e la regola vale per UNA sola.

    Una riga dice che cosa e' successo a QUEL trade, e uno stop colpito e' uno
    stop colpito anche se l'orizzonte non e' finito: nell'elenco resta. La
    media invece fa una domanda sulla POPOLAZIONE, e una popolazione di
    finestre aperte contiene solo le uscite veloci — cioe' gli stop.
    """
    s = _titolo(db, "OPN")
    _esito(db, s, esito="tp1", r_mult=2.0)
    _esito(db, s, esito="stop", r_mult=-1.0, stop_hit="2026-03-04", tp1_hit=None, chiusa=False)

    dati = elenco_esiti_piano(db)

    assert dati["total"] == 2, "l'elenco deve restare completo"
    assert dati["summary"]["n"] == 1
    assert dati["summary"]["expectancy_r"] == pytest.approx(2.0)
    assert dati["open_excluded"] == 1


def test_sole_finestre_aperte_nessun_riassunto_ma_si_dice_quante(db: Session) -> None:
    """Nessuna finestra chiusa: niente attesa (sarebbe una media di zero
    righe), ma il conteggio delle aperte c'e', cosi' lo schermo puo' dire
    «in corso» invece di sembrare vuoto."""
    s = _titolo(db, "OPN")
    _esito(db, s, esito="stop", r_mult=-1.0, stop_hit="2026-03-04", tp1_hit=None, chiusa=False)

    dati = elenco_esiti_piano(db)

    assert dati["total"] == 1
    assert dati["summary"] is None
    assert dati["open_excluded"] == 1


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


def test_le_escluse_attraversano_lo_schema(client: TestClient, db: Session) -> None:
    """Il conteggio delle finestre aperte deve arrivare al frontend: un campo
    che il servizio calcola e lo schema Pydantic non dichiara sparisce dalla
    risposta senza un errore."""
    s = _titolo(db, "SCH")
    _esito(db, s, esito="tp1", r_mult=2.0)
    _esito(db, s, esito="stop", r_mult=-1.0, stop_hit="2026-03-04", tp1_hit=None, chiusa=False)
    db.commit()

    dati = client.get("/api/alerts/plan-outcomes").json()

    assert dati["open_excluded"] == 1
    assert dati["summary"]["open_excluded"] == 1
    assert dati["summary"]["n"] == 1


def test_un_esito_inventato_e_un_400_che_dice_quali_esistono(client: TestClient) -> None:
    r = client.get("/api/alerts/plan-outcomes?esito=vinto")

    assert r.status_code == 400
    assert "tp1" in r.json()["detail"]


def test_il_menu_delle_condizioni_non_si_svuota_selezionandone_una(db: Session) -> None:
    """⚠️ I conteggi per condizione sono il MENU del filtro, quindi si contano
    prima che il filtro si applichi.

    Calcolati dopo, scegliere un detector farebbe sparire tutti gli altri dal
    menu: il controllo si disabiliterebbe da solo al primo uso, e per tornare
    indietro bisognerebbe sapere che esiste un «tutte».
    """
    s = _titolo(db, "HHH")
    _esito(db, s, detector="sr_flip")
    _esito(db, s, detector="gap_and_go")

    filtrato = elenco_esiti_piano(db, detector="sr_flip")

    assert filtrato["total"] == 1, "il filtro non restringe piu' le righe"
    assert filtrato["counts_by_detector"] == {"sr_flip": 1, "gap_and_go": 1}
    # Controllo negativo: gli ALTRI filtri invece devono restringere anche il
    # menu, altrimenti mostrerebbe condizioni che non hanno nessuna riga.
    assert elenco_esiti_piano(db, esito="stop")["counts_by_detector"] == {}


# ─── L'ordinamento (2026-09-22) ─────────────────────────────────────────────
# Le colonne della lista Esiti si ordinano come quelle della tabella Segnali.
# ⚠️ Sul server, sull'intera popolazione filtrata: ordinare la sola pagina
# metterebbe in cima il migliore di cinquanta righe.


def test_ordinare_per_R_attraversa_le_pagine(db: Session) -> None:
    s = _titolo(db, "AAA")
    for i, r in enumerate([0.5, 3.0, -1.0, 2.0, 1.0]):
        _esito(db, s, r_mult=r, risolto=f"2026-03-1{i}")

    prima = elenco_esiti_piano(db, ordina="r_multiple", verso="desc", limit=2)
    seconda = elenco_esiti_piano(db, ordina="r_multiple", verso="desc", limit=2, offset=2)
    assert [x["r_multiple"] for x in prima["items"]] == [3.0, 2.0]
    assert [x["r_multiple"] for x in seconda["items"]] == [1.0, 0.5]
    # E al contrario il peggiore viene primo.
    su = elenco_esiti_piano(db, ordina="r_multiple", verso="asc", limit=1)
    assert su["items"][0]["r_multiple"] == -1.0


def test_il_pl_si_ordina_sul_prezzo_d_ingresso_non_sull_R(db: Session) -> None:
    """Due righe con lo stesso R ma stop diversi hanno P/L diversi: e' la
    ragione per cui il P/L e' una colonna a se'."""
    s = _titolo(db, "AAA")
    stretto = _esito(db, s, r_mult=2.0, risolto="2026-03-10")
    largo = _esito(db, s, r_mult=2.0, risolto="2026-03-11")
    largo.r = 10.0   # stop a 10 punti: +20% invece di +8%
    db.flush()

    dati = elenco_esiti_piano(db, ordina="pl", verso="desc")
    assert [x["alert_id"] for x in dati["items"]] == [largo.alert_id, stretto.alert_id]


def test_per_titolo_in_ordine_alfabetico(db: Session) -> None:
    for t in ("MMM", "AAA", "ZZZ"):
        _esito(db, _titolo(db, t))
    dati = elenco_esiti_piano(db, ordina="ticker", verso="asc")
    assert [x["ticker"] for x in dati["items"]] == ["AAA", "MMM", "ZZZ"]


def test_senza_ordinamento_resta_la_chiusura_piu_recente(db: Session) -> None:
    """Controllo negativo: il parametro nuovo non cambia il default."""
    s = _titolo(db, "AAA")
    _esito(db, s, r_mult=3.0, risolto="2026-03-01")
    _esito(db, s, r_mult=0.1, risolto="2026-03-20")
    dati = elenco_esiti_piano(db)
    assert [x["r_multiple"] for x in dati["items"]] == [0.1, 3.0]


def test_l_ordinamento_non_cambia_il_riassunto(db: Session) -> None:
    s = _titolo(db, "AAA")
    for r in (0.5, 3.0, -1.0):
        _esito(db, s, r_mult=r)
    a = elenco_esiti_piano(db)["summary"]
    b = elenco_esiti_piano(db, ordina="r_multiple", verso="asc", limit=1)["summary"]
    assert a == b


def test_un_ordinamento_sconosciuto_e_un_400(client: TestClient) -> None:
    r = client.get("/api/alerts/plan-outcomes?sort_by=forza")
    assert r.status_code == 400
    assert "r_multiple" in r.json()["detail"]
    assert client.get("/api/alerts/plan-outcomes?sort_by=pl&sort_dir=su").status_code == 400
    assert client.get("/api/alerts/plan-outcomes?sort_by=pl&sort_dir=asc").status_code == 200
