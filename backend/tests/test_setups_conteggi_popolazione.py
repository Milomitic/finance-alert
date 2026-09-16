"""I numeri della pagina «In formazione» descrivono la POPOLAZIONE, non la pagina.

Segnalato dall'utente il 2026-09-16: il titolo diceva «Esiti — 50 setup chiusi»
perche' 50 erano le righe rese (in produzione i chiusi sono 795), e ogni gruppo
per condizione contava i titoli della pagina. Un numero che cambia con la
paginazione non e' un conteggio. Il server rende ora anche i conteggi per
condizione, calcolati su tutte le righe filtrate.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.setups import condition_key
from app.main import app
from app.models import Stock, StockSetup, User

_N = 70  # oltre il limite predefinito di 50: il troncamento e' reale


@pytest.fixture
def client(db):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _semina(db, n: int, *, status: str = "active", missing: str) -> None:
    ora = datetime.now(UTC)
    for i in range(n):
        s = Stock(ticker=f"{status[:1].upper()}{i:03d}", exchange="NASDAQ",
                  name=f"T{i}", country="US")
        db.add(s)
        db.flush()
        db.add(StockSetup(
            stock_id=s.id, detector="candle_reversal", tone="bull", proximity=0.8,
            convenience=100.0 - i,
            # Il numero cambia per riga e la chiave no: e' il caso che la
            # normalizzazione deve raccogliere in un gruppo solo.
            missing=missing.format(1.5 + i / 10),
            status=status, shortlisted=True, first_seen_at=ora, last_seen_at=ora,
            resolved_at=ora if status != "active" else None,
        ))
    db.commit()


def test_il_conteggio_per_condizione_conta_la_popolazione(client, db) -> None:
    _semina(db, _N, missing="Manca il {} ATR di spazio")
    body = client.get("/api/setups").json()

    assert len(body["setups"]) == 50            # la pagina
    assert body["total"] == _N                  # la popolazione
    assert body["counts_by_condition"] == {"manca il # atr di spazio": _N}


def test_i_chiusi_hanno_il_loro_totale(client, db) -> None:
    _semina(db, _N, status="expired", missing="x {}")
    body = client.get("/api/setups?status=closed").json()
    assert len(body["setups"]) == 50
    assert body["total"] == _N


def test_la_chiave_e_la_stessa_del_frontend() -> None:
    """`conditionKey` in setupGrouping.ts e `condition_key` qui devono
    raggruppare allo stesso modo, o un conteggio non trova il suo gruppo.
    Si confronta la SORGENTE TypeScript, perche' pytest non puo' eseguirla."""
    ts = (Path(__file__).resolve().parents[2]
          / "frontend" / "src" / "lib" / "setupGrouping.ts").read_text(encoding="utf-8")
    corpo = re.search(r"export function conditionKey\([^)]*\)[^{]*\{(.*?)\n\}", ts, re.S)
    assert corpo, "conditionKey non trovata in setupGrouping.ts"
    assert r'.replace(/\d+[.,]\d+/g, "#").trim().toLowerCase()' in corpo.group(1)

    assert condition_key("  Manca 1,25 ATR e 3.5% ") == "manca # atr e #%"
