"""FA-181: il job che tiene calde le pagine di dettaglio, e l'avvio che lo lancia."""
from __future__ import annotations

import contextlib
import threading

from app import main
from app.api import stocks as api_stocks
from app.models import Preferito, Stock
from app.scheduler.jobs import riscalda_cache_home
from app.scheduler.jobs import riscalda_dettagli as job
from app.services import market_detail_service


def test_i_titoli_da_riscaldare_sono_quelli_seguiti(db, monkeypatch):
    a = Stock(ticker="AAA", exchange="NASDAQ", name="A", country="US")
    b = Stock(ticker="BBB", exchange="NASDAQ", name="B", country="US")
    db.add_all([a, b])
    db.commit()
    db.add(Preferito(stock_id=b.id))
    db.commit()
    monkeypatch.setattr("app.core.db.SessionLocal", lambda: contextlib.nullcontext(db))
    assert job.titoli_da_riscaldare() == ["BBB"]


def test_nessun_titolo_seguito_nessuna_query(db, monkeypatch):
    monkeypatch.setattr("app.core.db.SessionLocal", lambda: contextlib.nullcontext(db))
    assert job.titoli_da_riscaldare() == []


def test_un_guasto_su_un_titolo_non_ferma_gli_altri_ne_gli_indici(monkeypatch):
    fatti: list[str] = []

    def dettaglio(t, r):
        if t == "ROTTO":
            raise RuntimeError("giu'")
        fatti.append(t)

    def mercato(s, r):
        if s == "^GSPC":
            raise RuntimeError("yahoo giu'")
        fatti.append(s)

    monkeypatch.setattr(job, "titoli_da_riscaldare", lambda: ["ROTTO", "OK"])
    monkeypatch.setattr(api_stocks, "riscalda_dettaglio", dettaglio)
    monkeypatch.setattr(market_detail_service, "get_detail", mercato)
    job.run_riscalda_dettagli()
    assert "OK" in fatti and "ROTTO" not in fatti
    assert "^IXIC" in fatti and "^GSPC" not in fatti
    # Prima i mercati (servono alla panoramica), poi i titoli seguiti.
    assert fatti.index("^IXIC") < fatti.index("OK")


def test_se_l_elenco_fallisce_si_riscaldano_comunque_gli_indici(monkeypatch):
    fatti: list[str] = []

    def guasto():
        raise RuntimeError("db giu'")

    monkeypatch.setattr(job, "titoli_da_riscaldare", guasto)
    monkeypatch.setattr(market_detail_service, "get_detail", lambda s, r: fatti.append(s))
    job.run_riscalda_dettagli()
    assert "^IXIC" in fatti


def test_l_avvio_riscalda_home_e_dettagli(monkeypatch):
    fatti: list[str] = []
    monkeypatch.setattr(riscalda_cache_home, "run_riscalda_cache_home", lambda: fatti.append("home"))
    monkeypatch.setattr(job, "run_riscalda_dettagli", lambda: fatti.append("dettagli"))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(threading.Thread, "start", lambda self: self.run())
    main._warm_home_cache_on_boot()
    assert fatti == ["home", "dettagli"]
