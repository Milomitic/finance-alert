"""Si puo' tarare il motore sulla storia? Walk-forward su ogni leva.

Per ogni anno di test Y: la leva si SCEGLIE sugli anni < Y (con un embargo di
100 giorni, perche' gli esiti degli ultimi segnali di train guardano dentro Y)
e si MISURA su Y, contro la configurazione di oggi. Il verdetto aggrega i
mesi di test: la differenza mensile fra scelta e configurazione attuale, con
un t su quei mesi — i segnali dello stesso mese NON sono indipendenti.

Metriche:
  R        attesa del piano in multipli di R (quello che l'utente vede)
  R_skill  R meno il controllo casuale (stessa geometria, stesso giorno, titolo a
           caso): cio' che resta e' la bravura dell'ingresso
"""
import json
import os
import sys

import numpy as np
import pandas as pd

from gara import gara

from percorsi import DATI as SW  # noqa: E402 — i dati stanno fuori da git
ANNI_TEST = list(range(2020, 2027))
EMBARGO = pd.Timedelta(days=100)
REPORT = {}


def carica():
    d = pd.read_csv(os.path.join(SW, "dataset.csv.gz"))
    p = np.load(os.path.join(SW, "dataset_paths.npy"), mmap_mode="r")
    d["dt"] = pd.to_datetime(d.date)
    d["mese"] = d.date.str.slice(0, 7)
    return d, p


def split(d, Y):
    start = pd.Timestamp(f"{Y}-01-01")
    tr = d[d.dt < start - EMBARGO]
    te = d[(d.dt >= start) & (d.dt < pd.Timestamp(f"{Y + 1}-01-01"))]
    return tr, te


def t_mensile(diff_by_month):
    x = np.asarray(diff_by_month, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return np.nan, len(x)
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))), len(x)


def stampa(titolo, df):
    print(f"\n=== {titolo} ===")
    print(df.to_string())


# ─── S1: i detector, anno per anno ────────────────────────────────────────
def s1_detector(d):
    L = d[d.ep_live & d.R.notna()]
    t = L.groupby("detector").agg(n=("R", "size"), R=("R", "mean"), R_ctrl=("R_ctrl", "mean"),
                                  R_skill=("R_skill", "mean"), exc_H=("exc_H", "mean"),
                                  hit=("exc_H", lambda s: (s > 0).mean() * 100)).round(3)
    # t su blocchi mensili di R_skill
    tt = {}
    for det, g in L.groupby("detector"):
        m = g.groupby("mese").R_skill.mean()
        tt[det] = t_mensile(m.values)[0]
    t["t_mesi_skill"] = pd.Series(tt).round(2)
    stampa("S1 detector (popolazione LIVE, 2017-2026)", t.sort_values("R_skill", ascending=False))
    # persistenza: la classifica dell'anno Y predice quella di Y+1?
    per_anno = L.groupby(["year", "detector"]).R_skill.mean().unstack()
    rho = []
    for y in per_anno.index[:-1]:
        a, b = per_anno.loc[y], per_anno.loc[y + 1]
        ok = a.notna() & b.notna()
        if ok.sum() >= 6:
            rho.append(a[ok].rank().corr(b[ok].rank()))
    print("\nPersistenza della classifica dei detector (Spearman anno -> anno successivo):",
          np.round(rho, 2), " media", round(float(np.mean(rho)), 3))
    segno = (per_anno > 0).mean().round(2)
    print("Quota di anni con R_skill > 0 per detector:\n", segno.sort_values().to_string())
    REPORT["s1"] = {"tabella": t.reset_index().to_dict("records"), "persistenza_rho": rho}
    return per_anno


# ─── S2a: la soglia di Forza ───────────────────────────────────────────────
SOGLIE = [0, 30, 40, 50, 60, 70, 80, 90]


