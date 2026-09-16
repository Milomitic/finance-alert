"""La migrazione `a7c3e19d2b60` ricostruisce `completed_at` delle esecuzioni chiuse.

18 scansioni `success` di maggio in produzione non avevano la data di fine, e
su Postgres un `ORDER BY completed_at DESC` le metteva in cima (FA-078). Qui si
esegue la migrazione VERA sulla catena Alembic, non una copia della sua SQL.
"""


import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import settings

_PRIMA = "5e2f0b7c9d41"
_QUESTA = "a7c3e19d2b60"


def _riga(c, id_: int, status: str, started: str, progress: str | None, completed: str | None) -> None:
    c.execute(text(
        "INSERT INTO scan_runs (id, kind, trigger, status, started_at, last_progress_at, "
        "completed_at, progress_done, progress_total, phase_history) "
        "VALUES (:i, 'alerts_scan', 'manual', :s, :st, :lp, :co, 10, 10, '[]')"
    ), {"i": id_, "s": status, "st": started, "lp": progress, "co": completed})


@pytest.fixture
def catena(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    # env.py legge SEMPRE settings.database_url: passare l'url a Config non
    # servirebbe a niente (CLAUDE.md, «env.py IGNORA l'url»).
    monkeypatch.setattr(settings, "database_url", url)
    cfg = Config("alembic.ini")
    eng = create_engine(url)
    yield cfg, eng
    eng.dispose()


def _leggi(eng) -> dict[int, str | None]:
    with eng.connect() as c:
        return {r[0]: r[1] for r in c.execute(text("SELECT id, completed_at FROM scan_runs"))}


def test_ricostruisce_la_data_dall_ultimo_avanzamento(catena) -> None:
    cfg, eng = catena
    command.upgrade(cfg, _PRIMA)
    with eng.begin() as c:
        _riga(c, 19, "success", "2026-05-05 00:04:11", "2026-05-05 00:05:38", None)
        _riga(c, 20, "failed", "2026-05-06 09:00:00", None, None)
        _riga(c, 21, "success", "2026-05-07 10:00:00", "2026-05-07 10:03:00", "2026-05-07 10:03:05")
        _riga(c, 22, "running", "2026-09-16 10:00:00", "2026-09-16 10:01:00", None)

    command.upgrade(cfg, _QUESTA)
    dopo = _leggi(eng)

    assert str(dopo[19]).startswith("2026-05-05 00:05:38")   # ultimo segno di vita
    assert str(dopo[20]).startswith("2026-05-06 09:00:00")   # senza avanzamento: l'avvio
    assert str(dopo[21]).startswith("2026-05-07 10:03:05")   # una data vera non si tocca
    # Una scansione in corso NON e' chiusa: darle una fine la farebbe sembrare
    # terminata al recupero all'avvio.
    assert dopo[22] is None


def test_nessuna_esecuzione_chiusa_resta_senza_data(catena) -> None:
    cfg, eng = catena
    command.upgrade(cfg, _PRIMA)
    with eng.begin() as c:
        for i in range(1, 19):
            _riga(c, i, "success", f"2026-05-{i:02d} 08:00:00", f"2026-05-{i:02d} 08:02:00", None)
    command.upgrade(cfg, _QUESTA)
    with eng.connect() as c:
        mancanti = c.execute(text(
            "SELECT count(*) FROM scan_runs WHERE completed_at IS NULL AND status <> 'running'"
        )).scalar()
        # Pavimento: 18 righe devono esserci, altrimenti «zero mancanti» sarebbe
        # vero di una tabella vuota.
        assert c.execute(text("SELECT count(*) FROM scan_runs")).scalar() == 18
    assert mancanti == 0
