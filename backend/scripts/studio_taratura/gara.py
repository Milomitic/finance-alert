"""La gara stop/target VETTORIALE: la stessa regola di `corri_la_gara`, su N
percorsi insieme, per provare geometrie alternative senza rifare il replay.

Percorsi: array (N, H, 3) di alto/basso/chiusura relativi all'ingresso
(prezzo/ingresso - 1), NaN dove la barra non esiste.

Regola, identica all'originale:
  - si guarda dalla barra SUCCESSIVA all'ingresso, per al massimo `h` barre
  - stop e target nella stessa barra -> "ambigua", valorizzata -1R (pessimista)
  - nessun tocco e finestra completa -> "scaduto", valorizzato alla chiusura
  - nessun tocco e finestra incompleta -> NaN (il trade e' ancora aperto)
"""
import numpy as np


def gara(paths, lungo, stop_d, tp_d, h):
    """R multiplo per riga.

    paths  (N, H, 3) float
    lungo  (N,) bool
    stop_d (N,) distanza dello stop, frazione del prezzo (>0)
    tp_d   (N,) distanza del target, frazione del prezzo (>0)
    h      (N,) orizzonte in barre (<= H)
    """
    N, H, _ = paths.shape
    hi, lo, cl = paths[:, :, 0], paths[:, :, 1], paths[:, :, 2]
    s = np.where(lungo, 1.0, -1.0)[:, None]
    # escursione favorevole e avversa, nel verso del trade
    fav = np.where(lungo[:, None], hi, -lo)
    avv = np.where(lungo[:, None], -lo, hi)
    k = np.arange(H)[None, :]
    dentro = k < h[:, None]
    # Tolleranza della precisione float32 dei percorsi: un minimo che cade
    # ESATTAMENTE sullo stop (lo stop di candle_reversal e' il minimo della
    # barra del segnale) altrimenti finisce dalla parte sbagliata del bordo.
    EPS = 1e-7
    colpo_stop = (avv >= stop_d[:, None] - EPS) & dentro
    colpo_tp = (fav >= tp_d[:, None] - EPS) & dentro
    tocco = colpo_stop | colpo_tp
    has = tocco.any(axis=1)
    primo = np.where(has, tocco.argmax(axis=1), -1)
    r = np.full(N, np.nan)
    idx = np.arange(N)
    pr = np.clip(primo, 0, H - 1)
    st = colpo_stop[idx, pr]
    tp = colpo_tp[idx, pr]
    rr = tp_d / stop_d
    r[has & st] = -1.0
    r[has & ~st & tp] = rr[has & ~st & tp]
    # nessun tocco: scaduto se la finestra c'e' tutta
    hc = np.clip(h - 1, 0, H - 1)
    ultima = cl[idx, hc]
    completa = ~np.isnan(ultima)
    nessuno = ~has & completa
    r[nessuno] = (s[:, 0] * ultima)[nessuno] / stop_d[nessuno]
    return r


def geometria_attuale(close, atr, level, tone, hz):
    """Le distanze (frazioni del prezzo) di stop e TP1 secondo `costruisci_piano`,
    vettoriale. Restituisce (stop_d, tp1_d) o NaN dove il piano non esiste."""
    HZ = {"short": (0.5, 4.0, 2.0), "medium": (2.5, 2.0, 10.0), "long": (1.0, 3.0, 8.0)}
    floor = np.array([HZ.get(x, HZ["medium"])[0] for x in hz])
    tp1R = np.array([HZ.get(x, HZ["medium"])[1] for x in hz])
    tp1cap = np.array([HZ.get(x, HZ["medium"])[2] for x in hz])
    a = np.where(np.isfinite(atr) & (atr > 0), atr, close * 0.02)
    dist = np.abs(close - level)
    r = np.minimum(np.maximum(dist, floor * a), 8.0 * a)
    d1 = np.minimum(np.minimum(tp1R * r, tp1cap * a), 0.95 * close)
    ok = np.isfinite(level) & (level > 0) & (r > 0)
    return np.where(ok, r / close, np.nan), np.where(ok, d1 / close, np.nan)
