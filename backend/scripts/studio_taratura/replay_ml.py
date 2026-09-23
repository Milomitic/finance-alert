"""Replay di studio: ogni match dei detector su 10 anni, con fattori, geometria
del piano, esito della gara e il percorso successivo, per tarare e per l'ML.

Due popolazioni di "alert", emulate con la STESSA logica di cooldown dello scan
(`signal_scan_service`, ~riga 220):

  ep_live  i match che passano i cancelli di oggi (Forza >= 60, allineamento al
           trend per i trend-following, follow-through, eta' <= 7 giorni)
  ep_all   i match che passano la sola eta' <= 7 giorni — la popolazione su cui
           si provano soglie e cancelli diversi

Una riga per ogni barra in cui almeno una delle due inserirebbe un alert NUOVO.
Ingresso = chiusura della barra dell'emissione, gara dalla barra successiva,
piano con `trade_plan.costruisci_piano` e gara con `corri_la_gara`: le stesse
funzioni del magazzino live.

Uscita per titolo: s<id>.csv.gz (righe) + s<id>.npy (percorsi, allineati).

Uso: python replay_ml.py <n_titoli> <processi>
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import warnings
from datetime import date
from multiprocessing import Pool

import numpy as np
import pandas as pd

from percorsi import DATI as SW  # noqa: E402 — i dati stanno fuori da git
OUT = os.path.join(SW, "replay")
WINDOW = 260
COOLDOWN = 14
CHAIN_CAP = 28
MAX_AGE = 7
PATH_H = 63
FWD = (1, 5, 10, 21, 63)
TREND_FOLLOWING = {
    "volume_breakout", "high52_momentum", "trend_pullback", "squeeze_expansion",
    "gap_and_go", "adx_confirmation", "sr_flip", "structure_break",
}
DAL_BARRE = {"gap_and_go", "rsi_divergence", "macd_divergence", "hidden_divergence"}


def _features(df: pd.DataFrame) -> pd.DataFrame:
    c, h, lo, o, v = (df[k].astype(float) for k in ("close", "high", "low", "open", "volume"))
    pc = c.shift(1)
    tr = pd.concat([h - lo, (h - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    f = pd.DataFrame(index=df.index)
    for k in (1, 5, 21, 63, 126, 252):
        f[f"ret_{k}"] = c / c.shift(k) - 1
    for span in (20, 50, 200):
        f[f"dist_ema{span}"] = (c - c.ewm(span=span, adjust=False).mean()) / atr
    f["atr_pct"] = atr / c
    f["atr_rank"] = f["atr_pct"].rolling(252, min_periods=120).rank(pct=True)
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    f["rsi14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    f["dist_hi252"] = c / h.rolling(252, min_periods=120).max() - 1
    f["dist_lo252"] = c / lo.rolling(252, min_periods=120).min() - 1
    f["vol_ratio"] = v / v.rolling(20).mean().shift(1)
    f["gap"] = o / pc - 1
    f["vol20"] = c.pct_change().rolling(20).std()
    f["log_dollar_vol"] = np.log((c * v).rolling(20).mean().replace(0, np.nan))
    mn, mx = c.rolling(20).min(), c.rolling(20).max()
    f["range_pos20"] = (c - mn) / (mx - mn).replace(0, np.nan)
    return f


def _worker(args):
    sid, df = args
    dest = os.path.join(OUT, f"s{sid}.csv.gz")
    if os.path.exists(dest):
        return sid, -1, 0.0
    warnings.filterwarnings("ignore")
    from loguru import logger
    logger.remove()
    from app.services.plan_outcome_service import Barra, corri_la_gara
    from app.services.signal_drift_service import _horizon_days
    from app.signals.context import build_context
    from app.signals.horizon import classify_horizon
    from app.signals.runner import detect_signals_and_setups
    from app.signals.trade_plan import costruisci_piano

    t0 = time.time()
    df = df.reset_index(drop=True)
    n = len(df)
    dates = df["date"].astype(str).str.slice(0, 10).tolist()
    gidx = {d: i for i, d in enumerate(dates)}
    C = df["close"].to_numpy(float)
    H = df["high"].to_numpy(float)
    L = df["low"].to_numpy(float)
    feats = _features(df)
    fcols = list(feats.columns)
    F = feats.to_numpy(float)
    barre = [Barra(dates[k], H[k], L[k], C[k]) for k in range(n)]
    hz_days: dict[str, int] = {}

    # Stato del cooldown, uno per popolazione: detector -> alert precedente.
    stato = {"live": {}, "all": {}}

    def _nuovo(pop, name, tone, sd, si, i):
        """Emula lo scan: True se questo match INSERISCE un alert nuovo."""
        prior = stato[pop].get(name)
        if prior is not None and prior["tone"] == tone \
                and 0 <= (sd - prior["sd"]).days <= COOLDOWN:
            maturato = (i - prior["si"]) >= hz_days[name]
            if maturato:
                if prior["sd"] == sd:
                    return False
                # maturato su una barra diversa: nuova riga (sotto)
            else:
                if (sd - prior["first"]).days > CHAIN_CAP:
                    return False            # la catena muore, niente riga
                prior["sd"], prior["si"] = sd, si   # revisione: l'ancora avanza
                return False
        stato[pop][name] = {"tone": tone, "sd": sd, "si": si, "first": date.fromisoformat(dates[i])}
        return True

    rows, paths = [], []
    for i in range(WINDOW, n):
        win = df.iloc[i - WINDOW:i + 1].reset_index(drop=True)
        try:
            ctx = build_context(win)
            ms, _ = detect_signals_and_setups(win, ctx=ctx)
        except Exception:  # noqa: BLE001
            continue
        if not ms:
            continue
        atr = float(ctx.atr) if (ctx.atr is not None and ctx.atr == ctx.atr) else None
        trend = ctx.trend_sign
        bar_d = date.fromisoformat(dates[i])
        for m in ms:
            sd_s = str(m.signal_date)[:10]
            si = gidx.get(sd_s)
            if si is None:
                continue
            sd = date.fromisoformat(sd_s)
            if (bar_d - sd).days > MAX_AGE:
                continue
            if m.name not in hz_days:
                hz_days[m.name] = _horizon_days(m.name)
            inv = m.invalidation if isinstance(m.invalidation, dict) else None
            level = inv.get("level") if inv else None
            # follow-through, identico a `_follow_through_ok`
            follow_ok = True
            if isinstance(level, (int, float)) and si < i:
                nc = C[si + 1]
                follow_ok = bool(nc >= level) if m.tone == "bull" else bool(nc <= level)
            trend_ok = not (m.name in TREND_FOLLOWING and (
                (m.tone == "bull" and trend < 0) or (m.tone == "bear" and trend > 0)))
            live_ok = m.strength >= 60 and trend_ok and follow_ok
            ep_live = _nuovo("live", m.name, m.tone, sd, si, i) if live_ok else False
            ep_all = _nuovo("all", m.name, m.tone, sd, si, i)
            if not (ep_live or ep_all):
                continue

            # Il livello dalle barre per i detector che il magazzino ricostruisce.
            if not isinstance(level, (int, float)) and m.name in DAL_BARRE:
                if m.name == "gap_and_go":
                    level = C[si - 1] if si > 0 else None
                else:
                    level = L[si] if m.tone == "bull" else H[si]
            hz = classify_horizon(m.name, m.chain)
            snap = {"tone": m.tone, "atr": atr, "horizon": hz,
                    "invalidation": {"level": float(level)} if isinstance(level, (int, float)) else None}
            piano = costruisci_piano(snap, C[i], m.name)
            H_d = hz_days[m.name]
            r = {
                "stock_id": sid, "date": dates[i], "i": i, "detector": m.name, "tone": m.tone,
                "strength": m.strength, "probability": m.probability,
                "lag_bars": i - si, "age_days": (bar_d - sd).days,
                "horizon": hz, "horizon_days": H_d, "close": C[i], "atr": atr,
                "level": float(level) if isinstance(level, (int, float)) else np.nan,
                "trend_sign": trend, "trend_ok": trend_ok, "follow_ok": follow_ok,
                "ep_live": ep_live, "ep_all": ep_all,
                "n_chain": len(m.chain or []),
                "factors": json.dumps(m.factors or {}, separators=(",", ":")),
                "complete": (n - 1 - i) >= H_d,
            }
            for k in FWD:
                r[f"fwd_{k}"] = C[i + k] / C[i] - 1 if i + k < n else np.nan
            for j, col in enumerate(fcols):
                r[f"f_{col}"] = F[i, j]
            if piano is not None:
                r.update(plan_r=piano.r, stop=piano.stop, stop_pct=piano.stop_pct,
                         stop_capped=piano.stop_capped, tp1=piano.targets[0].price,
                         tp1_rr=piano.targets[0].rr, tp2_rr=piano.targets[1].rr)
                g = corri_la_gara(piano, barre[i + 1:], H_d)
                if g is not None:
                    r.update(esito=g.esito, r_mult=g.r_multiplo, mae_r=g.mae_r, mfe_r=g.mfe_r,
                             bars_out=g.barre, tp2_hit=g.tp2_raggiunto)
            # Il percorso (alto, basso, chiusura) relativo all'ingresso, 63 barre.
            p = np.full((PATH_H, 3), np.nan, dtype=np.float32)
            k = min(PATH_H, n - 1 - i)
            if k > 0:
                p[:k, 0] = H[i + 1:i + 1 + k] / C[i] - 1
                p[:k, 1] = L[i + 1:i + 1 + k] / C[i] - 1
                p[:k, 2] = C[i + 1:i + 1 + k] / C[i] - 1
            rows.append(r)
            paths.append(p)
    arr = np.stack(paths) if paths else np.empty((0, PATH_H, 3), np.float32)
    np.save(os.path.join(OUT, f"s{sid}.npy"), arr)
    pd.DataFrame(rows).to_csv(dest + ".tmp", index=False, compression="gzip")
    os.replace(dest + ".tmp", dest)
    return sid, len(rows), time.time() - t0


def main():
    n_tit = int(sys.argv[1])
    procs = int(sys.argv[2])
    os.makedirs(OUT, exist_ok=True)
    t = time.time()
    tutto = pd.read_csv(os.path.join(SW, "ohlcv_full.csv.gz"))
    print(f"caricate {len(tutto):,} barre in {time.time() - t:.0f}s", flush=True)
    gruppi = {sid: g for sid, g in tutto.groupby("stock_id", sort=True) if len(g) >= 800}
    ids = sorted(gruppi)
    random.Random(20260923).shuffle(ids)
    scelti = ids[:n_tit]
    # I titoli piu' lunghi per primi: bilancia il carico fra i processi.
    scelti.sort(key=lambda s: -len(gruppi[s]))
    with open(os.path.join(OUT, "_universo.json"), "w") as fh:
        json.dump({"eleggibili": len(ids), "scelti": [int(s) for s in scelti]}, fh)
    print(f"{len(ids)} titoli con >=800 barre, ne replico {len(scelti)} su {procs} processi", flush=True)
    fatti = 0
    with Pool(procs) as pool:
        for sid, nr, dt in pool.imap_unordered(_worker, [(s, gruppi[s]) for s in scelti]):
            fatti += 1
            print(f"[{fatti}/{len(scelti)}] titolo {sid}: {nr} righe in {dt:.0f}s "
                  f"(trascorsi {(time.time() - t) / 60:.1f} min)", flush=True)


if __name__ == "__main__":
    main()
