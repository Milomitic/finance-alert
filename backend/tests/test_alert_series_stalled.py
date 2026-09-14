"""Lo stato «bloccato»: un segnale su un titolo la cui serie non avanza piu'.

Fino al 2026-09-14 il percorso di lettura degli alert conosceva UN solo stato
per un esito assente — «in maturazione» — e lo affermava anche di segnali su
titoli morti. Misurato in produzione quel giorno: 3.734 alert senza esito, di
cui 48 su dodici titoli la cui serie si era fermata, uno da quattro mesi.

⚠️ Zero alert avevano invece le barre per maturare senza averlo fatto. Lo stato
«avrebbe dovuto maturare» NON esiste in questi test perche' non esiste nei
dati: costruirlo sarebbe un'etichetta senza popolazione.
"""
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, OhlcvDaily, SignalOutcome, Stock, User
from app.services.alert_service import get_alert_detail, list_alerts
from app.services.ohlcv_service import QUARANTINE_STREAK

_OGGI = date(2026, 9, 14)


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _titolo(db, ticker, *, streak=0, ultima_barra=None):
    s = Stock(
        ticker=ticker, exchange="NASDAQ", name=ticker, country="US",
        ohlcv_nodata_streak=streak,
        ohlcv_last_nodata_at=_OGGI if streak else None,
    )
    db.add(s)
    db.flush()
    if ultima_barra is not None:
        # Due barre: se il codice leggesse la PRIMA invece del massimo, la
        # differenza si vedrebbe.
        for giorno in (ultima_barra - timedelta(days=7), ultima_barra):
            db.add(OhlcvDaily(
                stock_id=s.id, date=giorno,
                open=10, high=11, low=9, close=10, volume=1000,
            ))
    db.flush()
    return s


def _alert(db, stock, *, con_esito=False, signal_date=date(2026, 5, 1)):
    a = Alert(
        stock_id=stock.id, trigger_price=10.0,
        signal_date=signal_date, signal_name="volume_breakout",
        snapshot=json.dumps({"tone": "bull", "strength": 70, "chain": []}),
    )
    db.add(a)
    db.flush()
    if con_esito:
        db.add(SignalOutcome(
            alert_id=a.id, stock_id=stock.id, detector="volume_breakout",
            signal_date=signal_date, tone="bull", horizon_days=21, abs_hit=1,
            entry_close=10.0, forward_close=10.5, fwd_return=0.05,
        ))
    db.commit()
    return a


def test_una_serie_viva_non_e_bloccata(db):
    _alert(db, _titolo(db, "VIVO", streak=0, ultima_barra=_OGGI))
    (voce,), _total, _ = list_alerts(db)
    assert voce["series_stalled"] is False
    # Non si interroga la serie di un titolo sano: e' la ragione per cui
    # `_last_bar_dates` riceve un insieme ristretto e non l'intera pagina.
    assert voce["series_last_bar"] is None


def test_una_serie_ferma_e_bloccata_e_porta_la_sua_ultima_barra(db):
    ultima = date(2026, 7, 10)
    _alert(db, _titolo(db, "MORTO", streak=336, ultima_barra=ultima))
    (voce,), _total, _ = list_alerts(db)
    assert voce["series_stalled"] is True
    # ⚠️ La data e' la meta' che rende la bandiera controllabile. Senza,
    # «non maturera'» e' una conclusione che chi legge deve credere.
    assert voce["series_last_bar"] == ultima


def test_la_soglia_e_quella_dell_ingestione_non_una_copia(db):
    """Un titolo appena sotto soglia e' ancora «in attesa», non «bloccato».

    La soglia ha UN proprietario (`ohlcv_service.QUARANTINE_STREAK`): una
    seconda copia qui divergerebbe in silenzio il giorno in cui l'ingestione
    la cambia, ed e' esattamente la forma che questo progetto ha gia' pagato.
    """
    _alert(db, _titolo(db, "SOTTO", streak=QUARANTINE_STREAK - 1, ultima_barra=_OGGI))
    _alert(db, _titolo(db, "SOPRA", streak=QUARANTINE_STREAK, ultima_barra=_OGGI))
    items, _t, _ = list_alerts(db)
    per_ticker = {i["ticker"]: i["series_stalled"] for i in items}
    assert per_ticker == {"SOTTO": False, "SOPRA": True}


