"""Il promemoria delle trimestrali: la sera prima, su posizioni e preferiti."""
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Position, Stock
from app.models.preferito import Preferito
from app.services import notifier_service, position_service, stock_fundamentals_service
from app.services import promemoria_trimestrali_service as pt
from app.services.stock_fundamentals_service import Fundamentals

OGGI = date(2026, 9, 29)          # martedi'
DOMANI = date(2026, 9, 30)


@pytest.fixture(autouse=True)
def _cache_pulita():
    stock_fundamentals_service._CACHE.clear()
    yield
    stock_fundamentals_service._CACHE.clear()


def _cache(ticker: str, data: str | None, ora: str | None = None) -> None:
    stock_fundamentals_service._CACHE[ticker] = Fundamentals(
        ticker=ticker, next_earnings_date=data, next_earnings_time_utc=ora,
        fetched_at=datetime.now(UTC).timestamp(),
    )


@pytest.fixture
def catalogo(db: Session) -> dict[str, Stock]:
    out = {}
    for t in ["POS", "PREF", "NESSUNO", "CHIUSA", "DOPO"]:
        s = Stock(ticker=t, exchange="X", name=f"{t} Spa")
        db.add(s)
        db.flush()
        out[t] = s
    db.add(Position(stock_id=out["POS"].id, entry_price=Decimal("10")))
    db.add(Position(stock_id=out["CHIUSA"].id, entry_price=Decimal("10"),
                    closed_at=datetime(2026, 9, 1, tzinfo=UTC), exit_price=Decimal("11")))
    db.add(Preferito(stock_id=out["PREF"].id))
    db.add(Preferito(stock_id=out["DOPO"].id))
    db.commit()
    return out


# ─── chi entra ───────────────────────────────────────────────────────────


def test_solo_domani_e_solo_i_titoli_che_contano(db: Session, catalogo) -> None:
    for t in ["POS", "PREF", "NESSUNO", "CHIUSA"]:
        _cache(t, "2026-09-30")
    _cache("DOPO", "2026-10-01")          # dopodomani: lo ricorda domani sera
    trimestrali = pt.di_domani(db, OGGI, rinfresca=False)
    assert [(t.ticker, t.rilevanza) for t in trimestrali] == [
        ("POS", "posizione"), ("PREF", "preferito"),
    ]


def test_la_data_con_l_orario_attaccato_vale_uguale(db: Session, catalogo) -> None:
    """yfinance rende sia `2026-09-30` sia `2026-09-30 00:00:00`."""
    _cache("POS", "2026-09-30 00:00:00", "20:05")
    [t] = pt.di_domani(db, OGGI, rinfresca=False)
    assert (t.data, t.ora_utc) == (DOMANI, "20:05")


def test_una_trimestrale_di_oggi_non_si_ricorda_di_nuovo(db: Session, catalogo) -> None:
    _cache("POS", "2026-09-29")
    assert pt.di_domani(db, OGGI, rinfresca=False) == []


def test_senza_titoli_seguiti_non_tocca_la_cache(db: Session, monkeypatch) -> None:
    monkeypatch.setattr(stock_fundamentals_service, "get_fundamentals",
                        lambda *a, **k: pytest.fail("nessun titolo da rinfrescare"))
    assert pt.di_domani(db, OGGI) == []


def test_rinfresca_solo_i_titoli_seguiti_e_un_errore_non_ferma_gli_altri(
    db: Session, catalogo, monkeypatch,
) -> None:
    """Un titolo mai aperto non ha la data in memoria: senza il rinfresco il
    promemoria tacerebbe in silenzio."""
    chiesti: list[str] = []

    def finto(ticker, **_):
        chiesti.append(ticker)
        if ticker == "DOPO":
            raise RuntimeError("yahoo giu'")
        _cache(ticker, "2026-09-30")

    monkeypatch.setattr(stock_fundamentals_service, "get_fundamentals", finto)
    trimestrali = pt.di_domani(db, OGGI)
    assert sorted(chiesti) == ["DOPO", "POS", "PREF"]
    assert [t.ticker for t in trimestrali] == ["POS", "PREF"]


# ─── come si dice ────────────────────────────────────────────────────────


