"""Un ticker morto non si chiede a yfinance, e non si presenta come fresco.

⚠️ Il difetto era gia' stato trovato UNA VOLTA e corretto a meta'. Il docstring
di `ohlcv_service.not_quarantined_clause` lo racconta: il 26 agosto 2026 cinque
simboli morti (BK, CTRA, APLS, TERN, VSCO, con serie da 129 a 262 fallimenti)
producevano «circa 2.200 righe di log in 48 ore», e la clausola fu aggiunta al
solo `live_universe_sweep_service`.

I warning sono tornati il 13 settembre — stessi ticker, stesso messaggio —
perche' il difetto non era del chiamante: era che OGNI chiamante doveva
ricordarsene. Screener, dettaglio titolo e pagina mercati chiedono le stesse
quotazioni per conto proprio e nessuno dei tre filtrava. Il guardiano vive ora
nel SERVIZIO, cioe' nell'unico punto da cui passano tutti.

⚠️ E yfinance non aiuta a capirlo: per un simbolo senza dati solleva
`AttributeError: 'PriceHistory' object has no attribute '_dividends'` — un
guasto interno suo, che non nomina il fatto («Yahoo non ha dati per questo
simbolo») e che il contatore di salute non riconosce come fallimento. Quindi
il WARNING si ripeteva ogni quindici secondi e nessun cruscotto lo contava.
"""

from datetime import date, timedelta

import pytest

from app.models import OhlcvDaily, Stock
from app.services import live_quote_service, ohlcv_service


@pytest.fixture(autouse=True)
def _cache_pulita():
    live_quote_service.reset_quarantena_cache()
    live_quote_service.clear_cache()
    yield
    live_quote_service.reset_quarantena_cache()
    live_quote_service.clear_cache()


def _titolo(db, ticker: str, *, streak: int, ultimo_nodata: date | None,
            ultima_barra: date) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc.")
    s.ohlcv_nodata_streak = streak
    s.ohlcv_last_nodata_at = ultimo_nodata
    db.add(s)
    db.flush()
    for i in range(2):
        db.add(OhlcvDaily(
            stock_id=s.id, date=ultima_barra - timedelta(days=i),
            open=10.0, high=11.0, low=9.0, close=10.0 + i, volume=1_000,
        ))
    db.commit()
    return s


def test_un_ticker_in_quarantena_NON_interroga_yfinance(db, monkeypatch):
    """Il punto: zero chiamate di rete, quindi zero warning."""
    oggi = date.today()
    _titolo(db, "MORTO", streak=ohlcv_service.QUARANTINE_STREAK + 5,
            ultimo_nodata=oggi, ultima_barra=oggi - timedelta(days=60))

    chiamate: list[str] = []

    class _Ticker:
        def __init__(self, t):
            chiamate.append(t)

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", _Ticker)

    q = live_quote_service._fetch_fresh("MORTO")
    assert chiamate == [], f"yfinance e' stato interrogato lo stesso: {chiamate}"
    assert q.price is not None, "deve comunque servire l'ultima barra nota"


def test_e_la_presenta_come_STALE_non_come_CLOSED(db):
    """⚠️ Un prezzo di due mesi fa etichettato «mercato chiuso» sembra la
    chiusura di ieri.

    CLAUDE.md non lascia margini: un prezzo ripristinato non deve MAI
    presentarsi come vivo. `CLOSED` e' lo stato normale di un mercato chiuso;
    `STALE` e' quello che dice al lettore che il dato non e' stato rinfrescato.
    """
    oggi = date.today()
    vecchia = oggi - timedelta(days=60)
    _titolo(db, "MORTO2", streak=99, ultimo_nodata=oggi, ultima_barra=vecchia)

    q = live_quote_service._fetch_fresh("MORTO2")
    assert q.market_state == "STALE"
    assert q.as_of_date == vecchia.isoformat(), (
        "la data della barra servita deve viaggiare col prezzo, o il lettore "
        "non ha modo di sapere quanto e' vecchio"
    )


def test_un_ticker_VIVO_viene_interrogato(db, monkeypatch):
    """⚠️ Il controllo negativo, e senza di esso i due test sopra passerebbero
    anche con un guardiano che blocca TUTTO."""
    oggi = date.today()
    _titolo(db, "VIVO", streak=0, ultimo_nodata=None, ultima_barra=oggi)

    chiamate: list[str] = []

    class _Ticker:
        def __init__(self, t):
            chiamate.append(t)
            raise RuntimeError("basta sapere che e' stato chiamato")

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", _Ticker)

    live_quote_service._fetch_fresh("VIVO")
    assert chiamate == ["VIVO"]


def test_un_ticker_ri_sondabile_torna_interrogabile(db, monkeypatch):
    """La quarantena SCADE, e il servizio deve rispettarne anche quella meta'.

    `REPROBE_DAYS` esiste perche' un simbolo puo' tornare (re-listing, migrazione
    di borsa, singhiozzo di yfinance). Un guardiano che guarda solo la serie e
    non la data trasformerebbe una quarantena in una condanna.
    """
    oggi = date.today()
    scaduta = oggi - timedelta(days=ohlcv_service.REPROBE_DAYS + 1)
    _titolo(db, "RISORTO", streak=99, ultimo_nodata=scaduta, ultima_barra=oggi)

    chiamate: list[str] = []

    class _Ticker:
        def __init__(self, t):
            chiamate.append(t)
            raise RuntimeError("interrogato")

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", _Ticker)

    live_quote_service._fetch_fresh("RISORTO")
    assert chiamate == ["RISORTO"], (
        "un ticker oltre la finestra di ri-sonda deve tornare interrogabile"
    )


def test_la_regola_e_LETTA_da_ohlcv_service_non_riscritta(db):
    """⚠️ Due copie di una regola in due moduli sono la forma che diverge.

    `ohlcv_service` e' proprietario unico della quarantena e lo dichiara nel
    proprio docstring. Questo test lo verifica dal comportamento: spostando la
    SOGLIA del proprietario, il servizio delle quotazioni deve cambiare idea
    insieme a lui — cosa impossibile se avesse una costante propria.
    """
    oggi = date.today()
    _titolo(db, "LIMITE", streak=2, ultimo_nodata=oggi, ultima_barra=oggi)

    # Con la soglia di serie a 3, una serie di 2 NON e' in quarantena.
    assert "LIMITE" not in live_quote_service._ticker_in_quarantena()

    # Abbassando la soglia del proprietario a 2, deve entrarci.
    live_quote_service.reset_quarantena_cache()
    originale = ohlcv_service.QUARANTINE_STREAK
    try:
        ohlcv_service.QUARANTINE_STREAK = 2
        assert "LIMITE" in live_quote_service._ticker_in_quarantena()
    finally:
        ohlcv_service.QUARANTINE_STREAK = originale


def test_la_cache_della_quarantena_ha_una_scadenza():
    """Non e' un dettaglio di prestazioni: senza TTL la quarantena verrebbe
    letta a ogni quotazione, cioe' una query ogni quindici secondi per ticker;
    con un TTL infinito un simbolo tornato in vita resterebbe muto fino al
    riavvio del processo."""
    assert 60 <= live_quote_service._QUARANTENA_TTL <= 3600
