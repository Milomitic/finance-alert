"""FA-153: l'ipotesi PRE-REGISTRATA sulla volatilita', sul replay decennale.

Pre-registrazione: docs/superpowers/specs/2026-11-ipotesi-volatilita.md,
committata prima di rigenerare il replay. Questo script la applica alla
lettera e non sceglie niente da solo.

Ingressi (in `percorsi.DATI`): `replay/s*.csv.gz` (da `replay_ml.py`),
`ohlcv_full.csv.gz`, `etf_ids.txt`.

Uso, da backend/:  PYTHONPATH=. python scripts/studio_taratura/ipotesi_volatilita.py

⚠️ Uno scostamento dichiarato dalla lettera della pre-registrazione: il
controllo di FA-139 esclude i titoli con un alert dello stesso detector entro
5 giorni. Nel replay i segnali si conoscono solo per i titoli campionati,
quindi l'esclusione vale solo per quelli. Puo' solo far somigliare i
controlli ai segnali (diluire D), non crearlo.
"""
from __future__ import annotations

import glob
import json
import math
import os
import random
import sys
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from percorsi import DATI as SW  # noqa: E402

CONTROLLI = 5
VOL_SEDUTE = 20
MIN_SEZIONE = 30
ESCLUSIONE = 5
MIN_STORIA_TERZILI = 500
ANNI = list(range(2018, 2026))
T_SOGLIA = -2.6
ESCLUSI_PROVA_4 = {"squeeze_expansion", "gap_and_go"}
TRADING_TO_CALENDAR = 365.25 / 252


def carica_replay() -> pd.DataFrame:
    parti = [pd.read_csv(f) for f in sorted(glob.glob(os.path.join(SW, "replay", "s*.csv.gz")))]
    rows = pd.concat([p for p in parti if len(p)], ignore_index=True)
    rows = rows[(rows.ep_live.astype(bool)) & (rows.detector != "adx_confirmation")]
    piatte = (rows.atr / rows.close < 0.003) | rows.f_log_dollar_vol.isna()
    print(f"{len(rows):,} match ep_live, esclusi {int(piatte.sum())} su barre non negoziate",
          flush=True)
    rows = rows[~piatte].copy()
    rows["giorno"] = pd.to_datetime(rows.date).dt.date
    return rows.reset_index(drop=True)


def universo():
    o = pd.read_csv(os.path.join(SW, "ohlcv_full.csv.gz"), usecols=["stock_id", "date", "close"])
    etf = {int(x) for x in open(os.path.join(SW, "etf_ids.txt")).read().split() if x.strip()}
    o = o[~o.stock_id.isin(etf)]
    o["date"] = pd.to_datetime(o.date).dt.date
    serie = {}
    for sid, g in o.groupby("stock_id"):
        cs = g.close.to_numpy(dtype=float)
        vol = np.full(len(cs), np.nan)
        if len(cs) > VOL_SEDUTE:
            vol[1:] = pd.Series(cs[1:] / cs[:-1] - 1.0).rolling(VOL_SEDUTE).std().to_numpy()
        serie[int(sid)] = (g.date.tolist(), cs, vol)
    sezione: dict[date, list[tuple[int, float, int]]] = defaultdict(list)
    indice: dict[int, dict[date, int]] = {}
    for sid, (ds, _cs, vol) in serie.items():
        indice[sid] = {d: i for i, d in enumerate(ds)}
        for i, v in enumerate(vol):
            if v == v:
                sezione[ds[i]].append((sid, float(v), i))
    return serie, sezione, indice


def terzili_espandibili(rows: pd.DataFrame) -> np.ndarray:
    """2 = terzile alto. Tagli dai soli match con data STRETTAMENTE precedente;
    -1 dove la storia ha meno di MIN_STORIA_TERZILI match."""
    out = np.full(len(rows), -1)
    ordine = np.argsort(rows.giorno.to_numpy(), kind="stable")
    giorni = rows.giorno.to_numpy()[ordine]
    vals = rows.f_atr_pct.to_numpy()[ordine]
    storia: list[float] = []
    i = 0
    while i < len(ordine):
        j = i
        while j < len(ordine) and giorni[j] == giorni[i]:
            j += 1
        if len(storia) >= MIN_STORIA_TERZILI:
            a, b = np.quantile(storia, [1 / 3, 2 / 3])
            for k in range(i, j):
                v = vals[k]
                out[ordine[k]] = 0 if v <= a else 1 if v <= b else 2
        storia.extend(v for v in vals[i:j] if v == v)
        i = j
    return out