@pytest.mark.parametrize(("data", "ora", "attesa"), [
    (date(2026, 9, 30), "20:05", "22:05"),     # ora legale: UTC+2
    (date(2026, 12, 1), "21:05", "22:05"),     # ora solare: UTC+1
    (date(2026, 9, 30), None, None),
    (date(2026, 9, 30), "boh", None),
])
def test_l_ora_italiana(data, ora, attesa) -> None:
    assert pt.ora_italiana(data, ora) == attesa


def test_l_etichetta_della_data() -> None:
    assert pt.etichetta_data(DOMANI) == "mer 30 set"
    assert pt.etichetta_data(date(2026, 12, 1)) == "mar 1 dic"


# ─── la notifica ─────────────────────────────────────────────────────────


@pytest.fixture
def telegram(monkeypatch) -> list[str]:
    inviati: list[str] = []
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(settings, "telegram_promemoria_trimestrali", True)
    monkeypatch.setattr(notifier_service, "_send_telegram",
                        lambda text, what: inviati.append(text) or True)
    return inviati


def test_il_messaggio(telegram) -> None:
    esito = notifier_service.notify_trimestrali([
        pt.Trimestrale("MB.MI", "Mediobanca", "posizione", DOMANI, "05:30"),
        pt.Trimestrale("AAPL", None, "preferito", DOMANI, None),
    ], DOMANI)
    assert (esito.sent, esito.alerts_count) == (True, 2)
    [testo] = telegram
    assert "Trimestrali domani sui tuoi titoli — mer 30 set" in testo
    assert "💼 <b>MB.MI</b> Mediobanca — ore 07:30 italiane" in testo
    assert "★ <b>AAPL</b> — orario non comunicato" in testo


def test_niente_domani_niente_messaggio(telegram) -> None:
    assert notifier_service.notify_trimestrali([], DOMANI).reason == "no_alerts"
    assert telegram == []


def test_si_spegne_dalla_configurazione(telegram, monkeypatch) -> None:
    monkeypatch.setattr(settings, "telegram_promemoria_trimestrali", False)
    uno = [pt.Trimestrale("MB.MI", None, "posizione", DOMANI, None)]
    assert notifier_service.notify_trimestrali(uno, DOMANI).reason == "push_disabled"
    assert telegram == []


def test_senza_telegram_non_prova_a_inviare(telegram, monkeypatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    uno = [pt.Trimestrale("MB.MI", None, "posizione", DOMANI, None)]
    assert notifier_service.notify_trimestrali(uno, DOMANI).reason == "telegram_disabled"
    assert telegram == []


# ─── il job ──────────────────────────────────────────────────────────────


def test_il_job_chiede_domani_nel_giorno_di_roma(monkeypatch) -> None:
    """Alle 23:30 UTC del 29 a Roma e' gia' il 30: il «domani» e' il 1 ottobre."""
    from app.scheduler.jobs import promemoria_trimestrali as job

    class Orologio(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 29, 23, 30, tzinfo=UTC).astimezone(tz)

    visti = {}
    monkeypatch.setattr(job, "datetime", Orologio)
    monkeypatch.setattr(job.promemoria_trimestrali_service, "di_domani",
                        lambda db, oggi: visti.setdefault("oggi", oggi) and [])
    monkeypatch.setattr(job.notifier_service, "notify_trimestrali",
                        lambda t, domani: visti.setdefault("domani", domani)
                        and notifier_service.PushResult(sent=False, reason="no_alerts"))
    job.run_promemoria_trimestrali()
    assert visti == {"oggi": date(2026, 9, 30), "domani": date(2026, 10, 1)}


# ─── la data sulle posizioni ─────────────────────────────────────────────


def test_le_posizioni_aperte_portano_la_prossima_trimestrale(db: Session, catalogo) -> None:
    _cache("POS", "2026-10-02")
    _cache("CHIUSA", "2026-10-02")
    righe = {r["ticker"]: r for r in position_service.list_positions(db, price_fn=lambda t: 12.0)}
    assert righe["POS"]["next_earnings_date"] == date(2026, 10, 2)
    assert righe["CHIUSA"]["next_earnings_date"] is None
