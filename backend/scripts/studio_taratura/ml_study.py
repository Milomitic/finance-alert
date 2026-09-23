"""Meta-labeling: dato che un detector ha sparato, un modello sa dire QUALI
segnali tenere? Walk-forward annuale con embargo, contro basi oneste.

Etichette:
  win  il piano mostrato chiude in utile (R > 0)
  mn   il segnale batte la MEDIANA dell'universo all'orizzonte del detector
       (market-neutral, la stessa definizione del magazzino live)

Basi da battere:
  tasso del detector   la media dell'etichetta per detector x tono in train
  Forza                il punteggio che il motore gia' calcola

Il valore economico si misura sul R del piano e sul R_skill (al netto del
controllo casuale): tenere il 30% dei segnali con punteggio piu' alto, con la
soglia fissata sui punteggi di TRAIN, contro tenerli tutti.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

from ml import GBM, Logistica, auc, spearman

from percorsi import DATI as SW  # noqa: E402 — i dati stanno fuori da git
ANNI_TEST = list(range(2020, 2027))
EMBARGO = pd.Timedelta(days=100)
QUOTA = 0.30
FUTURO = ("fwd_", "umed_fwd_", "exc_", "R", "esito", "r_mult", "mae_r", "mfe_r",
          "bars_out", "tp2_hit", "complete")


def prepara(d):
    sgn = d.sgn.values
    X = pd.DataFrame(index=d.index)
    for det in sorted(d.detector.unique()):
        X[f"det_{det}"] = (d.detector == det).astype(float)
    X["bull"] = (d.tone == "bull").astype(float)
    X["hz"] = d.horizon.map({"short": 0, "medium": 1, "long": 2}).astype(float)
    for c in ("strength", "lag_bars", "age_days", "n_chain"):
        X[c] = d[c].astype(float)
    X["stop_d"] = d.stop_d
    X["rr"] = d.tp_d / d.stop_d
    a = np.where(d.atr > 0, d.atr, np.nan)
    X["stop_atr"] = d.stop_d * d.close / a
    fcols = [c for c in d.columns if c.startswith("f_")]
    for c in fcols:
        X[c] = d[c]
    # le variabili DIREZIONALI anche nel verso del segnale: "slancio a favore"
    for c in ("f_ret_1", "f_ret_5", "f_ret_21", "f_ret_63", "f_ret_126", "f_ret_252",
              "f_dist_ema20", "f_dist_ema50", "f_dist_ema200", "f_dist_hi252",
              "f_dist_lo252", "f_sector_rs63", "f_gap", "f_range_pos20"):
        X["s_" + c[2:]] = sgn * d[c]
    X["s_rsi"] = sgn * (d.f_rsi14 - 50)
    for c in ("m_breadth", "m_ret21", "m_ret63", "m_disp21", "m_vix", "m_curve", "m_credit", "m_vix_chg5"):
        X[c] = d[c]
        X["s_" + c] = sgn * d[c]
    # i fattori del detector (unione delle chiavi presenti in almeno l'1%)
    fac = pd.json_normalize(d.factors.map(json.loads).tolist())
    fac.index = d.index
    keep = [c for c in fac.columns if fac[c].notna().mean() >= 0.01]
    for c in keep:
        X["fac_" + c] = pd.to_numeric(fac[c], errors="coerce")
    for c in X.columns:
        assert not any(c.startswith(p) for p in FUTURO), f"variabile dal futuro: {c}"
    return X


def split(d, Y):
    start = pd.Timestamp(f"{Y}-01-01")
    tr = d.dt < start - EMBARGO
    te = (d.dt >= start) & (d.dt < pd.Timestamp(f"{Y + 1}-01-01"))
    return tr.values, te.values


def base_detector(d, tr, te, y):
    m = pd.Series(y[tr]).groupby([d.detector.values[tr], d.tone.values[tr]]).mean()
    key = list(zip(d.detector.values[te], d.tone.values[te]))
    return np.array([m.get(k, np.nan) for k in key])


def studia(d, etichetta, pop, permuta=False, n_trees=250, senza_mercato=False, cap=120_000, seme=3):
    D = d[pop & d.R.notna() & d.exc_H.notna()].copy()
    X = prepara(D)
    if senza_mercato:
        # Solo cio' che distingue un TITOLO da un altro lo stesso giorno: le
        # variabili di mercato sono una sola osservazione per data (regola A).
        X = X[[c for c in X.columns if not c.startswith(("m_", "s_m_"))]]
    D = D[D.R_skill.notna()] if etichetta == "sk" else D
    X = X.loc[D.index]
    y = {"win": (D.R > 0), "mn": (D.exc_H > 0), "sk": (D.R_skill > 0)}[etichetta].values.astype(float)
    print(f"\n##### etichetta={etichetta}  righe={len(D):,}  variabili={X.shape[1]}  "
          f"base={y.mean():.3f}  permutata={permuta}  senza_mercato={senza_mercato}", flush=True)
    rng = np.random.default_rng(seme)
    res, mesi = [], {"gbm": [], "log": [], "forza": []}
    imp_tot = np.zeros(X.shape[1])
    Xv = X.values
    for Y in ANNI_TEST:
        tr, te = split(D, Y)
        if te.sum() < 200 or tr.sum() < 2000:
            continue
        if tr.sum() > cap:
            keep = np.where(tr)[0]
            keep = np.sort(np.random.default_rng(Y).choice(keep, cap, replace=False))
            tr = np.zeros(len(tr), bool); tr[keep] = True
        ytr = y[tr].copy()
        if permuta:
            ytr = rng.permutation(ytr)
        t0 = time.time()
        g = GBM(n_trees=n_trees, depth=3, lr=0.03, min_leaf=max(100, int(tr.sum() / 300)),
                l2=10.0, seed=Y).fit(Xv[tr], ytr)
        pg_te, pg_tr = g.predict(Xv[te]), g.predict(Xv[tr])
        imp_tot += g.importanza(X.shape[1])
        lg = Logistica(l2=30.0).fit(Xv[tr], ytr)
        pl_te, pl_tr = lg.predict(Xv[te]), lg.predict(Xv[tr])
        bd = base_detector(D, tr, te, y)
        fz_te, fz_tr = D.strength.values[te], D.strength.values[tr]
        TE = D[te]
        riga = dict(anno=Y, n_test=int(te.sum()), base_test=float(y[te].mean()),
                    auc_gbm=auc(y[te], pg_te), auc_log=auc(y[te], pl_te),
                    auc_detector=auc(y[te], bd), auc_forza=auc(y[te], fz_te),
                    ic_gbm_R=spearman(pg_te, TE.R.values), ic_gbm_skill=spearman(pg_te, TE.R_skill.values),
                    R_tutti=TE.R.mean(), skill_tutti=TE.R_skill.mean(), secondi=round(time.time() - t0))
        for nome, s_te, s_tr in (("gbm", pg_te, pg_tr), ("log", pl_te, pl_tr), ("forza", fz_te, fz_tr)):
            soglia = np.quantile(s_tr, 1 - QUOTA)
            k = s_te >= soglia
            riga[f"quota_{nome}"] = float(k.mean())
            riga[f"R_{nome}"] = TE.R.values[k].mean() if k.any() else np.nan
            riga[f"skill_{nome}"] = TE.R_skill.values[k].mean() if k.any() else np.nan
            dm = (pd.Series(TE.R_skill.values[k], index=TE.mese.values[k]).groupby(level=0).mean()
                  - TE.R_skill.groupby(TE.mese).mean()).dropna()
            mesi[nome] += list(dm.values)
        res.append(riga)
        print(f"  {Y}: AUC gbm {riga['auc_gbm']:.3f} log {riga['auc_log']:.3f} "
              f"detector {riga['auc_detector']:.3f} forza {riga['auc_forza']:.3f} | "
              f"R tutti {riga['R_tutti']:+.3f} top30% gbm {riga['R_gbm']:+.3f} | "
              f"skill tutti {riga['skill_tutti']:+.3f} gbm {riga['skill_gbm']:+.3f} ({riga['secondi']}s)",
              flush=True)
    t = pd.DataFrame(res)
    riass = {c: float(t[c].mean()) for c in t.columns if c not in ("anno",)}
    for nome, v in mesi.items():
        x = np.asarray(v)
        riass[f"t_mesi_skill_{nome}"] = float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else np.nan
        riass[f"mesi_{nome}"] = len(x)
    imp = pd.Series(imp_tot / max(len(res), 1), index=X.columns).sort_values(ascending=False)
    print("  MEDIE:", {k: round(v, 4) for k, v in riass.items()
                       if k.startswith(("auc", "R_", "skill_", "t_mesi"))})
    print("  variabili piu' usate dal GBM:", imp.head(12).round(3).to_dict())
    return {"anni": res, "riassunto": riass, "importanze": imp.head(25).round(4).to_dict()}


if __name__ == "__main__":
    d = pd.read_csv(os.path.join(SW, "dataset.csv.gz"))
    d["dt"] = pd.to_datetime(d.date)
    d["mese"] = d.date.str.slice(0, 7)
    quale = sys.argv[1] if len(sys.argv) > 1 else "tutto"
    out = {}
    live = d.ep_live.values
    tutti = d.ep_all.values
    if quale in ("tutto", "live"):
        out["live_mn"] = studia(d, "mn", live)
        out["live_mn_senza_mercato"] = studia(d, "mn", live, senza_mercato=True)
        out["live_sk_senza_mercato"] = studia(d, "sk", live, senza_mercato=True)
        out["live_win_senza_mercato"] = studia(d, "win", live, senza_mercato=True)
        out["live_mn_senza_mercato_PERMUTATA_1"] = studia(d, "mn", live, senza_mercato=True, permuta=True, seme=11)
        out["live_mn_senza_mercato_PERMUTATA_2"] = studia(d, "mn", live, senza_mercato=True, permuta=True, seme=12)
    if quale in ("tutto", "all"):
        out["all_mn_senza_mercato"] = studia(d, "mn", tutti, senza_mercato=True)
        out["all_sk_senza_mercato"] = studia(d, "sk", tutti, senza_mercato=True)
    with open(os.path.join(SW, f"report_ml_{quale}.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=float)