def s2a_forza(d):
    A = d[d.ep_all & d.trend_ok & d.follow_ok & d.R.notna()]
    # monotonia grezza: Forza per decile, dentro i detector
    A = A.assign(dec=A.groupby("detector").strength.transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False)))
    mono = A.groupby("dec").agg(n=("R", "size"), R=("R", "mean"), R_skill=("R_skill", "mean"),
                                exc_H=("exc_H", "mean")).round(4)
    stampa("S2a Forza: quintili DENTRO ciascun detector (0 = piu' debole)", mono)
    ic = A.groupby(["detector", "year"]).apply(
        lambda g: g.strength.rank().corr(g.R_skill.rank()) if len(g) > 30 else np.nan,
        include_groups=False)
    print("IC Forza -> R_skill (detector x anno): media", round(ic.mean(), 4),
          " quota positiva", round((ic > 0).mean(), 2), " n", ic.notna().sum())
    righe, d_scelta, d_zero = [], [], []
    for Y in ANNI_TEST:
        tr, te = split(A, Y)
        if len(te) == 0:
            continue
        perf = {s: tr[tr.strength >= s].R.mean() for s in SOGLIE if (tr.strength >= s).sum() > 500}
        best = max(perf, key=perf.get)
        mm = {}
        for nome, s in (("scelta", best), ("attuale_60", 60), ("nessuna_0", 0)):
            sub = te[te.strength >= s]
            righe.append(dict(anno=Y, config=nome, soglia=s, n=len(sub), R=sub.R.mean(),
                              R_skill=sub.R_skill.mean()))
            mm[nome] = sub.groupby("mese").R.mean()
        d_scelta += list((mm["scelta"] - mm["attuale_60"]).dropna())
        d_zero += list((mm["nessuna_0"] - mm["attuale_60"]).dropna())
    t = pd.DataFrame(righe).round(3)
    stampa("S2a soglia di Forza, walk-forward", t)
    t1, n1 = t_mensile(d_scelta); t0, n0 = t_mensile(d_zero)
    print(f"  soglia scelta - 60, R per mese: media {np.mean(d_scelta):+.4f}, t = {t1:.2f} su {n1} mesi")
    print(f"  nessuna soglia - 60, R per mese: media {np.mean(d_zero):+.4f}, t = {t0:.2f} su {n0} mesi")
    REPORT["s2a_t"] = {"scelta_vs_60": [float(np.mean(d_scelta)), t1, n1],
                       "zero_vs_60": [float(np.mean(d_zero)), t0, n0]}
    REPORT["s2a"] = {"quintili": mono.reset_index().to_dict("records"), "ic_medio": float(ic.mean()),
                     "walk_forward": righe}


# ─── S2b: i cancelli trend e follow-through ────────────────────────────────
def s2b_cancelli(d):
    A = d[d.ep_all & (d.strength >= 60) & d.R.notna()]
    out = []
    for nome, col, sub in (("allineamento al trend", "trend_ok", A[A.detector.isin(
            ["volume_breakout", "high52_momentum", "trend_pullback", "squeeze_expansion",
             "gap_and_go", "adx_confirmation", "sr_flip", "structure_break"])]),
            ("follow-through", "follow_ok", A)):
        g = sub.groupby(col).agg(n=("R", "size"), R=("R", "mean"), R_skill=("R_skill", "mean"),
                                 exc_H=("exc_H", "mean")).round(4)
        m = sub.groupby(["mese", col]).R_skill.mean().unstack()
        tval, nm = t_mensile((m[True] - m[False]).values) if (True in m and False in m) else (np.nan, 0)
        print(f"\n=== S2b cancello: {nome} (Forza>=60) ===\n{g.to_string()}\n"
              f"  passa - scartati, R_skill per mese: t = {tval:.2f} su {nm} mesi")
        out.append(dict(cancello=nome, tabella=g.reset_index().to_dict("records"), t=tval, mesi=nm))
    REPORT["s2b"] = out


# ─── S2c: scegliere i detector sulla storia ────────────────────────────────
def s2c_selezione(d):
    L = d[d.ep_live & d.R.notna()]
    righe, mesi_diff = [], []
    for Y in ANNI_TEST:
        tr, te = split(L, Y)
        if len(te) == 0:
            continue
        st = tr.groupby("detector").R_skill.agg(["mean", "size"])
        tenuti = st[(st["mean"] > 0) & (st["size"] >= 50)].index
        k = te[te.detector.isin(tenuti)]
        righe.append(dict(anno=Y, tenuti=len(tenuti), n_tenuti=len(k), n_tutti=len(te),
                          R_tenuti=k.R.mean(), R_tutti=te.R.mean(),
                          skill_tenuti=k.R_skill.mean(), skill_tutti=te.R_skill.mean()))
        a = k.groupby("mese").R_skill.mean(); b = te.groupby("mese").R_skill.mean()
        mesi_diff += list((a - b).dropna().values)
    t = pd.DataFrame(righe).round(3)
    tval, nm = t_mensile(mesi_diff)
    stampa("S2c detector scelti sulla storia (R_skill>0 in train) vs tutti", t)
    print(f"  differenza mensile di R_skill: media {np.mean(mesi_diff):.4f}, t = {tval:.2f} su {nm} mesi")
    REPORT["s2c"] = {"walk_forward": righe, "t": tval, "mesi": nm}


# ─── S2d: la geometria ─────────────────────────────────────────────────────
FLOORS = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
TPS = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
#: Costo andata e ritorno (commissione + spread), frazione del prezzo. In R vale
#: COSTO/stop: 0,2R su uno stop dello 0,5%, 0,02R su uno del 5%.
COSTO = 0.001