def eccessi(rows, serie, sezione, indice) -> np.ndarray:
    tagli_cache: dict[date, tuple[float, float] | None] = {}
    esclusioni: dict[tuple[str, int], list[date]] = defaultdict(list)
    for det, sid, g in zip(rows.detector, rows.stock_id, rows.giorno, strict=True):
        esclusioni[(det, int(sid))].append(g)
    out = np.full(len(rows), np.nan)
    for k, r in enumerate(rows.itertuples(index=False)):
        sid, g, h = int(r.stock_id), r.giorno, int(r.horizon_days)
        s = serie.get(sid)
        if s is None or g not in indice[sid]:
            continue
        ds, cs, vol = s
        ti = indice[sid][g]
        if ti + h >= len(cs) or not (vol[ti] == vol[ti]):
            continue
        if g not in tagli_cache:
            vv = [v for _, v, _ in sezione.get(g, ())]
            tagli_cache[g] = (tuple(np.quantile(vv, [1 / 3, 2 / 3]))
                              if len(vv) >= MIN_SEZIONE else None)
        t = tagli_cache[g]
        if t is None:
            continue

        def fascia(v, t=t):
            return 0 if v <= t[0] else 1 if v <= t[1] else 2

        mia = fascia(vol[ti])
        candidati = sorted(
            c for c, v, _ in sezione[g] if c != sid and fascia(v) == mia
            and not any(abs((x - g).days) <= ESCLUSIONE
                        for x in esclusioni.get((r.detector, c), ()))
        )
        random.Random(k).shuffle(candidati)
        rc = []
        for c in candidati:
            _dc, cc, _vc = serie[c]
            i = indice[c][g]
            if i + h < len(cc) and cc[i] > 0:
                rc.append(cc[i + h] / cc[i] - 1.0)
                if len(rc) == CONTROLLI:
                    break
        if len(rc) < CONTROLLI:
            continue
        rend = cs[ti + h] / cs[ti] - 1.0
        e = rend - float(np.median(rc))
        out[k] = e if r.tone == "bull" else -e
    return out


def blocchi(giorni: list[date], orizzonte: int) -> list[int]:
    span = max(1, math.ceil(orizzonte * TRADING_TO_CALENDAR))
    ordine = sorted(range(len(giorni)), key=lambda i: giorni[i])
    out, b, fino = [0] * len(giorni), -1, None
    for i in ordine:
        if fino is None or giorni[i] >= fino:
            b += 1
            fino = giorni[i] + timedelta(days=span)
        out[i] = b
    return out


def prova(df: pd.DataFrame) -> dict:
    """D, e il t sui D di blocco (blocchi con entrambe le parti)."""
    if df.empty:
        return {"n": 0}
    alto, basso = df[df.terzile == 2], df[df.terzile < 2]
    D = float(alto.eccesso.mean() - basso.eccesso.mean())
    h = int(df.horizon_days.max())
    df = df.assign(blocco=blocchi(df.giorno.tolist(), h))
    db = []
    for _, g in df.groupby("blocco"):
        a, b = g[g.terzile == 2].eccesso, g[g.terzile < 2].eccesso
        if len(a) and len(b):
            db.append(a.mean() - b.mean())
    t = None
    if len(db) >= 3 and np.std(db, ddof=1) > 0:
        t = float(np.mean(db) / (np.std(db, ddof=1) / math.sqrt(len(db))))
    return {"n": len(df), "n_alto": len(alto), "D_pct": round(D * 100, 3),
            "blocchi": len(db), "t_blocchi": round(t, 2) if t is not None else None}


def verdetto(df: pd.DataFrame) -> dict:
    tutto = prova(df)
    pari = prova(df[df.stock_id % 2 == 0])
    dispari = prova(df[df.stock_id % 2 == 1])
    anni = {a: prova(df[pd.to_datetime(df.giorno).dt.year == a]) for a in ANNI}
    negativi = sum(1 for v in anni.values() if v.get("n") and v["D_pct"] < 0)
    c1 = tutto.get("D_pct", 0) < 0 and (tutto.get("t_blocchi") or 0) < T_SOGLIA
    c2 = all(x.get("n") and x["D_pct"] < 0 for x in (pari, dispari))
    c3 = negativi >= 6
    return {"tutto": tutto, "pari": pari, "dispari": dispari,
            "anni": anni, "anni_negativi": negativi,
            "condizioni": {"1_t": bool(c1), "2_gruppi": bool(c2), "3_anni": bool(c3)}}


def main() -> None:
    rows = carica_replay()
    print("universo e volatilita'...", flush=True)
    serie, sezione, indice = universo()
    rows["terzile"] = terzili_espandibili(rows)
    rows = rows[rows.terzile >= 0].reset_index(drop=True)
    print(f"{len(rows):,} match con terzile; calcolo dei controlli...", flush=True)
    rows["eccesso"] = eccessi(rows, serie, sezione, indice)
    rows = rows[rows.eccesso.notna()].reset_index(drop=True)
    rows = rows[pd.to_datetime(rows.giorno).dt.year.between(ANNI[0], ANNI[-1])]
    print(f"{len(rows):,} match valutati", flush=True)

    principale = verdetto(rows)
    senza = verdetto(rows[~rows.detector.isin(ESCLUSI_PROVA_4)])
    c = principale["condizioni"]
    c4 = all(senza["condizioni"].values())
    confermata = all(c.values()) and c4
    out = {
        "principale": principale,
        "senza_squeeze_gap": senza,
        "condizione_4": c4,
        "esito": "confermata" if confermata else "nulla",
        "per_detector": {d: prova(g) for d, g in rows.groupby("detector")},
        "descrittivo_altri_orizzonti": "vedi fwd_5/fwd_21 nel replay: non entrano nel verdetto",
    }
    with open(os.path.join(SW, "ipotesi_volatilita.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
