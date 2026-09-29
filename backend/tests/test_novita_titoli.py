"""Le novita' sui titoli seguiti nel digest: analisti, insider, trimestrali."""
import time
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import NovitaNotificata, Position, Stock
from app.models.preferito import Preferito
from app.services import notifier_service, stock_fundamentals_service
from app.services import novita_titoli_service as nt
from app.services.stock_fundamentals_service import (
    AnalystAction,
    EarningsPoint,
    Fundamentals,
    InsiderTransaction,
)

OGGI = date(2026, 9, 29)
DAL = date(2026, 9, 15)


@pytest.fixture(autouse=True)
def _cache_pulita():
    stock_fundamentals_service._CACHE.clear()
    yield
    stock_fundamentals_service._CACHE.clear()


def _az(data="2026-09-28", firm="Morgan Stanley", action="up", to="Overweight", da="Equal-Weight",
        target=None, prima=None, mossa=None) -> AnalystAction:
    return AnalystAction(date=data, firm=firm, to_grade=to, from_grade=da, action=action,
                         current_price_target=target, prior_price_target=prima,
                         price_target_action=mossa)


def _fund(ticker="POS", *, azioni=(), insider=(), utili=(), eta_ore=1.0) -> Fundamentals:
    f = Fundamentals(ticker=ticker, analyst_actions=list(azioni), insiders=list(insider),
                     earnings=list(utili), fetched_at=time.time() - eta_ore * 3600)
    stock_fundamentals_service._CACHE[ticker] = f
    return f


def _testi(fund) -> list[str]:
    return [n.testo for n in nt.dai_fondamentali(fund, ticker="POS", nome=None,
                                                 rilevanza="posizione", dal=DAL)]


# ─── che cosa e' una novita' ─────────────────────────────────────────────


def test_un_cambio_di_giudizio_con_il_target(db) -> None:
    f = _fund(azioni=[_az(target=310, prima=287, mossa="Raises")])
    assert _testi(f) == [
        "Morgan Stanley alza il giudizio a Overweight (era Equal-Weight), "
        "alza il prezzo-obiettivo: 287 → 310"
    ]


def test_una_conferma_conta_solo_se_sposta_il_target(db) -> None:
    f = _fund(azioni=[
        _az(action="main", to="Buy", da="Buy", target=100, prima=100, mossa="Maintains"),
        _az(action="main", firm="UBS", to="Buy", da="Buy", target=95, prima=100, mossa="Lowers"),
        _az(action="reit", firm="Jefferies", to="Hold", da="Hold"),
    ])
    assert _testi(f) == ["UBS abbassa il prezzo-obiettivo: 100 → 95"]


def test_una_copertura_nuova(db) -> None:
    f = _fund(azioni=[_az(action="init", firm="Barclays", to="Underweight", da="")])
    assert _testi(f) == ["Barclays inizia la copertura: Underweight"]


def test_gli_acquisti_degli_insider_si_le_vendite_no(db) -> None:
    f = _fund(insider=[
        InsiderTransaction("Mario Rossi", "CEO", "Purchase at price 12.50 per share.", "2026-09-25", 1000, 12500.0),
        InsiderTransaction("Anna Bianchi", "CFO", "Sale at price 13.00 per share.", "2026-09-26", 5000, 65000.0),
        InsiderTransaction("Luca Verdi", "Director", "Stock Gift", "2026-09-26", 100, None),
    ])
    assert _testi(f) == ["Mario Rossi (CEO) compra per 12.500 $"]


def test_una_trimestrale_pubblicata_con_la_sorpresa(db) -> None:
    f = _fund(utili=[
        EarningsPoint("2026-09-24", 1.40, 1.52, 8.57),
        EarningsPoint("2026-12-20", 1.60, None, None),     # futura: non e' una novita'
    ])
    assert _testi(f) == ["trimestrale pubblicata: utile per azione 1.52 contro 1.4 atteso (+8.6%)"]


def test_i_fatti_prima_della_finestra_non_sono_novita(db) -> None:
    f = _fund(azioni=[_az(data="2026-09-14")], utili=[EarningsPoint("2026-08-01", 1, 1.1, 10.0)])
    assert _testi(f) == []


# ─── quali titoli, e una volta sola ──────────────────────────────────────