def _geo(sub, f, tp, strutturale):
    c, a, lv = sub.close.values, sub.atr.values, sub.level.values
    a = np.where(np.isfinite(a) & (a > 0), a, c * 0.02)
    dist = np.abs(c - lv) if strutturale else np.zeros(len(c))
    r = np.minimum(np.maximum(dist, f * a), 8.0 * a)
    d1 = np.minimum(tp * r, 0.95 * c)
    return r / c, d1 / c


def s2d_geometria(d, P):
    from dataset import K_CTRL, r_controllo, unita_atr
    live_idx = np.load(os.path.join(SW, "ctrl_live_idx.npy"))
    pc = np.load(os.path.join(SW, "ctrl_live_paths.npy"), mmap_mode="r")
    ar = np.load(os.path.join(SW, "ctrl_live_atr.npy"))
    pos = pd.Series(np.arange(len(live_idx)), index=live_idx)
    L = d[d.ep_live & d.R.notna() & d.index.isin(live_idx)]
    rp = pos.loc[L.index].values
    sel = (rp[:, None] * K_CTRL + np.arange(K_CTRL)).ravel()
    pcL, arL = np.asarray(pc[sel]), ar[sel]
    PL = np.asarray(P[L.index.values])
    lungo = (L.tone == "bull").values
    h = L.horizon_days.values
    configs = [("attuale",)] + [(f, tp, s) for f in FLOORS for tp in TPS for s in (True, False)]
    NET, SK = {}, {}
    for cfg in configs:
        if cfg == ("attuale",):
            sd, td = L.stop_d.values, L.tp_d.values
        else:
            sd, td = _geo(L, *cfg)
        R = gara(PL, lungo, sd, td, h)
        Rc = r_controllo(pcL, arL, lungo, h, unita_atr(L, sd), td / sd)
        NET[str(cfg)] = R - COSTO / sd
        SK[str(cfg)] = R - Rc
    NET = pd.DataFrame(NET, index=L.index); SK = pd.DataFrame(SK, index=L.index)
    att = str(("attuale",))
    righe, diff_net, diff_sk = [], [], []
    for Y in ANNI_TEST:
        tr, te = split(L, Y)
        if len(te) == 0:
            continue
        for hz in ("short", "medium", "long"):
            trh, teh = tr[tr.horizon == hz], te[te.horizon == hz]
            if len(trh) < 300 or len(teh) < 30:
                continue
            m_net = NET.loc[trh.index].mean(); best_net = m_net.idxmax()
            m_sk = SK.loc[trh.index].mean(); best_sk = m_sk.idxmax()
            righe.append(dict(
                anno=Y, orizzonte=hz, n=len(teh),
                scelta_netto=best_net, netto_test_scelta=NET.loc[teh.index, best_net].mean(),
                netto_test_attuale=NET.loc[teh.index, att].mean(),
                scelta_skill=best_sk, skill_test_scelta=SK.loc[teh.index, best_sk].mean(),
                skill_test_attuale=SK.loc[teh.index, att].mean()))
            g = teh.mese
            diff_net += list((NET.loc[teh.index, best_net] - NET.loc[teh.index, att]).groupby(g).mean().dropna())
            diff_sk += list((SK.loc[teh.index, best_sk] - SK.loc[teh.index, att]).groupby(g).mean().dropna())
    t = pd.DataFrame(righe).round(3)
    stampa("S2d geometria scelta sulla storia vs attuale", t)
    tn, nn = t_mensile(diff_net); ts, ns = t_mensile(diff_sk)
    print(f"  R NETTO (scelta - attuale): media mensile {np.mean(diff_net):+.4f}, t = {tn:.2f} su {nn} mesi")
    print(f"  SKILL   (scelta - attuale): media mensile {np.mean(diff_sk):+.4f}, t = {ts:.2f} su {ns} mesi")
    sup = {}
    for hz in ("short", "medium", "long"):
        ix = L.index[L.horizon == hz]
        mn, ms = NET.loc[ix].mean(), SK.loc[ix].mean()
        sup[hz] = {"n": int(len(ix)), "attuale_netto": round(float(mn[att]), 4),
                   "attuale_skill": round(float(ms[att]), 4),
                   "top3_netto": mn.sort_values(ascending=False).head(3).round(3).to_dict(),
                   "top3_skill": ms.sort_values(ascending=False).head(3).round(3).to_dict(),
                   "skill_mediana_delle_config": round(float(ms.median()), 4)}
    print("\nSuperficie per orizzonte (tutto il periodo, IN-SAMPLE):")
    print(json.dumps(sup, indent=1))
    REPORT["s2d"] = {"walk_forward": righe, "t_netto": tn, "t_skill": ts, "mesi": nn, "superficie": sup}


