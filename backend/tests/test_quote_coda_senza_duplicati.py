"""Il batch interattivo non accoda due volte lo stesso titolo, e non aspetta chi ha gia' un valore.

FA-006, seconda misura (2026-09-16). Separare lo sweep in un pool suo (e01ebcf)
non e' bastato: dopo il rilascio restavano batch da 50 serviti 50/50 dalla
cache. Misurato nel pod: 5 thread recuperano ~8 quotazioni al secondo, e una
sola pagina ne chiede ~240 ogni 15 s (filtro titoli + Top Movers + volumi).

Due difetti rendevano il deficit permanente invece che passeggero:

1. Il single-flight di `get_quote` registra un titolo quando il recupero PARTE,
   non quando e' accodato. Ogni polling riaccodava i titoli ancora in coda dal
   polling prima: la coda cresceva senza limite.
2. Un titolo con un'ultima quotazione buona aspettava comunque fino a 6 s per
   poi ricevere proprio quella.
"""
import threading
import time

import pytest

from app.services import live_quote_service as lqs


@pytest.fixture
def pool_puliti(monkeypatch):
    monkeypatch.setattr(lqs, "_POOL", None)
    monkeypatch.setattr(lqs, "_BACKGROUND_POOL", None)
    monkeypatch.setattr(lqs, "_QUEUED", {})
    lqs.clear_cache()
    yield
    lqs.clear_cache()


def _finto_lento(monkeypatch, sblocca: threading.Event, chiamate: dict):
    def quotazione(ticker, **_kw):
        chiamate[ticker] = chiamate.get(ticker, 0) + 1
        sblocca.wait(timeout=10)
        return lqs.LiveQuote(ticker=ticker, price=2.0, fetched_at=time.time())
    monkeypatch.setattr(lqs, "get_quote", quotazione)


def test_due_polling_non_accodano_due_volte_lo_stesso_titolo(monkeypatch, pool_puliti, db) -> None:
    sblocca, chiamate = threading.Event(), {}
    _finto_lento(monkeypatch, sblocca, chiamate)
    titoli = [f"T{i}" for i in range(30)]          # piu' dei thread: resta una coda
    try:
        lqs.get_quotes_batch(titoli, deadline_seconds=0.2)
        lqs.get_quotes_batch(titoli, deadline_seconds=0.2)
    finally:
        sblocca.set()
    # Attende che la coda si svuoti, poi conta i recuperi per titolo.
    fine = time.monotonic() + 10
    while lqs._QUEUED and time.monotonic() < fine:
        time.sleep(0.05)
    assert not lqs._QUEUED
    assert max(chiamate.values()) == 1, {k: v for k, v in chiamate.items() if v > 1}
    assert len(chiamate) == 30


def test_un_titolo_con_un_valore_noto_non_aspetta(monkeypatch, pool_puliti, db) -> None:
    sblocca, chiamate = threading.Event(), {}
    _finto_lento(monkeypatch, sblocca, chiamate)
    noto = lqs.LiveQuote(ticker="NOTO", price=1.0, market_state="OPEN",
                         fetched_at=time.time() - 30)   # oltre il TTL di 10 s
    with lqs._CACHE_LOCK:
        lqs._LAST_LIVE["NOTO"] = noto
    try:
        inizio = time.monotonic()
        out = lqs.get_quotes_batch(["NOTO"], deadline_seconds=3.0)
        durata = time.monotonic() - inizio
    finally:
        sblocca.set()
    assert out["NOTO"].price == 1.0
    assert durata < 0.5
    # E l'aggiornamento e' comunque partito: il valore noto non congela il prezzo.
    fine = time.monotonic() + 5
    while "NOTO" not in chiamate and time.monotonic() < fine:
        time.sleep(0.02)
    assert chiamate.get("NOTO") == 1


def test_un_titolo_senza_valori_aspetta_il_recupero(monkeypatch, pool_puliti, db) -> None:
    monkeypatch.setattr(
        lqs, "get_quote",
        lambda t, **_kw: lqs.LiveQuote(ticker=t, price=3.0, fetched_at=time.time()),
    )
    out = lqs.get_quotes_batch(["NUOVO"], deadline_seconds=3.0)
    assert out["NUOVO"].price == 3.0
