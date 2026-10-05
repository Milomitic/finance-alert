"""La sincronizzazione del portafoglio eToro (FA-124).

Le risposte finte sono costruite sui campi della specifica OpenAPI di eToro
(`/trading/info/real/pnl`, `/market-data/instruments`, `/trade/history`,
`/aggregate-portfolio`), letta il 2026-10-05. Il conto dell'utente e' in USD,
con CFD a leva 5: e' il caso di partenza dei test.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import UpstreamUnavailable
from app.models import Position, Stock
from app.models.etoro import EtoroConto, EtoroPosizione, EtoroStrumento
from app.services import etoro_client, rilevanza_service
from app.services import etoro_portafoglio_service as svc

ADESSO = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def posizione(pid: int, iid: int, *, apertura=100.0, leva=5, lato_long=True, stop=80.0, target=130.0,
              pnl=25.0, margine=200.0, esposizione=1000.0, corrente=105.0, mirror=0, regolamento=0) -> dict:
    return {
        "positionID": pid, "CID": 1, "openDateTime": "2026-09-01T14:30:00Z", "openRate": apertura,
        "instrumentID": iid, "mirrorID": mirror, "parentPositionID": 0, "isBuy": lato_long,
        "takeProfitRate": target, "stopLossRate": stop, "amount": margine, "leverage": leva,
        "units": 10.0, "totalFees": -1.25, "initialAmountInDollars": margine, "isTslEnabled": False,
        "settlementTypeID": regolamento, "isNoTakeProfit": target is None, "isNoStopLoss": stop is None,
        "unrealizedPnL": {
            "pnL": pnl, "exposureInAccountCurrency": esposizione, "marginInAccountCurrency": margine,
            "closeRate": corrente, "timestamp": "2026-10-05T11:59:00Z",
        },
    }


class FintoEtoro:
    """Risponde per percorso e registra le chiamate."""

    def __init__(self) -> None:
        self.posizioni: list[dict] = []
        self.mirrors: list[dict] = []
        self.anagrafica: dict[int, dict] = {}
        self.storico: list[dict] = []
        self.totali: dict | None = {
            "accountTotalValue": 5230.5, "accountCurrentPnl": 25.0,
            "dailyGainAccountCurrency": 12.5, "dailyGainAccountCurrencyPercent": 0.24,
        }
        self.watchlist: dict | None = {"watchlists": []}
        self.pnl_rotto = False
        self.aggregato_rotto = False
        self.chiamate: list[tuple[str, dict | None]] = []

    def get(self, percorso: str, *, op: str, params=None):
        self.chiamate.append((percorso, params))
        if percorso == svc._PNL:
            if self.pnl_rotto:
                return {"clientPortfolio": {"credit": 10.0}}
            return {"clientPortfolio": {"positions": self.posizioni, "mirrors": self.mirrors,
                                        "credit": 1234.5, "orders": []}}
        if percorso == svc._STRUMENTI:
            ids = [int(x) for x in params["instrumentsIds"].split(",")]
            return {"results": [self.anagrafica[i] for i in ids if i in self.anagrafica],
                    "pagination": {"hasNext": False}}
        if percorso == svc._STORICO:
            return [r for r in self.storico]
        if percorso == svc._AGGREGATO:
            if self.aggregato_rotto:
                raise UpstreamUnavailable("giu'", source="etoro", op="portafoglio")
            return {"accountCurrency": "USD", "accountTotals": self.totali}
        if percorso == "/api/v1/watchlists":
            return self.watchlist
        raise AssertionError(percorso)

    def percorsi(self) -> list[str]:
        return [p for p, _ in self.chiamate]


@pytest.fixture
def etoro(monkeypatch: pytest.MonkeyPatch) -> FintoEtoro:
    monkeypatch.setattr(settings, "etoro_api_key", "a")
    monkeypatch.setattr(settings, "etoro_user_key", "b")
    finto = FintoEtoro()
    monkeypatch.setattr(etoro_client, "get", finto.get)
    return finto


def strumento(iid: int, simbolo: str, nome: str, tipo: str = "Stocks") -> dict:
    return {"instrumentId": iid, "displayName": nome, "type": tipo, "symbol": simbolo, "exchangeId": 4}


@pytest.fixture
def catalogo(db: Session) -> dict[str, Stock]:
    out = {}
    for t, n, ex in [
        ("AAPL", "Apple Inc.", "NASDAQ"), ("MB.MI", "Mediobanca Banca di Credito Finanziario S.p.A.", "MIL"),
        ("BRK-B", "Berkshire Hathaway Inc.", "NYSE"), ("RR", "Richtech Robotics Inc.", "NASDAQ"),
    ]:
        s = Stock(ticker=t, exchange=ex, name=n, currency="USD")
        db.add(s)
        out[t] = s
    db.commit()
    return out


# ─── Spento, e risposte rotte ───────────────────────────────────────────────


def test_senza_chiavi_non_fa_niente(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "etoro_api_key", "")
    chiamate = []
    monkeypatch.setattr(etoro_client, "get", lambda *a, **k: chiamate.append(a))
    assert svc.sincronizza(db).saltata == "non configurato"
    assert chiamate == []


def test_una_risposta_senza_posizioni_non_chiude_niente(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001)]
    svc.sincronizza(db, adesso=ADESSO)
    etoro.pnl_rotto = True
    with pytest.raises(UpstreamUnavailable):
        svc.sincronizza(db, adesso=ADESSO + timedelta(days=2))
    assert db.get(EtoroPosizione, 1).chiusa_il is None


# ─── Le posizioni ───────────────────────────────────────────────────────────


def test_la_prima_lettura_porta_i_numeri_di_etoro(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001, pnl=25.0, margine=200.0, esposizione=1000.0, corrente=105.0)]
    esito = svc.sincronizza(db, adesso=ADESSO)
    assert (esito.aperte, esito.nuove, esito.strumenti_nuovi) == (1, 1, 1)
    p = db.get(EtoroPosizione, 1)
    assert (p.lato, p.leva, p.regolamento) == ("long", 5, "cfd")
    # P/L, margine ed esposizione sono quelli di eToro, non ricalcolati.
    assert (p.pnl_usd, p.margine_usd, p.esposizione_usd, p.prezzo_corrente) == (25.0, 200.0, 1000.0, 105.0)
    assert (p.stop, p.target, p.commissioni_usd) == (80.0, 130.0, -1.25)
    assert p.mirror_id is None


def test_stop_e_target_disattivati_restano_vuoti(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001, stop=None, target=None)]
    svc.sincronizza(db, adesso=ADESSO)
    p = db.get(EtoroPosizione, 1)
    assert p.stop is None and p.target is None


def test_le_posizioni_del_copy_trading_entrano_col_loro_mirror(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.mirrors = [{"mirrorID": 77, "positions": [posizione(9, 1001, mirror=77, leva=1, regolamento=1)]}]
    svc.sincronizza(db, adesso=ADESSO)
    p = db.get(EtoroPosizione, 9)
    assert (p.mirror_id, p.regolamento) == (77, "reale")


def test_una_posizione_sparita_si_chiude_quando_lo_storico_lo_conferma(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001, target=130.0)]
    svc.sincronizza(db, adesso=ADESSO)

    etoro.posizioni = []
    etoro.storico = [{"positionId": 1, "closeRate": 130.2, "closeTimestamp": "2026-10-05T13:00:00Z",
                      "netProfit": 145.0, "stopLossRate": 80.0, "takeProfitRate": 130.0}]
    esito = svc.sincronizza(db, adesso=ADESSO + timedelta(minutes=10))
    assert esito.chiuse == [1]
    p = db.get(EtoroPosizione, 1)
    assert (p.prezzo_chiusura, p.profitto_netto_usd, p.motivo_chiusura) == (130.2, 145.0, "target")
    assert p.notificata is False


def test_senza_conferma_dello_storico_resta_aperta_per_24_ore(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001)]
    svc.sincronizza(db, adesso=ADESSO)
    etoro.posizioni = []
    assert svc.sincronizza(db, adesso=ADESSO + timedelta(hours=2)).chiuse == []
    assert db.get(EtoroPosizione, 1).chiusa_il is None
    assert svc.sincronizza(db, adesso=ADESSO + timedelta(hours=25)).chiuse == [1]
    assert db.get(EtoroPosizione, 1).motivo_chiusura == "non_trovata"


def test_lo_storico_si_chiede_dall_apertura_ma_mai_oltre_un_anno(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    vecchia = posizione(1, 1001)
    vecchia["openDateTime"] = "2024-01-02T10:00:00Z"
    etoro.posizioni = [vecchia]
    svc.sincronizza(db, adesso=ADESSO)
    etoro.posizioni = []
    svc.sincronizza(db, adesso=ADESSO + timedelta(minutes=10))
    params = [p for percorso, p in etoro.chiamate if percorso == svc._STORICO][0]
    assert params["minDate"] == (ADESSO + timedelta(minutes=10) - timedelta(days=364)).date().isoformat()


@pytest.mark.parametrize("prezzo,atteso", [(80.2, "stop"), (129.6, "target"), (110.0, "chiusa"), (None, "chiusa")])
def test_il_motivo_della_chiusura(prezzo, atteso) -> None:
    assert svc.motivo_chiusura(prezzo, 80.0, 130.0) == atteso


# ─── Abbinamento al catalogo ────────────────────────────────────────────────


def test_simbolo_e_nome_compatibili_si_abbinano_da_soli(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001)]
    svc.sincronizza(db, adesso=ADESSO)
    s = db.get(EtoroStrumento, 1001)
    assert (s.abbinamento, s.stock_id) == ("automatico", catalogo["AAPL"].id)


def test_stesso_simbolo_altra_societa_aspetta_una_conferma(db: Session, etoro: FintoEtoro, catalogo) -> None:
    """«RR» su eToro e' Rolls-Royce; nel catalogo «RR» e' Richtech Robotics."""
    etoro.anagrafica[2002] = strumento(2002, "RR", "Rolls-Royce Holdings")
    etoro.posizioni = [posizione(2, 2002)]
    esito = svc.sincronizza(db, adesso=ADESSO)
    s = db.get(EtoroStrumento, 2002)
    assert (s.abbinamento, s.stock_id, s.candidato_stock_id) == ("da_confermare", None, catalogo["RR"].id)
    assert esito.da_confermare == 1
    # Non abbinata, la posizione NON e' fra i tuoi titoli.
    assert catalogo["RR"].id not in rilevanza_service.titoli_rilevanti(db)


def test_classe_di_azioni_col_punto(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[3003] = strumento(3003, "BRK.B", "Berkshire Hathaway Inc")
    etoro.posizioni = [posizione(3, 3003)]
    svc.sincronizza(db, adesso=ADESSO)
    assert db.get(EtoroStrumento, 3003).stock_id == catalogo["BRK-B"].id


def test_un_suffisso_di_borsa_non_e_una_classe() -> None:
    assert svc._varianti("MB.MI") == {"MB.MI"}
    assert svc._varianti("brk.b") == {"BRK.B", "BRK-B"}


def test_il_suffisso_us_degli_etf_si_toglie() -> None:
    assert svc._varianti("LABU.US") == {"LABU.US", "LABU"}
    assert svc._varianti(".US") == {".US"}


# Le nove coppie del portafoglio vero del 2026-10-05: nome eToro, nome del catalogo.
COPPIE_VERE = [
    ("Nebius Group NV", "Nebius Group"),
    ("Super Micro Computer, Inc", "Supermicro"),
    ("Micron Technology, Inc.", "Micron Technology"),
    ("Direxion Daily S&P Biotech Bull 3X ETF", "Direxion Daily S&P Biotech Bull 3X Shares"),
    ("Direxion Daily Gold Miners Index Bull 2X ETF", "Direxion Daily Gold Miners Bull 2X Shares"),
    ("Direxion Daily Semiconductor Bull 3X ETF", "Direxion Daily Semiconductor Bull 3X Shares"),
    ("Sandisk Corp/DE", "Sandisk"),
    ("Credo Technology Group Holding Ltd", "Credo Technology Group Holding Ltd"),
    ("Keel Infrastructure Corp", "Keel Infrastructure Corp"),
]


@pytest.mark.parametrize("etoro_nome,catalogo_nome", COPPIE_VERE)
def test_le_coppie_del_portafoglio_vero_si_riconoscono(etoro_nome, catalogo_nome) -> None:
    assert svc.nomi_compatibili(etoro_nome, catalogo_nome)


def test_un_etf_col_suffisso_si_abbina(db: Session, etoro: FintoEtoro) -> None:
    db.add(Stock(ticker="LABU", exchange="NYSE Arca", name="Direxion Daily S&P Biotech Bull 3X Shares"))
    db.commit()
    etoro.anagrafica[3199] = strumento(3199, "LABU.US", "Direxion Daily S&P Biotech Bull 3X ETF", tipo="ETF")
    etoro.posizioni = [posizione(7, 3199)]
    svc.sincronizza(db, adesso=ADESSO)
    assert db.get(EtoroStrumento, 3199).abbinamento == "automatico"


def test_uno_strumento_fuori_catalogo_e_assente(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[100000] = strumento(100000, "BTC", "Bitcoin", tipo="Crypto")
    etoro.posizioni = [posizione(4, 100000)]
    svc.sincronizza(db, adesso=ADESSO)
    s = db.get(EtoroStrumento, 100000)
    assert (s.abbinamento, s.stock_id, s.tipo) == ("assente", None, "Crypto")


def test_una_conferma_dell_utente_non_si_rifa_da_sola(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[2002] = strumento(2002, "RR", "Rolls-Royce Holdings")
    etoro.posizioni = [posizione(2, 2002)]
    svc.sincronizza(db, adesso=ADESSO)
    svc.conferma_abbinamento(db, 2002, None)  # «non e' nel catalogo»
    # Un mese dopo l'anagrafica si rilegge: l'abbinamento resta quello deciso.
    svc.sincronizza(db, adesso=ADESSO + timedelta(days=30))
    s = db.get(EtoroStrumento, 2002)
    assert (s.abbinamento, s.stock_id, s.candidato_stock_id) == ("manuale", None, None)


def test_conferma_su_un_ticker(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[5005] = strumento(5005, "MB", "Mediobanca")
    etoro.posizioni = [posizione(5, 5005)]
    svc.sincronizza(db, adesso=ADESSO)
    svc.conferma_abbinamento(db, 5005, "mb.mi")
    assert db.get(EtoroStrumento, 5005).stock_id == catalogo["MB.MI"].id
    with pytest.raises(ValueError):
        svc.conferma_abbinamento(db, 5005, "NONESISTE")
    with pytest.raises(LookupError):
        svc.conferma_abbinamento(db, 999, "AAPL")


def test_l_anagrafica_si_rilegge_solo_dopo_una_settimana(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001)]
    svc.sincronizza(db, adesso=ADESSO)
    svc.sincronizza(db, adesso=ADESSO + timedelta(hours=1))
    assert etoro.percorsi().count(svc._STRUMENTI) == 1
    svc.sincronizza(db, adesso=ADESSO + timedelta(days=8))
    assert etoro.percorsi().count(svc._STRUMENTI) == 2


def test_da_decidere_solo_cio_che_chiede_una_decisione(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica.update({
        2002: strumento(2002, "RR", "Rolls-Royce Holdings"),
        6006: strumento(6006, "ZZZZ", "Societa' fuori catalogo", tipo="Stocks"),
        100000: strumento(100000, "BTC", "Bitcoin", tipo="Crypto"),
        1001: strumento(1001, "AAPL", "Apple"),
    })
    etoro.posizioni = [posizione(i, iid) for i, iid in enumerate([6006, 2002, 100000, 1001], start=1)]
    svc.sincronizza(db, adesso=ADESSO)
    # Prima l'incerto, poi l'azionario assente; crypto e abbinati no.
    assert [s.instrument_id for s in svc.da_decidere(db)] == [2002, 6006]
    # Una posizione chiusa non chiede piu' niente.
    etoro.posizioni = [p for p in etoro.posizioni if p["instrumentID"] != 6006]
    etoro.storico = [{"positionId": 1, "closeRate": 1.0, "closeTimestamp": "2026-10-05T13:00:00Z", "netProfit": 0.0}]
    svc.sincronizza(db, adesso=ADESSO + timedelta(minutes=10))
    assert [s.instrument_id for s in svc.da_decidere(db)] == [2002]


@pytest.mark.parametrize("a,b,atteso", [
    ("Apple", "Apple Inc.", True),
    ("Mediobanca", "Mediobanca Banca di Credito Finanziario S.p.A.", True),
    ("Rolls-Royce Holdings", "Richtech Robotics Inc.", False),
    ("", "Apple Inc.", False),
])
def test_nomi_compatibili(a, b, atteso) -> None:
    assert svc.nomi_compatibili(a, b) is atteso


# ─── I tuoi titoli ──────────────────────────────────────────────────────────


def test_una_posizione_eToro_abbinata_e_fra_i_tuoi_titoli(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001)]
    svc.sincronizza(db, adesso=ADESSO)
    aapl = catalogo["AAPL"].id
    assert rilevanza_service.titoli_rilevanti(db)[aapl] == rilevanza_service.POSIZIONE
    # E smette di esserlo quando si chiude.
    etoro.posizioni = []
    etoro.storico = [{"positionId": 1, "closeRate": 110.0, "closeTimestamp": "2026-10-05T13:00:00Z", "netProfit": 50.0}]
    svc.sincronizza(db, adesso=ADESSO + timedelta(minutes=10))
    assert aapl not in rilevanza_service.titoli_rilevanti(db)


def test_le_posizioni_manuali_restano_fra_i_tuoi_titoli(db: Session, catalogo) -> None:
    db.add(Position(stock_id=catalogo["MB.MI"].id, side="long", entry_price=26.7))
    db.commit()
    assert rilevanza_service.titoli_rilevanti(db)[catalogo["MB.MI"].id] == rilevanza_service.POSIZIONE


# ─── Conto ──────────────────────────────────────────────────────────────────


def test_i_totali_del_conto(db: Session, etoro: FintoEtoro, catalogo) -> None:
    esito = svc.sincronizza(db, adesso=ADESSO)
    conto = db.get(EtoroConto, 1)
    assert esito.conto_aggiornato is True
    assert (conto.valuta, conto.credito_usd, conto.valore_totale, conto.guadagno_giorno) == ("USD", 1234.5, 5230.5, 12.5)
    params = [p for percorso, p in etoro.chiamate if percorso == svc._AGGREGATO][0]
    # Mezzanotte di Roma (ora legale): le 22:00 UTC del giorno prima.
    assert params["dailyCutoffUtc"] == "2026-10-04T22:00:00Z"


def test_i_totali_mancanti_non_fermano_le_posizioni(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001)]
    etoro.aggregato_rotto = True
    esito = svc.sincronizza(db, adesso=ADESSO)
    assert esito.conto_aggiornato is False and esito.aperte == 1
    assert db.get(EtoroConto, 1).credito_usd == 1234.5


def test_un_conto_senza_totali_non_e_aggiornato(db: Session, etoro: FintoEtoro) -> None:
    etoro.totali = None
    assert svc.sincronizza(db, adesso=ADESSO).conto_aggiornato is False


@pytest.mark.parametrize("adesso,atteso", [
    (datetime(2026, 7, 1, 10, tzinfo=UTC), datetime(2026, 6, 30, 22, tzinfo=UTC)),
    (datetime(2026, 12, 1, 10, tzinfo=UTC), datetime(2026, 11, 30, 23, tzinfo=UTC)),
    # Le 23:30 UTC d'estate sono gia' il giorno dopo a Roma.
    (datetime(2026, 7, 1, 23, 30, tzinfo=UTC), datetime(2026, 7, 1, 22, tzinfo=UTC)),
])
def test_mezzanotte_di_roma(adesso, atteso) -> None:
    assert svc.mezzanotte_di_roma_utc(adesso) == atteso


# ─── Geometria a leva ───────────────────────────────────────────────────────


def test_lo_stop_in_percento_del_margine_moltiplica_per_la_leva() -> None:
    # Long da 100 con stop a 90 e leva 5: -10% del prezzo = -50% del margine.
    assert svc.stop_sul_margine("long", 100.0, 90.0, 5) == pytest.approx(-50.0)
    # Short da 100 con stop a 104: -4% x 5 = -20%.
    assert svc.stop_sul_margine("short", 100.0, 104.0, 5) == pytest.approx(-20.0)
    assert svc.stop_sul_margine("long", 100.0, None, 5) is None


def test_il_pnl_in_percento_del_margine() -> None:
    assert svc.pct_sul_margine(25.0, 200.0) == pytest.approx(12.5)
    assert svc.pct_sul_margine(25.0, 0.0) is None
    assert svc.pct_sul_margine(None, 200.0) is None


# ─── Notifiche ──────────────────────────────────────────────────────────────


def test_le_chiusure_da_notificare_si_segnano_una_volta(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.posizioni = [posizione(1, 1001)]
    svc.sincronizza(db, adesso=ADESSO)
    assert svc.da_notificare(db) == []
    etoro.posizioni = []
    etoro.storico = [{"positionId": 1, "closeRate": 110.0, "closeTimestamp": "2026-10-05T13:00:00Z", "netProfit": 50.0}]
    svc.sincronizza(db, adesso=ADESSO + timedelta(minutes=10))
    [(pos, strum, stock)] = svc.da_notificare(db)
    assert (pos.position_id, strum.simbolo, stock.ticker) == (1, "AAPL", "AAPL")
    svc.segna_notificate(db, [1])
    assert svc.da_notificare(db) == []


# ─── Le costanti stanno nelle colonne ───────────────────────────────────────


def test_le_costanti_entrano_nelle_colonne() -> None:
    lung = lambda m, c: m.__table__.c[c].type.length  # noqa: E731
    assert max(map(len, svc.ABBINAMENTI)) <= lung(EtoroStrumento, "abbinamento")
    assert max(map(len, svc.MOTIVI)) <= lung(EtoroPosizione, "motivo_chiusura")
    assert max(map(len, [*svc.REGOLAMENTI.values(), svc.ALTRO])) <= lung(EtoroPosizione, "regolamento")
    assert max(len("long"), len("short")) <= lung(EtoroPosizione, "lato")
