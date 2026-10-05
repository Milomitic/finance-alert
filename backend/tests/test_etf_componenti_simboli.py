"""I simboli dei componenti ETF tradotti in simboli Yahoo, e la liquidita'
che non e' un componente (letti dalla cache di produzione il 2026-10-06)."""
import sys
import types

import pandas as pd
import pytest

from app.services import etf_holdings_service as svc


@pytest.mark.parametrize(("dentro", "fuori"), [
    ("00939", "0939.HK"), ("01211", "1211.HK"), ("03988", "3988.HK"),
    # Gia' nella forma Yahoo, o non di Hong Kong: restano come sono.
    ("1810.HK", "1810.HK"), ("AAPL", "AAPL"), ("MOG-A", "MOG-A"), ("ABX.TO", "ABX.TO"),
    # Controllo negativo: quattro o sei cifre non sono il codice di HK.
    ("7203", "7203"), ("005930", "005930"), ("10939", "10939"),
])
def test_il_simbolo_yahoo(dentro: str, fuori: str) -> None:
    assert svc.simbolo_yahoo(dentro) == fuori


def test_la_liquidita_non_e_un_componente() -> None:
    assert svc.e_liquidita("BlackRock Cash Funds Treasury SL Agency")
    assert svc.e_liquidita("State Street Money Market Fund")
    assert not svc.e_liquidita("Cash America International")
    assert not svc.e_liquidita("Apple Inc")


def test_il_recupero_traduce_e_scarta(monkeypatch) -> None:
    df = pd.DataFrame(
        {"Name": ["China Construction Bank", "BlackRock Cash Funds Treasury SL Agency", "Xiaomi"],
         "Holding Percent": [0.08, 0.003, 0.05]},
        index=["00939", "XTSLA", "1810.HK"],
    )

    class Fondo:
        funds_data = types.SimpleNamespace(top_holdings=df)

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda s: Fondo()))
    from app.services import yfinance_health

    monkeypatch.setattr(yfinance_health, "is_open", lambda *a, **k: False)
    monkeypatch.setattr(yfinance_health, "record_success", lambda *a, **k: None)
    out = svc._fetch_from_yf("FXI")
    assert [h.symbol for h in out] == ["0939.HK", "1810.HK"]
