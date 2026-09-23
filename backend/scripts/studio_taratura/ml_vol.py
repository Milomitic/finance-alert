"""Controprova costruttiva: dove l'ML HA presa su questi dati?

La direzione non si prevede (studi precedenti + ml_study). La VOLATILITA'
futura si': e' l'ingresso del dimensionamento dello stop. Obiettivo:
log(range medio delle 10 barre successive / ATR all'ingresso), cioe' "di quanto
l'ATR di oggi sbaglia la volatilita' di domani". Walk-forward annuale.

Base da battere: zero (l'ATR di oggi e' la previsione, come fa il motore).
"""
import os

import numpy as np
import pandas as pd

from ml import GBM, spearman
from ml_study import ANNI_TEST, prepara, split

from percorsi import DATI as SW  # noqa: E402 — i dati stanno fuori da git

d = pd.read_csv(os.path.join(SW, "dataset.csv.gz"))
d["dt"] = pd.to_datetime(d.date); d["mese"] = d.date.str.slice(0, 7)
P = np.load(os.path.join(SW, "dataset_paths.npy"), mmap_mode="r")
D = d[d.ep_live & d.R.notna()].copy()
rng10 = np.nanmean(np.asarray(P[D.index.values, :10, 0] - P[D.index.values, :10, 1]), axis=1)
D["y"] = np.log(rng10 / (D.atr / D.close))
D = D[np.isfinite(D.y)]
X = prepara(D)
X = X[[c for c in X.columns if not c.startswith(("m_", "s_m_"))]]
Xv, y = X.values, D.y.values
righe = []
for Y in ANNI_TEST:
    tr, te = split(D, Y)
    if te.sum() < 200:
        continue
    g = GBM(n_trees=200, depth=3, lr=0.05, min_leaf=200, loss="l2", seed=Y).fit(Xv[tr], y[tr])
    p = g.predict(Xv[te])
    sse = ((y[te] - p) ** 2).sum()
    r2_zero = 1 - sse / (y[te] ** 2).sum()                       # contro "ATR di oggi"
    r2_media = 1 - sse / ((y[te] - y[tr].mean()) ** 2).sum()     # contro la media di train
    righe.append(dict(anno=Y, n=int(te.sum()), R2_vs_ATR=r2_zero, R2_vs_media=r2_media,
                      spearman=spearman(p, y[te])))
t = pd.DataFrame(righe).round(3)
print(t.to_string(index=False))
print("MEDIE:", t.mean(numeric_only=True).round(3).to_dict())
imp = pd.Series(g.importanza(X.shape[1]), index=X.columns).sort_values(ascending=False)
print("variabili piu' usate:", imp.head(8).round(3).to_dict())
