"""Statistica storica a schermo (FA-157): tre domande sul passato di un simbolo.

    dopo_movimento   che cosa e' successo nelle H sedute dopo una variazione
                     di almeno X% in N sedute
    stagionalita     il rendimento per mese dell'anno e per giorno della
                     settimana
    evento           il percorso medio attorno alle trimestrali del titolo o
                     ai rilasci di una serie macro

⚠️ Ogni risposta porta le stesse quattro cose, ed e' la regola di onesta' di
tutto il progetto applicata a una domanda libera:

1. i CASI e le FINESTRE INDIPENDENTI (`independent_blocks`): dieci giorni di
   fila che soddisfano la condizione sono un episodio, non dieci;
2. l'INTERVALLO della media, largo quanto le finestre indipendenti giustificano
   (`mean_interval`), o None quando sono meno di due;
3. il CASO BASE: la stessa misura su tutte le finestre della stessa lunghezza.
   «Dopo un calo del 10% il titolo ha fatto +3% in un mese» non dice niente se
   in un mese qualunque ha fatto +2,5%;
4. nessun verdetto di previsione. Lo studio descrive.

Una serie costante rende zero casi e non una media (FA-157, test).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.stats.media import mean_interval
from app.stats.sizing import independent_blocks

MODELLI = ("dopo_movimento", "stagionalita", "evento")
MESI = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")
GIORNI = ("lun", "mar", "mer", "gio", "ven")


@dataclass(frozen=True)
class Serie:
    date: list[date]
    chiusure: list[float]


def _misura(valori: list[float], date_: list[date], orizzonte: int) -> dict:
    """Media, mediana, quota positiva, finestre indipendenti e intervallo."""
    if not valori:
        return {"casi": 0, "finestre": 0, "media": None, "mediana": None,
                "quota_positivi": None, "intervallo": None}
    finestre = independent_blocks(date_, orizzonte)
    iv = mean_interval(valori, effective_n=finestre)
    return {
        "casi": len(valori), "finestre": finestre,
        "media": mean(valori), "mediana": median(valori),
        "quota_positivi": sum(1 for v in valori if v > 0) / len(valori),
        "intervallo": list(iv) if iv else None,
    }


def dopo_movimento(s: Serie, *, sedute: int, soglia_pct: float, orizzonte: int) -> dict:
    """Le H sedute dopo ogni giorno in cui la variazione delle N sedute
    precedenti e' stata almeno `soglia_pct` (negativa = un calo almeno pari)."""
    c, d = s.chiusure, s.date
    soglia = soglia_pct / 100.0
    casi, date_casi, base, date_base = [], [], [], []
    for t in range(sedute, len(c) - orizzonte):
        if c[t] <= 0 or c[t - sedute] <= 0:
            continue
        avanti = c[t + orizzonte] / c[t] - 1.0
        base.append(avanti)
        date_base.append(d[t])
        mossa = c[t] / c[t - sedute] - 1.0
        if (soglia < 0 and mossa <= soglia) or (soglia > 0 and mossa >= soglia):
            casi.append(avanti)
            date_casi.append(d[t])
    out = {"condizione": _misura(casi, date_casi, orizzonte),
           "base": _misura(base, date_base, orizzonte),
           "parametri": {"sedute": sedute, "soglia_pct": soglia_pct, "orizzonte": orizzonte}}
    m, b = out["condizione"]["media"], out["base"]["media"]
    out["differenza"] = m - b if m is not None and b is not None else None
    return out


def stagionalita(s: Serie) -> dict:
    """Rendimento per mese (da fine mese a fine mese) e per giorno della
    settimana (seduta su seduta). Mesi e giorni diversi sono finestre
    disgiunte: ogni osservazione e' indipendente dalle altre del suo gruppo."""
    fine_mese: dict[tuple[int, int], float] = {}
    for g, c in zip(s.date, s.chiusure, strict=True):
        fine_mese[(g.year, g.month)] = c
    chiavi = sorted(fine_mese)
    per_mese: dict[int, list[float]] = defaultdict(list)
    tutti_mesi = []
    for prima, dopo in zip(chiavi, chiavi[1:], strict=False):
        if fine_mese[prima] > 0:
            r = fine_mese[dopo] / fine_mese[prima] - 1.0
            per_mese[dopo[1]].append(r)
            tutti_mesi.append(r)
    per_giorno: dict[int, list[float]] = defaultdict(list)
    tutti_giorni = []
    for i in range(1, len(s.chiusure)):
        if s.chiusure[i - 1] > 0 and s.date[i].weekday() < 5:
            r = s.chiusure[i] / s.chiusure[i - 1] - 1.0
            per_giorno[s.date[i].weekday()].append(r)
            tutti_giorni.append(r)

    def gruppo(valori: list[float]) -> dict:
        iv = mean_interval(valori, effective_n=len(valori)) if valori else None
        return {"casi": len(valori), "finestre": len(valori),
                "media": mean(valori) if valori else None,
                "quota_positivi": sum(1 for v in valori if v > 0) / len(valori) if valori else None,
                "intervallo": list(iv) if iv else None}

    return {
        "mesi": [{"mese": MESI[m - 1], **gruppo(per_mese.get(m, []))} for m in range(1, 13)],
        "base_mesi": gruppo(tutti_mesi),
        "giorni": [{"giorno": GIORNI[g], **gruppo(per_giorno.get(g, []))} for g in range(5)],
        "base_giorni": gruppo(tutti_giorni),
    }


