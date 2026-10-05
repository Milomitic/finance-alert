"""L'intestazione di «Componenti ETF»: variazione e link dell'ETF di riferimento.

Un ETF a leva mostra il paniere del suo ETF fisico (TNA -> IWM). L'intestazione
porta la variazione di QUELL'ETF, presa dallo stesso lotto di quotazioni delle
componenti, e dice se ha una pagina: 8 dei sottostanti mappati non sono nel
catalogo, e un link a una pagina vuota e' peggio di nessun link.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User
from app.services import etf_holdings_service, live_quote_service
from app.services.etf_holdings_service import EtfHolding


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _quote(pct: float | None, error: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(change_pct=pct, price=100.0, currency="USD", error=error)


@pytest.fixture
def chiesti(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    monkeypatch.setattr(
        etf_holdings_service, "get_holdings",
        lambda db, t: [EtfHolding("AAA", "Aaa Corp", 0.5), EtfHolding("BBB", "Bbb Inc", 0.5)],
    )
    lotti: list[list[str]] = []

    def batch(symbols: list[str], **_k: object) -> dict[str, SimpleNamespace]:
        lotti.append(list(symbols))
        return {"AAA": _quote(1.0), "BBB": _quote(-1.0), "IWM": _quote(0.52), "DIA": _quote(None, "boom")}

    monkeypatch.setattr(live_quote_service, "get_quotes_batch", batch)
    return lotti


def test_il_sottostante_porta_la_sua_variazione_e_il_link(
    client: TestClient, db: Session, chiesti: list[list[str]],
) -> None:
    db.add(Stock(ticker="IWM", exchange="NYSEARCA", name="iShares Russell 2000"))
    db.commit()
    body = client.get("/api/stocks/TNA/etf-holdings").json()
    assert body["underlying"] == "IWM"
    assert body["underlying_change_pct"] == pytest.approx(0.52)
    assert body["underlying_in_catalog"] is True
    # Lo stesso lotto, non una seconda chiamata.
    assert chiesti == [["AAA", "BBB", "IWM"]]


def test_un_sottostante_fuori_catalogo_non_ha_link(
    client: TestClient, chiesti: list[list[str]],
) -> None:
    body = client.get("/api/stocks/UDOW/etf-holdings").json()
    assert body["underlying"] == "DIA"
    assert body["underlying_in_catalog"] is False
    # Una quotazione in errore non diventa una variazione.
    assert body["underlying_change_pct"] is None


def test_un_etf_normale_non_chiede_niente_in_piu(
    client: TestClient, chiesti: list[list[str]],
) -> None:
    body = client.get("/api/stocks/SPY/etf-holdings").json()
    assert body["underlying"] is None
    assert body["underlying_change_pct"] is None
    assert body["underlying_in_catalog"] is False
    assert chiesti == [["AAA", "BBB"]]
