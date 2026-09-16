"""Le richieste della pagina non fanno la coda dietro lo sweep di sfondo.

Misurato in produzione (FA-006, 2026-09-16): `/api/stocks/quotes` aveva
mediana 5,5 s e p95 9,5 s, e 102 richieste su 121 in 24 ore sforavano la
scadenza di 6 s — fino a «50/50 served warm», cioe' nemmeno una quotazione
viva su cinquanta. La causa: lo sweep dei movers (200 titoli ogni 75 s,
`deadline_seconds=None`) e le richieste dell'utente condividevano UN pool da
8 thread. Un executor e' una coda FIFO, quindi un batch interattivo inviato
durante uno sweep aspettava che finissero le centinaia di future accodate
prima di lui, e la scadenza scattava sempre.

Il test riproduce la forma esatta: lo sweep occupa ogni thread con quotazioni
che non finiscono, e una richiesta interattiva deve comunque ricevere le sue.
"""
import threading
import time

import pytest

from app.services import live_quote_service as lqs


@pytest.fixture
def pool_puliti(monkeypatch):
    # Pool freschi per il test: quelli globali potrebbero avere thread vivi di
    # altri test, e una coda sporca renderebbe il risultato casuale.
    monkeypatch.setattr(lqs, "_POOL", None)
    monkeypatch.setattr(lqs, "_BACKGROUND_POOL", None)
    lqs.clear_cache()
    yield
    lqs.clear_cache()


def test_una_richiesta_interattiva_non_aspetta_lo_sweep(monkeypatch, pool_puliti, db) -> None:
    sblocca = threading.Event()
    iniziate = threading.Semaphore(0)

    def quotazione_finta(ticker, **_kw):
        if ticker.startswith("BG"):
            iniziate.release()
            sblocca.wait(timeout=30)     # lo sweep resta appeso finche' il test non chiude
        return lqs.LiveQuote(ticker=ticker, price=1.0, fetched_at=time.time())

    monkeypatch.setattr(lqs, "get_quote", quotazione_finta)
    sfondo = [f"BG{i}" for i in range(60)]
    sweep = threading.Thread(
        target=lqs.get_quotes_batch, args=(sfondo,),
        kwargs={"deadline_seconds": None, "background": True},
    )
    sweep.start()
    try:
        # Aspetta che lo sweep abbia davvero occupato i suoi thread: senza,
        # la richiesta interattiva potrebbe passare prima e il test sarebbe
        # vero di niente.
        assert iniziate.acquire(timeout=5)

        inizio = time.monotonic()
        out = lqs.get_quotes_batch(["AAA", "BBB"], deadline_seconds=2.0)
        durata = time.monotonic() - inizio

        assert out["AAA"].error is None and out["AAA"].price == 1.0
        assert out["BBB"].error is None and out["BBB"].price == 1.0
        assert durata < 1.5
    finally:
        sblocca.set()
        sweep.join(timeout=30)


def test_lo_sweep_usa_il_proprio_pool() -> None:
    assert lqs._pool(background=True) is not lqs._pool()
    # Il totale dei thread verso Yahoo non cresce: la separazione divide gli
    # 8 di prima, non ne aggiunge.
    assert lqs._POOL_WORKERS + lqs._BACKGROUND_POOL_WORKERS == 8
