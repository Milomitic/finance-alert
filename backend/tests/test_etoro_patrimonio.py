"""Patrimonio e andamento del conto eToro (FA-127).

Le forme delle risposte sono quelle lette dal pod il 2026-10-06:
`/balances/history` con due conti per fotografia (Trading in USD, Cash in EUR
quasi vuoto), lo storico delle chiuse come lista, l'istantanea con
`dailyGainAccountCurrency` per strumento.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import UpstreamUnavailable
from app.main import app
from app.models import Stock, User
from app.models.etoro import EtoroOperazione, EtoroPatrimonioGiorno, EtoroPuntoIntraday
from app.services import etoro_patrimonio_service as pat
from app.services import etoro_portafoglio_service as svc
from tests.test_etoro_portafoglio import FintoEtoro, posizione, strumento

ADESSO = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)  # 12:00 a Roma


def snapshot(g: str, totale: float, pnl: float, cassa: float = 0.0, investito: float | None = None) -> dict:
    inv = totale - cassa - pnl if investito is None else investito
    return {"date": g, "totalBalance": totale + 0.86, "accountSnapshots": [
        {"accountType": "Trading", "currency": "USD", "displayTotal": totale, "displayCash": cassa,
         "displayInvestedAmount": inv, "displayPnl": pnl},
        {"accountType": "Cash", "currency": "EUR", "displayTotal": 0.86, "displayCash": 0.86,
         "displayInvestedAmount": 0.0, "displayPnl": 0.0},
    ]}


@pytest.fixture
def etoro(monkeypatch: pytest.MonkeyPatch) -> FintoEtoro:
    from app.core.config import settings
    from app.services import etoro_client

    monkeypatch.setattr(settings, "etoro_api_key", "a")
    monkeypatch.setattr(settings, "etoro_user_key", "b")
    finto = FintoEtoro()
    monkeypatch.setattr(etoro_client, "get", finto.get)
    pat.svuota_cache()
    return finto


def test_il_recupero_prende_solo_il_conto_trading_e_lascia_oggi_vivo(db: Session, etoro: FintoEtoro) -> None:
    etoro.saldi = {"snapshots": [
        snapshot("2026-10-04", 8658.74, 1064.15, cassa=-30.37),
        snapshot("2026-10-05", 8700.0, 1100.0),
        snapshot("2026-10-06", 9999.0, 0.0),  # oggi: eToro lo fotografa a giorno chiuso
    ]}
    etoro.storico = [{"positionId": 7, "closeTimestamp": "2026-10-05T15:00:00+02:00", "netProfit": 145.0,
                      "openTimestamp": "2026-09-01T10:00:00Z", "isBuy": True, "leverage": 5,
                      "openRate": 30.0, "closeRate": 33.0, "investment": 300.0, "fees": 1.5, "instrumentId": 3226}]
    giorni, operazioni = pat.recupera(db, adesso=ADESSO)
    assert (giorni, operazioni) == (2, 1)
    g = db.get(EtoroPatrimonioGiorno, date(2026, 10, 4))
    # Il conto Cash in euro (0,86) NON entra: il dato vivo e' del solo Trading.
    assert (g.valore, g.cassa, g.pnl_aperto, g.fonte) == (8658.74, -30.37, 1064.15, "storico")
    assert db.get(EtoroPatrimonioGiorno, date(2026, 10, 6)) is None
    op = db.get(EtoroOperazione, 7)
    # In UTC: le 15:00 di Roma sono le 13:00.
    assert op.chiusa_il.replace(tzinfo=None) == datetime(2026, 10, 5, 13, 0)
    assert pat.ha_storico(db) is True


def test_le_date_della_richiesta_sono_in_utc(db: Session, etoro: FintoEtoro) -> None:
    """00:55 del 6 a Roma = 22:55 UTC del 5: per eToro «domani» e' nel futuro."""
    notte = datetime(2026, 10, 5, 22, 55, tzinfo=UTC)
    pat.recupera(db, adesso=notte)
    params = [p for percorso, p in etoro.chiamate if percorso == "/api/v1/balances/history"][0]
    assert (params["toDate"], params["fromDate"]) == ("2026-10-05", "2025-10-06")


