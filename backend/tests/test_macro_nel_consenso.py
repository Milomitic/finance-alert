"""Attuale, previsto e precedente nella STESSA unita' (2026-10-06).

A schermo stava «Attuale 334.1 · Previsto 0.6 · Precedente 332.8»: il livello
FRED dell'indice CPI accanto alla variazione mensile del consenso."""
from datetime import date

import pytest

from app.services.calendar_service import valori_nel_consenso

# I livelli FRED veri del CPI (CPIAUCSL), luglio e agosto 2026, piu' giugno.
STORIA = [(date(2026, 6, 1), 331.5), (date(2026, 7, 1), 332.813), (date(2026, 8, 1), 334.131)]


def test_prima_dell_uscita_attuale_e_l_ultima_release_e_precedente_dai_livelli() -> None:
    attuale, previsto, precedente, formato = valori_nel_consenso(
        "CPI m/m", "0.6%", "", "0.4%", "index", STORIA)
    assert (attuale, previsto, formato) == (0.4, 0.6, "%")
    # La release di prima: luglio su giugno, dai livelli.
    assert precedente == pytest.approx((332.813 / 331.5 - 1) * 100)


def test_una_serie_fred_che_non_e_la_stessa_misura_non_da_il_precedente() -> None:
    """Il PPI del 2026-10-11: FRED +0,96% sull'ultimo mese, Forexfactory 0,4%.
    Sono due indici diversi, e il precedente ricavato da FRED sarebbe un numero
    di un'altra misura accanto al consenso."""
    ppi = [(date(2026, 6, 1), 286.0), (date(2026, 7, 1), 285.181), (date(2026, 8, 1), 287.928)]
    attuale, _, precedente, _ = valori_nel_consenso("PPI m/m", "0.5%", "", "0.4%", "index", ppi)
    assert attuale == 0.4
    assert precedente is None


def test_uscito_il_dato_attuale_e_il_dato_e_precedente_il_previous() -> None:
    assert valori_nel_consenso("CPI m/m", "0.6%", "0.3%", "0.4%", "index", STORIA) == (0.3, 0.6, 0.4, "%")


def test_nfp_resta_nella_scala_in_cui_e_scritto() -> None:
    """«212K» e' 212 in migliaia, non 212.000 accanto a un 150 di FRED."""
    attuale, previsto, precedente, formato = valori_nel_consenso(
        "Non-Farm Employment Change", "150K", "", "212K", "level", [(date(2026, 8, 1), 159_000.0)])
    assert (attuale, previsto, formato) == (212.0, 150.0, "K")
    # ⚠️ Niente conti sui livelli fuori dalle m/m: la differenza di PAYEMS e'
    # in migliaia e il consenso in K, un precedente calcolato sbaglierebbe.
    assert precedente is None


def test_una_y_y_non_si_inventa_il_precedente() -> None:
    assert valori_nel_consenso("CPI y/y", "2.9%", "", "3.0%", "index", STORIA)[2] is None


def test_un_tasso_resta_un_tasso() -> None:
    assert valori_nel_consenso("Federal Funds Rate", "3.75%", "", "4.00%", "pct", []) == (4.0, 3.75, None, "%")
