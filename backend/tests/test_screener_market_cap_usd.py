"""Il market cap dello screener e la classifica che ci si ordina sopra.

FA-026, voce D-1 del piano. `Stock.market_cap` e nella valuta di QUOTAZIONE —
yfinance restituisce `marketCap` denominato nella valuta di scambio — e la
colonna dello screener stampava `$` sul numero grezzo **ed era ordinabile**.

⚠️ NON e una rietichettatura. Misurato in produzione l'11 settembre 2026 su
984 titoli con market cap: la top 10 in valuta nativa e la top 10 convertita in
dollari **non hanno un solo titolo in comune**. La prima e fatta di dieci
titoli coreani, perche una cifra in KRW e circa 1300 volte piu grande. E lo
stesso difetto che `risk.py` ha gia pagato: 158 nomi superavano la soglia
mega-cap in valuta nativa contro 83 in USD, quindi 75 titoli erano classificati
mega-cap stabili senza esserlo.

L'opzione scelta e la terza del piano: **ordinare in USD, mostrare in valuta
nativa**. La colonna esiste per ordinare, quindi l'ordinamento non puo
rompersi; e stampare `HK$2.86T` accanto a un prezzo `HK$165.60` e coerente con
la riga, mentre convertire i numeri a schermo cambierebbe cifre che l'utente e
abituato a leggere in un contesto dove il resto della riga resta nativo.

⚠️ L'espressione vive nel SORT, come `DIVARIO_EXPR` e `pct_off_high`. Ordinare
lato client le 50 righe della pagina le presenterebbe come una classifica
dell'universo, che e precisamente il difetto che questa voce chiude.

⚠️ E il tasso si legge SOLO DA CACHE. `fx_service._get_rate` fa una chiamata
yfinance quando la cache e fredda: sul path di una lista e inaccettabile, ed e
la stessa regola che `calendar_service` e `next_earnings_dates_cached` gia
rispettano.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User
from app.services import fx_service


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _stock(db: Session, ticker: str, cap: float | None, currency: str | None) -> None:
    db.add(Stock(
        ticker=ticker, exchange="X", name=ticker, country="US",
        market_cap=cap, currency=currency,
    ))
    db.commit()


def _rows(client: TestClient, **params) -> list[dict]:
    """Le anagrafiche delle righe. La riga dello screener e annidata —
    `{stock, score, technical, metrics}` — e `market_cap_usd` sta accanto a
    `market_cap` e `currency`, cioe dove vive il valore che qualifica."""
    r = client.get("/api/stocks/search", params=params)
    assert r.status_code == 200, r.text
    return [item["stock"] for item in r.json()["items"]]


def test_l_ordinamento_e_in_dollari_non_in_valuta_nativa(client, db):
    """Il caso reale: un titolo coreano davanti a una mega-cap americana."""
    # 300.000 miliardi di won = ~231 miliardi di dollari.
    _stock(db, "005930.KS", 300_000_000_000_000, "KRW")
    # 3.000 miliardi di dollari: dodici volte tanto, cifra grezza piu piccola.
    _stock(db, "NVDA", 3_000_000_000_000, "USD")
    ordinati = [r["ticker"] for r in _rows(client, sort_by="market_cap", sort_dir="desc")]
    assert ordinati[0] == "NVDA", f"ordinato sulla cifra grezza: {ordinati}"


def test_la_cifra_mostrata_resta_in_valuta_nativa(client, db):
    """Convertire a schermo cambierebbe numeri che il resto della riga non
    converte: il prezzo accanto resta in valuta di quotazione."""
    _stock(db, "0005.HK", 2_860_000_000_000, "HKD")
    riga = _rows(client, q="0005.HK")[0]
    assert riga["market_cap"] == 2_860_000_000_000
    assert riga["currency"] == "HKD"


def test_il_valore_convertito_viaggia_accanto_alla_cifra_nativa(client, db):
    _stock(db, "0005.HK", 2_860_000_000_000, "HKD")
    riga = _rows(client, q="0005.HK")[0]
    atteso = fx_service.to_usd(2_860_000_000_000, "HKD")
    assert atteso is not None
    assert riga["market_cap_usd"] == pytest.approx(atteso, rel=1e-6)


def test_una_valuta_ignota_non_diventa_dollari(client, db):
    """⚠️ La regola che `fx_service` dichiara nel proprio docstring: assumere
    USD perche il campo e vuoto e un'ipotesi presentata come un fatto."""
    _stock(db, "IGN", 1_000_000_000, "ZZZ")
    riga = _rows(client, q="IGN")[0]
    assert riga["market_cap_usd"] is None
    assert riga["market_cap"] == 1_000_000_000


def test_lo_sconosciuto_finisce_in_fondo_in_ENTRAMBI_i_versi(client, db):
    """Sconosciuto non e zero, e zero sarebbe per giunta un valore vero."""
    _stock(db, "IGN", 1_000_000_000, "ZZZ")
    _stock(db, "NVDA", 3_000_000_000_000, "USD")
    _stock(db, "TINY", 1_000_000, "USD")
    for verso in ("asc", "desc"):
        ordinati = [r["ticker"] for r in _rows(client, sort_by="market_cap", sort_dir=verso)]
        assert ordinati[-1] == "IGN", f"{verso}: {ordinati}"


def test_le_pence_usano_il_tasso_della_sterlina_non_diviso_cento(client, db):
    """`GBp` e un'ETICHETTA sulla stessa cifra: il valore e gia nell'unita
    maggiore, e ridividere per cento sarebbe il bug x100 al contrario."""
    _stock(db, "SHEL.L", 196_000_000_000, "GBp")
    _stock(db, "SHEL2.L", 196_000_000_000, "GBP")
    righe = {r["ticker"]: r["market_cap_usd"] for r in _rows(client, q="SHEL")}
    assert righe["SHEL.L"] == pytest.approx(righe["SHEL2.L"], rel=1e-9)


def test_il_path_della_lista_non_chiama_mai_la_rete(client, db, monkeypatch):
    """⚠️ `_get_rate` fa una chiamata yfinance su cache fredda. Su una lista e
    inaccettabile, ed e la stessa regola del calendario e delle trimestrali."""
    fx_service.clear_cache()
    chiamate = []
    monkeypatch.setattr(fx_service, "_fetch_live_rate",
                        lambda c: chiamate.append(c) or None)
    _stock(db, "005930.KS", 300_000_000_000_000, "KRW")
    _stock(db, "0005.HK", 2_860_000_000_000, "HKD")
    righe = _rows(client, sort_by="market_cap", sort_dir="desc")
    assert len(righe) == 2
    assert chiamate == [], f"la lista ha innescato un fetch FX: {chiamate}"
    # e converte comunque, con la tabella di riserva
    assert all(r["market_cap_usd"] is not None for r in righe)
