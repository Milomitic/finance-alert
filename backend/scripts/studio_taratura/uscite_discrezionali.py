"""Uscite di chi chiude a mano (FA-206), sul replay decennale locale.

Da backend: python -m scripts.studio_taratura.uscite_discrezionali
Le regole e il criterio sono scritti prima dei dati in
docs/superpowers/specs/2026-11-15-uscite-in-ombra.md.
"""
import json
from datetime import date
from math import isclose
from pathlib import Path

import pandas as pd

from app.scripts.rapporto_uscite_ombra import confronto
from app.services.plan_outcome_service import Barra, corri_la_gara
from app.services.uscite_ombra_service import VARIANTI, corri_variante
from app.signals.trade_plan import costruisci_piano, sedute_della_gara
from scripts.studio_taratura.percorsi import DATI

NUOVE = ("restituz_50", "restituz_75", "presa_75")
ATTRITO = 0.0005  # 5 punti base sul nozionale della chiusura anticipata


def misura() -> pd.DataFrame:
    dati = Path(DATI)
    replay = dati / "replay"
    scelti = set(json.loads((replay / "_universo.json").read_text())["scelti"])
    serie = pd.read_csv(dati / "ohlcv_full.csv.gz", usecols=["stock_id", "date", "high", "low", "close"])
    varianti = {v.nome: v for v in VARIANTI}
    out = []
    for sid, barre in serie[serie.stock_id.isin(scelti)].groupby("stock_id"):
        storico = [Barra(b.date, b.high, b.low, b.close) for b in barre.itertuples()]
        episodi = pd.read_csv(replay / f"s{sid}.csv.gz")
        validi = episodi.ep_live & (episodi.atr / episodi.close >= 0.003) & episodi.f_log_dollar_vol.notna()
        for e in episodi[validi & episodi.level.notna()].itertuples():
            h = sedute_della_gara(e.detector, e.horizon_days)
            finestra = storico[e.i + 1:e.i + 1 + h]
            if len(finestra) < h:
                continue
            snap = dict(tone=e.tone, atr=e.atr, horizon=e.horizon, invalidation={"level": e.level})
            piano = costruisci_piano(snap, e.close, e.detector)
            if piano is None:
                continue
            base = corri_la_gara(piano, finestra, h)
            args = dict(lato=piano.side, ingresso=e.close, stop=piano.stop,
                        tp1=piano.targets[0].price, r=piano.r, barre=finestra, orizzonte=h)
            controllo = corri_variante(**args, variante=varianti["attuale"])
            if (controllo.esito != base.esito
                    or not isclose(controllo.r_multiplo, base.r_multiplo, abs_tol=1e-8)):
                raise ValueError(f"Parità fallita: {sid}, {e.date}")
            riga = dict(data=e.date, titolo=sid, h=h, detector=e.detector, esito=base.esito,
                        r_base=base.r_multiplo)
            for nome in NUOVE:
                v = corri_variante(**args, variante=varianti[nome])
                anticipata = v.esito in ("restituzione", "presa")
                riga[nome] = v.r_multiplo - base.r_multiplo
                riga[nome + "_attr"] = riga[nome] - (ATTRITO * e.close / piano.r if anticipata else 0)
                riga[nome + "_usc"] = anticipata
            out.append(riga)
    return pd.DataFrame(out)


def rapporto(df: pd.DataFrame) -> None:
    print("Periodo", df.data.min(), df.data.max(), "titoli", df.titolo.nunique(), "piani", len(df))
    gruppo_a = df.titolo % 2 == 0
    for nome in NUOVE:
        print(f"\n=== {nome} ===")
        print("uscite anticipate", int(df[nome + "_usc"].sum()), "su", len(df))
        for h, g in df.groupby("h"):
            d = [date.fromisoformat(x) for x in g.data]
            print(f" h={h}", confronto(g[nome].tolist(), d, int(h)),
                  "con attrito", round(g[nome + "_attr"].mean(), 4))
            for etichetta, sub in (("titoli pari", g[gruppo_a.loc[g.index]]),
                                   ("titoli dispari", g[~gruppo_a.loc[g.index]])):
                print(f"   {etichetta}", confronto(sub[nome].tolist(),
                                                   [date.fromisoformat(x) for x in sub.data], int(h)))
        anni = df.groupby(df.data.str[:4])[nome].mean()
        print(" anni positivi", int((anni > 0).sum()), "su", len(anni), anni.round(4).to_dict())
        # Da dove viene: per esito del piano fisso, la somma delle differenze.
        print(" per esito del piano fisso (n, delta medio, delta totale):")
        print(df.groupby("esito")[nome].agg(["size", "mean", "sum"]).round(4).to_string())
    df.to_csv(Path(DATI) / "uscite_discrezionali.csv.gz", index=False)


if __name__ == "__main__":
    rapporto(misura())
