"""Quanta parte del bilancio mostrato esiste davvero (FA-156).

⚠️ GEMELLO di `frontend/src/lib/confidenza.ts::completezzaFondamentali`, ed e'
la stessa regola per costruzione: i due leggono
`frontend/src/lib/completezzaVectors.json` nei rispettivi test. Qui serve
allo screener, che pagina sul server e non puo' filtrare nel client; la scheda
fondamentali continua a calcolarla nel browser sul payload che ha gia'.

La regola, e le sue ragioni, stanno nel docstring del gemello: bilancio
annuale sempre (quattro anni, tre valori l'anno), trimestrali e risultati solo
se la sezione esiste, dei risultati solo quelli passati.
"""
from __future__ import annotations

from datetime import date

from app.services import stock_fundamentals_service as sfs

ANNI_ATTESI = 4
RIGHE_RECENTI = 4
#: La soglia della scheda fondamentali (`CONFIDENZA_BASSA_FONDAMENTALI`).
SOGLIA_COMPLETI = 90


def completezza(annual, quarterly, earnings, oggi: str) -> int | None:
    """Percentuale intera, o None se non c'e' nessun dato. Pura."""
    annual = sorted(annual, key=lambda r: r.fiscal_year_end, reverse=True)[:ANNI_ATTESI]
    quarterly = sorted(quarterly, key=lambda r: r.fiscal_quarter_end, reverse=True)[:RIGHE_RECENTI]
    passati = sorted((e for e in earnings if e.date[:10] <= oggi),
                     key=lambda e: e.date, reverse=True)[:RIGHE_RECENTI]
    if not annual and not quarterly and not passati:
        return None

    def c(v) -> int:
        return 1 if v is not None else 0

    presenti = sum(c(r.revenue) + c(r.net_income) + c(r.eps) for r in annual)
    attesi = ANNI_ATTESI * 3
    if quarterly:
        presenti += sum(c(r.revenue) + c(r.eps) for r in quarterly)
        attesi += len(quarterly) * 2
    if passati:
        presenti += sum(c(e.eps_estimate) + c(e.eps_reported) for e in passati)
        attesi += len(passati) * 2
    # Arrotondamento come Math.round del gemello: meta' verso l'alto.
    return int(presenti / attesi * 100 + 0.5)


def titoli_completi(tickers: set[str], *, oggi: date | None = None) -> set[str]:
    """I ticker con la completezza sopra la soglia, dalla sola cache."""
    giorno = (oggi or date.today()).isoformat()
    out = set()
    for t in tickers:
        f = sfs._CACHE.get(t)
        if f is None:
            continue
        v = completezza(f.annual, f.quarterly, f.earnings, giorno)
        if v is not None and v >= SOGLIA_COMPLETI:
            out.add(t)
    return out
