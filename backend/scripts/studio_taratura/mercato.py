"""Variabili per data e per (titolo, data) calcolate sull'INTERO universo.

- mediana dei rendimenti futuri (benchmark market-neutral: la MEDIANA, regola del
  progetto — la media e' spinta dall'asimmetria a destra)
- breadth: quota di titoli sopra la propria EMA200
- mediana e dispersione dei rendimenti a 21 barre
- forza relativa al settore a 63 barre
- VIX / curva / credito letti STRETTAMENTE prima della data
"""
import os
import numpy as np
import pandas as pd

from percorsi import DATI as SW  # noqa: E402 — i dati stanno fuori da git


def costruisci():
    o = pd.read_csv(os.path.join(SW, "ohlcv_full.csv.gz"))
    o["date"] = o["date"].astype(str).str.slice(0, 10)
    o = o.sort_values(["stock_id", "date"]).reset_index(drop=True)
    g = o.groupby("stock_id")["close"]
    for h in (1, 5, 10, 21, 63):
        o[f"fwd_{h}"] = g.shift(-h) / o["close"] - 1
    o["ret_21"] = o["close"] / g.shift(21) - 1
    o["ret_63"] = o["close"] / g.shift(63) - 1
    o["sopra200"] = (o["close"] > g.transform(lambda s: s.ewm(span=200, adjust=False).mean())).astype(float)
    o.loc[g.cumcount() < 200, "sopra200"] = np.nan
    st = pd.read_csv(os.path.join(SW, "stocks.csv"))[["id", "sector"]].rename(columns={"id": "stock_id"})
    o = o.merge(st, on="stock_id", how="left")
    per_data = o.groupby("date").agg(
        **{f"umed_fwd_{h}": (f"fwd_{h}", "median") for h in (1, 5, 10, 21, 63)},
        m_breadth=("sopra200", "mean"), m_ret21=("ret_21", "median"), m_ret63=("ret_63", "median"),
        m_disp21=("ret_21", lambda s: s.quantile(0.75) - s.quantile(0.25)), m_n=("close", "size"),
    ).reset_index()
    sett = o.groupby(["date", "sector"])["ret_63"].median().rename("sect_ret63").reset_index()
    o = o.merge(sett, on=["date", "sector"], how="left")
    o["f_sector_rs63"] = o["ret_63"] - o["sect_ret63"]
    per_titolo = o[["stock_id", "date", "f_sector_rs63", "sector"]]
    # macro: ultimo valore STRETTAMENTE prima della data
    mac = pd.read_csv(os.path.join(SW, "macro.csv"))
    date_all = pd.DataFrame({"date": sorted(per_data["date"])})
    for s, nome in (("VIXCLS", "m_vix"), ("T10Y2Y", "m_curve"), ("BAA10Y", "m_credit")):
        ms = mac[mac.series == s][["date", "value"]].copy()
        ms["date"] = pd.to_datetime(ms["date"]) + pd.Timedelta(days=1)   # strettamente prima
        ms = ms.sort_values("date")
        d = date_all.copy(); d["dt"] = pd.to_datetime(d["date"])
        d = pd.merge_asof(d.sort_values("dt"), ms.rename(columns={"date": "dt", "value": nome}), on="dt", direction="backward")
        per_data = per_data.merge(d[["date", nome]], on="date", how="left")
    per_data = per_data.sort_values("date")
    per_data["m_vix_chg5"] = per_data["m_vix"] - per_data["m_vix"].shift(5)
    per_data.to_csv(os.path.join(SW, "mercato_per_data.csv"), index=False)
    per_titolo.to_csv(os.path.join(SW, "settore_per_titolo.csv.gz"), index=False, compression="gzip")
    print(per_data.tail(3).to_string())
    print(len(per_data), "date;", per_titolo.f_sector_rs63.notna().sum(), "valori di forza settoriale")


if __name__ == "__main__":
    costruisci()
