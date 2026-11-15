"""Rapporto delle uscite alternative in prova silenziosa (FA-141).

    python -m app.scripts.rapporto_uscite_ombra [--senza-controllo]

Criterio d'adozione e lettura: docs/superpowers/specs/2026-11-15-uscite-in-ombra.md.

Per ogni variante, contro `attuale`, sugli STESSI trade a finestra chiusa:
differenza appaiata in R, finestre indipendenti (blocchi di tempo lunghi un
orizzonte, per data d'ingresso) e t sulle medie per blocco. Accanto, lo
stesso confronto sul controllo casuale: la geometria del piano in ATR(14) del
titolo del segnale, applicata lo stesso giorno a cinque titoli scelti con un
seme riproducibile.

⚠️ La parita' si legge per prima: `attuale` deve coincidere con
`plan_outcomes.r_multiple`. Se non coincide il resto non vale.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median, stdev

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import OhlcvDaily, PlanOutcome, PlanOutcomeOmbra
from app.services import uscite_ombra_service as uo
from app.services.esiti_orizzonti_service import CONTROLLI, ordine_dei_controlli
from app.services.plan_outcome_service import Barra
from app.stats.sizing import _TRADING_TO_CALENDAR

ATR_SEDUTE = 14


def blocchi(date_: list[date], orizzonte: int) -> list[int]:
    """L'indice di blocco di ciascuna data, con la copertura greedy di
    `independent_blocks`: stesso conteggio, ma per elemento."""
    span = max(1, math.ceil(orizzonte * _TRADING_TO_CALENDAR))
    ordine = sorted(range(len(date_)), key=lambda i: date_[i])
    out = [0] * len(date_)
    blocco, fino = -1, None
    for i in ordine:
        if fino is None or date_[i] >= fino:
            blocco += 1
            fino = date_[i] + timedelta(days=span)
        out[i] = blocco
    return out


def confronto(diff: list[float], date_: list[date], orizzonte: int) -> dict:
    """Media appaiata, finestre indipendenti e t sulle medie per blocco."""
    if not diff:
        return {"n": 0}
    b = blocchi(date_, orizzonte)
    per: dict[int, list[float]] = defaultdict(list)
    for d, k in zip(diff, b, strict=True):
        per[k].append(d)
    medie = [mean(v) for v in per.values()]
    t = None
    if len(medie) >= 3 and stdev(medie) > 0:
        t = mean(medie) / (stdev(medie) / math.sqrt(len(medie)))
    return {"n": len(diff), "finestre": len(medie), "media_r": round(mean(diff), 4),
            "t_blocchi": round(t, 2) if t is not None else None}


def _atr(barre: list[Barra]) -> float | None:
    if len(barre) < ATR_SEDUTE + 1:
        return None
    coppie = zip(barre[-ATR_SEDUTE - 1:-1], barre[-ATR_SEDUTE:], strict=True)
    tr = [max(b.alto - b.basso, abs(b.alto - p.chiusura), abs(b.basso - p.chiusura))
          for p, b in coppie]
    return sum(tr) / len(tr)


def _barre(db, dal: date, al: date) -> dict[int, list[Barra]]:
    out: dict[int, list[Barra]] = defaultdict(list)
    for sid, d, hi, lo, cl in db.execute(
        select(OhlcvDaily.stock_id, OhlcvDaily.date, OhlcvDaily.high, OhlcvDaily.low,
               OhlcvDaily.close)
        .where(OhlcvDaily.date >= dal, OhlcvDaily.date <= al)
        .order_by(OhlcvDaily.stock_id, OhlcvDaily.date)
    ):
        out[sid].append(Barra(str(d)[:10], float(hi), float(lo), float(cl)))
    return out


def indice_per_giorno(barre: dict[int, list[Barra]]) -> dict[str, dict[int, int]]:
    """{giorno: {titolo: posizione della barra}}, costruito una volta sola."""
    out: dict[str, dict[int, int]] = defaultdict(dict)
    for s, bb in barre.items():
        for j, b in enumerate(bb):
            out[b.data][s] = j
    return out


def controllo(p: PlanOutcome, barre: dict[int, list[Barra]],
              per_giorno: dict[str, dict[int, int]]) -> dict[str, float]:
    """La mediana, sui controlli, della differenza variante - attuale."""
    giorno = p.entry_date.isoformat()
    indici = per_giorno.get(giorno, {})
    mio = indici.get(p.stock_id)
    if mio is None:
        return {}
    a = _atr(barre[p.stock_id][: mio + 1])
    if not a or a <= 0:
        return {}
    k_stop, k_tp = abs(p.entry - p.stop) / a, abs(p.tp1 - p.entry) / a
    lato = "long" if p.tone == "bull" else "short"
    candidati = [s for s in indici if s != p.stock_id]
    diffs: dict[str, list[float]] = defaultdict(list)
    presi = 0
    for s in ordine_dei_controlli(candidati, p.alert_id):
        bb, i = barre[s], indici[s]
        ac = _atr(bb[: i + 1])
        if not ac or ac <= 0:
            continue
        ing = bb[i].chiusura
        stop = ing - k_stop * ac if lato == "long" else ing + k_stop * ac
        tp1 = ing + k_tp * ac if lato == "long" else ing - k_tp * ac
        esiti = {v.nome: uo.corri_variante(lato=lato, ingresso=ing, stop=stop, tp1=tp1,
                                           r=k_stop * ac, barre=bb[i + 1:],
                                           orizzonte=p.horizon_days, variante=v)
                 for v in uo.VARIANTI if not v.vol_modello}
        if any(e is None for e in esiti.values()):
            continue
        for nome, e in esiti.items():
            if nome != "attuale":
                diffs[nome].append(e.r_multiplo - esiti["attuale"].r_multiplo)
        presi += 1
        if presi >= CONTROLLI:
            break
    if presi < CONTROLLI:
        return {}
    return {k: median(v) for k, v in diffs.items()}


def rapporto(db, *, con_controllo: bool = True) -> dict:
    ver = uo.versione()
    piani = {p.alert_id: p for p in db.execute(
        select(PlanOutcome).where(PlanOutcome.legs_window_complete.is_(True))).scalars()}
    righe: dict[int, dict[str, float]] = defaultdict(dict)
    for o in db.execute(
        select(PlanOutcomeOmbra).where(PlanOutcomeOmbra.method_version == ver)
    ).scalars():
        righe[o.alert_id][o.variante] = o.r_multiple
    complete = [a for a, v in righe.items() if all(n in v for n in uo.SEMPRE) and a in piani]

    parita = [abs(righe[a]["attuale"] - piani[a].r_multiple) < 1e-6 for a in complete]
    out: dict = {"versione": ver, "trade": len(complete),
                 "parita": {"coincidono": sum(parita), "su": len(parita)}}

    controlli: dict[int, dict[str, float]] = {}
    if con_controllo and complete:
        dal = min(piani[a].entry_date for a in complete) - timedelta(days=40)
        al = max(piani[a].entry_date for a in complete) + timedelta(days=120)
        barre = _barre(db, dal, al)
        per_giorno = indice_per_giorno(barre)
        for a in complete:
            controlli[a] = controllo(piani[a], barre, per_giorno)

    per_variante: dict[str, dict] = {}
    for v in uo.VARIANTI:
        if v.nome == "attuale":
            continue
        gruppi: dict[tuple[str, int], list[int]] = defaultdict(list)
        for a in complete:
            if v.nome not in righe[a]:
                continue
            gruppi[("tutti", piani[a].horizon_days)].append(a)
            gruppi[(piani[a].detector, piani[a].horizon_days)].append(a)
        voci = {}
        for (det, h), ids in sorted(gruppi.items()):
            diff = [righe[a][v.nome] - righe[a]["attuale"] for a in ids]
            voce = {"orizzonte": h,
                    "segnali": confronto(diff, [piani[a].entry_date for a in ids], h)}
            con = [(controlli[a][v.nome], piani[a].entry_date) for a in ids
                   if v.nome in controlli.get(a, {})]
            if con:
                voce["controllo"] = confronto([c for c, _ in con], [d for _, d in con], h)
            voci[f"{det}@{h}"] = voce
        per_variante[v.nome] = voci
    out["varianti"] = per_variante
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Rapporto delle uscite in prova silenziosa (FA-141)")
    ap.add_argument("--senza-controllo", action="store_true",
                    help="salta il controllo casuale, che carica le barre di tutto il catalogo")
    args = ap.parse_args()
    with SessionLocal() as db:
        print(json.dumps(rapporto(db, con_controllo=not args.senza_controllo),
                         indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
