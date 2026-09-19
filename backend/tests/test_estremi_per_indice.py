"""Chi tira e chi frena un indice, dentro la riga di ampiezza.

⚠️ E' una domanda DIVERSA dai Top movers del cruscotto, che ordinano l'intero
catalogo: li' i primi posti sono quasi sempre micro-cap ed ETF a leva, quindi
non dicono niente su come sta andando l'S&P 500. Il perimetro e' l'indice.
"""
from __future__ import annotations

from app.services.market_stats_service import StockMetrics, aggregate_by_index


def _m(ticker: str, cambio: float | None, indici: list[str]) -> StockMetrics:
    return StockMetrics(
        stock_id=abs(hash(ticker)) % 10_000, ticker=ticker, name=f"{ticker} Inc.",
        sector="Tech", index_codes=indici, market_cap=1e9, bars_count=300,
        last_close=100.0, prev_close=100.0, change_pct=cambio,
        ema50=90.0, ema200=80.0, rsi14=50.0, high_252=120.0, low_252=80.0,
        near_52w_high=False, near_52w_low=False, new_52w_high=False,
        new_52w_low=False, vol_today=1000, vol_avg_20=900.0, vol_ratio=1.1,
        has_full_data=True,
    )


def test_tre_per_lato_ordinati_dentro_l_indice() -> None:
    metriche = [
        _m("AAA", 5.0, ["SP500"]), _m("BBB", 3.0, ["SP500"]), _m("CCC", 1.0, ["SP500"]),
        _m("DDD", 0.5, ["SP500"]),
        _m("XXX", -4.0, ["SP500"]), _m("YYY", -2.0, ["SP500"]), _m("ZZZ", -1.0, ["SP500"]),
        # Di un ALTRO indice: non deve comparire fra gli estremi dell'S&P.
        _m("FUORI", 99.0, ["NDX"]),
    ]

    riga = next(r for r in aggregate_by_index(metriche, [("SP500", "S&P 500")]))

    assert [x["ticker"] for x in riga["top_gainers"]] == ["AAA", "BBB", "CCC"]
    assert [x["ticker"] for x in riga["top_losers"]] == ["XXX", "YYY", "ZZZ"]
    assert riga["top_gainers"][0]["change_pct"] == 5.0


def test_un_indice_tutto_in_rosso_non_inventa_titoli_in_salita() -> None:
    """⚠️ Il controllo che conta. Prendere «i primi tre» qualunque cosa siano
    riempirebbe la colonna «su» col meno peggio dei ribassi: una riga che
    dice il contrario di cio' che e' successo, con l'aria di un dato."""
    metriche = [_m("AAA", -1.0, ["SP500"]), _m("BBB", -2.0, ["SP500"])]

    riga = aggregate_by_index(metriche, [("SP500", "S&P 500")])[0]

    assert riga["top_gainers"] == []
    # Il PEGGIORE per primo, come nei gainers il migliore: le due colonne si
    # leggono dall'alto e devono partire entrambe dall'estremo.
    assert [x["ticker"] for x in riga["top_losers"]] == ["BBB", "AAA"]


def test_una_variazione_IGNOTA_resta_fuori_da_entrambe() -> None:
    # «Ignota» non e' «ferma»: un titolo senza quotazione non e' ne' il
    # migliore ne' il peggiore, e contarlo come zero lo metterebbe in mezzo
    # alla classifica come se fosse stato misurato.
    metriche = [_m("AAA", 2.0, ["SP500"]), _m("MUTO", None, ["SP500"])]

    riga = aggregate_by_index(metriche, [("SP500", "S&P 500")])[0]

    assert [x["ticker"] for x in riga["top_gainers"]] == ["AAA"]
    assert riga["top_losers"] == []


def test_un_indice_vuoto_rende_liste_vuote_non_assenti() -> None:
    # La chiave c'e' sempre: un consumatore che fa `.map()` su `undefined`
    # esplode, e il caso «indice senza titoli» e' reale (un paniere che il
    # catalogo non copre ancora).
    riga = aggregate_by_index([], [("SP500", "S&P 500")])[0]

    assert riga["top_gainers"] == []
    assert riga["top_losers"] == []
