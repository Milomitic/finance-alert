"""L'aggregazione degli esiti di piano per il cruscotto.

⚠️ L'intestazione e' l'ATTESA IN R, non il tasso di successo, e non e' una
preferenza estetica. TP1 sta a R:R fino a 4,0: per costruzione questo motore fa
piani a bassa frequenza di vincita e alto guadagno unitario, quindi un tasso da
solo sembrerebbe pessimo mentre il sistema guadagna. Il numero che aggrega e'
l'attesa.

E ogni numero porta il campione che lo regge: righe, FINESTRE INDIPENDENTI e
un intervallo che le paga. Questo progetto ha gia' mostrato «100%» su sei
setup risolti e un detector con due soli valori di Forza distinti su 95 alert;
la regola che ne e' uscita e' che un numero senza il suo campione e' lo stesso
difetto di un numero sbagliato.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, PlanOutcome, Stock
from app.services.plan_performance_service import compute_plan_performance


def _titolo(db: Session, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Corp", country="US")
    db.add(s)
    db.flush()
    return s


def _riga(db: Session, stock: Stock, *, detector: str = "sr_flip",
          giorno: int = 1, esito: str = "tp1", r_mult: float = 2.0,
          orizzonte: int = 21, stop_il: int | None = None, tp1_il: int | None = None,
          mae: float = 0.3, mfe: float = 2.2, chiusa: bool | None = True) -> PlanOutcome:
    d = date(2026, 1, 1) + timedelta(days=giorno)
    a = Alert(stock_id=stock.id, signal_name=detector, signal_date=d,
              triggered_at=datetime.combine(d, datetime.min.time(), tzinfo=UTC),
              trigger_price=100.0, snapshot="{}")
    db.add(a)
    db.flush()
    riga = PlanOutcome(
        alert_id=a.id, stock_id=stock.id, detector=detector, signal_date=d,
        tone="bull", horizon_days=orizzonte, entry_date=d, entry=100.0,
        stop=96.0, tp1=108.0, tp2=112.0, r=4.0, esito=esito,
        resolved_date=d + timedelta(days=5), bars_to_outcome=5,
        r_multiple=r_mult, mae_r=mae, mfe_r=mfe, tp2_reached=False,
        stop_hit_date=(d + timedelta(days=stop_il)) if stop_il is not None else None,
        tp1_hit_date=(d + timedelta(days=tp1_il)) if tp1_il is not None else None,
        method_version="1", matured_at=datetime.now(UTC),
        legs_window_complete=chiusa,
    )
    db.add(riga)
    db.flush()
    return riga


def _per_detector(dati: dict) -> dict[str, dict]:
    return {r["detector"]: r for r in dati["rows"]}


# ─── 1. L'intestazione e' l'attesa, non il tasso ───────────────────────────

def test_l_attesa_in_R_e_la_media_dei_multipli_non_il_tasso_di_successo(db: Session) -> None:
    """Il caso che rende il punto: tre perdite e una vincita grossa.

    Tasso di successo 25%, che letto da solo sembra un disastro. Attesa
    +0,25R, cioe' il sistema guadagna. Sono lo stesso campione.
    """
    s = _titolo(db, "AAA")
    for g in (1, 2, 3):
        _riga(db, s, giorno=g, esito="stop", r_mult=-1.0)
    _riga(db, s, giorno=40, esito="tp1", r_mult=4.0)

    riga = _per_detector(compute_plan_performance(db))["sr_flip"]
    assert riga["expectancy_r"] == pytest.approx(0.25)
    assert riga["win_rate"] == pytest.approx(25.0)


def test_un_detector_che_perde_ha_attesa_negativa(db: Session) -> None:
    s = _titolo(db, "AAA")
    for g in (1, 20, 40, 60):
        _riga(db, s, giorno=g, esito="stop", r_mult=-1.0)

    riga = _per_detector(compute_plan_performance(db))["sr_flip"]
    assert riga["expectancy_r"] == pytest.approx(-1.0)
    assert riga["verdict"] == "negative"


# ─── 2. Ogni numero porta il campione che lo regge ─────────────────────────

def test_le_finestre_indipendenti_sono_MENO_delle_righe_quando_si_sovrappongono(db: Session) -> None:
    """Quattro segnali in quattro giorni, etichettati a 21 sedute, non sono
    quattro estrazioni indipendenti: condividono quasi tutta la finestra."""
    s = _titolo(db, "AAA")
    for g in (1, 2, 3, 4):
        _riga(db, s, giorno=g, orizzonte=21)

    riga = _per_detector(compute_plan_performance(db))["sr_flip"]
    assert riga["n"] == 4
    assert riga["effective_n"] < 4


def test_con_una_sola_finestra_indipendente_non_si_pubblica_un_intervallo(db: Session) -> None:
    """⚠️ `None`, e verdetto «non concludente».

    Con una sola osservazione indipendente la dispersione non e' stimabile.
    Stampare comunque un intervallo suggerirebbe che una misura ci sia — ed e'
    la risposta che il cubo dei detector da' gia' sedici volte su sedici,
    correttamente.
    """
    s = _titolo(db, "AAA")
    for g in (1, 2):
        _riga(db, s, giorno=g, orizzonte=63)

    riga = _per_detector(compute_plan_performance(db))["sr_flip"]
    assert riga["expectancy_ci"] is None
    assert riga["verdict"] == "inconclusive"


def test_un_campione_ampio_e_coerente_produce_un_verdetto(db: Session) -> None:
    s = _titolo(db, "AAA")
    for k in range(24):
        _riga(db, s, giorno=k * 40, esito="tp1", r_mult=2.0 + (k % 3) * 0.1, orizzonte=5)

    riga = _per_detector(compute_plan_performance(db))["sr_flip"]
    assert riga["expectancy_ci"] is not None
    assert riga["expectancy_ci"][0] > 0
    assert riga["verdict"] == "positive"


# ─── 3. Il numero che nessun altro magazzino sa dare ───────────────────────

def test_lo_stop_colpito_PRIMA_di_un_target_poi_raggiunto_viene_contato(db: Session) -> None:
    """La misura di uno stop troppo stretto, e la ragione per cui le date di
    tocco esistono. Senza, questa riga direbbe solo «stop, -1R»."""
    s = _titolo(db, "AAA")
    _riga(db, s, giorno=1, esito="stop", r_mult=-1.0, stop_il=3, tp1_il=12)
    _riga(db, s, giorno=40, esito="stop", r_mult=-1.0, stop_il=2, tp1_il=None)
    _riga(db, s, giorno=80, esito="tp1", r_mult=4.0, stop_il=None, tp1_il=4)

    riga = _per_detector(compute_plan_performance(db))["sr_flip"]
    assert riga["stop_too_tight"] == 1


def test_un_target_toccato_PRIMA_dello_stop_non_conta_come_stop_stretto(db: Session) -> None:
    """Controllo negativo: l'ordine conta, e invertirlo deve cambiare il
    numero. Senza, un conteggio di «entrambi toccati» passerebbe per una
    diagnosi."""
    s = _titolo(db, "AAA")
    _riga(db, s, giorno=1, esito="tp1", r_mult=4.0, stop_il=12, tp1_il=3)

    riga = _per_detector(compute_plan_performance(db))["sr_flip"]
    assert riga["stop_too_tight"] == 0


# ─── 4. La copertura si dichiara, non si sottintende ───────────────────────

def test_i_detector_senza_nessun_piano_compaiono_nella_copertura(db: Session) -> None:
    """⚠️ Il difetto che questa sezione esiste per impedire.

    Sei detector su diciassette non emettevano un livello di invalidazione:
    una classifica costruita sui piani li avrebbe omessi IN SILENZIO, coprendo
    11 detector su 17 e sembrando completa.
    """
    s = _titolo(db, "AAA")
    _riga(db, s, detector="sr_flip", giorno=1)
    # Un alert di un altro detector, senza riga di esito.
    a = Alert(stock_id=s.id, signal_name="squeeze_expansion", signal_date=date(2026, 2, 1),
              triggered_at=datetime(2026, 2, 1, tzinfo=UTC), trigger_price=100.0, snapshot="{}")
    db.add(a)
    db.flush()

    copertura = {c["detector"]: c for c in compute_plan_performance(db)["meta"]["coverage"]}
    assert copertura["squeeze_expansion"]["with_plan"] == 0
    assert copertura["squeeze_expansion"]["alerts"] == 1
    assert copertura["sr_flip"]["with_plan"] == 1


def test_un_magazzino_vuoto_non_esplode_e_non_inventa_numeri(db: Session) -> None:
    dati = compute_plan_performance(db)
    assert dati["rows"] == []
    assert dati["meta"]["rows"] == 0


# ─── 4bis. Le finestre APERTE non entrano nelle medie ──────────────────────

def test_le_finestre_aperte_non_entrano_nell_attesa(db: Session) -> None:
    """⚠️ Il difetto misurato in produzione il 2026-09-23.

    Una riga nasce appena la gara si risolve, di solito molto prima della fine
    dell'orizzonte. Quindi fra le righe dei segnali RECENTI ci sono solo le
    uscite VELOCI — e le veloci sono soprattutto gli stop: gli scaduti arrivano
    per ultimi per definizione. Il 18% del magazzino stava cosi', e
    `structure_break` leggeva −0,20 R sul pannello contro +0,06 a finestre
    chiuse: il segno ribaltato da una popolazione parziale.
    """
    s = _titolo(db, "AAA")
    _riga(db, s, giorno=1, esito="tp1", r_mult=2.0)
    _riga(db, s, giorno=40, esito="stop", r_mult=-1.0, chiusa=False)
    _riga(db, s, giorno=41, esito="stop", r_mult=-1.0, chiusa=False)

    riga = _per_detector(compute_plan_performance(db))["sr_flip"]

    assert riga["expectancy_r"] == pytest.approx(2.0)
    assert riga["n"] == 1
    assert riga["esiti"]["stop"] == 0
    # Le escluse si DICONO: sparire in silenzio sarebbe lo stesso difetto
    # della copertura, con un'altra popolazione.
    assert riga["open_excluded"] == 2


def test_una_finestra_senza_marcatura_conta_come_aperta(db: Session) -> None:
    """Le righe scritte prima che la colonna esistesse la portano NULL. Non si
    sa se la loro finestra fosse chiusa, e il dubbio va dalla parte che non
    distorce: fuori dalla media finche' la maturazione non le riesamina."""
    s = _titolo(db, "AAA")
    _riga(db, s, giorno=1, esito="tp1", r_mult=2.0)
    _riga(db, s, giorno=40, esito="stop", r_mult=-1.0, chiusa=None)

    riga = _per_detector(compute_plan_performance(db))["sr_flip"]

    assert riga["expectancy_r"] == pytest.approx(2.0)
    assert riga["open_excluded"] == 1


