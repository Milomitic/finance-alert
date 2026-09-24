"""I punteggi dei modelli in ombra per UN match, al momento dello scan.

Due numeri, fissati accanto a quelli che il motore usa davvero:

  vol.fattore   quante volte l'ATR di oggi sara' l'escursione media delle 10
                sedute successive, secondo il modello. 1,0 = «l'ATR ha ragione»,
                che e' la previsione implicita del motore.
  sel.p         la probabilita' che il match batta lo stesso piano su un titolo
                a caso lo stesso giorno; `sel.top30` se sta nel 30% piu' alto
                dei punteggi di addestramento — la quota con cui lo studio ha
                misurato il guadagno.

⚠️ Non deve MAI rompere uno scan: ogni guasto — modello assente, artefatto
illeggibile, variabile inattesa — rende un dizionario vuoto e basta. Un
punteggio in prova che ferma la produzione sarebbe il danno esatto che la prova
silenziosa esiste per evitare.
"""
from __future__ import annotations

import json
import math
import time

import numpy as np
from loguru import logger
from sqlalchemy import select

from app.ml.caratteristiche import matrice, riga_selezione, riga_volatilita
from app.ml.gbm import GBM

#: Ogni quanto rileggere i modelli dal database: il job li riaddestra una volta
#: al mese, lo scan legge un modello per titolo.
_RILEGGI_OGNI_S = 1800.0

_cache: dict = {"quando": None, "modelli": {}}


def _carica(db) -> dict:
    """{nome: {"gbm", "nomi", "versione", "soglia_top30"?}} delle ultime righe."""
    from app.models.modello_ombra import ModelloOmbra

    adesso = time.monotonic()
    if _cache["quando"] is not None and adesso - _cache["quando"] < _RILEGGI_OGNI_S:
        return _cache["modelli"]
    modelli: dict = {}
    for nome in ("volatilita", "selezione"):
        riga = db.execute(
            select(ModelloOmbra).where(ModelloOmbra.nome == nome)
            .order_by(ModelloOmbra.addestrato_il.desc(), ModelloOmbra.id.desc()).limit(1)
        ).scalars().first()
        if riga is None:
            continue
        art = json.loads(riga.artefatto)
        modelli[nome] = {
            "gbm": GBM.from_dict(art["gbm"]), "nomi": list(art["nomi"]),
            "versione": riga.versione, "soglia_top30": art.get("soglia_top30"),
        }
    _cache["quando"], _cache["modelli"] = adesso, modelli
    return modelli


def dimentica() -> None:
    """Forza la rilettura al prossimo uso (dopo un addestramento, e nei test)."""
    _cache["quando"], _cache["modelli"] = None, {}


def _r(x: float, cifre: int = 4) -> float | None:
    return round(float(x), cifre) if math.isfinite(float(x)) else None


def punteggi(
    db, *, detector: str, tone: str, horizon: str | None, strength: float | None,
    factors: dict | None, ctx: dict | None, stop_atr: float | None, rr: float | None,
) -> dict:
    """I punteggi disponibili per questo match, o {} se non ce n'e' nessuno."""
    try:
        modelli = _carica(db)
    except Exception as exc:  # noqa: BLE001 — mai rompere lo scan
        logger.debug(f"[ombra] modelli non caricati: {exc}")
        return {}
    out: dict = {}
    try:
        m = modelli.get("volatilita")
        if m is not None and ctx:
            X = matrice([riga_volatilita(ctx)], m["nomi"])
            f = float(np.exp(m["gbm"].predict(X)[0]))
            if _r(f) is not None:
                out["vol"] = {"fattore": _r(f), "versione": m["versione"]}
        m = modelli.get("selezione")
        if m is not None and ctx:
            riga = riga_selezione(detector=detector, tone=tone, horizon=horizon,
                                  strength=strength, factors=factors, ctx=ctx,
                                  stop_atr=stop_atr, rr=rr)
            X = matrice([riga], m["nomi"], zero_se_manca=("det_",))
            p = float(m["gbm"].predict(X)[0])
            if _r(p) is not None:
                sel = {"p": _r(p), "versione": m["versione"]}
                soglia = m.get("soglia_top30")
                if isinstance(soglia, (int, float)):
                    sel["top30"] = bool(p >= soglia)
                out["sel"] = sel
    except Exception as exc:  # noqa: BLE001 — mai rompere lo scan
        logger.debug(f"[ombra] punteggio saltato per {detector}: {exc}")
        return {}
    return out


def punteggi_per_match(db, m, *, ctx: dict | None, atr: float | None, close: float) -> dict:
    """Come `punteggi`, ricavando orizzonte e geometria del piano dal match.

    La geometria e' quella che il piano mostrerebbe su QUESTO istante
    (`trade_plan.costruisci_piano`), la stessa che l'addestramento ricostruisce
    sulla storia: stop in unita' di ATR e rapporto del primo target.
    """
    try:
        from app.signals.horizon import classify_horizon
        from app.signals.trade_plan import costruisci_piano

        horizon = classify_horizon(m.name, m.chain)
        stop_atr = rr = None
        if atr:
            piano = costruisci_piano(
                {"tone": m.tone, "atr": atr, "invalidation": m.invalidation, "horizon": horizon},
                close, m.name)
            if piano is not None:
                stop_atr = piano.r / atr
                rr = piano.targets[0].rr
    except Exception as exc:  # noqa: BLE001 — mai rompere lo scan
        logger.debug(f"[ombra] geometria non ricavata per {m.name}: {exc}")
        return {}
    return punteggi(db, detector=m.name, tone=m.tone, horizon=horizon,
                    strength=m.strength, factors=m.factors, ctx=ctx,
                    stop_atr=stop_atr, rr=rr)
