"""FA-182: gli indicatori in forma compatta dicono la stessa cosa di quelli estesi."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api import indicatori_compatti as ic
from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User
from tests.test_api_stock_detail import _seed


@dataclass
class P:
    date: date
    value: float | None


D = [date(2026, 11, d) for d in (23, 24, 25)]


def test_allineata_si_legge_per_posizione_e_si_arrotonda():
    assert ic.compatta([P(D[0], 1.123456789), P(D[1], None), P(D[2], 26658.25)], D) == [1.123457, None, 26658.25]


def test_disallineata_si_abbina_per_data():
    assert ic.compatta([P(D[2], 3.0), P(D[0], 1.0)], D) == [1.0, None, 3.0]


def test_vuota_resta_vuota():
    assert ic.compatta([], D) == []


@pytest.mark.parametrize("v", [float("nan"), float("inf"), "x", None])
def test_un_valore_non_finito_diventa_null(v):
    assert ic.arrotonda(v) is None


def test_sette_cifre_tengono_i_centesimi_di_un_indice_e_un_macd_piccolo():
    assert ic.arrotonda(26658.25) == 26658.25
    assert math.isclose(ic.arrotonda(0.000123456789), 0.0001234568)


@pytest.fixture
def client(db):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _riespandi(corpo: dict, date_barre: list[str]) -> dict:
    return {k: [{"date": d, "value": v} for d, v in zip(date_barre, corpo["indicators"][k], strict=True)]
            if corpo["indicators"][k] else [] for k in ic.SERIE}


def _vicini(a, b) -> bool:
    """La forma estesa del titolo arrotonda a 4 decimali (`IndicatorPointOut`),
    la compatta a 7 cifre significative: coincidono entro mezzo decimillesimo."""
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=5.1e-5)


def _uguali(esteso: dict, riespanso: dict) -> None:
    for k in ic.SERIE:
        e, r = esteso["indicators"][k], riespanso[k]
        assert [p["date"] for p in e] == [p["date"] for p in r], k
        assert all(_vicini(x["value"], y["value"]) for x, y in zip(e, r, strict=True)), k


def test_il_dettaglio_di_un_titolo_compatto_dice_lo_stesso_dell_esteso(client, db):
    _seed(db, "AAPL")
    esteso = client.get("/api/stocks/AAPL/detail?range=1d").json()
    r = client.get("/api/stocks/AAPL/detail?range=1d&formato=compatto")
    compatto = r.json()
    assert compatto["indicators_formato"] == "compatto"
    assert "indicators_formato" not in esteso
    assert compatto["ohlcv"] == esteso["ohlcv"]
    assert compatto["indicators"]["periods"] == esteso["indicators"]["periods"]
    assert len(compatto["indicators"]["ema20"]) == len(esteso["ohlcv"])
    _uguali(esteso, _riespandi(compatto, [b["date"] for b in esteso["ohlcv"]]))
    assert len(r.content) < len(client.get("/api/stocks/AAPL/detail?range=1d").content) / 2


def test_il_dettaglio_di_un_indice_compatto_dice_lo_stesso_dell_esteso(client):
    from tests.test_market_detail_service import _lungo

    with patch("app.services.market_detail_service.get_detail", return_value=_lungo()), \
         patch("app.services.live_quote_service.get_quote", return_value=None):
        esteso = client.get("/api/markets/%5EGSPC/detail?range=1d").json()
        compatto = client.get("/api/markets/%5EGSPC/detail?range=1d&formato=compatto").json()
    assert compatto["indicators_formato"] == "compatto"
    assert compatto["bars"] == esteso["bars"]
    _uguali(esteso, _riespandi(compatto, [b["date"] for b in esteso["bars"]]))


def test_un_formato_sconosciuto_e_422(client, db):
    _seed(db, "AAPL")
    assert client.get("/api/stocks/AAPL/detail?range=1d&formato=boh").status_code == 422
