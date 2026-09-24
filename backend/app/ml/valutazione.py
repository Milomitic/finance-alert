"""Il confronto dal vivo: i modelli in ombra contro cio' che il motore usa oggi.

Due domande, e nessuna delle due si decide qui:

  volatilita'  l'escursione media delle 10 sedute dopo l'emissione era piu'
               vicina all'ATR (la previsione di oggi) o all'ATR per il fattore
               del modello? R² contro l'ATR: sopra zero il modello sbaglia meno.
  selezione    fra i match con un punteggio — alert E scartati, perche' il
               modello sceglie fra tutti, prima dei cancelli — quelli nel 30%
               piu' alto battono il mercato piu' spesso degli altri? E fra gli
               alert, il loro piano rende di piu' a finestre CHIUSE?

⚠️ I tassi portano il numero di FINESTRE indipendenti accanto alle righe, come
il cubo dei detector (`app.stats.sizing.independent_blocks`):
righe che condividono la finestra d'esito non sono osservazioni separate. Il
criterio di promozione e' scritto in
`docs/superpowers/specs/2026-09-24-modelli-in-ombra.md`; questo modulo misura,
non promuove.
"""
from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
from sqlalchemy import select


def _snap(testo: str | None) -> dict:
    try:
        s = json.loads(testo) if testo else {}
    except (ValueError, TypeError):
        return {}
    return s if isinstance(s, dict) else {}


def _giorno(x: object) -> date | None:
    if isinstance(x, date):
        return x
    if isinstance(x, str) and len(x) >= 10:
        try:
            return date.fromisoformat(x[:10])
        except ValueError:
            return None
    return None


def _escursione_dopo(db, stock_id: int, giorno: date, n: int = 10) -> float | None:
    from app.models import OhlcvDaily

    righe = db.execute(
        select(OhlcvDaily.high, OhlcvDaily.low)
        .where(OhlcvDaily.stock_id == stock_id, OhlcvDaily.date > giorno)
        .order_by(OhlcvDaily.date).limit(n)
    ).all()
    if len(righe) < n:
        return None
    return float(np.mean([h - lo for h, lo in righe]))


def _tasso(valori: list[int], date_: list[date], orizzonte: int) -> dict:
    from app.stats.sizing import independent_blocks

    n = len(valori)
    return {
        "n": n,
        "finestre": independent_blocks(date_, orizzonte) if n else 0,
        "tasso": round(sum(valori) / n, 4) if n else None,
    }


def valuta_volatilita(db) -> dict:
    from app.models import Alert

    y, p = [], []
    for a in db.execute(select(Alert)).scalars():
        s = _snap(a.snapshot)
        vol = (s.get("first_ombra") or {}).get("vol") or {}
        f, atr = vol.get("fattore"), s.get("first_atr")
        giorno = _giorno(s.get("first_emitted_at"))
        if not (isinstance(f, (int, float)) and f > 0 and isinstance(atr, (int, float)) and atr > 0 and giorno):
            continue
        esc = _escursione_dopo(db, a.stock_id, giorno)
        if esc is None or esc <= 0:
            continue
        y.append(math.log(esc / atr))
        p.append(math.log(f))
    if not y:
        return {"n": 0}
    ya, pa = np.array(y), np.array(p)
    return {
        "n": len(y),
        "R2_contro_ATR": round(float(1 - ((ya - pa) ** 2).sum() / (ya ** 2).sum()), 4),
        "errore_medio_ATR": round(float(np.abs(ya).mean()), 4),
        "errore_medio_modello": round(float(np.abs(ya - pa).mean()), 4),
    }


def valuta_selezione(db) -> dict:
    from app.models import Alert, PlanOutcome, SignalCandidate, SignalOutcome

    gruppi: dict[bool, dict[str, list]] = {
        v: {"hit": [], "date": [], "orizzonti": [], "R": [], "date_R": []} for v in (True, False)
    }
    esiti = {o.alert_id: o for o in db.execute(select(SignalOutcome)).scalars()}
    piani = {p.alert_id: p for p in db.execute(
        select(PlanOutcome).where(PlanOutcome.legs_window_complete.is_(True))).scalars()}
    for a in db.execute(select(Alert)).scalars():
        sel = (_snap(a.snapshot).get("first_ombra") or {}).get("sel") or {}
        if not isinstance(sel.get("top30"), bool):
            continue
        g = gruppi[sel["top30"]]
        o = esiti.get(a.id)
        if o is not None and o.mkt_neutral_hit is not None:
            g["hit"].append(int(o.mkt_neutral_hit))
            g["date"].append(o.signal_date)
            g["orizzonti"].append(o.horizon_days)
        pr = piani.get(a.id)
        if pr is not None and pr.r_multiple is not None:
            g["R"].append(float(pr.r_multiple))
            g["date_R"].append(pr.signal_date)
    for c in db.execute(select(SignalCandidate).where(
            SignalCandidate.ombra.is_not(None), SignalCandidate.mkt_neutral_hit.is_not(None))).scalars():
        sel = _snap(c.ombra).get("sel") or {}
        if not isinstance(sel.get("top30"), bool):
            continue
        g = gruppi[sel["top30"]]
        g["hit"].append(int(c.mkt_neutral_hit))
        g["date"].append(c.signal_date)
        g["orizzonti"].append(c.horizon_days or 21)
    out: dict = {}
    for chiave, top in (("top30", True), ("resto", False)):
        g = gruppi[top]
        orizzonte = int(np.median(g["orizzonti"])) if g["orizzonti"] else 21
        out[chiave] = {
            "mercato": _tasso(g["hit"], g["date"], orizzonte),
            "piano_R_medio": round(float(np.mean(g["R"])), 4) if g["R"] else None,
            "piano_n": len(g["R"]),
        }
    return out


def rapporto(db) -> dict:
    """Le metriche d'addestramento dell'ultimo modello e il confronto dal vivo."""
    from app.models.modello_ombra import ModelloOmbra

    modelli = {}
    for nome in ("volatilita", "selezione"):
        r = db.execute(select(ModelloOmbra).where(ModelloOmbra.nome == nome)
                       .order_by(ModelloOmbra.addestrato_il.desc()).limit(1)).scalars().first()
        if r is not None:
            modelli[nome] = {"versione": r.versione, "addestramento": _snap(r.metriche)}
    return {"modelli": modelli, "volatilita": valuta_volatilita(db), "selezione": valuta_selezione(db)}