@pytest.fixture
def seguiti(db: Session) -> dict[str, Stock]:
    out = {}
    for t in ["POS", "PREF", "NESSUNO"]:
        s = Stock(ticker=t, exchange="X", name=f"{t} Spa")
        db.add(s)
        db.flush()
        out[t] = s
    db.add(Position(stock_id=out["POS"].id, entry_price=Decimal("10")))
    db.add(Preferito(stock_id=out["PREF"].id))
    db.commit()
    return out


def test_solo_i_titoli_seguiti_posizioni_prima(db: Session, seguiti) -> None:
    for t in ["PREF", "POS", "NESSUNO"]:
        _fund(t, azioni=[_az()])
    novita = nt.da_mandare(db, OGGI, rinfresca=False)
    assert [(n.ticker, n.rilevanza) for n in novita] == [("POS", "posizione"), ("PREF", "preferito")]


def test_una_novita_mandata_non_riparte(db: Session, seguiti) -> None:
    _fund("POS", azioni=[_az()])
    prima = nt.da_mandare(db, OGGI, rinfresca=False)
    nt.segna_mandate(db, prima)
    nt.segna_mandate(db, prima)          # due volte: nessun errore
    assert nt.da_mandare(db, OGGI, rinfresca=False) == []
    # Una novita' che affiora DOPO, con una data vecchia, parte ancora.
    _fund("POS", azioni=[_az(), _az(data="2026-09-20", firm="UBS", action="down", to="Neutral", da="Buy")])
    [nuova] = nt.da_mandare(db, OGGI, rinfresca=False)
    assert nuova.testo.startswith("UBS abbassa il giudizio")


def test_due_voci_identiche_sono_un_fatto_solo(db: Session, seguiti) -> None:
    """La stessa azione dalla tabella di yfinance e da un titolo di notizia."""
    _fund("POS", azioni=[_az(), _az()])
    assert len(nt.da_mandare(db, OGGI, rinfresca=False)) == 1


def test_si_rinfresca_solo_la_cache_vecchia(db: Session, seguiti, monkeypatch) -> None:
    _fund("POS", eta_ore=nt.MAX_ETA_ORE + 1)
    _fund("PREF", eta_ore=1)
    chiesti = []
    monkeypatch.setattr(stock_fundamentals_service, "get_fundamentals",
                        lambda t, force_refresh=False: chiesti.append((t, force_refresh)))
    nt.da_mandare(db, OGGI)
    assert chiesti == [("POS", True)]


# ─── nel digest ──────────────────────────────────────────────────────────


@pytest.fixture
def telegram(monkeypatch) -> list[str]:
    inviati: list[str] = []
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(notifier_service, "_send_telegram",
                        lambda text, what: inviati.append(text) or True)
    monkeypatch.setattr(stock_fundamentals_service, "get_fundamentals",
                        lambda *a, **k: None)
    return inviati


def test_il_digest_parte_anche_senza_alert_e_non_ripete(db: Session, seguiti, telegram) -> None:
    _fund("POS", azioni=[_az(target=310, prima=287, mossa="Raises")])
    primo = notifier_service.send_daily_digest(db)
    assert primo.sent
    [testo] = telegram
    assert "Novità sui tuoi titoli (1):" in testo
    assert "💼 <b>POS</b> 28/09 — Morgan Stanley alza il giudizio" in testo
    assert "Nessun alert nuovo nelle ultime 24h." in testo
    assert notifier_service.send_daily_digest(db).reason == "no_alerts"
    assert len(telegram) == 1


def test_se_telegram_fallisce_le_novita_ripartono_domani(db: Session, seguiti, telegram, monkeypatch) -> None:
    _fund("POS", azioni=[_az()])
    monkeypatch.setattr(notifier_service, "_send_telegram", lambda text, what: False)
    assert notifier_service.send_daily_digest(db).reason == "http_error"
    assert db.execute(select(func.count()).select_from(NovitaNotificata)).scalar() == 0


def test_un_errore_nelle_novita_non_toglie_il_digest(db: Session, seguiti, telegram, monkeypatch) -> None:
    import json

    from app.models import Alert

    db.add(Alert(stock_id=seguiti["NESSUNO"].id, signal_name="volume_breakout", trigger_price=10,
                 snapshot=json.dumps({"tone": "bull"}), emitted_at=datetime.now(UTC)))
    db.commit()

    def rotto(*a, **k):
        raise RuntimeError("cache illeggibile")

    monkeypatch.setattr(nt, "da_mandare", rotto)
    assert notifier_service.send_daily_digest(db).sent
    assert "Novità" not in telegram[0]


