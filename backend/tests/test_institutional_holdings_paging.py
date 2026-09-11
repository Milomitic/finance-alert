"""Le holdings di una dichiarazione hanno un limite, a tutti e tre gli strati.

FA-034. `get_institutional_detail` non aveva `limit`/`offset` — a differenza di
`holders_for_ticker` poche righe piu sotto, che ha `limit: int = 25` — la query
non aveva `.limit()`, e il frontend mappava l'intero array. Uno screenshot
interno superava i **302.900 pixel** di altezza.

⚠️ Misurato in produzione prima di scegliere dove mettere il limite: la
dichiarazione piu grande porta **7.530 righe**, e su tutte le 377.995 righe del
magazzino le coppie (dichiarazione, ticker) duplicate sono **ZERO**. Conta,
perche la deduplicazione avviene in Python DOPO la query: se togliesse righe,
un `.limit()` SQL darebbe pagine corte in silenzio. Non ne toglie, quindi
paginare nella query e sicuro — e il guardiano resta come difesa, non come
meccanismo.

⚠️ E i conteggi a schermo sono DUE cose diverse, non uno sbagliato: su 356
dichiarazioni, 145 hanno `total_positions` diverso dal numero di righe. La
direzione non e nemmeno sempre la stessa — sui fondi SEC le righe eccedono
(`compute_qoq_deltas` inserisce righe sintetiche per le uscite e non aggiorna
mai `total_positions`), sui fondi Dataroma MANCANO, con zero uscite, perche lo
scrape ne ha prese meno di quante il fondo ne dichiari. Percio' l'etichetta
dice cosa conta ciascun numero e non spiega la differenza: spiegarla con le
uscite sarebbe vero per 107 casi su 145 e falso per gli altri 38.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User
from app.models.institutional import (
    Institutional,
    InstitutionalFiling,
    InstitutionalHolding,
)
from app.services import institutional_service


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _fondo(db: Session, n_righe: int, *, dichiarate: int | None = None) -> str:
    from datetime import date

    inst = Institutional(slug="grande", name="Fondo Grande", type="fund", source="sec")
    db.add(inst)
    db.flush()
    f = InstitutionalFiling(
        institutional_id=inst.id,
        period_end_date=date(2026, 6, 30),
        total_positions=dichiarate if dichiarate is not None else n_righe,
    )
    db.add(f)
    db.flush()
    for i in range(n_righe):
        db.add(InstitutionalHolding(
            filing_id=f.id, ticker=f"T{i:04d}", company_name=f"Soc {i}",
            shares=100, value_usd=1000.0,
            # decrescente: la riga 0 e la piu pesante
            portfolio_pct=float(n_righe - i),
        ))
    db.commit()
    return inst.slug


def test_la_prima_pagina_e_corta_e_ordinata_dalla_piu_pesante(client, db):
    _fondo(db, 300)
    d = client.get("/api/institutionals/grande?limit=50").json()
    assert len(d["holdings"]) == 50
    assert d["holdings"][0]["ticker"] == "T0000"


def test_la_risposta_dice_quante_righe_esistono_in_tutto(client, db):
    """Senza il totale, una pagina corta e indistinguibile da «e finito»."""
    _fondo(db, 300)
    d = client.get("/api/institutionals/grande?limit=50").json()
    assert d["holdings_total"] == 300


def test_offset_prende_la_pagina_successiva_senza_sovrapporsi(client, db):
    _fondo(db, 300)
    p1 = client.get("/api/institutionals/grande?limit=50").json()["holdings"]
    p2 = client.get("/api/institutionals/grande?limit=50&offset=50").json()["holdings"]
    assert p2[0]["ticker"] == "T0050"
    assert not ({h["ticker"] for h in p1} & {h["ticker"] for h in p2})


def test_la_pagina_e_piena_anche_quando_il_limite_e_minore_del_totale(client, db):
    """⚠️ Il guardiano sui ticker gia visti gira DOPO la query: se togliesse
    righe, la pagina uscirebbe corta in silenzio. Misurato in produzione: zero
    duplicati su 377.995 righe, quindi non ne toglie — e questo test lo pinna."""
    _fondo(db, 7530)   # la dichiarazione piu grande vista in produzione
    d = client.get("/api/institutionals/grande?limit=100").json()
    assert len(d["holdings"]) == 100
    assert d["holdings_total"] == 7530


def test_senza_limite_esplicito_non_si_scarica_tutto(client, db):
    """⚠️ Il difetto era l'ASSENZA di un limite: se il valore di riposo restasse
    «tutte», il frontend che non passa nulla ricadrebbe nel caso di partenza."""
    _fondo(db, 7530)
    d = client.get("/api/institutionals/grande").json()
    assert len(d["holdings"]) < 7530
    assert d["holdings_total"] == 7530


def test_i_due_conteggi_restano_distinti_e_arrivano_entrambi(client, db):
    """Le dichiarate e le righe sono DUE misure. Su 145 dichiarazioni su 356
    differiscono, e in entrambe le direzioni."""
    _fondo(db, 300, dichiarate=280)
    d = client.get("/api/institutionals/grande?limit=10").json()
    assert d["institutional"]["total_positions"] == 280
    assert d["holdings_total"] == 300


def test_il_servizio_espone_limit_e_offset_come_holders_for_ticker(db):
    """La firma vicina aveva gia `limit: int = 25`; questa non aveva niente."""
    import inspect

    p = inspect.signature(institutional_service.get_institutional_detail).parameters
    assert "limit" in p and "offset" in p


def test_gli_aggregati_non_dipendono_dalla_pagina(client, db):
    """⚠️ La pagina ha TRE aggregati di livello-portafoglio — top 10 per peso,
    infografica di composizione, conteggio delle variazioni — che oggi leggono
    l'array intero. Paginare la tabella senza servirli a parte li farebbe
    cambiare a ogni «mostra altri», cioe un numero che si muove perche hai
    scrollato.

    ⚠️ E le uscite sono il caso che smaschera il difetto: hanno
    `portfolio_pct` a zero o nullo, quindi nell'ordinamento per peso finiscono
    ULTIME — una prima pagina non ne contiene nemmeno una, per quanto sia
    grande. In produzione la dichiarazione piu grande ne ha 1.301 su 7.530.
    """
    from datetime import date

    from app.models.institutional import (
        Institutional,
        InstitutionalFiling,
        InstitutionalHolding,
    )

    inst = Institutional(slug="misto", name="Misto", type="fund", source="sec")
    db.add(inst); db.flush()
    f = InstitutionalFiling(institutional_id=inst.id, period_end_date=date(2026, 6, 30), total_positions=300)
    db.add(f); db.flush()
    for i in range(300):
        db.add(InstitutionalHolding(
            filing_id=f.id, ticker=f"V{i:04d}", company_name=f"Viva {i}",
            shares=100, value_usd=1000.0, portfolio_pct=float(300 - i)))
    for i in range(40):
        db.add(InstitutionalHolding(
            filing_id=f.id, ticker=f"X{i:04d}", company_name=f"Uscita {i}",
            shares=0, value_usd=0.0, portfolio_pct=0.0, action="sold_out"))
    db.commit()

    d = client.get("/api/institutionals/misto?limit=20").json()
    assert len(d["holdings"]) == 20
    assert d["holdings_total"] == 340

    comp = d["composition"]
    assert comp, "la composizione deve arrivare a parte dalla pagina"
    # porta le piu pesanti...
    assert comp[0]["ticker"] == "V0000"
    # ...E almeno un'uscita, che nessuna prima pagina per peso conterrebbe
    assert any(h["action"] == "sold_out" for h in comp), \
        "senza uscite l'infografica perde le posizioni chiuse"
    # ma resta piccola: e un aggregato, non un secondo scarico
    assert len(comp) <= 25


def test_la_composizione_non_cresce_con_il_limite(client, db):
    """E un aggregato: chiedere una pagina piu grande non deve gonfiarlo."""
    _fondo(db, 400)
    a = client.get("/api/institutionals/grande?limit=10").json()["composition"]
    b = client.get("/api/institutionals/grande?limit=400").json()["composition"]
    assert a == b
