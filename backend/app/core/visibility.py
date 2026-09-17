"""Single source of truth for "stocks hidden from user-facing surfaces".

These countries are seeded into the catalog so they contribute to the
dashboard breadth row + Asia market-mood aggregation in
`market_stats_service._load_metrics`, but the user explicitly opted
out of trading / tracking them individually:

- Search / autocomplete
- Screener
- Stock detail page (deep links return 404)
- Alert generation (scan service skips them)
- Movers list (gainers / losers)
- Treemap
- Sectors heatmap
- Top picks score-rank lists

The metrics pipeline (`_load_metrics`) intentionally does NOT consult
this set — that's how the breadth + mood signal still see the hidden
stocks, while every consumer that exposes individual rows to the user
filters them.

Adding/removing a country here changes the visibility cutoff for the
whole app from one place.
"""
from __future__ import annotations

from sqlalchemy import or_

from app.models import Stock

# ISO-2 country codes whose stocks are catalog-only (metrics) and
# never surfaced individually in the UI.
HIDDEN_COUNTRIES: frozenset[str] = frozenset({"CN", "JP", "KR"})

# Listings on these exchanges are ALWAYS surfaced regardless of domicile,
# overriding the country-based hide:
#   - US (NASDAQ / NYSE / NYSE Arca): a CN/JP company trading as a US ADR
#     (BIDU, PDD, TM, LI, DQ, ...) is liquid and individually tradable.
#   - HK (HKEX): the user's watchlist holds Hong Kong-listed Chinese names
#     (9988.HK Alibaba, 0700.HK Tencent, 3690.HK Meituan, ...) imported from
#     eToro — they must be navigable AND signal-generating. Mainland China
#     (SSE/SZSE), Tokyo (JPX) and Korea (KRX) listings stay breadth-only.
# Exchange labels match the catalog convention (see catalog_refresh_service /
# source_catalog). This is the standing rule: "le stock cinesi quotate ...
# devono essere visibili e generare segnali".
SURFACED_EXCHANGES: frozenset[str] = frozenset({"NASDAQ", "NYSE", "NYSE Arca", "HKEX"})

# Singoli titoli esposti NONOSTANTE la loro borsa sia breadth-only, richiesti
# dall'utente uno per uno (2026-09-17). Samsung e SK Hynix sono in catalogo da
# sempre con dieci anni di storico, ma stanno su KRX: erano nel motore per
# l'ampiezza e invisibili a ricerca, screener e generazione segnali — che e'
# esattamente come sono state descritte, «non riesco a trovarle dalla barra di
# ricerca».
#
# ⚠️ L'eccezione e' per TICKER e non per paese DI PROPOSITO. Togliere "KR" da
# HIDDEN_COUNTRIES otterrebbe lo stesso risultato per queste due e
# sbloccherebbe anche le altre diciotto KOSPI, che nessuno ha chiesto. Il
# controllo negativo in `tests/test_asia_nel_motore.py` fissa proprio questa
# differenza: se qualcuno "semplifica" verso il paese, quel test diventa rosso.
#
# ⚠️ Questo elenco e' ANCHE il marcatore di non-potabilita': la potatura del
# 2026-06 (1494 -> 1000) e' un'operazione a mano, e la sua regola era «si
# tengono i membri di indice, le scelte a mano e i nomi con un price_alert».
# Un ticker nominato qui e' una scelta a mano esplicita e non va tolto.
SURFACED_TICKERS: frozenset[str] = frozenset({
    "005930.KS",  # Samsung Electronics
    "000660.KS",  # SK Hynix
})


def visible_country_clause():
    """SQLAlchemy WHERE clause: rows whose country is NULL OR not in
    `HIDDEN_COUNTRIES`. NULL-tolerant by design — test fixtures and
    legacy rows without a populated country still flow through.

    Use:
        stmt = stmt.where(visible_country_clause())
    """
    return or_(
        Stock.country.is_(None),
        ~Stock.country.in_(HIDDEN_COUNTRIES),
        # US-listed ADRs + HK-listed names of CN/JP/KR companies stay visible.
        Stock.exchange.in_(SURFACED_EXCHANGES),
        # Singoli titoli esposti a mano, borsa breadth-only compresa.
        Stock.ticker.in_(SURFACED_TICKERS),
    )


def is_visible_country(
    country: str | None,
    exchange: str | None = None,
    ticker: str | None = None,
) -> bool:
    """Python-side equivalent of `visible_country_clause()` for callsites
    that already have a `country` value in memory (e.g. filtering an
    in-memory metrics list before passing to mover/treemap aggregators).

    `exchange`, when supplied, applies the surfaced-exchange exception: a
    stock on NASDAQ / NYSE / NYSE Arca / HKEX is always visible regardless
    of its domicile. `ticker`, when supplied, applies the per-ticker
    exception (`SURFACED_TICKERS`).

    ⚠️ Le due forme della stessa regola vanno tenute in pari: un test le
    confronta caso per caso, perche' due copie divergono al primo ritocco e
    qui la divergenza farebbe sparire un titolo da una superficie sola."""
    if ticker is not None and ticker in SURFACED_TICKERS:
        return True
    if country is None:
        return True
    if exchange is not None and exchange in SURFACED_EXCHANGES:
        return True
    return country.upper() not in HIDDEN_COUNTRIES
