"""Il contatore d'uso delle pagine (FA-114)."""
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core import rotte
from app.main import app
from app.models import User
from app.models.uso_pagina import UsoPagina
from app.services import uso_pagine_service as uso

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
OGGI = date(2026, 9, 28)


# ── la chiave ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "vista", "chiave"),
    [
        ("/", None, "/"),
        ("/stocks", None, "/stocks"),
        ("/stocks/AAPL", None, "/stocks/:ticker"),
        ("/stocks/0700.HK/", None, "/stocks/:ticker"),
        ("/institutionals/berkshire", None, "/institutionals/:slug"),
        ("/alerts", None, "/alerts?vista=segnali"),
        ("/alerts", "formazione", "/alerts?vista=formazione"),
        ("/alerts", "boh", "/alerts?vista=segnali"),          # come fa il frontend
        ("/diagnostics", "motore", "/diagnostics?vista=motore"),
        ("/diagnostics", None, "/diagnostics?vista=piattaforma"),
        ("/una/pagina/che/non/esiste", None, "/other"),
    ],
)
def test_la_chiave_ha_cardinalita_limitata(path, vista, chiave) -> None:
    assert rotte.rotta_uso(path, vista) == chiave


@pytest.mark.parametrize("path", ["/setups", "/health", "/settings", "/login"])
def test_i_reindirizzamenti_non_si_contano(path) -> None:
    """Il router li rimanda altrove e il cambio di rotta verso la destinazione
    arriva subito dopo: contarli li conterebbe due volte."""
    assert rotte.rotta_uso(path) is None


def test_ogni_chiave_possibile_entra_nella_colonna() -> None:
    """La colonna ha una lunghezza, e Postgres la fa rispettare (la lezione
    di FA-061). Si generano TUTTE le chiavi possibili, non un esempio."""
    chiavi = {rotte.rotta_uso(p) for p in rotte.ROTTE_STATICHE} | {
        rotte.rotta_uso(f"/{pref}/x") for pref in rotte.ROTTE_DINAMICHE
    } | {rotte.rotta_uso(pag, v) for pag, (_, ammesse) in rotte.VISTE.items() for v in ammesse}
    chiavi |= {rotte.rotta_uso("/non/esiste")}
    chiavi.discard(None)
    lunghezza = UsoPagina.__table__.c.rotta.type.length
    # 6 statiche senza viste, 5 dinamiche, 5 viste, /other.
    assert len(chiavi) == 17
    assert max(map(len, chiavi)) <= lunghezza, max(chiavi, key=len)


# ── il gemello del frontend ───────────────────────────────────────────────


def test_le_rotte_sono_quelle_di_app_tsx() -> None:
    """⚠️ Il RUM aveva la sua lista a mano ed era gia' indietro: `/diagnostics`
    finiva sotto `/other`. Un gemello si confronta con l'originale."""
    sorgente = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    percorsi = set(re.findall(r'path="([^"]+)"', sorgente)) - {"*"}
    assert len(percorsi) >= 15, "App.tsx letto male: troppe poche rotte"
    statici = {p for p in percorsi if ":" not in p}
    dinamici = {p.split("/")[1]: p.split(":")[1] for p in percorsi if ":" in p}
    assert statici == rotte.ROTTE_STATICHE | set(rotte.REINDIRIZZAMENTI)
    assert dinamici == rotte.ROTTE_DINAMICHE


def test_le_viste_sono_quelle_delle_pagine() -> None:
    def ids(file: str, nome: str) -> set[str]:
        testo = (FRONTEND / file).read_text(encoding="utf-8")
        blocco = testo[testo.index(f"{nome} = ["):]
        blocco = blocco[: blocco.index("] as const")]
        return set(re.findall(r'id:\s*"([^"]+)"', blocco))

    assert ids("lib/schedeSegnali.ts", "SCHEDE") == set(rotte.VISTE["/alerts"][1])
    assert ids("pages/DiagnosticsPage.tsx", "TABS") == set(rotte.VISTE["/diagnostics"][1])


def _chiavi_possibili() -> set[str]:
    chiavi = {rotte.rotta_uso(p) for p in rotte.ROTTE_STATICHE} | {
        rotte.rotta_uso(f"/{pref}/x") for pref in rotte.ROTTE_DINAMICHE
    } | {rotte.rotta_uso(pag, v) for pag, (_, ammesse) in rotte.VISTE.items() for v in ammesse}
    chiavi |= {rotte.rotta_uso("/non/esiste")}
    chiavi.discard(None)
    return chiavi


