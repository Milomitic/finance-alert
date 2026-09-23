"""Unisce le uscite del replay in un dataset unico, con le variabili di
mercato, l'eccesso market-neutral e il CONTROLLO casuale.

Il controllo: per ogni segnale, K titoli presi a caso fra quelli che hanno una
barra quel GIORNO, con la stessa geometria espressa in unita' di volatilita'
(stop nello stesso multiplo dell'ATR del titolo di controllo, target nello
stesso multiplo di R) e lo stesso verso. Cio' che resta fra segnale e
controllo e' la bravura dell'INGRESSO, al netto della deriva del mercato e
della geometria.

⚠️ I percorsi del controllo si SALVANO (per la popolazione LIVE): una geometria
diversa va confrontata con un controllo che usa la STESSA geometria, altrimenti
uno stop strettissimo «vince» solo perche' moltiplica la deriva del mercato.
"""
import glob
import os

import numpy as np
import pandas as pd

from gara import gara, geometria_attuale

from percorsi import DATI as SW  # noqa: E402 — i dati stanno fuori da git
K_CTRL = 5
H = 63


def carica_replay():
    R, P = [], []
    for f in sorted(glob.glob(os.path.join(SW, "replay", "s*.csv.gz"))):
        df = pd.read_csv(f)
        if len(df) == 0:
            continue
        R.append(df)
        P.append(np.load(f.replace(".csv.gz", ".npy")))
    rows = pd.concat(R, ignore_index=True)
    paths = np.concatenate(P)
    assert len(rows) == len(paths)
    return rows, paths


class Universo:
    """Le serie di TUTTI i titoli, per pescare i controlli."""

    def __init__(self):
        o = pd.read_csv(os.path.join(SW, "ohlcv_full.csv.gz"))
        o["date"] = o["date"].astype(str).str.slice(0, 10)
        o = o.sort_values(["stock_id", "date"]).reset_index(drop=True)
        pc = o.groupby("stock_id")["close"].shift(1)
        tr = pd.concat([o.high - o.low, (o.high - pc).abs(), (o.low - pc).abs()], axis=1).max(axis=1)
        o["atr"] = tr.groupby(o.stock_id).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
        o["k"] = o.groupby("stock_id").cumcount()
        o.loc[o.k < 20, "atr"] = np.nan
        n_by = o.groupby("stock_id").size()
        self.base_of = dict(zip(n_by.index, np.concatenate([[0], np.cumsum(n_by.values)])[:-1]))
        self.len_of = dict(zip(n_by.index, n_by.values))
        self.per_data = {d: g.index.values for d, g in o.groupby("date")}
        self.HI, self.LO, self.CL, self.ATR = (o[c].to_numpy(float) for c in ("high", "low", "close", "atr"))
        self.SID = o.stock_id.to_numpy()
        self.K = o.k.to_numpy()

    def pesca(self, dates, sids, rng):
        """Per ogni riga, K indici di barre di controllo (o -1)."""
        out = np.full((len(dates), K_CTRL), -1, dtype=np.int64)
        for j, (d, s) in enumerate(zip(dates, sids)):
            cand = self.per_data.get(d)
            if cand is None:
                continue
            cand = cand[self.SID[cand] != s]
            if len(cand) >= K_CTRL:
                out[j] = rng.choice(cand, K_CTRL, replace=False)
        return out

    def percorsi(self, flat):
        """(M, H, 3) float32 dei percorsi dopo le barre `flat`, + atr/prezzo."""
        ok = flat >= 0
        f = np.where(ok, flat, 0)
        sid = self.SID[f]; kk = self.K[f]
        rem = np.array([self.len_of[s] for s in sid]) - 1 - kk
        b0 = np.array([self.base_of[s] for s in sid]) + kk
        steps = np.arange(1, H + 1)[None, :]
        valid = (steps <= rem[:, None]) & ok[:, None]
        ix = np.where(valid, b0[:, None] + steps, 0)
        c0 = self.CL[f][:, None]
        p = np.stack([self.HI[ix] / c0 - 1, self.LO[ix] / c0 - 1, self.CL[ix] / c0 - 1], axis=2).astype(np.float32)
        p[~valid] = np.nan
        atr_rel = np.where(ok, self.ATR[f] / self.CL[f], np.nan)
        return p, atr_rel


def unita_atr(rows, stop_d):
    """Lo stop del segnale espresso in multipli del SUO ATR (col ripiego al 2%)."""
    a = np.where(np.isfinite(rows.atr.values) & (rows.atr.values > 0), rows.atr.values, rows.close.values * 0.02)
    return stop_d * rows.close.values / a


