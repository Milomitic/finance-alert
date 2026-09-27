"""I KPI multi-timeframe della pagina titolo (FA-107).

`compute_timeframe_kpis` riduce gli indicatori di ogni timeframe (30m, 1h,
giornaliero, settimanale, mensile) all'ultima lettura e a un giudizio
composto, e la tabella di confronto della pagina titolo li mostra. Non era
mai stato eseguito da un test.

Le soglie si provano con un bundle costruito a mano, cosi' ogni confine e'
esatto; tre serie vere passano poi dal calcolo reale degli indicatori.
Scrivendoli e' emerso un difetto: su una serie PIATTA il prezzo e' uguale alle
medie, «sopra» risultava falso e contava come «sotto», e un titolo fermo — per
esempio sotto offerta pubblica — veniva etichettato ribassista.
"""
from datetime import date, timedelta

import pytest

from app.services import timeframe_service as tf
from app.services.timeframe_service import (
    Bar,
    IndicatorBundle,
    IndicatorPoint,
    compute_timeframe_kpis,
)


def _barre(prezzi: list[float]) -> list[Bar]:
    inizio = date(2025, 1, 1)
    return [
        Bar(date=inizio + timedelta(days=i), open=p, high=p, low=p, close=p, volume=1000)
        for i, p in enumerate(prezzi)
    ]


def _bundle(*, rsi=None, ema20=None, ema50=None, ema200=None,
            bb=(None, None, None), macd_hist=None) -> IndicatorBundle:
    giorno = date(2026, 9, 25)

    def serie(v):
        return [IndicatorPoint(giorno, v)] if v is not None else []

    return IndicatorBundle(
        ema20=serie(ema20), ema50=serie(ema50), ema200=serie(ema200), rsi14=serie(rsi),
        bb_upper=serie(bb[0]), bb_middle=serie(bb[1]), bb_lower=serie(bb[2]),
        macd_line=serie(0.0), macd_signal=serie(0.0), macd_hist=serie(macd_hist),
    )


@pytest.fixture
def kpi(monkeypatch):
    def calcola(ultimo: float = 100.0, **indicatori):
        monkeypatch.setattr(tf, "compute_bundle", lambda bars: _bundle(**indicatori))
        return compute_timeframe_kpis(_barre([ultimo]), "1d")
    return calcola


# ── soglie ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("rsi", "tono"),
    [(29.99, "oversold"), (30.0, "neutral"), (70.0, "neutral"), (70.01, "overbought"), (None, "neutral")],
)
def test_i_confini_dell_rsi(kpi, rsi, tono) -> None:
    assert kpi(rsi=rsi).rsi_tone == tono


@pytest.mark.parametrize(
    ("hist", "tono"), [(0.01, "bullish"), (0.0, "neutral"), (-0.01, "bearish"), (None, "neutral")],
)
def test_il_tono_del_macd(kpi, hist, tono) -> None:
    assert kpi(macd_hist=hist).macd_tone == tono


@pytest.mark.parametrize(
    ("indicatori", "punteggio", "etichetta"),
    [
        # sopra entrambe le medie, MACD positivo, RSI in ipervenduto: tutti a favore
        (dict(ema20=90, ema50=90, macd_hist=1, rsi=25), 4, "very_bullish"),
        (dict(ema20=90, ema50=90, macd_hist=1), 3, "very_bullish"),
        (dict(ema20=90, ema50=90), 2, "bullish"),
        (dict(ema20=90), 1, "bullish"),
        (dict(), 0, "neutral"),
        (dict(ema20=110), -1, "bearish"),
        (dict(ema20=110, ema50=110), -2, "bearish"),
        (dict(ema20=110, ema50=110, macd_hist=-1), -3, "very_bearish"),
        (dict(ema20=110, ema50=110, macd_hist=-1, rsi=75), -4, "very_bearish"),
    ],
)
def test_punteggio_ed_etichetta(kpi, indicatori, punteggio, etichetta) -> None:
    k = kpi(100.0, **indicatori)
    assert (k.composite_score, k.composite_label) == (punteggio, etichetta)


def test_il_prezzo_sulla_media_non_e_sotto(kpi) -> None:
    """Il difetto trovato: uguale non e' «sotto». Senza la correzione questo
    rendeva -2 e «bearish» per un titolo semplicemente fermo."""
    k = kpi(100.0, ema20=100.0, ema50=100.0, ema200=100.0)
    assert (k.ema20_above, k.ema50_above, k.ema200_above) == (None, None, None)
    assert (k.composite_score, k.composite_label) == (0, "neutral")


def test_la_posizione_nelle_bande_esce_da_zero_uno(kpi) -> None:
    """Dentro la banda e' una frazione; fuori la banda vale meno di 0 o piu' di
    1, e il frontend lo sa (TechnicalKpiCard). Una banda senza ampiezza non ha
    una posizione."""
    assert kpi(105.0, bb=(110.0, 100.0, 90.0)).bb_position == pytest.approx(0.75)
    assert kpi(115.0, bb=(110.0, 100.0, 90.0)).bb_position == pytest.approx(1.25)
    assert kpi(85.0, bb=(110.0, 100.0, 90.0)).bb_position == pytest.approx(-0.25)
    assert kpi(100.0, bb=(100.0, 100.0, 100.0)).bb_position is None


def test_senza_barre_niente_letture() -> None:
    k = compute_timeframe_kpis([], "1w")
    assert (k.bars, k.last_close, k.rsi, k.composite_label) == (0, None, None, "neutral")


# ── serie vere, dal calcolo reale degli indicatori ────────────────────────


def test_una_salita_che_accelera() -> None:
    k = compute_timeframe_kpis(_barre([100 * 1.01 ** i for i in range(260)]), "1d")
    assert (k.ema20_above, k.ema50_above, k.ema200_above) == (True, True, True)
    assert k.macd_tone == "bullish"
    # Nessuna seduta in calo: RSI al massimo, cioe' ipercomprato, che toglie un
    # punto — la scelta dichiarata nel tipo («frena un rialzo surriscaldato»).
    assert k.rsi_tone == "overbought"
    assert (k.composite_score, k.composite_label) == (2, "bullish")


def test_una_discesa_che_accelera() -> None:
    """⚠️ Accelera in valore ASSOLUTO: il MACD si misura in unita' di prezzo.
    Una discesa a percentuale costante (100·0,99^i) perde sempre MENO in
    assoluto, il MACD risale verso zero e il suo istogramma e' positivo — il
    primo tentativo di questo test lo pretendeva ribassista, ed era il test a
    sbagliare."""
    k = compute_timeframe_kpis(_barre([200 - 0.002 * i * i for i in range(260)]), "1d")
    assert (k.ema20_above, k.ema50_above, k.ema200_above) == (False, False, False)
    assert (k.macd_tone, k.rsi_tone) == ("bearish", "oversold")
    assert (k.composite_score, k.composite_label) == (-2, "bearish")


def test_una_serie_piatta_e_neutra() -> None:
    k = compute_timeframe_kpis(_barre([50.0] * 260), "1d")
    assert k.last_close == 50.0
    assert (k.composite_score, k.composite_label) == (0, "neutral")