PRIMA, DOPO = 5, 10


def evento(s: Serie, date_eventi: list[date], *, orizzonte: int = 5) -> dict:
    """Il percorso medio da PRIMA sedute prima a DOPO sedute dopo ogni evento,
    in rendimento dalla chiusura della seduta precedente all'evento; e la
    misura a `orizzonte` sedute contro il caso base."""
    c = s.chiusure
    percorsi, a_h, date_h = [], [], []
    for g in sorted(set(date_eventi)):
        # La seduta dell'evento: la prima in data g o dopo (un annuncio di
        # sabato reagisce il lunedi').
        t0 = _primo_da(s.date, g)
        if t0 - 1 - PRIMA < 0 or t0 + DOPO >= len(c) or c[t0 - 1] <= 0:
            continue
        rif = c[t0 - 1]
        percorsi.append([c[t0 + k] / rif - 1.0 for k in range(-PRIMA - 1, DOPO + 1)])
        a_h.append(c[t0 - 1 + orizzonte] / rif - 1.0)
        date_h.append(g)
    base, date_base = [], []
    for t in range(1, len(c) - orizzonte):
        if c[t - 1] > 0:
            base.append(c[t - 1 + orizzonte] / c[t - 1] - 1.0)
            date_base.append(s.date[t])
    percorso = [
        {"seduta": k, "media": mean(p[k + PRIMA + 1] for p in percorsi)}
        for k in range(-PRIMA - 1, DOPO + 1)
    ] if percorsi else []
    return {"percorso": percorso, "a_orizzonte": _misura(a_h, date_h, orizzonte),
            "base": _misura(base, date_base, orizzonte), "orizzonte": orizzonte}


def _primo_da(date_: list[date], g: date) -> int:
    lo, hi = 0, len(date_)
    while lo < hi:
        m = (lo + hi) // 2
        if date_[m] < g:
            lo = m + 1
        else:
            hi = m
    return lo


# ─── Le fonti ──────────────────────────────────────────────────────────────

def serie_di(db: Session, simbolo: str) -> Serie | None:
    """Le chiusure del simbolo: dal catalogo per un titolo, dal dettaglio
    mercati per un indice o una materia prima."""
    from app.models import OhlcvDaily, Stock  # noqa: PLC0415

    t = simbolo.strip().upper()
    s = db.execute(select(Stock).where(Stock.ticker == t).limit(1)).scalars().first()
    if s is not None:
        righe = db.execute(select(OhlcvDaily.date, OhlcvDaily.close)
                           .where(OhlcvDaily.stock_id == s.id).order_by(OhlcvDaily.date)).all()
        d = [g if isinstance(g, date) else date.fromisoformat(str(g)[:10]) for g, _ in righe]
        return Serie(d, [float(c) for _, c in righe]) if righe else None
    from app.services import rischio_posizioni_service as rp  # noqa: PLC0415

    barre = rp._barre_indice(t)
    if not barre:
        return None
    return Serie([date.fromisoformat(b.data[:10]) for b in barre], [b.chiusura for b in barre])


def date_trimestrali(simbolo: str) -> list[date]:
    from app.services import stock_fundamentals_service as sfs  # noqa: PLC0415

    f = sfs._CACHE.get(simbolo.strip().upper())
    out = []
    for e in (f.earnings if f is not None else []):
        if e.eps_reported is None:
            continue
        try:
            out.append(date.fromisoformat(str(e.date)[:10]))
        except ValueError:
            continue
    return out


def date_macro(db: Session, serie: str) -> list[date]:
    from app.models import MacroReleaseDate, MacroSeries  # noqa: PLC0415

    return list(db.execute(
        select(MacroReleaseDate.date).join(MacroSeries, MacroSeries.id == MacroReleaseDate.series_id)
        .where(MacroSeries.fred_series_id == serie).order_by(MacroReleaseDate.date)
    ).scalars())
