"""Le due verifiche mirate uscite dalla pre-analisi.

1. L'ipotesi PRE-REGISTRATA (preregistrazione.json, scritta prima di vedere i
   titoli restanti): sull'orizzonte breve, lo stop largo (floor 4 ATR, TP1 1,5R,
   strutturale) migliora la skill rispetto alla geometria attuale. Si misura sui
   SOLI titoli che la pre-analisi non conteneva.
2. Per detector: quanto della skill negativa si spiega con la geometria (stessa
   misura con lo stop largo) e quanto con la direzione (hit market-neutral).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.argv = sys.argv[:1]
import tuning as T  # noqa: E402
from dataset import K_CTRL, r_controllo, unita_atr  # noqa: E402
from gara import gara  # noqa: E402

SW = T.SW


def _prepara(d, maschera):
    live_idx = np.load(os.path.join(SW, "ctrl_live_idx.npy"))
    pc = np.load(os.path.join(SW, "ctrl_live_paths.npy"), mmap_mode="r")
    ar = np.load(os.path.join(SW, "ctrl_live_atr.npy"))
    pos = pd.Series(np.arange(len(live_idx)), index=live_idx)
    L = d[d.ep_live & d.R.notna() & d.index.isin(live_idx) & maschera]
    sel = (pos.loc[L.index].values[:, None] * K_CTRL + np.arange(K_CTRL)).ravel()
    return L, np.asarray(pc[sel]), ar[sel]


def _valuta(L, PL, pcL, arL, sd, td, costo):
    lungo, h = (L.tone == "bull").values, L.horizon_days.values
    R = gara(PL, lungo, sd, td, h)
    Rc = r_controllo(pcL, arL, lungo, h, unita_atr(L, sd), td / sd)
    return R - costo / sd, R - Rc


def preregistrata(d, P):
    pre = set(json.load(open(os.path.join(SW, "preregistrazione.json")))["titoli_preanalisi"])
    for nome, m in (("HOLDOUT", ~d.stock_id.isin(pre)), ("pre-analisi", d.stock_id.isin(pre))):
        L, pcL, arL = _prepara(d, m & (d.horizon == "short"))
        PL = np.asarray(P[L.index.values])
        print(f"\n{nome}: {L.stock_id.nunique()} titoli, {len(L):,} segnali brevi")
        for costo in (0.0, 0.001, 0.002):
            n0, s0 = _valuta(L, PL, pcL, arL, L.stop_d.values, L.tp_d.values, costo)
            n1, s1 = _valuta(L, PL, pcL, arL, *T._geo(L, 4.0, 1.5, True), costo)
            dn = pd.Series(n1 - n0, index=L.index).groupby(L.mese).mean()
            ds = pd.Series(s1 - s0, index=L.index).groupby(L.mese).mean()
            print(f"  costo {costo * 100:.1f}%: netto {np.nanmean(n0):+.3f} -> {np.nanmean(n1):+.3f} "
                  f"(t {T.t_mensile(dn)[0]:.2f}) | skill {np.nanmean(s0):+.3f} -> {np.nanmean(s1):+.3f} "
                  f"(t {T.t_mensile(ds)[0]:.2f})")


def per_detector(d, P):
    L, pcL, arL = _prepara(d, d.index == d.index)
    PL = np.asarray(P[L.index.values])
    _, s_att = _valuta(L, PL, pcL, arL, L.stop_d.values, L.tp_d.values, 0.0)
    _, s_alt = _valuta(L, PL, pcL, arL, *T._geo(L, 4.0, 1.5, True), 0.0)
    t = pd.DataFrame({"det": L.detector.values, "hz": L.horizon.values, "mese": L.mese.values,
                      "att": s_att, "alt": s_alt, "hit": (L.exc_H > 0).values})
    out = []
    for (det, hz), g in t.groupby(["det", "hz"]):
        if len(g) < 300:
            continue
        out.append(dict(detector=det, orizzonte=hz, n=len(g),
                        skill_attuale=g.att.mean(), t_att=T.t_mensile(g.groupby("mese").att.mean())[0],
                        skill_stop_largo=g.alt.mean(), t_largo=T.t_mensile(g.groupby("mese").alt.mean())[0],
                        hit_mn=g.hit.mean() * 100))
    r = pd.DataFrame(out).sort_values("t_att")
    # BH sulle t attuali (p a due code, t di Student coi mesi come gradi di liberta')
    p = [T._p_t(abs(x), 100) for x in r.t_att]
    r["q_bh"] = T._bh(p)
    print("\n" + r.round(3).to_string(index=False))


if __name__ == "__main__":
    d, P = T.carica()
    preregistrata(d, P)
    per_detector(d, P)