def test_la_sincronizzazione_scrive_la_riga_di_oggi_e_un_punto(db: Session, etoro: FintoEtoro) -> None:
    db.add(Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc."))
    db.commit()
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001)]
    svc.sincronizza(db, adesso=ADESSO)
    oggi = db.get(EtoroPatrimonioGiorno, date(2026, 10, 6))
    assert (oggi.valore, oggi.fonte) == (5230.5, "vivo")
    assert oggi.investito == pytest.approx(5230.5 - 1234.5 - 25.0)
    assert len(db.query(EtoroPuntoIntraday).all()) == 1
    # Un altro giro dopo 30 s: la riga si aggiorna, il punto no (uno al minuto).
    etoro.totali["accountTotalValue"] = 5240.0
    svc.sincronizza(db, adesso=ADESSO + timedelta(seconds=30))
    assert db.get(EtoroPatrimonioGiorno, date(2026, 10, 6)).valore == 5240.0
    assert len(db.query(EtoroPuntoIntraday).all()) == 1
    svc.sincronizza(db, adesso=ADESSO + timedelta(minutes=2))
    assert len(db.query(EtoroPuntoIntraday).all()) == 2


def test_una_riga_storica_non_si_riscrive_col_vivo(db: Session) -> None:
    db.add(EtoroPatrimonioGiorno(giorno=date(2026, 10, 6), valore=100.0, fonte="storico", aggiornato_il=ADESSO))
    db.commit()
    pat.fotografa(db, 999.0, 0.0, 0.0, 0.0, ADESSO)
    assert db.get(EtoroPatrimonioGiorno, date(2026, 10, 6)).valore == 100.0


def test_i_punti_vecchi_si_tolgono(db: Session) -> None:
    db.add(EtoroPuntoIntraday(istante=ADESSO - timedelta(days=4), valore=1.0))
    db.commit()
    pat.fotografa(db, 2.0, None, None, None, ADESSO)
    db.commit()
    assert [p.valore for p in db.query(EtoroPuntoIntraday).all()] == [2.0]


def test_fotografa_senza_valore_non_scrive(db: Session) -> None:
    assert pat.fotografa(db, None, 1.0, 1.0, 1.0, ADESSO) is False


# ─── Il rendimento senza versamenti ─────────────────────────────────────────


def _giorni(db: Session, valori: list[tuple[str, float, float]]) -> None:
    for g, v, p in valori:
        db.add(EtoroPatrimonioGiorno(giorno=date.fromisoformat(g), valore=v, pnl_aperto=p,
                                     fonte="storico", aggiornato_il=ADESSO))
    db.commit()


def test_il_generato_non_conta_un_versamento(db: Session) -> None:
    """Un versamento di 5.000 alza il valore ma non il rendimento."""
    _giorni(db, [("2026-09-28", 2000.0, 100.0), ("2026-10-02", 7300.0, 400.0), ("2026-10-06", 7500.0, 500.0)])
    db.add(EtoroOperazione(position_id=1, instrument_id=1, chiusa_il=datetime(2026, 10, 1, 14, tzinfo=UTC),
                           lato="long", leva=5, profitto_netto_usd=100.0))
    db.commit()
    [s1] = [p for p in pat.periodi(db, list(db.query(EtoroPatrimonioGiorno).order_by(EtoroPatrimonioGiorno.giorno)),
                                   date(2026, 10, 6)) if p.chiave == "1S"]
    assert s1.dal == date(2026, 9, 28)
    assert s1.variazione == pytest.approx(5500.0)
    # 100 realizzati + (500 - 100) di P/L aperto = 500 generati; 5.000 di flussi.
    assert (s1.realizzato, s1.generato, s1.flussi) == (100.0, 500.0, 5000.0)
    # In % del capitale MEDIO (Modified Dietz), non dei 2.000 di partenza: il
    # 2 ottobre entrano 4.900 (5.300 di variazione, 100 realizzati, 300 di P/L
    # aperto) e restano nel conto meta' del periodo: 500 / (2.000 + 4.900 / 2).
    # Sul valore di partenza sarebbe stato il 25%.
    assert s1.generato_pct == pytest.approx(500 / 4450 * 100)


