"""La lista setup mostrava una popolazione e ne descriveva un'altra.

FA-056. Misurato in produzione: **1.415 setup attivi, 59 in shortlist, e la
lista ne rende 50**. Sui chiusi la divergenza e' maggiore: **637 nel database,
lista limitata a 50, statistiche calcolate su 18**.

Tre difetti distinti, che vanno tenuti separati perche' hanno cause diverse:

1. **La lista tronca a 50 e non c'e' modo di vedere il resto.** Nessun `offset`,
   nessun totale: chi guarda non sa nemmeno che manca qualcosa.
2. **Filtro per detector e ordinamento operavano sul sottoinsieme GIA' RICEVUTO**
   (`all.filter(...)` e `groupByCondition(all, sort)` nella pagina). Un detector
   i cui setup cadono tutti oltre la cinquantesima riga era irraggiungibile, e
   i conteggi dei chip contavano la pagina.
3. **Le statistiche descrivono una popolazione diversa dalla lista.**

Il terzo e' stato prima dichiarato e poi, il 2026-09-16, deciso dall'utente:
le misure contano TUTTI i setup registrati, non i soli in shortlist. Filtrate
sulla shortlist dicevano «nessun esito maturato» mentre fra tutti i convertiti
gli esiti maturati erano 83. La shortlist resta il perimetro della lista e
viaggia a parte come `active_shortlisted`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, StockSetup, User


@pytest.fixture
def client(db):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


#: Piu' del limite predefinito (50), cosi' il troncamento e' reale e non
#: ipotetico: un caso sotto soglia passerebbe anche col difetto presente.
_N = 70


def _titolo(db, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    return s


def _semina(db, *, n: int = _N) -> None:
    """`n` setup attivi in shortlist, su `n` titoli distinti.

    ⚠️ Il detector RARO sta in fondo per convenienza decrescente, cioe' oltre
    la prima pagina: e' il caso che distingue «filtro sul server» da «filtro
    sulla pagina», e senza di esso il test sarebbe vero anche col difetto.
    """
    ora = datetime.now(UTC)
    for i in range(n):
        s = Stock(ticker=f"T{i:03d}", exchange="NASDAQ", name=f"Titolo {i}",
                  country="US")
        db.add(s)
        db.flush()
        raro = i >= n - 3
        db.add(StockSetup(
            stock_id=s.id,
            detector="squeeze_expansion" if raro else "candle_reversal",
            tone="bull" if i % 2 == 0 else "bear",
            proximity=0.8,
            distance_atr=float(i % 7),
            convenience=100.0 - i,          # decrescente: i grandi in testa
            missing="manca qualcosa",
            status="active",
            shortlisted=True,
            first_seen_at=ora - timedelta(days=i),
            last_seen_at=ora,
        ))
    db.commit()


# ─── 1. Il perimetro della lista ─────────────────────────────────────────


def test_the_payload_says_how_many_rows_exist(client, db) -> None:
    """Senza un totale, una lista troncata e' indistinguibile da una completa.

    E' il difetto nella sua forma piu' semplice: in produzione 1.415 setup
    attivi e una risposta da 50, senza niente che lo dica."""
    _semina(db)
    r = client.get("/api/setups")
    assert r.status_code == 200
    body = r.json()
    assert len(body["setups"]) == 50      # il limite predefinito
    assert body["total"] == _N            # ma la popolazione e' questa
    assert body["has_more"] is True


def test_paging_covers_the_population_without_overlap(client, db) -> None:
    """⚠️ Si asserisce l'UNIONE e la disgiunzione, non «la seconda pagina non e'
    vuota»: un offset ignorato renderebbe due volte la stessa pagina, e un test
    che guarda solo la lunghezza non lo vedrebbe."""
    _semina(db)
    prima = client.get("/api/setups?limit=50&offset=0").json()["setups"]
    seconda = client.get("/api/setups?limit=50&offset=50").json()["setups"]
    id_a = {s["id"] for s in prima}
    id_b = {s["id"] for s in seconda}
    assert len(id_a) == 50 and len(id_b) == _N - 50
    assert id_a.isdisjoint(id_b)
    assert len(id_a | id_b) == _N


# ─── 2. Filtro e ordinamento sulla POPOLAZIONE ───────────────────────────


def test_the_detector_filter_reaches_beyond_the_first_page(client, db) -> None:
    """Il difetto vero di questo punto. I tre setup `squeeze_expansion` hanno
    la convenienza piu' bassa, quindi cadono oltre la cinquantesima riga: col
    filtro applicato lato client erano IRRAGGIUNGIBILI, e la pagina mostrava
    un chip che non selezionava niente."""
    _semina(db)
    intera = client.get("/api/setups").json()["setups"]
    assert not any(s["detector"] == "squeeze_expansion" for s in intera), (
        "il caso non distingue: il detector raro e' gia' nella prima pagina"
    )

    filtrata = client.get("/api/setups?detector=squeeze_expansion").json()
    assert filtrata["total"] == 3
    assert {s["detector"] for s in filtrata["setups"]} == {"squeeze_expansion"}


def test_the_detector_counts_describe_the_population_not_the_page(client, db) -> None:
    """I chip dicevano «candle_reversal 50» perche' contavano le righe
    ricevute. Un conteggio che cambia con la dimensione della pagina non e' un
    conteggio della popolazione."""
    _semina(db)
    conteggi = client.get("/api/setups").json()["counts_by_detector"]
    assert conteggi == {"candle_reversal": _N - 3, "squeeze_expansion": 3}


def test_the_counts_survive_the_detector_filter(client, db) -> None:
    """⚠️ Filtrando su un detector, i conteggi NON devono collassare a quello
    solo: i chip servono a cambiare selezione, e un chip che sparisce appena lo
    premi e' una trappola. Il conteggio ignora il filtro che descrive."""
    _semina(db)
    conteggi = client.get("/api/setups?detector=squeeze_expansion").json()["counts_by_detector"]
    assert conteggi == {"candle_reversal": _N - 3, "squeeze_expansion": 3}


