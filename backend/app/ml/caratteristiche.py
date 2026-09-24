"""Le variabili dei due modelli in ombra, costruite per NOME.

Un modello salvato porta l'elenco dei nomi con cui e' stato addestrato, e a
previsione il vettore si costruisce da quell'elenco: una variabile aggiunta qui
dopo l'addestramento non sposta le colonne di un modello gia' in servizio, e
una che manca vale NaN (il GBM la manda nel suo bin dedicato) invece di
scivolare nella colonna accanto.

Tutte note alla chiusura del giorno di emissione: il contesto del titolo
(`app.signals.contesto_emissione`, la stessa finestra di 260 barre dello
scan), il detector, la Forza, i fattori e la geometria del piano. Nessuna di
mercato — sono una per data, e lo studio le ha tenute fuori dalla variante
che ha retto alla replica.

Modulo FOGLIA: solo la libreria standard e numpy.
"""
from __future__ import annotations

import math

import numpy as np

#: Le variabili del contesto del titolo, nell'ordine di `contesto_emissione`.
CONTESTO: tuple[str, ...] = (
    "ret_1", "ret_5", "ret_21", "ret_63", "ret_126", "ret_252",
    "atr_pct", "dist_sma20", "dist_sma50", "dist_sma200", "atr_rank", "rsi14",
    "dist_hi252", "dist_lo252", "vol_ratio", "vol20", "log_dollar_vol",
    "range_pos20", "gap",
)

#: Le direzionali, ripetute «nel verso del segnale»: per un segnale ribassista
#: un rendimento negativo e' slancio A FAVORE. Come in `ml_study.prepara`.
_DIREZIONALI: tuple[str, ...] = (
    "ret_1", "ret_5", "ret_21", "ret_63", "ret_126", "ret_252",
    "dist_sma20", "dist_sma50", "dist_sma200", "dist_hi252", "dist_lo252",
    "range_pos20", "gap",
)

_ORIZZONTI = {"short": 0.0, "medium": 1.0, "long": 2.0}


def _f(x: object) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return math.nan
    x = float(x)
    return x if math.isfinite(x) else math.nan


def _derivate_contesto(ctx: dict) -> dict[str, float]:
    out = {k: _f(ctx.get(k)) for k in CONTESTO}
    # La volatilita' da chiusura a chiusura contro quella da escursione: un
    # rapporto che un albero non sa costruire da solo con due tagli.
    v, a = out["vol20"], out["atr_pct"]
    out["vol20_su_atr"] = v / a if (a == a and a > 0 and v == v) else math.nan
    return out


# ─── volatilita' ────────────────────────────────────────────────────────────

def nomi_volatilita() -> list[str]:
    return [*CONTESTO, "vol20_su_atr"]


def riga_volatilita(ctx: dict) -> dict[str, float]:
    """Le variabili del modello di volatilita' per un contesto del titolo."""
    return _derivate_contesto(ctx or {})


# ─── selezione ──────────────────────────────────────────────────────────────

def riga_selezione(
    *, detector: str, tone: str, horizon: str | None, strength: float | None,
    factors: dict | None, ctx: dict | None, stop_atr: float | None, rr: float | None,
) -> dict[str, float]:
    """Le variabili del modello di selezione per UN match, per nome.

    I fattori entrano come `fac_<chiave>` e il detector come `det_<nome>`: chi
    addestra decide quali tenere (quelli presenti in almeno l'1% delle righe),
    e chi prevede li legge dall'elenco del modello.
    """
    sgn = 1.0 if tone == "bull" else -1.0
    out = _derivate_contesto(ctx or {})
    for k in _DIREZIONALI:
        out[f"s_{k}"] = sgn * out[k]
    out["s_rsi"] = sgn * (out["rsi14"] - 50.0)
    out[f"det_{detector}"] = 1.0
    out["bull"] = 1.0 if tone == "bull" else 0.0
    out["hz"] = _ORIZZONTI.get(horizon or "", math.nan)
    out["strength"] = _f(strength)
    out["stop_atr"] = _f(stop_atr)
    out["rr"] = _f(rr)
    for k, v in (factors or {}).items():
        out[f"fac_{k}"] = _f(v)
    return out


def matrice(righe: list[dict[str, float]], nomi: list[str], *, zero_se_manca: tuple[str, ...] = ()) -> np.ndarray:
    """Le righe nell'ordine di `nomi`. Una chiave assente vale NaN — tranne i
    prefissi in `zero_se_manca` (le indicatrici del detector: un `det_x`
    assente e' un «no», non un «non noto»)."""
    X = np.full((len(righe), len(nomi)), np.nan)
    for i, r in enumerate(righe):
        for j, n in enumerate(nomi):
            v = r.get(n)
            if v is None:
                if n.startswith(zero_se_manca):
                    X[i, j] = 0.0
                continue
            X[i, j] = v
    return X