# ─── i depositi 13F ──────────────────────────────────────────────────────


def _fondo(db: Session, nome: str, periodi: list[date]) -> list:
    """Un fondo con un deposito per periodo; l'ultimo ricevuto oggi, gli altri
    tre mesi fa."""
    from app.models import Institutional, InstitutionalFiling

    fondo = Institutional(slug=nome.lower().replace(" ", "-"), name=nome, type="superinvestor",
                          source="dataroma")
    db.add(fondo)
    db.flush()
    depositi = []
    for i, p in enumerate(periodi):
        ultimo = i == len(periodi) - 1
        f = InstitutionalFiling(institutional_id=fondo.id, period_end_date=p,
                                created_at=datetime(2026, 9, 28, 9, tzinfo=UTC) if ultimo
                                else datetime(2026, 6, 1, tzinfo=UTC))
        db.add(f)
        db.flush()
        depositi.append(f)
    return depositi


def _posizione(db: Session, deposito, ticker: str, mossa: str | None, var=None, peso=None) -> None:
    from app.models import InstitutionalHolding

    db.add(InstitutionalHolding(filing_id=deposito.id, ticker=ticker, action=mossa,
                                qoq_change_pct=var, portfolio_pct=peso))
    db.commit()


def test_le_mosse_dei_fondi_sui_titoli_seguiti(db: Session, seguiti) -> None:
    *_, ultimo = _fondo(db, "Pershing Square", [date(2026, 3, 31), date(2026, 6, 30)])
    _posizione(db, ultimo, "POS", "add", 25.4, 12.3)
    _posizione(db, ultimo, "PREF", "sold_out", -100.0, 0.0)
    _posizione(db, ultimo, "NESSUNO", "new", None, 5.0)      # non seguito
    novita = nt.da_mandare(db, OGGI, rinfresca=False)
    assert [(n.ticker, n.tipo, n.data, n.testo) for n in novita] == [
        ("POS", "superinvestor", date(2026, 9, 28),
         "Pershing Square aumenta la posizione (+25% di azioni), 12.3% del portafoglio — 13F al 30/06/2026"),
        ("PREF", "superinvestor", date(2026, 9, 28), "Pershing Square esce dal titolo — 13F al 30/06/2026"),
    ]


def test_un_nuovo_senza_deposito_precedente_non_e_una_notizia(db: Session, seguiti) -> None:
    """Un fondo con un deposito solo: «nuovo» vuol dire «non so»."""
    [unico] = _fondo(db, "BlackRock", [date(2026, 6, 30)])
    _posizione(db, unico, "POS", "new", None, 0.02)
    *_, ultimo = _fondo(db, "Akre", [date(2026, 3, 31), date(2026, 6, 30)])
    _posizione(db, ultimo, "POS", "new", None, 4.0)
    assert [n.testo for n in nt.da_mandare(db, OGGI, rinfresca=False)] == [
        "Akre apre una posizione, 4.0% del portafoglio — 13F al 30/06/2026",
    ]


def test_conferme_e_depositi_vecchi_non_sono_novita(db: Session, seguiti) -> None:
    vecchio, ultimo = _fondo(db, "Baupost", [date(2026, 3, 31), date(2026, 6, 30)])
    _posizione(db, ultimo, "POS", "hold", 0.0, 3.0)
    _posizione(db, vecchio, "PREF", "add", 10.0, 3.0)        # ricevuto a giugno
    assert nt.da_mandare(db, OGGI, rinfresca=False) == []


def test_il_ticker_col_trattino_trova_il_deposito_col_punto(db: Session) -> None:
    s = Stock(ticker="BRK-B", exchange="NYSE", name="Berkshire")
    db.add(s)
    db.flush()
    db.add(Preferito(stock_id=s.id))
    *_, ultimo = _fondo(db, "Markel", [date(2026, 3, 31), date(2026, 6, 30)])
    _posizione(db, ultimo, "BRK.B", "reduce", -10.0, 2.0)
    [n] = nt.da_mandare(db, OGGI, rinfresca=False)
    assert (n.ticker, n.testo.split(" (")[0]) == ("BRK-B", "Markel riduce la posizione")