def test_pending_e_stalled_sono_disgiunti_e_sommano_al_totale(db):
    """L'invariante che tiene onesti i conteggi.

    Separare uno stato in due e' utile solo se la somma non cambia: se i due
    insiemi si sovrapponessero, ogni schermata li mostrerebbe da sola e
    plausibile, e nessuno vedrebbe che il totale non torna.
    """
    for i in range(3):
        _alert(db, _titolo(db, f"VIVO{i}", streak=0, ultima_barra=_OGGI))
    for i in range(2):
        _alert(db, _titolo(db, f"MORTO{i}", streak=99, ultima_barra=date(2026, 6, 1)))
    # Un esito gia' maturato su un titolo morto: non e' ne' l'uno ne' l'altro.
    _alert(db, _titolo(db, "MORTOMAT", streak=99, ultima_barra=date(2026, 6, 1)),
           con_esito=True)

    _, senza_esito, _ = list_alerts(db, outcome="pending")
    _, bloccati, _ = list_alerts(db, outcome="stalled")
    assert (senza_esito, bloccati) == (3, 2)

    v_pending = {i["ticker"] for i in list_alerts(db, outcome="pending")[0]}
    v_stalled = {i["ticker"] for i in list_alerts(db, outcome="stalled")[0]}
    assert v_pending & v_stalled == set()
    assert v_pending | v_stalled == {"VIVO0", "VIVO1", "VIVO2", "MORTO0", "MORTO1"}
    # L'esito maturato resta fuori da entrambi, e sta in "hit".
    assert [i["ticker"] for i in list_alerts(db, outcome="hit")[0]] == ["MORTOMAT"]


def test_la_finestra_di_ri_sondaggio_non_cambia_lo_stato(db):
    """Controllo negativo su una scelta deliberata.

    `ohlcv_service.not_quarantined_clause()` porta anche il termine su
    REPROBE_DAYS e risponde a «vale la pena ritentare il download adesso?».
    Usarla qui farebbe oscillare l'alert fra «bloccato» e «in maturazione»
    ogni sette giorni senza che nulla sia cambiato nei dati — quindi questo
    test fissa che il ri-sondaggio NON e' entrato nel predicato.
    """
    from app.services import ohlcv_service

    s = _titolo(db, "DASONDARE", streak=99, ultima_barra=date(2026, 6, 1))
    # Ultimo tentativo molto vecchio: per il piano di fetch e' di nuovo
    # scaricabile, cioe' NON in quarantena...
    s.ohlcv_last_nodata_at = _OGGI - timedelta(days=ohlcv_service.REPROBE_DAYS + 1)
    _alert(db, s)
    fetchable, quarantined = ohlcv_service.split_quarantined([s], today=_OGGI)
    assert (len(fetchable), len(quarantined)) == (1, 0)
    # ...e la sua serie e' ferma lo stesso.
    (voce,), _t, _ = list_alerts(db)
    assert voce["series_stalled"] is True
    assert list_alerts(db, outcome="stalled")[1] == 1


def test_il_dettaglio_dice_le_stesse_cose_della_lista(db):
    """`_row_to_item` ha due chiamanti, ed e' il motivo per cui esiste."""
    ultima = date(2026, 7, 10)
    a = _alert(db, _titolo(db, "DUEVIE", streak=336, ultima_barra=ultima))
    (dalla_lista,), _t, _ = list_alerts(db)
    dal_dettaglio = get_alert_detail(db, a.id)
    assert dal_dettaglio is not None
    for campo in ("series_stalled", "series_last_bar"):
        assert dal_dettaglio[campo] == dalla_lista[campo]
    assert dal_dettaglio["series_last_bar"] == ultima


@pytest.mark.parametrize("valore", ["hit", "miss", "pending", "stalled"])
def test_l_api_accetta_i_quattro_valori(client, valore):
    r = client.get(f"/api/alerts?outcome={valore}")
    assert r.status_code == 200


def test_l_api_rifiuta_un_valore_inventato(client):
    r = client.get("/api/alerts?outcome=bloccato")
    assert r.status_code == 422
