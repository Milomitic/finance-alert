"""Il solo risultato ML "positivo" regge? (logistica CON variabili di mercato,
etichetta market-neutral, t 3,5 sul campione intero ma 0,10 sull'anteprima).

Due prove, entrambe decise PRIMA di guardarne l'esito:
  1. controllo permutato CON le variabili di mercato (due semi): quanto vale t
     quando per costruzione non c'e' niente da imparare, in QUESTA variante;
  2. replica su due gruppi di titoli DISGIUNTI (i 176 della pre-analisi e i 274
     nuovi): un effetto vero compare in entrambi.
"""
import json
import os

import pandas as pd

from ml_study import studia

from percorsi import DATI as SW  # noqa: E402 — i dati stanno fuori da git

d = pd.read_csv(os.path.join(SW, "dataset.csv.gz"))
d["dt"] = pd.to_datetime(d.date)
d["mese"] = d.date.str.slice(0, 7)
pre = set(json.load(open(os.path.join(SW, "preregistrazione.json")))["titoli_preanalisi"])
live = d.ep_live.values
out = {
    "perm_mercato_1": studia(d, "mn", live, permuta=True, seme=21, n_trees=150),
    "perm_mercato_2": studia(d, "mn", live, permuta=True, seme=22, n_trees=150),
    "gruppo_preanalisi": studia(d, "mn", live & d.stock_id.isin(pre).values),
    "gruppo_nuovi": studia(d, "mn", live & ~d.stock_id.isin(pre).values),
}
with open(os.path.join(SW, "report_ml_robustezza.json"), "w") as fh:
    json.dump(out, fh, indent=1, default=float)