def test_sorting_by_ticker_returns_the_GLOBAL_first_row(client, db) -> None:
    """Ordinare lato client riordina la pagina, non la popolazione: il primo
    per ticker era il minimo dei cinquanta ricevuti, non dei settanta."""
    _semina(db)
    per_convenienza = client.get("/api/setups").json()["setups"]
    per_ticker = client.get("/api/setups?sort=ticker").json()["setups"]
    assert per_ticker[0]["ticker"] == "T000"
    # Il caso distingue davvero solo se i due ordinamenti differiscono.
    assert per_ticker[0]["id"] != per_convenienza[0]["id"] or \
        per_convenienza[0]["ticker"] == "T000"


def test_sorting_by_waiting_puts_the_OLDEST_wait_first(client, db) -> None:
    """`waiting` e' derivato da `first_seen_at`: attesa piu' lunga = prima
    vista. Il seme mette il piu' vecchio in fondo per convenienza, quindi un
    ordinamento che restasse sulla pagina non potrebbe trovarlo."""
    _semina(db)
    righe = client.get("/api/setups?sort=waiting").json()["setups"]
    assert righe[0]["ticker"] == f"T{_N - 1:03d}"


# ─── 3. Il perimetro STATISTICO, che va dichiarato e non uniformato ──────


def test_the_stats_describe_the_whole_population(client, db) -> None:
    """Le misure contano TUTTI i setup registrati (decisione dell'utente,
    2026-09-16), e il perimetro della lista — la shortlist — viaggia a parte
    come `active_shortlisted`, cosi' che la pagina non confonda i due numeri."""
    _semina(db)
    # Un setup attivo FUORI shortlist: non sta nella lista globale, ma e' parte
    # della popolazione misurata.
    s = Stock(ticker="FUORI", exchange="NASDAQ", name="Fuori", country="US")
    db.add(s)
    db.flush()
    db.add(StockSetup(
        stock_id=s.id, detector="candle_reversal", tone="bull", proximity=0.5,
        convenience=99.0, missing="x", status="active", shortlisted=False,
        first_seen_at=datetime.now(UTC), last_seen_at=datetime.now(UTC),
    ))
    db.commit()

    stats = client.get("/api/setups").json()["stats"]
    assert stats["scope"] == "all"
    assert stats["total"] == _N + 1, "le statistiche contano anche i setup fuori shortlist"
    assert stats["active_shortlisted"] == stats["active"] - 1


def test_the_close_reason_reaches_the_payload(client, db) -> None:
    """⚠️ Un campo che resta nel database e non raggiunge nessuno e' il difetto
    di FA-055 in miniatura: esiste, e nessuno puo' vederlo.

    `expire_stale_setups` calcolava gia' la distinzione fra «le condizioni si
    sono sfaldate» e «ha toccato il tetto d'attesa» — le contava separatamente
    nel log — e poi scriveva entrambe come `expired` senza conservare quale.
    """
    from app.models.stock_setup import REASON_AGED

    s = _titolo(db, "CHIUSO")
    ora = datetime.now(UTC)
    db.add(StockSetup(
        stock_id=s.id, detector="candle_reversal", tone="bull", proximity=0.8,
        convenience=70.0, missing="x", status="expired", closed_reason=REASON_AGED,
        resolved_at=ora, shortlisted=True, first_seen_at=ora, last_seen_at=ora,
    ))
    db.commit()

    righe = client.get("/api/setups?status=closed").json()["setups"]
    riga = next(r for r in righe if r["ticker"] == "CHIUSO")
    assert riga["closed_reason"] == "aged"
