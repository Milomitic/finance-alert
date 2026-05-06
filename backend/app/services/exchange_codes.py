"""Single source of truth per la mappa "suffisso ticker -> codice exchange".

Storicamente questa mappa esisteva duplicata in
`catalog_refresh_service._normalize_ticker` e in
`scripts/dedupe_stocks.canonical_exchange_for`. Le due copie hanno
generato duplicati nella tabella `stocks` quando una vecchia versione
del seed scriveva label leggibili ("Borsa Italiana") e il catalog
refresh scriveva il codice ("BIT"). Centralizzando la mappa qui le
due ingestion non possono più divergere.

Convenzione: i suffissi sono quelli usati da yfinance (es. ".MI" per
Borsa Italiana). Il valore del dict è il codice corto stabile usato
nella colonna `stocks.exchange`, in modo da matchare l'invariante
DB-level `UNIQUE(ticker, exchange)` indipendentemente dalla sorgente
di scrittura.
"""
from __future__ import annotations

# Suffisso ticker (yfinance) -> codice exchange canonico salvato in DB.
SUFFIX_TO_EXCHANGE: dict[str, str] = {
    ".MI": "BIT",      # Borsa Italiana
    ".DE": "XETRA",    # Deutsche Boerse
    ".PA": "EPA",      # Euronext Paris
    ".AS": "AEX",      # Euronext Amsterdam
    ".SW": "SIX",      # Swiss Exchange
    ".CO": "CSE",      # Copenhagen
    ".HE": "HEL",      # Nasdaq Helsinki
    ".BR": "BRU",      # Euronext Brussels
    ".MC": "BME",      # BME Madrid
    ".IR": "ISE",      # Irish Stock Exchange
    ".SS": "SSE",      # Shanghai Stock Exchange
    ".SZ": "SZSE",     # Shenzhen Stock Exchange
    ".HK": "HKEX",     # Hong Kong
    ".T":  "JPX",      # Japan Exchange Group (Tokyo)
    ".KS": "KRX",      # Korea Exchange (KOSPI)
    ".L":  "LSE",      # London Stock Exchange
}


def has_known_suffix(ticker: str) -> bool:
    """True se il ticker termina con un suffisso yfinance noto.

    Quando True, la chiave `(ticker, exchange)` è autoritativa (es.
    "ENEL.MI" è inequivocabilmente Borsa Italiana). Quando False (es.
    "AAPL"), l'exchange è solo il default per-indice scelto dal chiamante
    e potrebbe collidere fra refresh di indici diversi: in quel caso il
    catalog refresh deve fare lookup per `ticker` soltanto, per non
    duplicare la stessa security in più righe.
    """
    t = ticker.strip().upper()
    return any(t.endswith(suffix) for suffix in SUFFIX_TO_EXCHANGE)


def canonical_exchange(ticker: str, default: str) -> str:
    """Restituisce il codice exchange canonico per un ticker.

    Se il ticker termina con un suffisso noto (es. ".MI"), il valore
    mappato vince sempre sul `default`: questo serve a sopprimere
    eventuali label leggibili come "Borsa Italiana" che vivono ancora
    in CSV o in righe DB legacy.

    Per ticker senza suffisso noto (tipicamente US: "AAPL", "MSFT")
    restituisce `default` invariato — non c'è modo di dedurre la
    venue (NASDAQ vs NYSE) dal ticker stesso.
    """
    t = ticker.strip().upper()
    for suffix, exchange in SUFFIX_TO_EXCHANGE.items():
        if t.endswith(suffix):
            return exchange
    return default
