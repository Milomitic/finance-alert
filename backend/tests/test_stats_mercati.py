"""FA-184/185: rendimenti per periodo, calendario mensile e cali, i tre
calcoli condivisi da Mercati e Studio."""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.stats import calendario as cal
from app.stats import drawdown as dd
from app.stats import rendimenti as rd


def _feriali(dal: date, n: int) -> list[date]:
    out, g = [], dal
    while len(out) < n:
        if g.weekday() < 5:
            out.append(g)
        g += timedelta(days=1)
    return out


# ── rendimenti ──────────────────────────────────────────────────────────────

def test_ytd_parte_dall_ultima_chiusura_dell_anno_prima():
    d = [date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 2), date(2026, 6, 1)]
    r = rd.rendimenti_per_periodo(d, [90.0, 100.0, 101.0, 120.0])
    assert r["ytd"] == pytest.approx(0.20)


def test_un_periodo_che_comincia_di_sabato_parte_dal_venerdi():
    d = [date(2026, 11, 20), date(2026, 11, 23), date(2026, 11, 27)]  # ven, lun, ven
    r = rd.rendimenti_per_periodo(d, [100.0, 50.0, 110.0])
    # 1 settimana prima del 27 e' il 20: base 100
    assert r["1s"] == pytest.approx(0.10)


def test_storia_piu_corta_del_periodo_rende_none_non_zero():
    d = _feriali(date(2026, 6, 1), 60)
    r = rd.rendimenti_per_periodo(d, [100.0] * 60)
    assert r["1m"] == 0.0
    assert r["1a"] is None and r["5a"] is None and r["5a_ann"] is None and r["ytd"] is None


def test_annualizzato():
    d = [date(2021, 1, 4), date(2026, 1, 5)]
    r = rd.rendimenti_per_periodo(d, [100.0, 200.0])
    assert r["5a"] == pytest.approx(1.0)
    assert r["5a_ann"] == pytest.approx(2 ** (1 / 5) - 1)


def test_volatilita_di_una_serie_costante_e_zero_e_le_cripto_usano_365():
    assert rd.volatilita_annua([100.0] * 30, 20) == 0.0
    c = [100.0 * (1.01 if i % 2 else 0.99) ** 1 for i in range(30)]
    v252, v365 = rd.volatilita_annua(c, 20), rd.volatilita_annua(c, 20, 365)
    assert v365 / v252 == pytest.approx(math.sqrt(365 / 252))
    assert rd.volatilita_annua([100.0] * 5, 20) is None


def test_distanza_dal_massimo_e_dal_minimo():
    d = _feriali(date(2026, 1, 1), 5)
    c = [100.0, 120.0, 90.0, 80.0, 96.0]
    m = rd.distanza_dal_massimo(d, c)
    assert m["valore"] == 120.0 and m["distanza"] == pytest.approx(-0.2) and m["sedute_da"] == 3
    n = rd.distanza_dal_minimo(d, c, sedute=3)
    assert n["valore"] == 80.0 and n["distanza"] == pytest.approx(0.2)


def test_la_ema_e_quella_dell_indicatore():
    import pandas as pd

    from app.indicators.ema import ema

    c = [float(100 + (i % 7)) for i in range(250)]
    assert rd.ema_ultima(c, 200) == pytest.approx(float(ema(pd.Series(c), 200).iloc[-1]))
    assert rd.ema_ultima(c[:50], 200) is None


# ── calendario ──────────────────────────────────────────────────────────────

def test_il_mese_e_da_fine_mese_a_fine_mese():
    d = [date(2025, 12, 31), date(2026, 1, 15), date(2026, 1, 30), date(2026, 2, 27)]
    c = cal.calendario_mensile(d, [100.0, 80.0, 110.0, 121.0])
    riga = c["anni"][0]
    assert riga["anno"] == 2026 and riga["parziale"] is True
    assert riga["mesi"][0] == pytest.approx(0.10) and riga["mesi"][1] == pytest.approx(0.10)
    assert riga["anno_totale"] == pytest.approx(0.21)
    assert c["ultimo_mese"] == "2026-02"


def test_un_mese_senza_sedute_non_inventa_un_rendimento_a_cavallo():
    d = [date(2026, 1, 30), date(2026, 3, 31)]   # febbraio assente
    assert cal.rendimenti_mensili(d, [100.0, 120.0]) == {}


def test_media_e_positivi_per_mese():
    d, c = [], []
    for a in (2023, 2024, 2025):
        d += [date(a - 1, 12, 31), date(a, 1, 31)]
        c += [100.0, 110.0 if a != 2024 else 95.0]
    out = cal.calendario_mensile(d, c)
    assert out["casi_mesi"][0] == 3
    assert out["positivi_mesi"][0] == pytest.approx(2 / 3)


# ── cali ────────────────────────────────────────────────────────────────────

def test_un_calo_recuperato_e_uno_aperto():
    d = _feriali(date(2026, 1, 1), 9)
    c = [100.0, 80.0, 70.0, 90.0, 100.0, 105.0, 95.0, 84.0, 90.0]
    ep = dd.episodi(d, c, soglia=0.10)
    assert len(ep) == 2
    aperto, chiuso = ep
    assert chiuso["profondita"] == pytest.approx(-0.30) and chiuso["recupero"] == d[4].isoformat()
    assert chiuso["sedute_discesa"] == 2 and chiuso["sedute_recupero"] == 2
    assert aperto["recupero"] is None and aperto["profondita"] == pytest.approx(84 / 105 - 1)


def test_sotto_soglia_non_e_un_episodio_e_una_serie_che_sale_non_ha_cali():
    d = _feriali(date(2026, 1, 1), 4)
    assert dd.episodi(d, [100.0, 95.0, 101.0, 102.0], soglia=0.10) == []
    assert dd.calo_massimo(d, [1.0, 2.0, 3.0, 4.0])["profondita"] == 0.0


def test_calo_massimo_e_corrente():
    d = _feriali(date(2026, 1, 1), 6)
    c = [100.0, 50.0, 100.0, 120.0, 108.0, 110.0]
    m = dd.calo_massimo(d, c)
    assert m["profondita"] == pytest.approx(-0.5) and m["recupero"] == d[2].isoformat()
    corr = dd.calo_corrente(d, c)
    assert corr["profondita"] == pytest.approx(110 / 120 - 1) and corr["sedute_dal_picco"] == 2
    assert dd.calo_massimo(d, c, sedute=3)["profondita"] == pytest.approx(-0.10)