# ─── S2e: i pesi dei fattori dentro la Forza ───────────────────────────────
def _bh(p):
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    q = np.empty(n)
    q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def _p_t(t, df):
    # coda a due lati della t di Student, via beta incompleta (niente scipy)
    from math import lgamma, exp, log
    x = df / (df + t * t)
    a, b = df / 2, 0.5
    # frazione continua di Lentz per I_x(a, b)
    def betacf(a, b, x):
        tiny = 1e-30
        c, dd = 1.0, 1.0 - (a + b) * x / (a + 1)
        dd = 1 / (dd if abs(dd) > tiny else tiny)
        h = dd
        for m in range(1, 200):
            m2 = 2 * m
            aa = m * (b - m) * x / ((a + m2 - 1) * (a + m2))
            dd = 1 + aa * dd; dd = 1 / (dd if abs(dd) > tiny else tiny)
            c = 1 + aa / c; c = c if abs(c) > tiny else tiny
            h *= dd * c
            aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1))
            dd = 1 + aa * dd; dd = 1 / (dd if abs(dd) > tiny else tiny)
            c = 1 + aa / c; c = c if abs(c) > tiny else tiny
            de = dd * c; h *= de
            if abs(de - 1) < 1e-10:
                break
        return h
    lbt = lgamma(a + b) - lgamma(a) - lgamma(b) + a * log(x) + b * log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return exp(lbt) * betacf(a, b, x) / a
    return 1 - exp(lbt) * betacf(b, a, 1 - x) / b


def s2e_fattori(d):
    A = d[d.ep_all & d.exc_H.notna()].copy()
    A["blk_m"] = (A.dt.dt.year - 2017) * 12 + A.dt.dt.month
    fac = pd.json_normalize(A.factors.map(json.loads).tolist())
    fac.index = A.index
    righe = []
    for det, g in A.groupby("detector"):
        h = int(g.horizon_days.iloc[0])
        passo = 3 if h >= 63 else 1          # blocchi lunghi quanto l'orizzonte
        blk = g.blk_m // passo
        fg = fac.loc[g.index]
        for col in fg.columns:
            x = pd.to_numeric(fg[col], errors="coerce")
            if x.notna().mean() < 0.5 or x.nunique() < 5:
                continue
            ics, anni = [], []
            for b, ix in g.groupby(blk).groups.items():
                if len(ix) < 20:
                    continue
                v = x.loc[ix]; e = g.exc_H.loc[ix]
                if v.nunique() < 3:
                    continue
                ics.append(v.rank().corr(e.rank())); anni.append(g.year.loc[ix].iloc[0])
            ics = np.array(ics); anni = np.array(anni)
            ok = np.isfinite(ics); ics, anni = ics[ok], anni[ok]
            if len(ics) < 8:
                continue
            t = ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics)))
            prima, dopo = ics[anni <= 2021], ics[anni >= 2022]
            righe.append(dict(detector=det, fattore=col, blocchi=len(ics), ic=ics.mean(), t=t,
                              p=_p_t(abs(t), len(ics) - 1),
                              ic_2017_21=prima.mean() if len(prima) else np.nan,
                              ic_2022_26=dopo.mean() if len(dopo) else np.nan))
    t = pd.DataFrame(righe)
    t["q_bh"] = _bh(t.p.values)
    t["segno_stabile"] = np.sign(t.ic_2017_21) == np.sign(t.ic_2022_26)
    t = t.sort_values("p")
    stampa("S2e fattori: IC per blocchi vs eccesso market-neutral (i 15 piu' forti)",
           t.head(15).round(4))
    sopr = t[t.q_bh < 0.10]
    print(f"\n  test: {len(t)}  |  sopravvissuti a FDR 10%: {len(sopr)}  |  "
          f"di cui con segno stabile fra 2017-21 e 2022-26: {int(sopr.segno_stabile.sum())}")
    print(f"  quota di segni stabili su TUTTI i test (0,5 = caso): {t.segno_stabile.mean():.3f}")
    REPORT["s2e"] = {"test": len(t), "sopravvissuti": sopr.round(4).to_dict("records"),
                     "quota_segno_stabile": float(t.segno_stabile.mean()),
                     "top15": t.head(15).round(4).to_dict("records")}


if __name__ == "__main__":
    d, P = carica()
    print(f"dataset: {len(d):,} righe, LIVE {int(d.ep_live.sum()):,}, anni {d.year.min()}-{d.year.max()}")
    quali = sys.argv[1:] or ["s1", "s2a", "s2b", "s2c", "s2d", "s2e"]
    if "s1" in quali: s1_detector(d)
    if "s2a" in quali: s2a_forza(d)
    if "s2b" in quali: s2b_cancelli(d)
    if "s2c" in quali: s2c_selezione(d)
    if "s2d" in quali: s2d_geometria(d, P)
    if "s2e" in quali: s2e_fattori(d)
    with open(os.path.join(SW, "report_tuning.json"), "w") as fh:
        json.dump(REPORT, fh, indent=1, default=float)
