"""I parser di Dataroma su pagine VERE (FA-107).

Le fixture sono pagine reali di dataroma.com scaricate il 2026-09-28 e ridotte
all'intestazione del portafoglio e alla tabella, con alcune righe per ogni tipo
di attivita'. Un parser di pagine altrui si rompe in SILENZIO quando la pagina
cambia — come il catalogo del Dow Jones (FA-103) — e nessuno di questi era mai
stato eseguito da un test.

Eseguiti la prima volta hanno trovato due difetti, entrambi a schermo:

- il valore totale non si leggeva MAI: la pagina scrive «Portfolio value:», il
  parser cercava «total value». In produzione 226 depositi su 357 — tutti
  quelli di Dataroma, cioe' i superinvestor — avevano il totale vuoto;
- «Buy», che su Dataroma e' una posizione NUOVA nel trimestre, finiva in
  «hold»: «Le mosse che contano» conta come acquisti solo `new` e `add`, quindi
  le posizioni nuove dei superinvestor non comparivano mai fra gli acquisti.
"""
from datetime import date
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from app.services import institutional_scraper as s

FIXTURE = Path(__file__).parent / "fixtures" / "dataroma"


def _html(nome: str) -> str:
    return (FIXTURE / nome).read_text(encoding="utf-8")


def _soup(nome: str) -> BeautifulSoup:
    return BeautifulSoup(_html(nome), "html.parser")


def _righe(nome: str) -> dict[str, s.ScrapedHolding]:
    righe = list(s._parse_holdings_rows(_soup(nome)))
    # Il pavimento: un parser che non trova la tabella renderebbe vero di
    # niente ogni asserzione sulle singole righe.
    assert len(righe) >= 7, f"{nome}: lette solo {len(righe)} righe"
    return {r.ticker: r for r in righe}


# ── intestazione del portafoglio ──────────────────────────────────────────


@pytest.mark.parametrize("nome", ["holdings_brk.html", "holdings_psc.html"])
def test_la_data_del_trimestre(nome: str) -> None:
    assert s._parse_period_end(_soup(nome)) == date(2026, 6, 30)


@pytest.mark.parametrize(
    ("nome", "totale"),
    [("holdings_brk.html", 299_253_558_000), ("holdings_psc.html", 19_465_694_000)],
)
def test_il_valore_totale_si_legge_da_portfolio_value(nome: str, totale: int) -> None:
    assert s._parse_total_value(_soup(nome)) == totale


def test_il_totale_accetta_ancora_la_vecchia_etichetta() -> None:
    soup = BeautifulSoup("<p>Total Value: $1.5B</p>", "html.parser")
    assert s._parse_total_value(soup) == 1_500_000_000


def test_il_totale_non_prende_un_importo_che_non_segue_l_etichetta() -> None:
    """Un contenitore esterno contiene il testo di tutta la pagina: il numero
    va preso DOPO l'etichetta, non il primo importo che capita."""
    soup = BeautifulSoup(
        "<div><p>Prezzo: $12.00</p><p>Portfolio value: <span>$2,000,000</span></p></div>",
        "html.parser",
    )
    assert s._parse_total_value(soup) == 2_000_000


# ── righe ─────────────────────────────────────────────────────────────────


def test_una_riga_porta_quantita_valore_e_peso() -> None:
    aapl = _righe("holdings_brk.html")["AAPL"]
    assert aapl.company_name == "Apple Inc."
    assert aapl.shares == 227_917_808
    assert aapl.value_usd == 65_950_296_000
    assert aapl.portfolio_pct == 22.04


def test_buy_e_una_posizione_nuova() -> None:
    righe = _righe("holdings_psc.html")
    for ticker in ("V", "MA"):
        assert righe[ticker].action == "new", ticker
        # Una posizione nuova non ha una variazione sul trimestre prima.
        assert righe[ticker].qoq_change_pct is None
    assert _righe("holdings_brk.html")["DHI"].action == "new"


