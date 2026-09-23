"""La selezione ML regge, ed e' selezione VERA?

Per le etichette 'mn' e 'sk', senza variabili di mercato:
  - guadagno del 30% scelto sul totale (come ml_study)
  - guadagno del 30% scelto DENTRO ciascun detector (soglia per detector sui
    punteggi di train): se sparisce, il modello stava solo imparando quali
    detector evitare — cosa che una regola da una riga fa gia'
  - su tre popolazioni di titoli: tutti, i 176 della pre-analisi, i 274 nuovi

Uso: python ml_robustezza2.py <mn|sk> <tutti|pre|nuovi>
"""
import json
import os
import sys

import numpy as np
import pandas as pd

from ml import GBM, auc
from ml_study import ANNI_TEST, QUOTA, prepara, split

from percorsi import DATI as SW  # noqa: E402 — i dati stanno fuori da git
etichetta, gruppo = sys.argv[1], sys.argv[2]

d = pd.read_csv(os.path.join(SW, "dataset.csv.gz"))
d["dt"] = pd.to_datetime(d.date)
d["mese"] = d.date.str.slice(0, 7)
pre = set(json.load(open(os.path.join(SW, "preregistrazione.json")))["titoli_preanalisi"])
m = d.ep_live & d.R.notna() & d.exc_H.notna() & d.R_skill.notna()
if gruppo == "pre":
    m &= d.stock_id.isin(pre)
elif gruppo == "nuovi":
    m &= ~d.stock_id.isin(pre)
D = d[m].copy()
X = prepara(D)
X = X[[c for c in X.columns if not c.startswith(("m_", "s_m_"))]]
y = {"mn": D.exc_H > 0, "sk": D.R_skill > 0}[etichetta].values.astype(float)
Xv = X.values
tot, dentro = [], []
aucs = []
for Y in ANNI_TEST:
    tr, te = split(D, Y)
    if te.sum() < 200 or tr.sum() < 2000:
        continue
    if tr.sum() > 120_000:
        k = np.sort(np.random.default_rng(Y).choice(np.where(tr)[0], 120_000, replace=False))
        tr = np.zeros(len(tr), bool); tr[k] = True
    g = GBM(n_trees=250, depth=3, lr=0.03, min_leaf=max(100, int(tr.sum() / 300)), l2=10.0, seed=Y).fit(Xv[tr], y[tr])
    p_tr, p_te = g.predict(Xv[tr]), g.predict(Xv[te])
    aucs.append(auc(y[te], p_te))
    TR, TE = D[tr], D[te]
    # sul totale
    k_tot = p_te >= np.quantile(p_tr, 1 - QUOTA)
    # dentro ciascun detector
    soglie = pd.Series(p_tr, index=TR.index).groupby(TR.detector).quantile(1 - QUOTA)
    k_det = p_te >= TE.detector.map(soglie).fillna(np.inf).values
    base = TE.R_skill.groupby(TE.mese).mean()
    for k, dest in ((k_tot, tot), (k_det, dentro)):
        sel = pd.Series(TE.R_skill.values[k], index=TE.mese.values[k]).groupby(level=0).mean()
        dest += list((sel - base).dropna().values)
    # nel "dentro" il confronto giusto e' con la media degli STESSI detector:
    # la base per mese e' la stessa, e la quota per detector e' ~30% ovunque.


def t(x):
    x = np.asarray(x)
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


res = dict(etichetta=etichetta, gruppo=gruppo, righe=len(D), auc=float(np.mean(aucs)),
           guadagno_totale=float(np.mean(tot)), t_totale=float(t(tot)),
           guadagno_dentro_detector=float(np.mean(dentro)), t_dentro_detector=float(t(dentro)), mesi=len(tot))
print(json.dumps(res))
with open(os.path.join(SW, f"rob2_{etichetta}_{gruppo}.json"), "w") as fh:
    json.dump(res, fh)