def test_un_conto_quasi_vuoto_alla_partenza_non_gonfia_la_percentuale(db: Session) -> None:
    """Il caso vero dei tre mesi: 914 USD, poi zero, poi 3.000 versati."""
    _giorni(db, [("2026-09-29", 914.0, 0.0), ("2026-09-30", 0.0, 0.0), ("2026-10-02", 3000.0, 0.0),
                 ("2026-10-06", 3300.0, 300.0)])
    righe = list(db.query(EtoroPatrimonioGiorno).order_by(EtoroPatrimonioGiorno.giorno))
    [s1] = [p for p in pat.periodi(db, righe, date(2026, 10, 6)) if p.chiave == "1S"]
    assert s1.generato == pytest.approx(300.0)
    assert s1.dal == date(2026, 9, 29)
    # -914 per 6 giorni su 7, +3.000 per 4 su 7: capitale medio 1.844,86.
    assert s1.generato_pct == pytest.approx(300 / (914 - 914 * 6 / 7 + 3000 * 4 / 7) * 100)
    # Sul valore di partenza sarebbe stato il +32,8%.
    assert s1.generato_pct < 20


def test_un_capitale_medio_nullo_non_da_percentuale(db: Session) -> None:
    _giorni(db, [("2026-09-28", 0.0, 0.0), ("2026-10-06", 0.0, 0.0)])
    righe = list(db.query(EtoroPatrimonioGiorno).order_by(EtoroPatrimonioGiorno.giorno))
    [s1] = [p for p in pat.periodi(db, righe, date(2026, 10, 6)) if p.chiave == "1S"]
    assert (s1.generato, s1.generato_pct) == (0.0, None)


def _chiusa(pid: int, giorno: str) -> dict:
    return {"positionId": pid, "closeTimestamp": f"{giorno}T15:00:00Z", "netProfit": 1.0, "isBuy": True,
            "leverage": 5, "instrumentId": 3226, "openTimestamp": f"{giorno}T10:00:00Z"}


def test_lo_storico_si_legge_fino_alla_pagina_vuota_non_alla_corta(db: Session, etoro: FintoEtoro) -> None:
    """eToro rende 87 righe su 100 a pagina 1 e ne ha altre sette pagine dopo."""
    etoro.pagine_storico = [
        [_chiusa(i, "2026-10-01") for i in range(1, 4)],
        [_chiusa(i, "2026-07-01") for i in range(4, 6)],
        [_chiusa(6, "2025-11-01")],
    ]
    _, operazioni = pat.recupera(db, adesso=ADESSO)
    assert operazioni == 6
    pagine = [p["page"] for percorso, p in etoro.chiamate if percorso == svc._STORICO]
    assert pagine == [1, 2, 3, 4]
    # Controllo negativo: con la regola vecchia («corta = ultima») ci si
    # sarebbe fermati alla prima, perche' 3 righe sono meno di 100.
    assert len(etoro.pagine_storico[0]) < 100


def test_una_pagina_senza_posizioni_nuove_ferma_la_lettura(db: Session, etoro: FintoEtoro) -> None:
    """Un'API che ignorasse `page` renderebbe sempre le stesse righe."""
    etoro.storico = [_chiusa(1, "2026-10-01"), _chiusa(2, "2026-10-02")]
    _, operazioni = pat.recupera(db, adesso=ADESSO)
    assert operazioni == 2
    assert [p["page"] for percorso, p in etoro.chiamate if percorso == svc._STORICO] == [1, 2]


