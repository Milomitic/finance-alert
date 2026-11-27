"""FA-179, fase B: la risposta sempre pronta, servita vecchia e rinfrescata dietro."""
from __future__ import annotations

import threading
import time

from app.core.cache_fresca import CacheFresca


def _contatore():
    n = {"v": 0}

    def calcola():
        n["v"] += 1
        return n["v"]

    return n, calcola


def test_entro_l_eta_non_ricalcola():
    n, calcola = _contatore()
    c = CacheFresca("t", 60, calcola, attiva=True)
    assert c.leggi() == 1
    assert c.leggi() == 1
    assert n["v"] == 1


def test_oltre_l_eta_serve_subito_il_vecchio_e_rinfresca_dietro():
    n, calcola = _contatore()
    c = CacheFresca("t", 0.01, calcola, attiva=True)
    assert c.leggi() == 1
    time.sleep(0.03)
    assert c.leggi() == 1            # subito il vecchio, senza aspettare
    for t in threading.enumerate():  # il ricalcolo dietro finisce
        if t.name == "cache-t":
            t.join(2)
    assert c.leggi() == 2


def test_un_ricalcolo_fallito_lascia_servito_il_vecchio():
    stato = {"rompi": False}

    def calcola():
        if stato["rompi"]:
            raise RuntimeError("upstream giu'")
        return "buono"

    c = CacheFresca("t", 0.01, calcola, attiva=True)
    assert c.leggi() == "buono"
    stato["rompi"] = True
    time.sleep(0.03)
    assert c.leggi() == "buono"
    for t in threading.enumerate():
        if t.name == "cache-t":
            t.join(2)
    assert c.leggi() == "buono"


def test_sotto_i_test_calcola_sempre_sul_posto():
    n, calcola = _contatore()
    c = CacheFresca("t", 60, calcola)   # accesa solo fuori dai test
    assert c.accesa() is False
    assert (c.leggi(), c.leggi()) == (1, 2)


def test_rinfresca_e_svuota():
    n, calcola = _contatore()
    c = CacheFresca("t", 60, calcola, attiva=True)
    assert c.rinfresca() == 1 and c.eta_s() is not None
    c.svuota()
    assert c.eta_s() is None
    assert c.leggi() == 2


def test_il_job_rinfresca_entrambe_e_un_guasto_non_ferma_l_altra(monkeypatch):
    from app.api.dashboard import CACHE_RIEPILOGO
    from app.api.market import CACHE_PANIERE
    from app.scheduler.jobs.riscalda_cache_home import run_riscalda_cache_home

    chiamate = []

    def rotta():
        raise RuntimeError("giu'")

    monkeypatch.setattr(CACHE_RIEPILOGO, "rinfresca", rotta)
    monkeypatch.setattr(CACHE_PANIERE, "rinfresca", lambda: chiamate.append("paniere"))
    run_riscalda_cache_home()
    assert chiamate == ["paniere"]


def test_il_riepilogo_si_calcola_anche_fuori_da_una_richiesta(db, monkeypatch):
    """La cache calcola con una sessione sua, non con quella di una richiesta."""
    import contextlib

    from app.api import dashboard

    monkeypatch.setattr(dashboard, "SessionLocal", lambda: contextlib.nullcontext(db))
    r = dashboard._riepilogo_da_sessione()
    assert r.kpis is not None


def test_oltre_il_limite_non_serve_il_vecchio_ma_ricalcola_sul_posto():
    """FA-181: una voce dimenticata per ore non esce come se fosse fresca."""
    n, calcola = _contatore()
    c = CacheFresca("t", 0.01, calcola, attiva=True, eta_limite_s=0.02)
    assert c.leggi() == 1
    time.sleep(0.04)
    assert c.leggi() == 2            # sul posto, non il vecchio
    assert n["v"] == 2