def test_add_e_reduce_portano_la_variazione_col_segno() -> None:
    righe = _righe("holdings_brk.html")
    assert (righe["GOOGL"].action, righe["GOOGL"].qoq_change_pct) == ("add", 45.24)
    assert (righe["BAC"].action, righe["BAC"].qoq_change_pct) == ("reduce", -5.89)


def test_attivita_vuota_e_una_posizione_invariata() -> None:
    """Colonna presente e cella vuota: la posizione non e' cambiata nel
    trimestre, che e' `hold` — la stessa etichetta del percorso SEC."""
    assert _righe("holdings_brk.html")["AAPL"].action == "hold"
    assert _righe("holdings_psc.html")["SEG"].action == "hold"


def test_senza_la_colonna_attivita_l_azione_resta_ignota() -> None:
    """Se la pagina smette di avere la colonna, NON si inventa «hold»: non
    sapere e' diverso da sapere che non e' cambiato niente."""
    soup = _soup("holdings_psc.html")
    tabella = s._largest_table(soup)
    for riga in tabella.find_all("tr"):
        celle = riga.find_all(["th", "td"])
        if len(celle) > 3:
            celle[3].decompose()
    righe = list(s._parse_holdings_rows(soup))
    assert len(righe) >= 7
    assert {r.action for r in righe} == {None}


# ── indice dei gestori e percorso completo ────────────────────────────────


def test_l_indice_dei_gestori_toglie_i_doppioni_e_separa_il_gestore(monkeypatch) -> None:
    monkeypatch.setattr(s, "_http_get", lambda url: _html("managers.html"))
    gestori = s.scrape_managers_index()

    assert len(gestori) == 6
    assert len({g.code for g in gestori}) == 6
    roepers = next(g for g in gestori if g.manager_name == "Alex Roepers")
    assert roepers.name == "Atlantic Investment Management"
    assert roepers.source_url.startswith("https://www.dataroma.com/")
    assert roepers.slug == roepers.code.lower()


def test_un_portafoglio_intero_dalla_pagina(monkeypatch) -> None:
    monkeypatch.setattr(s, "_http_get", lambda url: _html("holdings_brk.html"))
    deposito = s.scrape_portfolio("BRK")

    assert deposito is not None
    assert deposito.period_end_date == date(2026, 6, 30)
    assert deposito.total_value_usd == 299_253_558_000
    assert len(deposito.holdings) == 7


def test_una_pagina_che_non_arriva_non_e_un_portafoglio_vuoto(monkeypatch) -> None:
    monkeypatch.setattr(s, "_http_get", lambda url: None)
    assert s.scrape_portfolio("BRK") is None
    assert s.scrape_managers_index() == []


def test_un_errore_su_un_gestore_non_ferma_gli_altri(monkeypatch) -> None:
    def scarica(code: str):
        if code == "B":
            raise RuntimeError("pagina rotta")
        return s.ScrapedFiling(code=code, period_end_date=None, total_value_usd=None)

    monkeypatch.setattr(s, "scrape_portfolio", scarica)
    gestori = [s.ScrapedManager(code=c, slug=c.lower(), name=c) for c in ("A", "B", "C")]
    esiti = s.scrape_all_portfolios(gestori, delay_sec=0)

    assert [(m.code, f is not None) for m, f in esiti] == [("A", True), ("B", False), ("C", True)]


# ── numeri ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("testo", "atteso"),
    [("$1,234,567", 1_234_567), ("$1.5B", 1_500_000_000), ("$250K", 250_000), ("", None), ("n/d", None)],
)
def test_importi(testo: str, atteso: int | None) -> None:
    assert s._parse_money(testo) == atteso


@pytest.mark.parametrize(("testo", "atteso"), [("22.04", 22.04), ("0,69", 0.69), ("", None)])
def test_percentuali(testo: str, atteso: float | None) -> None:
    assert s._parse_pct(testo) == atteso
