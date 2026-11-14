"""I due lavori che l'avvio lancia in un thread: il pre-market e
l'andamento dei settori.

Sotto pytest non partono (vedi `main._warm_sector_performance_on_boot`), quindi
il loro corpo si esercita qui, con il thread eseguito sul posto e le fonti
esterne finte. Senza, girerebbe solo in produzione."""
from __future__ import annotations

import threading
from datetime import datetime

from app import main
from app.scheduler.jobs import refresh_premarket as job
from app.services import premarket_service, sector_performance_service


def _in_linea(monkeypatch):
    """Toglie la guardia di pytest e fa girare il thread subito."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(threading.Thread, "start", lambda self: self.run())


def test_il_riscaldamento_dei_settori_precalcola(monkeypatch):
    chiamate = []
    monkeypatch.setattr(sector_performance_service, "precalcola",
                        lambda proxy: chiamate.append(proxy) or 3)
    _in_linea(monkeypatch)
    main._warm_sector_performance_on_boot()
    assert len(chiamate) == 1 and chiamate[0]


def test_il_pre_market_lavora_solo_nella_sua_finestra(monkeypatch):
    rinfreschi = []
    monkeypatch.setattr(premarket_service, "us_market_open_now", lambda: False)
    monkeypatch.setattr(premarket_service, "refresh", lambda db: rinfreschi.append(db))
    monkeypatch.setattr(job, "SessionLocal", lambda: type("S", (), {"close": lambda self: None})())

    class Ora(datetime):
        valore = datetime(2026, 11, 16, 8, 0, tzinfo=premarket_service._ET)   # lunedi', pre-market

        @classmethod
        def now(cls, tz=None):
            return cls.valore

    monkeypatch.setattr(job, "datetime", Ora)
    _in_linea(monkeypatch)
    main._warm_premarket_on_boot()
    assert len(rinfreschi) == 1

    Ora.valore = datetime(2026, 11, 16, 12, 0, tzinfo=premarket_service._ET)   # fuori finestra
    job.run_refresh_premarket()
    Ora.valore = datetime(2026, 11, 15, 8, 0, tzinfo=premarket_service._ET)    # domenica
    job.run_refresh_premarket()
    assert len(rinfreschi) == 1