def test_ogni_chiave_ha_un_nome_a_schermo() -> None:
    """Una chiave senza nome si vedrebbe grezza nella Diagnostica
    («/institutionals/:slug»): il frontend deve conoscerle tutte."""
    testo = (FRONTEND / "lib" / "rotteUso.ts").read_text(encoding="utf-8")
    blocco = testo[testo.index("const NOMI"):]
    blocco = blocco[: blocco.index("};")]
    nomi = set(re.findall(r'"([^"]+)":', blocco))
    assert nomi == _chiavi_possibili()
    pagine = set(re.findall(r'"(/[a-z]+)"', testo[testo.index("PAGINE_A_VISTE"):testo.index("const NOMI")]))
    assert pagine == set(rotte.VISTE)


# ── il contatore ──────────────────────────────────────────────────────────


def test_due_aperture_lo_stesso_giorno_sono_due(db: Session) -> None:
    uso.registra(db, "/", oggi=OGGI)
    uso.registra(db, "/", oggi=OGGI)
    uso.registra(db, "/", oggi=OGGI - timedelta(days=1))
    righe = {(r.giorno, r.aperture) for r in db.execute(select(UsoPagina)).scalars()}
    assert righe == {(OGGI, 2), (OGGI - timedelta(days=1), 1)}


def test_il_riepilogo_separa_sette_e_trenta_giorni(db: Session) -> None:
    for giorni_fa, rotta, n in [(0, "/", 3), (6, "/", 2), (7, "/", 5), (29, "/", 1),
                                 (30, "/", 100), (-1, "/", 100), (2, "/calendar", 4)]:
        for _ in range(n):
            uso.registra(db, rotta, oggi=OGGI - timedelta(days=giorni_fa))

    r = uso.riepilogo(db, oggi=OGGI)
    per_rotta = {u.rotta: (u.ultimi_7, u.ultimi_30) for u in r.rotte}
    # 7 giorni = oggi e i sei prima; 30 = oggi e i ventinove prima. Il giorno 30
    # e quello di domani (un orologio sbagliato) restano fuori da entrambi.
    assert per_rotta == {"/": (5, 11), "/calendar": (4, 4)}
    assert [u.rotta for u in r.rotte] == ["/", "/calendar"]
    assert r.dal == OGGI - timedelta(days=30)


def test_senza_aperture_il_riepilogo_e_vuoto_e_non_sa_da_quando(db: Session) -> None:
    r = uso.riepilogo(db, oggi=OGGI)
    assert (r.dal, r.rotte) == (None, [])


# ── l'endpoint e la Diagnostica ───────────────────────────────────────────


@pytest.fixture
def client(db: Session):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_l_endpoint_conta_e_rende_la_chiave(client, db: Session) -> None:
    r = client.post("/api/uso/pagina", json={"path": "/alerts", "vista": "esiti"})
    assert (r.status_code, r.json()) == (202, {"rotta": "/alerts?vista=esiti"})
    r = client.post("/api/uso/pagina", json={"path": "/setups"})
    assert (r.status_code, r.json()) == (202, {"rotta": None})
    assert [(u.rotta, u.aperture) for u in db.execute(select(UsoPagina)).scalars()] == [
        ("/alerts?vista=esiti", 1)
    ]


def test_un_percorso_enorme_e_rifiutato(client) -> None:
    assert client.post("/api/uso/pagina", json={"path": "/" + "x" * 300}).status_code == 422


def test_il_riepilogo_arriva_con_lo_snapshot_di_salute(db: Session) -> None:
    from app.api.platform_health import _uso_pagine

    uso.registra(db, "/stocks/:ticker")
    out = _uso_pagine(db)
    assert [(u.rotta, u.ultimi_7) for u in out.rotte] == [("/stocks/:ticker", 1)]
    assert out.dal == out.oggi


def test_una_lettura_rotta_non_toglie_lo_snapshot(db: Session, monkeypatch) -> None:
    from app.api import platform_health

    def rotto(_db):
        raise RuntimeError("tabella mancante")

    monkeypatch.setattr(platform_health.uso_pagine_service, "riepilogo", rotto)
    assert platform_health._uso_pagine(db) is None