def test_un_detector_con_sole_finestre_aperte_si_dichiara_invece_di_sparire(db: Session) -> None:
    """`squeeze_expansion` e `adx_confirmation` emettono il livello solo dal
    2026-09-17: TUTTI i loro piani sono in finestre aperte. Una media di zero
    righe non e' un numero, quindi nella classifica non entrano — ma una
    classifica che li omette senza dirlo sembrerebbe completa."""
    s = _titolo(db, "AAA")
    _riga(db, s, detector="sr_flip", giorno=1)
    _riga(db, s, detector="squeeze_expansion", giorno=40, esito="stop", r_mult=-1.0, chiusa=False)
    _riga(db, s, detector="squeeze_expansion", giorno=41, esito="stop", r_mult=-1.0, chiusa=False)

    dati = compute_plan_performance(db)

    assert set(_per_detector(dati)) == {"sr_flip"}
    assert dati["meta"]["only_open"] == [{"detector": "squeeze_expansion", "open": 2}]
    assert dati["meta"]["rows"] == 1
    assert dati["meta"]["open_excluded"] == 2


# ─── 5. L'endpoint ─────────────────────────────────────────────────────────

def test_l_endpoint_risponde_e_dichiara_la_copertura(db: Session) -> None:
    """Il contratto che il frontend legge. ⚠️ Un test che monta davvero l'app:
    uno schema Pydantic sbagliato non si vede chiamando il servizio."""
    import pytest as _pytest
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models import User

    s = _titolo(db, "AAA")
    _riga(db, s, giorno=1, esito="stop", r_mult=-1.0, stop_il=3, tp1_il=12)
    # E una a finestra aperta di un altro detector: i campi che la dichiarano
    # devono attraversare lo schema, non solo il servizio.
    _riga(db, s, detector="squeeze_expansion", giorno=40, esito="stop", r_mult=-1.0, chiusa=False)
    utente = User(username="admin", password_hash="x")
    db.add(utente)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: utente
    try:
        r = TestClient(app).get("/api/platform/plan-performance")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    dati = r.json()
    assert dati["meta"]["rows"] == 1
    assert "coverage" in dati["meta"]
    riga = dati["rows"][0]
    assert riga["expectancy_r"] == _pytest.approx(-1.0)
    assert riga["stop_too_tight"] == 1
    assert riga["verdict"] == "inconclusive", "una riga sola non puo' dare un verdetto"
    assert riga["open_excluded"] == 0
    assert dati["meta"]["open_excluded"] == 1
    assert dati["meta"]["only_open"] == [{"detector": "squeeze_expansion", "open": 1}]
