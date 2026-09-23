"""S0 — il replay racconta la stessa storia del motore vivo?

Sullo stesso periodo (le date del magazzino live), per detector: l'attesa in R
dei piani del replay (popolazione LIVE, finestre complete) contro quella del
magazzino di produzione (finestre complete). Titoli diversi (450 a caso contro
l'intero universo), stesse regole: se i numeri divergono molto, il replay non e'
un sostituto affidabile della storia vera e tutto il resto va letto con cautela.
"""
import os

import numpy as np
import pandas as pd

from percorsi import DATI as SW  # noqa: E402 — i dati stanno fuori da git

d = pd.read_csv(os.path.join(SW, "dataset.csv.gz"))
p = pd.read_csv(os.path.join(SW, "plan_outcomes_marcati.csv"))
lo, hi = p.entry_date.min(), p.entry_date.max()
rep = d[d.ep_live & d.R.notna() & d.complete & (d.date >= lo) & (d.date <= hi)]
viv = p[p.completa]
t = pd.DataFrame({
    "n_replay": rep.groupby("detector").R.size(),
    "R_replay": rep.groupby("detector").R.mean(),
    "n_live": viv.groupby("detector").r_multiple.size(),
    "R_live": viv.groupby("detector").r_multiple.mean(),
    "stop%_replay": rep.groupby("detector").esito.apply(lambda s: (s == "stop").mean() * 100),
    "stop%_live": viv.groupby("detector").esito.apply(lambda s: (s == "stop").mean() * 100),
}).round(3)
print(f"periodo {lo} -> {hi}")
print(t.sort_values("n_live", ascending=False).to_string())
ok = t.n_replay.fillna(0).ge(30) & t.n_live.fillna(0).ge(30)
print("\ncorrelazione (Spearman) R_replay vs R_live sui detector con >=30 righe per parte:",
      round(t[ok].R_replay.rank().corr(t[ok].R_live.rank()), 3), f"({ok.sum()} detector)")
print("totale: replay %.3f R (n=%d), live %.3f R (n=%d)" % (rep.R.mean(), len(rep), viv.r_multiple.mean(), len(viv)))
# Distribuzione degli esiti: il replay e' la stessa MACCHINA?
print("\nquota di esiti, replay vs live:")
print(pd.DataFrame({"replay": rep.esito.value_counts(normalize=True).round(3),
                    "live": viv.esito.value_counts(normalize=True).round(3)}))
