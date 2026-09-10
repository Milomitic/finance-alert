"""Il Divario fra le due lenti, ordinabile lato server.

Lo screener aveva `composite` e `tech_composite` sulla STESSA riga e non ne
faceva mai la differenza, mentre Esplora la calcola da sempre per gli undici
settori. Un titolo con Qualita 81 e Tecnico 40 e un oggetto diverso da uno con
81 e 80, e nessuna delle due colonne lo dice da sola.

⚠️ E ordinabile lato SERVER di proposito. Ordinare 50 righe di una lista
paginata lato client le presenterebbe come una classifica dell'universo — lo
stesso difetto della colonna market cap, che ordina cifre in valuta nativa
sotto un simbolo del dollaro.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, StockScore, TechnicalScore, User
from app.services.stock_service import StockFilter, search_stocks

NOW = datetime.now(UTC)


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed(db: Session, ticker: str, qualita: float | None, tecnico: float | None) -> None:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Corp", country="US")
    db.add(s)
    db.flush()
    if qualita is not None:
        db.add(
            StockScore(
                stock_id=s.id, composite=qualita, risk_tier="moderate",
                computed_at=NOW, breakdown="{}",
            )
        )
    if tecnico is not None:
        db.add(
            TechnicalScore(
                stock_id=s.id, composite=tecnico, posture="Neutro",
                computed_at=NOW, breakdown="{}",
            )
        )


def _universe(db: Session) -> None:
    # CORRE:   il prezzo e molto avanti ai fondamentali   (+40)
    # AVANTI:  un po' avanti                              (+10)
    # FERMO:   le due lenti coincidono                    (  0)
    # INDIETRO: i fondamentali sono avanti al prezzo      (-35)
    # MEZZA:   ha solo la Qualita → Divario ignoto
    _seed(db, "CORRE", 40.0, 80.0)
    _seed(db, "AVANTI", 60.0, 70.0)
    _seed(db, "FERMO", 55.0, 55.0)
    _seed(db, "INDIETRO", 85.0, 50.0)
    _seed(db, "MEZZA", 70.0, None)
    db.commit()


def test_ordina_dal_prezzo_piu_avanti_ai_fondamentali(db: Session) -> None:
    _universe(db)

    page = search_stocks(db, StockFilter(sort_by="divario", sort_dir="desc"))

    assert [it.stock.ticker for it in page.items] == [
        "CORRE", "AVANTI", "FERMO", "INDIETRO", "MEZZA",
    ]


def test_il_verso_opposto_mette_i_fondamentali_davanti(db: Session) -> None:
    _universe(db)

    page = search_stocks(db, StockFilter(sort_by="divario", sort_dir="asc"))

    assert [it.stock.ticker for it in page.items] == [
        "INDIETRO", "FERMO", "AVANTI", "CORRE", "MEZZA",
    ]


def test_una_lente_sola_non_vale_zero(db: Session) -> None:
    """⚠️ La riga con una sola lente sta in fondo in ENTRAMBI i versi.

    Sconosciuto non e zero. Se il Divario nullo venisse trattato come 0 finirebbe
    in mezzo alla classifica in un verso e in fondo nell'altro — cioe una riga
    che non abbiamo misurato comparirebbe fra quelle che concordano. Le due
    asserzioni insieme sono il test: una sola sarebbe soddisfatta anche da uno
    zero fortunato.
    """
    _universe(db)

    desc = [it.stock.ticker for it in search_stocks(db, StockFilter(sort_by="divario", sort_dir="desc")).items]
    asc = [it.stock.ticker for it in search_stocks(db, StockFilter(sort_by="divario", sort_dir="asc")).items]

    assert desc[-1] == "MEZZA"
    assert asc[-1] == "MEZZA"


def test_ordina_tutto_l_universo_non_la_pagina(db: Session) -> None:
    """La ragione per cui l'espressione vive nel SQL e non nel frontend.

    Con una pagina da due righe, il titolo con il Divario piu grande deve
    comunque essere il primo: un ordinamento lato client vedrebbe solo le due
    righe che gli sono state consegnate e presenterebbe la seconda migliore
    dell'universo come la migliore in assoluto.
    """
    _universe(db)

    page = search_stocks(db, StockFilter(sort_by="divario", sort_dir="desc", limit=2))

    assert [it.stock.ticker for it in page.items] == ["CORRE", "AVANTI"]
    assert page.total == 5


def test_l_api_accetta_la_chiave(client: TestClient, db: Session) -> None:
    _universe(db)

    r = client.get("/api/stocks/search?sort_by=divario&sort_dir=desc")

    assert r.status_code == 200
    assert [it["stock"]["ticker"] for it in r.json()["items"]][:2] == ["CORRE", "AVANTI"]


def test_una_chiave_inventata_resta_rifiutata(client: TestClient) -> None:
    # Il controllo negativo sulla whitelist: se `divario` passasse perche la
    # validazione e stata allentata invece che estesa, passerebbe anche questa.
    assert client.get("/api/stocks/search?sort_by=divarioo").status_code == 422
