"""La completezza dei fondamentali: gemella di confidenza.ts (FA-156)."""
import json
from pathlib import Path
from types import SimpleNamespace

from app.services import completezza_service as cs

VETTORI = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "completezzaVectors.json"


def test_i_vettori_condivisi_col_frontend():
    d = json.loads(VETTORI.read_text(encoding="utf-8"))
    ns = lambda xs: [SimpleNamespace(**x) for x in xs]  # noqa: E731
    for caso in d["casi"]:
        v = cs.completezza(ns(caso["annual"]), ns(caso["quarterly"]), ns(caso["earnings"]), d["oggi"])
        assert v == caso["atteso"], caso["perche"]


def test_lo_screener_tiene_solo_i_titoli_completi(db, monkeypatch):
    from app.models import Stock
    from app.services import stock_fundamentals_service as sfs
    from app.services.stock_service import StockFilter, search_stocks

    anni = [sfs.AnnualPoint(fiscal_year_end=f"{2025 - i}-12-31", revenue=1, net_income=1, eps=1)
            for i in range(4)]
    db.add_all([Stock(ticker="PIENO", exchange="X", name="Pieno"),
                Stock(ticker="VUOTO", exchange="X", name="Vuoto"),
                Stock(ticker="IGNOTO", exchange="X", name="Ignoto")])
    db.commit()
    monkeypatch.setitem(sfs._CACHE, "PIENO", sfs.Fundamentals(ticker="PIENO", annual=anni))
    monkeypatch.setitem(sfs._CACHE, "VUOTO", sfs.Fundamentals(ticker="VUOTO", annual=anni[:1]))
    tick = {i.stock.ticker for i in search_stocks(db, StockFilter(solo_dati_completi=True)).items}
    assert tick == {"PIENO"}
    tutti = {i.stock.ticker for i in search_stocks(db, StockFilter()).items}
    assert {"PIENO", "VUOTO", "IGNOTO"} <= tutti
