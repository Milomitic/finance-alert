"""Gli endpoint dei superinvestor e dei fondi (FA-107).

I servizi sotto hanno i loro test; tre rotte che li servono non erano mai
state eseguite: l'elenco, l'aggregato della pagina Superinvestor, e i
detentori di un titolo sulla pagina titolo. Qui si prova cio' che aggiungono:
l'ordine delle rotte (`/aggregate` prima di `/{slug}`), i filtri, e la
serializzazione fino al JSON.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Institutional, InstitutionalFiling, InstitutionalHolding, User

# Relativi a oggi, come negli altri test del dominio: il taglio di freschezza
# a 18 mesi deve valere a qualunque data giri la suite.
FRESCO = date.today() - timedelta(days=40)
PRIMA = date.today() - timedelta(days=130)


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _fondo(db: Session, slug: str, tipo: str, fonte: str) -> Institutional:
    f = Institutional(slug=slug, name=slug.title(), type=tipo, source=fonte)
    db.add(f)
    db.flush()
    return f


def _deposito(db: Session, fondo: Institutional, periodo: date, righe: list[tuple]) -> None:
    dep = InstitutionalFiling(institutional_id=fondo.id, period_end_date=periodo)
    db.add(dep)
    db.flush()
    for ticker, azione, azioni, peso in righe:
        db.add(InstitutionalHolding(
            filing_id=dep.id, ticker=ticker, company_name=f"{ticker} Inc.",
            shares=azioni, value_usd=azioni * 100, portfolio_pct=peso, action=azione,
        ))


@pytest.fixture
def fondi(db: Session) -> None:
    buffett = _fondo(db, "buffett", "superinvestor", "dataroma")
    _deposito(db, buffett, PRIMA, [("AAPL", "hold", 1000, 40.0), ("KO", "hold", 500, 20.0),
                                   ("OLD", "hold", 300, 10.0)])
    _deposito(db, buffett, FRESCO, [("AAPL", "add", 1200, 45.0), ("KO", "hold", 500, 20.0),
                                    ("NEWCO", "new", 200, 5.0), ("OLD", "sold_out", 0, 0.0)])
    ackman = _fondo(db, "ackman", "superinvestor", "dataroma")
    # Ackman esce da KO, che Buffett tiene ancora: il suo nome non deve
    # comparire fra i detentori di KO nell'aggregato.
    _deposito(db, ackman, PRIMA, [("AAPL", "hold", 800, 30.0), ("KO", "hold", 100, 5.0)])
    _deposito(db, ackman, FRESCO, [("AAPL", "reduce", 400, 15.0), ("KO", "sold_out", 0, 0.0)])
    vanguard = _fondo(db, "vanguard", "institution", "sec_13f")
    _deposito(db, vanguard, FRESCO, [("AAPL", None, 9000, 5.0)])
    db.commit()


def test_l_elenco_e_il_filtro_per_tipo(client, fondi) -> None:
    tutti = client.get("/api/institutionals").json()
    assert {f["slug"] for f in tutti} == {"buffett", "ackman", "vanguard"}
    assert all(f["latest_period_end"] == FRESCO.isoformat() for f in tutti)
    solo = client.get("/api/institutionals?type=superinvestor").json()
    assert {f["slug"] for f in solo} == {"buffett", "ackman"}


def test_aggregate_non_e_scambiato_per_un_fondo(client, fondi) -> None:
    """`/aggregate` e' dichiarata prima di `/{slug}`: se l'ordine si
    invertisse, la pagina Superinvestor riceverebbe un 404 «fondo non
    trovato»."""
    r = client.get("/api/institutionals/aggregate")
    assert r.status_code == 200
    assert set(r.json()) == {"most_picked", "recent_buys", "recent_sells", "sector_tilt"}
    assert client.get("/api/institutionals/nessuno").status_code == 404


def test_i_piu_scelti_contano_chi_detiene(client, fondi) -> None:
    per_ticker = {x["ticker"]: x for x in client.get("/api/institutionals/aggregate").json()["most_picked"]}
    assert per_ticker["AAPL"]["holder_count"] == 3
    assert set(per_ticker["AAPL"]["holders"]) == {"Buffett", "Ackman", "Vanguard"}
    solo = client.get("/api/institutionals/aggregate?type=superinvestor").json()["most_picked"]
    assert next(x for x in solo if x["ticker"] == "AAPL")["holder_count"] == 2


def test_una_posizione_venduta_non_e_una_scelta(client, fondi) -> None:
    """Il difetto trovato. Buffett ha venduto OLD: il salvataggio scrive una
    riga a zero azioni perche' la pagina titolo mostri l'uscita, e «I piu'
    scelti» la contava come un detentore — in produzione 5.091 titoli
    gonfiati. L'uscita resta dove ha senso: fra le vendite."""
    agg = client.get("/api/institutionals/aggregate").json()
    per_ticker = {x["ticker"]: x for x in agg["most_picked"]}
    assert "OLD" not in per_ticker
    assert (per_ticker["KO"]["holder_count"], per_ticker["KO"]["holders"]) == (1, ["Buffett"])
    assert ("OLD", "buffett", "sold_out") in {
        (x["ticker"], x["institutional_slug"], x["action"]) for x in agg["recent_sells"]
    }


def test_acquisti_e_vendite_del_trimestre(client, fondi) -> None:
    agg = client.get("/api/institutionals/aggregate").json()

    def mosse(chiave):
        return {(x["ticker"], x["institutional_slug"], x["action"]) for x in agg[chiave]}

    assert mosse("recent_buys") == {("AAPL", "buffett", "add"), ("NEWCO", "buffett", "new")}
    assert mosse("recent_sells") == {
        ("AAPL", "ackman", "reduce"), ("OLD", "buffett", "sold_out"), ("KO", "ackman", "sold_out"),
    }


def test_i_detentori_di_un_titolo(client, fondi) -> None:
    d = client.get("/api/stocks/KO/institutional-holders").json()
    assert d["ticker"] == "KO"
    assert [(h["institutional_slug"], h["shares"], h["action"]) for h in d["holders"]] == [
        ("buffett", 500, "hold"), ("ackman", 0, "sold_out"),
    ]
    assert d["historical"] == []


def test_sulla_pagina_titolo_l_uscita_si_vede(client, fondi) -> None:
    """Qui la riga a zero azioni e' VOLUTA: «chi e' uscito questo trimestre»
    e' il segnale che la scheda esiste per mostrare. E non compare due volte:
    chi e' fra i correnti non si ripete fra gli storici."""
    d = client.get("/api/stocks/OLD/institutional-holders?include_historical=true").json()
    assert [(h["institutional_slug"], h["shares"], h["action"]) for h in d["holders"]] == [("buffett", 0, "sold_out")]
    assert d["historical"] == []


def test_un_titolo_senza_fondi_non_e_un_errore(client, fondi) -> None:
    r = client.get("/api/stocks/ZZZZ/institutional-holders?include_historical=true")
    assert (r.status_code, r.json()["holders"], r.json()["historical"]) == (200, [], [])