def r_controllo(pc, atr_rel, lungo, h, u_stop, rr):
    """R medio del controllo, per riga, data la geometria (u_stop in ATR, rr in R)."""
    n = len(lungo)
    stop_c = np.repeat(u_stop, K_CTRL) * atr_rel
    tp_c = stop_c * np.repeat(rr, K_CTRL)
    good = np.isfinite(stop_c) & (stop_c > 0)
    out = np.full(n * K_CTRL, np.nan)
    if good.any():
        out[good] = gara(pc[good], np.repeat(lungo, K_CTRL)[good], stop_c[good], tp_c[good],
                         np.repeat(h, K_CTRL)[good])
    with np.errstate(all="ignore"):
        return np.nanmean(out.reshape(n, K_CTRL), axis=1)


def costruisci():
    rows, paths = carica_replay()
    print(f"{len(rows):,} righe dal replay, {rows.stock_id.nunique()} titoli, "
          f"{rows.date.min()} -> {rows.date.max()}", flush=True)
    # ⚠️ Barre NON negoziate: un titolo sospeso (BMPS.MI nel 2017, prezzo
    # riportato piatto per mesi a volume zero) ha ATR ~0, quindi stop ~0, e un
    # solo segnale li' vale -800R di costo o +1000R di "scaduto". 78 righe su
    # 118mila spostavano la media dell'orizzonte lungo da -0,016 a -0,851 R.
    # Il motore vivo NON ha questa guardia: e' un rilievo, non solo un filtro.
    piatte = (rows.atr / rows.close < 0.003) | rows.f_log_dollar_vol.isna()
    print(f"escluse {int(piatte.sum())} righe su barre non negoziate (ATR < 0,3% o volume nullo)", flush=True)
    keep = ~piatte.values
    rows = rows[keep].reset_index(drop=True)
    paths = paths[keep]
    md = pd.read_csv(os.path.join(SW, "mercato_per_data.csv"))
    st = pd.read_csv(os.path.join(SW, "settore_per_titolo.csv.gz"))
    n0 = len(rows)
    rows = rows.merge(md, on="date", how="left").merge(st, on=["stock_id", "date"], how="left")
    assert len(rows) == n0, "il merge ha duplicato righe: percorsi disallineati"
    sgn = np.where(rows.tone == "bull", 1.0, -1.0)
    rows["sgn"] = sgn
    for h in (5, 21, 63):
        rows[f"exc_{h}"] = sgn * (rows[f"fwd_{h}"] - rows[f"umed_fwd_{h}"])
    Hd = rows.horizon_days.values
    rows["exc_H"] = np.select([Hd == 5, Hd == 21, Hd == 63], [rows.exc_5, rows.exc_21, rows.exc_63], np.nan)
    rows["year"] = rows.date.str.slice(0, 4).astype(int)
    sd, td = geometria_attuale(rows.close.values, rows.atr.values, rows.level.values,
                               rows.tone.values, rows.horizon.values)
    rows["stop_d"], rows["tp_d"] = sd, td
    ok = np.isfinite(sd)
    rv = np.full(len(rows), np.nan)
    rv[ok] = gara(paths[ok], (rows.tone == "bull").values[ok], sd[ok], td[ok], Hd[ok])
    rows["R"] = rv
    chk = rows.r_mult.notna()
    bad = int(((rows.R - rows.r_mult).abs() > 1e-4)[chk].sum())
    print(f"gara vettoriale vs replay: {bad} discordanti su {int(chk.sum())}", flush=True)

    U = Universo()
    rng = np.random.default_rng(7)
    lungo = (rows.tone == "bull").values
    u = unita_atr(rows, sd)
    rr = td / sd
    # R del controllo con la geometria ATTUALE, per tutte le righe, a blocchi.
    rc = np.full(len(rows), np.nan)
    live_idx = np.where(rows.ep_live.values & ok)[0]
    pesc = U.pesca(rows.date.values, rows.stock_id.values, rng)
    for a in range(0, len(rows), 20000):
        sl = slice(a, a + 20000)
        pc, ar = U.percorsi(pesc[sl].ravel())
        rc[sl] = r_controllo(pc, ar, lungo[sl], Hd[sl], u[sl], rr[sl])
        print(f"  controllo {min(a + 20000, len(rows)):,}/{len(rows):,}", flush=True)
    rows["R_ctrl"] = rc
    rows["R_skill"] = rows.R - rows.R_ctrl
    # I percorsi del controllo della popolazione LIVE restano, per la geometria.
    pc, ar = U.percorsi(pesc[live_idx].ravel())
    np.save(os.path.join(SW, "ctrl_live_paths.npy"), pc)
    np.save(os.path.join(SW, "ctrl_live_atr.npy"), ar)
    np.save(os.path.join(SW, "ctrl_live_idx.npy"), live_idx)
    rows.to_csv(os.path.join(SW, "dataset.csv.gz"), index=False, compression="gzip")
    np.save(os.path.join(SW, "dataset_paths.npy"), paths)
    print("salvato:", len(rows), "righe;", "LIVE", int(rows.ep_live.sum()), "ALL", int(rows.ep_all.sum()))


if __name__ == "__main__":
    costruisci()
