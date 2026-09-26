"""La migrazione `a9d4e7f1c2b8` riempie `alerts.emitted_at` dallo storico (FA-100).

Si esegue la migrazione VERA sulla catena Alembic, su righe costruite come le
popolazioni che esistono in produzione: alert rivisti con `first_emitted_at`,
alert di prezzo e righe anteriori al campo che non l'hanno, snapshot rotti,
istanti con un altro fuso o senza fuso.

Il Postgres ha il suo giro in `test_postgres_integration.py`.
"""
import json
from datetime import UTC, datetime

import pytest
from alembic.config import Config
from sqlalchemy import DateTime, Integer, column, create_engine, inspect, select, table, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings

_PRIMA = "f7a3c9e2b1d4"
_QUESTA = "a9d4e7f1c2b8"

_ALERTS = table("alerts", column("id", Integer), column("emitted_at", DateTime(timezone=True)))


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


def _alert(c, id_: int, *, snapshot: str, triggered_at: str) -> None:
    c.execute(text(
        "INSERT INTO alerts (id, stock_id, trigger_price, snapshot, triggered_at) "
        "VALUES (:i, 1, 50.0, :s, :t)"
    ), {"i": id_, "s": snapshot, "t": triggered_at})


def _nascite(eng) -> dict[int, datetime]:
    with eng.connect() as c:
        return {
            i: n.replace(tzinfo=UTC) if n.tzinfo is None else n
            for i, n in c.execute(select(_ALERTS.c.id, _ALERTS.c.emitted_at))
        }


def _prima(istante: str) -> str:
    return json.dumps({"tone": "bull", "first_emitted_at": istante})


def test_la_nascita_viene_dallo_snapshot_e_ripiega_su_triggered_at(catena) -> None:
    cfg, eng = catena
    with eng.begin() as c:
        # Rivisto: nato il 20, ultima revisione il 25.
        _alert(c, 1, snapshot=_prima("2026-09-20T23:32:00+00:00"),
               triggered_at="2026-09-25 23:33:00")
        # Alert di prezzo, o anteriore al campo: mai rivisto.
        _alert(c, 2, snapshot=json.dumps({"kind": "price_target"}),
               triggered_at="2026-09-22 23:31:00")
        _alert(c, 3, snapshot="{non e' json", triggered_at="2026-09-23 10:00:00")
        # Un altro fuso: le 01:30 di Roma sono le 23:30 UTC del giorno prima.
        _alert(c, 4, snapshot=_prima("2026-09-21T01:30:00+02:00"),
               triggered_at="2026-09-24 23:30:00")
        # Senza fuso: la convenzione del progetto e' UTC.
        _alert(c, 5, snapshot=_prima("2026-09-19T23:30:00"),
               triggered_at="2026-09-24 23:30:00")
        _alert(c, 6, snapshot=_prima("ieri"), triggered_at="2026-09-18 12:00:00")
    command.upgrade(cfg, _QUESTA)

    assert _nascite(eng) == {
        1: datetime(2026, 9, 20, 23, 32, tzinfo=UTC),
        2: datetime(2026, 9, 22, 23, 31, tzinfo=UTC),
        3: datetime(2026, 9, 23, 10, 0, tzinfo=UTC),
        4: datetime(2026, 9, 20, 23, 30, tzinfo=UTC),
        5: datetime(2026, 9, 19, 23, 30, tzinfo=UTC),
        6: datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
    }


def test_il_riempimento_attraversa_il_confine_delle_pagine(catena) -> None:
    """Le pagine esistono per la memoria del pod, 2000 righe alla volta. Un
    errore sul confine lascerebbe righe al ripiego su `triggered_at` senza
    dirlo: con 2003 righe il confine cade dentro il test."""
    cfg, eng = catena
    with eng.begin() as c:
        c.execute(text(
            "INSERT INTO alerts (id, stock_id, trigger_price, snapshot, triggered_at) "
            "VALUES (:i, 1, 50.0, :s, '2026-09-25 23:33:00')"
        ), [{"i": i, "s": _prima("2026-09-20T12:00:00+00:00")} for i in range(1, 2004)])
    command.upgrade(cfg, _QUESTA)

    nascite = _nascite(eng)
    assert len(nascite) == 2003
    assert set(nascite.values()) == {datetime(2026, 9, 20, 12, tzinfo=UTC)}


def test_dopo_la_migrazione_la_colonna_e_obbligatoria_indicizzata_e_ha_un_default(
    catena,
) -> None:
    cfg, eng = catena
    command.upgrade(cfg, _QUESTA)

    colonne = {c["name"]: c for c in inspect(eng).get_columns("alerts")}
    assert colonne["emitted_at"]["nullable"] is False
    assert "ix_alerts_emitted_at" in {i["name"] for i in inspect(eng).get_indexes("alerts")}
    # Il default lato database: una INSERT scritta a mano non nomina la colonna.
    with eng.begin() as c:
        _alert(c, 7, snapshot="{}", triggered_at="2026-09-26 08:00:00")
    assert 7 in _nascite(eng)
    with pytest.raises(IntegrityError), eng.begin() as c:
        c.execute(text("UPDATE alerts SET emitted_at = NULL WHERE id = 7"))


def test_ricreare_la_tabella_non_si_porta_via_le_righe_figlie(catena) -> None:
    """⚠️ Su SQLite il NOT NULL ricrea `alerts`: copia, DROP della vecchia,
    RENAME della nuova. Misurato il 2026-09-26: un `DROP TABLE alerts` eseguito
    A MANO con `PRAGMA foreign_keys=ON` cancella a cascata gli esiti che la
    puntano, sia da sqlite3 sia da SQLAlchemy. Durante la migrazione non
    succede: `alembic/env.py` crea il proprio engine senza l'ascoltatore che
    accende il pragma — e anche accendendolo sul solo passo di questa
    migrazione gli esiti sono rimasti, per un meccanismo che non e' stato
    accertato. Il test sorveglia quindi la PROPRIETA', non il meccanismo."""
    cfg, eng = catena
    with eng.begin() as c:
        _alert(c, 1, snapshot=_prima("2026-09-20T23:32:00+00:00"),
               triggered_at="2026-09-25 23:33:00")
        c.execute(text(
            "INSERT INTO signal_outcomes (alert_id, stock_id, detector, signal_date, "
            "tone, horizon_days, entry_close, forward_close, fwd_return, abs_hit, "
            "matured_at) VALUES (1, 1, 'sr_flip', '2026-09-20', 'bull', 21, 50.0, "
            "55.0, 0.1, 1, '2026-09-25 23:40:00')"
        ))
    command.upgrade(cfg, _QUESTA)
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM signal_outcomes")).scalar_one() == 1


def test_il_ritorno_toglie_la_colonna_e_l_andata_la_ricostruisce_uguale(catena) -> None:
    cfg, eng = catena
    with eng.begin() as c:
        _alert(c, 1, snapshot=_prima("2026-09-20T23:32:00+00:00"),
               triggered_at="2026-09-25 23:33:00")
    command.upgrade(cfg, _QUESTA)
    andata = _nascite(eng)

    command.downgrade(cfg, _PRIMA)
    assert "emitted_at" not in {c["name"] for c in inspect(eng).get_columns("alerts")}
    # Il batch ricrea la tabella: gli indici che c'erano devono esserci ancora.
    indici = {i["name"] for i in inspect(eng).get_indexes("alerts")}
    assert {"ix_alerts_triggered_at", "ix_alerts_stock_id"} <= indici

    command.upgrade(cfg, _QUESTA)
    assert _nascite(eng) == andata