def test_il_tetto_di_pagine_si_dichiara(etoro: FintoEtoro) -> None:
    from loguru import logger

    etoro.pagine_storico = [[_chiusa(i, "2026-10-01")] for i in range(1, 6)]
    righe: list[str] = []
    gancio = logger.add(lambda m: righe.append(str(m)), level="WARNING")
    try:
        out = svc.leggi_storico(date(2026, 1, 1), pagine=3)
    finally:
        logger.remove(gancio)
    assert sorted(out) == [1, 2, 3]
    assert any("fermato a 3 pagine" in r for r in righe)


def test_una_chiusa_del_giorno_di_partenza_non_conta(db: Session) -> None:
    _giorni(db, [("2026-09-28", 2000.0, 0.0), ("2026-10-06", 2100.0, 0.0)])
    # Chiusa il 28 alle 20:00 di Roma: e' gia' dentro il valore di fine giornata del 28.
    db.add(EtoroOperazione(position_id=1, instrument_id=1, chiusa_il=datetime(2026, 9, 28, 18, tzinfo=UTC),
                           lato="long", leva=5, profitto_netto_usd=999.0))
    db.commit()
    righe = list(db.query(EtoroPatrimonioGiorno).order_by(EtoroPatrimonioGiorno.giorno))
    [s1] = [p for p in pat.periodi(db, righe, date(2026, 10, 6)) if p.chiave == "1S"]
    assert s1.realizzato == 0.0


def test_uno_storico_corto_parte_dal_primo_giorno(db: Session) -> None:
    _giorni(db, [("2026-09-20", 1000.0, 0.0), ("2026-10-06", 1100.0, 50.0)])
    righe = list(db.query(EtoroPatrimonioGiorno).order_by(EtoroPatrimonioGiorno.giorno))
    per = {p.chiave: p for p in pat.periodi(db, righe, date(2026, 10, 6))}
    assert per["1A"].dal == date(2026, 9, 20)
    assert per["YTD"].dal == date(2026, 9, 20)


def test_senza_pnl_il_generato_e_ignoto_non_zero(db: Session) -> None:
    db.add_all([
        EtoroPatrimonioGiorno(giorno=date(2026, 9, 28), valore=1.0, pnl_aperto=None, fonte="storico", aggiornato_il=ADESSO),
        EtoroPatrimonioGiorno(giorno=date(2026, 10, 6), valore=2.0, pnl_aperto=1.0, fonte="vivo", aggiornato_il=ADESSO),
    ])
    db.commit()
    righe = list(db.query(EtoroPatrimonioGiorno).order_by(EtoroPatrimonioGiorno.giorno))
    s1 = [p for p in pat.periodi(db, righe, date(2026, 10, 6)) if p.chiave == "1S"][0]
    assert (s1.generato, s1.flussi, s1.generato_pct) == (None, None, None)


def test_con_un_giorno_solo_non_ci_sono_periodi(db: Session) -> None:
    _giorni(db, [("2026-10-06", 1.0, 0.0)])
    assert pat.periodi(db, list(db.query(EtoroPatrimonioGiorno)), date(2026, 10, 6)) == []


# ─── Dal vivo ───────────────────────────────────────────────────────────────


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_vivo_porta_i_numeri_del_giorno_e_chi_muove_il_conto(client: TestClient, db: Session, etoro: FintoEtoro) -> None:
    db.add(Stock(ticker="SOXL", exchange="NYSE Arca", name="Direxion Daily Semiconductor Bull 3X Shares"))
    db.commit()
    etoro.anagrafica[3226] = strumento(3226, "SOXL", "Direxion Daily Semiconductor Bull 3X ETF", tipo="ETF")
    etoro.posizioni = [posizione(1, 3226)]
    svc.sincronizza(db, adesso=ADESSO)
    pat.svuota_cache()
    etoro.totali.update(accountTotalUsedMargin=7483.79, accountAvailableCash=111.28, yesterdayTotalValue=8713.89)
    vecchio_get = etoro.get

    def con_aggregati(percorso, **k):
        r = vecchio_get(percorso, **k)
        if percorso == svc._AGGREGATO:
            r["instrumentAggregates"] = [
                {"instrumentId": 3226, "dailyGainAccountCurrency": -300.0, "accountCurrencyReturn": 965.6,
                 "netCurrentExposureAccountCurrency": 8685.4, "totalMarginAccountCurrency": 1547.9},
                {"instrumentId": 999, "dailyGainAccountCurrency": 20.0, "netCurrentExposureAccountCurrency": 1000.0},
            ]
        return r

    from app.services import etoro_client

    etoro_client.get = con_aggregati  # ripristinato dal monkeypatch della fixture
    body = client.get("/api/etoro/vivo").json()
    assert body["in_ritardo"] is False and body["valore"] == 5230.5
    assert (body["margine_usato"], body["cassa"], body["valore_ieri"]) == (7483.79, 111.28, 8713.89)
    assert body["esposizione"] == pytest.approx(9685.4)
    assert body["leva_effettiva"] == pytest.approx(9685.4 / 5230.5)
    # Ordinati per peso del movimento di oggi, col ticker del catalogo se abbinato.
    assert [(s["ticker"], s["guadagno_giorno"]) for s in body["strumenti"]] == [("SOXL", -300.0), (None, 20.0)]


