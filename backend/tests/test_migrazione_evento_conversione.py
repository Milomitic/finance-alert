"""La migrazione `c4f1a7d20e93` riconcilia i setup con regole verificate.

Si esegue la migrazione VERA sulla catena Alembic, su righe costruite come le
tre popolazioni misurate in produzione il 2026-09-16: conversioni storiche,
conversioni di verso opposto, e setup rimasti attivi con la condizione gia'
scattata. Ogni regola ha accanto il suo caso di confine, perche' una
riconciliazione che converte troppo e' peggio del difetto che ripara.
"""
import json

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import settings

_PRIMA = "a7c3e19d2b60"
_QUESTA = "c4f1a7d20e93"


@pytest.fixture
def catena(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    # env.py legge SEMPRE settings.database_url (CLAUDE.md, «env.py IGNORA l'url»).
    monkeypatch.setattr(settings, "database_url", url)
    cfg = Config("alembic.ini")
    eng = create_engine(url)
    command.upgrade(cfg, _PRIMA)
    with eng.begin() as c:
        c.execute(text(
            "INSERT INTO stocks (id, ticker, exchange, name) VALUES (1, 'AAA', 'NYSE', 'A')"
        ))
    yield cfg, eng
    eng.dispose()


def _alert(c, id_: int, detector: str, giorno: str, tono: str | None, amend: int = 0) -> None:
    snap = {"strength": 70}
    if tono is not None:
        snap["tone"] = tono
    if amend:
        snap["amend_count"] = amend
    c.execute(text(
        "INSERT INTO alerts (id, stock_id, signal_name, signal_date, trigger_price, "
        "snapshot, triggered_at) VALUES (:i, 1, :d, :g, 50.0, :s, :g)"
    ), {"i": id_, "d": detector, "g": giorno, "s": json.dumps(snap)})


def _setup(c, id_: int, detector: str, tono: str, stato: str, aperto: str,
           alert_id: int | None = None) -> None:
    c.execute(text(
        "INSERT INTO stock_setups (id, stock_id, detector, tone, proximity, convenience, "
        "missing, status, shortlisted, first_seen_at, last_seen_at, converted_alert_id, "
        "resolved_at, lead_days) VALUES (:i, 1, :d, :t, 0.8, 70, '-', :s, 1, :a, :a, "
        ":al, :r, :l)"
    ), {"i": id_, "d": detector, "t": tono, "s": stato, "a": aperto, "al": alert_id,
        "r": "2026-09-01 20:00:00" if stato == "converted" else None,
        "l": 3 if stato == "converted" else None})


def _righe(eng) -> dict[int, dict]:
    with eng.connect() as c:
        return {
            r._mapping["id"]: dict(r._mapping)
            for r in c.execute(text("SELECT * FROM stock_setups"))
        }


def test_le_conversioni_storiche_restano_e_si_datano_solo_se_e_certo(catena) -> None:
    cfg, eng = catena
    with eng.begin() as c:
        _alert(c, 10, "d_mai_rivisto", "2026-08-30", "bull")
        _setup(c, 1, "d_mai_rivisto", "bull", "converted", "2026-08-25 20:00:00", 10)
        _alert(c, 11, "d_rivisto", "2026-09-10", "bull", amend=4)
        _setup(c, 2, "d_rivisto", "bull", "converted", "2026-08-25 20:00:00", 11)
    command.upgrade(cfg, _QUESTA)
    r = _righe(eng)

    assert r[1]["status"] == "converted" and r[1]["conversion_source"] == "legacy"
    assert str(r[1]["converted_signal_date"]) == "2026-08-30"
    assert r[1]["converted_tone"] == "bull" and r[1]["converted_price"] == 50.0
    # Rivisto dopo la conversione: la data che ha oggi NON e' quella dell'evento.
    assert r[2]["status"] == "converted" and r[2]["conversion_source"] == "legacy"
    assert r[2]["converted_signal_date"] is None


def test_il_verso_opposto_chiude_come_mislinked_e_il_senza_direzione_no(catena) -> None:
    cfg, eng = catena
    with eng.begin() as c:
        _alert(c, 20, "d_opposto", "2026-08-30", "bear")
        _setup(c, 3, "d_opposto", "bull", "converted", "2026-08-25 20:00:00", 20)
        _alert(c, 21, "d_squeeze", "2026-08-30", "bear")
        _setup(c, 4, "d_squeeze", "undetermined", "converted", "2026-08-25 20:00:00", 21)
        _alert(c, 22, "d_senza_tono", "2026-08-30", None)
        _setup(c, 5, "d_senza_tono", "bull", "converted", "2026-08-25 20:00:00", 22)
    command.upgrade(cfg, _QUESTA)
    r = _righe(eng)

    assert (r[3]["status"], r[3]["closed_reason"]) == ("expired", "mislinked")
    # Un setup senza direzione accetta entrambi i versi: la conversione era buona.
    assert r[4]["status"] == "converted"
    # Un alert senza tono non e' giudicabile: non si chiude su un'ipotesi.
    assert r[5]["status"] == "converted" and r[5]["converted_signal_date"] is None


def test_gli_attivi_con_evento_successivo_si_riconciliano_senza_inventare(catena) -> None:
    cfg, eng = catena
    with eng.begin() as c:
        # BMY: setup aperto l'11, segnale compatibile sulla barra del 15.
        _setup(c, 6, "d_dopo", "bull", "active", "2026-09-11 20:00:00")
        _alert(c, 30, "d_dopo", "2026-09-15", "bull", amend=2)
        # Stessa data dell'apertura: non si sa se l'evento precedesse il setup.
        _setup(c, 7, "d_stesso_giorno", "bull", "active", "2026-09-11 20:00:00")
        _alert(c, 31, "d_stesso_giorno", "2026-09-11", "bull", amend=2)
        # Verso opposto: non e' l'evento atteso.
        _setup(c, 8, "d_opposto_attivo", "bear", "active", "2026-09-11 20:00:00")
        _alert(c, 32, "d_opposto_attivo", "2026-09-15", "bull")
        # Segnale PRIMA dell'apertura: un vecchio segnale, non la conversione.
        _setup(c, 9, "d_vecchio", "bull", "active", "2026-09-11 20:00:00")
        _alert(c, 33, "d_vecchio", "2026-09-05", "bull")
    command.upgrade(cfg, _QUESTA)
    r = _righe(eng)

    assert r[6]["status"] == "converted"
    assert r[6]["conversion_source"] == "reconciled"
    assert r[6]["converted_alert_id"] == 30
    # La prima rilevazione dopo l'apertura non fu registrata: niente data,
    # niente anticipo, niente esito.
    assert r[6]["converted_signal_date"] is None
    assert r[6]["lead_days"] is None and r[6]["bar_lead_days"] is None
    for sid in (7, 8, 9):
        assert r[sid]["status"] == "active", sid
        assert r[sid]["conversion_source"] is None, sid


def test_il_ritorno_riapre_le_riconciliate_e_ripristina_le_mislinked(catena) -> None:
    cfg, eng = catena
    with eng.begin() as c:
        _setup(c, 6, "d_dopo", "bull", "active", "2026-09-11 20:00:00")
        _alert(c, 30, "d_dopo", "2026-09-15", "bull")
        _alert(c, 20, "d_opposto", "2026-08-30", "bear")
        _setup(c, 3, "d_opposto", "bull", "converted", "2026-08-25 20:00:00", 20)
    command.upgrade(cfg, _QUESTA)
    command.downgrade(cfg, _PRIMA)
    r = _righe(eng)
    assert r[6]["status"] == "active" and r[6]["converted_alert_id"] is None
    assert (r[3]["status"], r[3]["closed_reason"]) == ("converted", None)
    assert "conversion_source" not in r[6]
