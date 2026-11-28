"""Percorso confermato e uscita di metà al 90% di TP1, sul replay locale.

Da backend: python -m scripts.studio_taratura.percorso_piani
La sensibilità aggiunge 5 punti base sul solo nozionale della mezza uscita.
"""
import json
from datetime import date
from math import isclose
from pathlib import Path

import pandas as pd

from app.scripts.rapporto_uscite_ombra import confronto
from app.services.plan_outcome_service import Barra, corri_la_gara, percorso_confermato
from app.services.uscite_ombra_service import VARIANTI, corri_variante
from app.signals.trade_plan import costruisci_piano, sedute_della_gara
from scripts.studio_taratura.percorsi import DATI


def misura() -> pd.DataFrame:
    dati = Path(DATI)
    replay = dati / "replay"
    scelti = set(json.loads((replay / "_universo.json").read_text())["scelti"])
    serie = pd.read_csv(dati / "ohlcv_full.csv.gz", usecols=["stock_id", "date", "high", "low", "close"])
    varianti = {v.nome: v for v in VARIANTI}
    risultati = []
    for sid, barre in serie[serie.stock_id.isin(scelti)].groupby("stock_id"):
        storico = [Barra(b.date, b.high, b.low, b.close) for b in barre.itertuples()]
        episodi = pd.read_csv(replay / f"s{sid}.csv.gz")
        validi = episodi.ep_live & (episodi.atr / episodi.close >= 0.003) & episodi.f_log_dollar_vol.notna()
        for e in episodi[validi & episodi.level.notna()].itertuples():
            h = sedute_della_gara(e.detector, e.horizon_days)
            finestra = storico[e.i + 1:e.i + 1 + h]
            if len(finestra) < h:
                continue
            if storico[e.i].data != e.date or not isclose(storico[e.i].chiusura, e.close):
                raise ValueError(f"Barra di ingresso diversa: {sid}, {e.date}")
            snap = dict(tone=e.tone, atr=e.atr, horizon=e.horizon, invalidation={"level": e.level})
            piano = costruisci_piano(snap, e.close, e.detector)
            if piano is None:
                continue
            base = corri_la_gara(piano, finestra, h)
            args = dict(lato=piano.side, ingresso=e.close, stop=piano.stop,
                        tp1=piano.targets[0].price, r=piano.r, barre=finestra, orizzonte=h)
            controllo = corri_variante(**args, variante=varianti["attuale"])
            if (controllo.esito != base.esito or controllo.barre != base.barre
                    or not isclose(controllo.r_multiplo, base.r_multiplo, abs_tol=1e-8)):
                raise ValueError(f"Parità fallita: {sid}, {e.date}")
            meta = corri_variante(**args, variante=varianti["meta_al_90"])
            percorso = percorso_confermato(piano, finestra, base)
            tocco = percorso["peak_fraction"] >= 0.9 - 1e-12
            delta = meta.r_multiplo - base.r_multiplo
            risultati.append(dict(data=e.date, titolo=sid, h=h, esito=base.esito,
                                  chiusura_90=percorso["close_90_before_exit"],
                                  vicino=tocco and base.esito != "tp1", tocco=tocco,
                                  delta=delta, sensibilita=delta - (0.00025 * e.close / piano.r if tocco else 0)))
    return pd.DataFrame(risultati)


if __name__ == "__main__":
    df = misura()
    print("Periodo", df.data.min(), df.data.max(), "titoli", df.titolo.nunique(), "piani", len(df))
    print(df.groupby("h").agg(piani=("esito", "size"), al_90=("tocco", "sum"),
                              quasi=("vicino", "sum"), delta_r=("delta", "mean"),
                              con_attrito=("sensibilita", "mean")).to_string())
    for h, gruppo in df.groupby("h"):
        print(h, confronto(gruppo.delta.tolist(), [date.fromisoformat(d) for d in gruppo.data], int(h)))
    print("Dopo chiusura al 90%", df[df.chiusura_90].esito.value_counts().to_dict())
    print(df[df.tocco].esito.value_counts().to_string())
    print(df.groupby(df.data.str[:4])[["delta", "sensibilita"]].mean().to_string())
    print("Delta complessivo", df[["delta", "sensibilita"]].mean().to_dict())