def test_vivo_usa_la_cache_per_trenta_secondi(db: Session, etoro: FintoEtoro) -> None:
    orologio = [100.0]
    pat.vivo(db, adesso=ADESSO, ora=lambda: orologio[0])
    orologio[0] += 10
    pat.vivo(db, adesso=ADESSO, ora=lambda: orologio[0])
    assert etoro.percorsi().count(svc._AGGREGATO) == 1
    orologio[0] += 31
    pat.vivo(db, adesso=ADESSO, ora=lambda: orologio[0])
    assert etoro.percorsi().count(svc._AGGREGATO) == 2


def test_vivo_senza_eToro_rende_l_ultima_sincronizzazione_in_ritardo(db: Session, etoro: FintoEtoro, monkeypatch) -> None:
    db.add(Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc."))
    db.commit()
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001, esposizione=1000.0, margine=200.0)]
    svc.sincronizza(db, adesso=ADESSO)
    pat.svuota_cache()
    from app.services import etoro_client

    def giu(*a, **k):
        raise UpstreamUnavailable("giu'", source="etoro", op="portafoglio")

    monkeypatch.setattr(etoro_client, "get", giu)
    v = pat.vivo(db, adesso=ADESSO)
    assert v.in_ritardo is True and v.valore == 5230.5
    assert (v.esposizione, v.margine_usato, v.posizioni) == (1000.0, 200.0, 1)


def test_vivo_senza_niente_rende_none(db: Session, etoro: FintoEtoro, monkeypatch) -> None:
    from app.services import etoro_client

    monkeypatch.setattr(etoro_client, "get", lambda *a, **k: {"accountTotals": None})
    assert pat.vivo(db, adesso=ADESSO) is None


def test_gli_endpoint_senza_chiavi(client: TestClient, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "etoro_api_key", "")
    assert client.get("/api/etoro/vivo").json()["configurato"] is False
    a = client.get("/api/etoro/andamento").json()
    assert (a["configurato"], a["giorni"], a["periodi"]) == (False, [], [])


def test_l_andamento_porta_giorni_punti_di_oggi_e_periodi(client: TestClient, db: Session, etoro: FintoEtoro) -> None:
    oggi = datetime.now(UTC)
    _giorni(db, [((oggi - timedelta(days=40)).date().isoformat(), 2000.0, 100.0),
                 ((oggi - timedelta(days=2)).date().isoformat(), 2100.0, 150.0)])
    pat.fotografa(db, 2200.0, 0.0, 200.0, 10.0, oggi)
    db.commit()
    a = client.get("/api/etoro/andamento").json()
    assert len(a["giorni"]) == 3 and a["giorni"][-1]["fonte"] == "vivo"
    assert [p["valore"] for p in a["oggi"]] == [2200.0]
    assert {p["chiave"] for p in a["periodi"]} >= {"1M", "3M", "1A"}


def test_le_fonti_entrano_nella_colonna() -> None:
    assert max(map(len, pat.FONTI)) <= EtoroPatrimonioGiorno.__table__.c["fonte"].type.length
