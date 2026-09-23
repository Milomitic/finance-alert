"""Il contesto del titolo fissato all'emissione di un alert.

⚠️ La proprieta' che conta di piu' non e' il valore di una variabile: e' che il
numero NON dipenda da quanta storia si passa. Lo scan passa 260 barre; chi
ricalcola all'indietro, o addestra un modello, puo' averne duemila. Se le due
letture differissero, il modello imparerebbe su numeri che il motore vivo non
produce.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from app.signals.contesto_emissione import VERSIONE, contesto


def _serie(n: int, seme: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seme)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.018, n)))
    o = c * (1 + rng.normal(0, 0.004, n))
    h = np.maximum(c, o) * (1 + np.abs(rng.normal(0, 0.008, n)))
    lo = np.minimum(c, o) * (1 - np.abs(rng.normal(0, 0.008, n)))
    v = rng.integers(500_000, 2_000_000, n).astype(float)
    date = pd.bdate_range("2018-01-01", periods=n).strftime("%Y-%m-%d")
    return pd.DataFrame({"date": date, "open": o, "high": h, "low": lo, "close": c, "volume": v})


def test_con_storia_sufficiente_ci_sono_tutte_le_variabili() -> None:
    ctx = contesto(_serie(300))
    attese = {"ret_1", "ret_5", "ret_21", "ret_63", "ret_126", "ret_252", "atr_pct",
              "dist_sma20", "dist_sma50", "dist_sma200", "atr_rank", "rsi14",
              "dist_hi252", "dist_lo252", "vol_ratio", "vol20", "log_dollar_vol",
              "range_pos20", "gap"}
    assert attese <= set(ctx)
    assert ctx["versione"] == VERSIONE


def test_il_rendimento_e_quello_delle_chiusure() -> None:
    df = _serie(300)
    ctx = contesto(df)
    atteso = df.close.iloc[-1] / df.close.iloc[-22] - 1
    assert ctx["ret_21"] == pytest.approx(atteso, rel=1e-5)


@pytest.mark.parametrize("chiave", [
    "ret_1", "ret_5", "ret_21", "ret_63", "ret_126", "ret_252", "atr_pct",
    "dist_sma20", "dist_sma50", "dist_sma200", "rsi14", "dist_hi252", "dist_lo252",
    "vol_ratio", "vol20", "log_dollar_vol", "range_pos20", "gap",
])
def test_la_finestra_dello_scan_e_la_storia_intera_danno_lo_stesso_numero(chiave: str) -> None:
    """⚠️ Il motivo per cui le distanze sono dalle medie SEMPLICI.

    Lo scan vede 260 barre; un ricalcolo o un addestramento possono vederne
    duemila. Una EMA200 su 260 barre dipende da dove comincia la serie — il
    controllo negativo qui sotto lo mostra — una SMA200 no."""
    lunga = _serie(2000)
    breve = lunga.iloc[-260:].reset_index(drop=True)
    assert contesto(breve)[chiave] == pytest.approx(contesto(lunga)[chiave], rel=1e-4)


def test_controllo_negativo_una_ema_lunga_DIPENDE_dalla_finestra() -> None:
    """Senza questo il test sopra potrebbe essere vero di niente: se anche una
    EMA200 non distinguesse le due finestre, la scelta della SMA non sarebbe
    dimostrata da nessuna parte."""
    lunga = _serie(2000)
    breve = lunga.iloc[-260:].reset_index(drop=True)
    ema = lambda df: df.close.ewm(span=200, adjust=False).mean().iloc[-1]  # noqa: E731
    assert abs(ema(breve) / ema(lunga) - 1) > 1e-3


def test_con_poca_storia_le_variabili_lunghe_MANCANO_invece_di_valere_zero() -> None:
    """Una chiave assente dice «non noto», uno zero direbbe un valore: un
    titolo con 60 barre non ha un rendimento a un anno."""
    ctx = contesto(_serie(60))
    for chiave in ("ret_63", "ret_126", "ret_252", "dist_sma200", "dist_hi252", "dist_lo252"):
        assert chiave not in ctx
    assert "ret_21" in ctx


def test_niente_valori_non_finiti() -> None:
    """Un volume a zero farebbe un logaritmo infinito e un rapporto diviso per
    zero: nello snapshot finirebbe un `Infinity` che il JSON standard non
    ammette. Si omette la chiave."""
    df = _serie(300)
    df.loc[df.index[-25:], "volume"] = 0.0
    ctx = contesto(df)
    assert "log_dollar_vol" not in ctx
    assert "vol_ratio" not in ctx
    assert all(math.isfinite(x) for k, x in ctx.items() if k != "versione")


def test_una_serie_di_due_barre_non_esplode() -> None:
    ctx = contesto(_serie(2))
    assert ctx["versione"] == VERSIONE
    assert "ret_1" in ctx
