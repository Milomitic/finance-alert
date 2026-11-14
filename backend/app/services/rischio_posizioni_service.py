"""Il rischio delle posizioni aperte, descritto con la storia degli strumenti (FA-143).

Tutto DESCRITTIVO: distanze, frequenze passate, esposizione, una stima lineare
sotto scenario. Niente qui dice che cosa fare, e lo stesso vale per la pagina
che lo mostra: e' statistica storica dello strumento, non una previsione ne' un
consiglio.

Le funzioni pure stanno in alto e si provano senza database; l'assemblatore
(`rischio`) legge posizioni, barre e indici.

⚠️ Tre scelte che non sono dettagli.

1. **Il primo passaggio usa finestre NON sovrapposte.** Partire da ogni seduta
   darebbe migliaia di «prove» che condividono quasi tutto il percorso, e un
   intervallo stretto e falso. Con finestre disgiunte il conteggio e' piccolo e
   onesto: dieci anni a 21 sedute sono ~120 finestre.
2. **Nella stessa barra stop e target insieme contano come stop**, la stessa
   convenzione pessimista di `plan_outcome_service.corri_la_gara`: dalla barra
   giornaliera non si sa quale sia venuto prima.
3. **Lo scenario e' lineare**: esposizione x beta x movimento dell'indice. Un
   ETF a leva su un movimento di piu' giorni NON e' lineare (decadimento da
   volatilita'), e lo si dichiara a schermo.
"""
from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EtoroConto, EtoroPosizione, EtoroStrumento, Stock
from app.stats.sizing import wilson_interval

#: Sedute della gara del primo passaggio.
ORIZZONTE_GARA = 21

#: Sotto queste barre la storia non basta: si dice, non si stima.
MIN_STORIA = 252

#: Sedute per ATR e range tipico.
SEDUTE_ATR = 14
SEDUTE_RANGE = 60

#: Sedute della correlazione fra posizioni e del beta.
SEDUTE_CORRELAZIONE = 60
SEDUTE_BETA = 252

#: I fondi a leva sul loro sottostante: (etichetta, moltiplicatore giornaliero,
#: industria). L'esposizione di una posizione su SOXL e' tre volte il suo
#: valore SUI SEMICONDUTTORI, ed e' la stessa scommessa di una su un titolo del
#: settore: senza questa mappa le due si leggerebbero come cose diverse.
SOTTOSTANTI: dict[str, tuple[str, float, str]] = {
    "SOXL": ("Semiconduttori (SOX)", 3.0, "Semiconductors"),
    "SOXS": ("Semiconduttori (SOX)", -3.0, "Semiconductors"),
    "TECL": ("Tecnologia USA (XLK)", 3.0, "Technology"),
    "TECS": ("Tecnologia USA (XLK)", -3.0, "Technology"),
    "TQQQ": ("Nasdaq 100", 3.0, "Nasdaq 100"),
    "SQQQ": ("Nasdaq 100", -3.0, "Nasdaq 100"),
    "QQQ": ("Nasdaq 100", 1.0, "Nasdaq 100"),
    "UPRO": ("S&P 500", 3.0, "S&P 500"),
    "SPXL": ("S&P 500", 3.0, "S&P 500"),
    "SPXS": ("S&P 500", -3.0, "S&P 500"),
    "SPY": ("S&P 500", 1.0, "S&P 500"),
}

#: Gli indici dello scenario, fra quelli che l'app gia' scarica.
INDICI: dict[str, str] = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq Composite"}
SHOCK: tuple[float, ...] = (-0.05, -0.10)


@dataclass(frozen=True)
class Barra:
    data: str
    alto: float
    basso: float
    chiusura: float


# ─── Funzioni pure ──────────────────────────────────────────────────────────

def atr(barre: list[Barra], sedute: int = SEDUTE_ATR) -> float | None:
    """ATR semplice (media dei true range) delle ultime `sedute`."""
    if len(barre) <= sedute:
        return None
    tr = []
    for i in range(len(barre) - sedute, len(barre)):
        b, p = barre[i], barre[i - 1].chiusura
        tr.append(max(b.alto - b.basso, abs(b.alto - p), abs(b.basso - p)))
    v = sum(tr) / len(tr)
    return v if v > 0 else None


def range_tipico(barre: list[Barra], sedute: int = SEDUTE_RANGE) -> float | None:
    """Mediana dell'escursione giornaliera in percentuale del prezzo."""
    righe = [(b.alto - b.basso) / b.chiusura for b in barre[-sedute:] if b.chiusura > 0]
    if len(righe) < 10:
        return None
    v = float(np.median(righe))
    return v if v > 0 else None


def distanza_dallo_stop(
    prezzo: float, stop: float | None, lato: str, atr_valore: float | None,
    range_pct: float | None,
) -> dict:
    """Quanto manca allo stop: in %, in ATR e in «sedute tipiche» (distanza
    divisa per l'escursione mediana di una seduta). Negativa se lo stop e'
    gia' oltrepassato. Campi a None quando la grandezza non c'e'."""
    if stop is None or stop <= 0 or prezzo <= 0:
        return {"pct": None, "atr": None, "sedute_tipiche": None}
    d = (prezzo - stop) if lato == "long" else (stop - prezzo)
    pct = d / prezzo
    return {
        "pct": pct,
        "atr": d / atr_valore if atr_valore else None,
        "sedute_tipiche": pct / range_pct if range_pct else None,
    }


def primo_passaggio(
    barre: list[Barra], lato: str, stop_pct: float, target_pct: float | None,
    orizzonte: int = ORIZZONTE_GARA,
) -> dict | None:
    """In quante finestre storiche il prezzo ha toccato prima lo stop, prima
    il target, o nessuno dei due entro `orizzonte` sedute.

    Ogni finestra parte da una chiusura e mette stop e target alle STESSE
    distanze percentuali di oggi. Finestre disgiunte; stop e target nella stessa
    barra = stop. None quando la storia non basta o lo stop non ha distanza."""
    if stop_pct is None or stop_pct <= 0 or len(barre) < MIN_STORIA:
        return None
    lungo = lato == "long"
    stop_n = target_n = nessuno = 0
    i = 0
    while i + orizzonte < len(barre):
        ingresso = barre[i].chiusura
        if ingresso <= 0:
            i += orizzonte
            continue
        livello_stop = ingresso * (1 - stop_pct) if lungo else ingresso * (1 + stop_pct)
        livello_target = None
        if target_pct is not None and target_pct > 0:
            livello_target = ingresso * (1 + target_pct) if lungo else ingresso * (1 - target_pct)
        esito = "nessuno"
        for b in barre[i + 1: i + 1 + orizzonte]:
            colpo_stop = b.basso <= livello_stop if lungo else b.alto >= livello_stop
            colpo_target = livello_target is not None and (
                b.alto >= livello_target if lungo else b.basso <= livello_target)
            if colpo_stop:
                esito = "stop"
                break
            if colpo_target:
                esito = "target"
                break
        if esito == "stop":
            stop_n += 1
        elif esito == "target":
            target_n += 1
        else:
            nessuno += 1
        i += orizzonte
    n = stop_n + target_n + nessuno
    if n == 0:
        return None
    lo, hi = wilson_interval(stop_n, n)
    return {
        "finestre": n, "stop": stop_n, "target": target_n, "nessuno": nessuno,
        "orizzonte": orizzonte,
        "stop_pct_ci": (round(lo * 100, 1), round(hi * 100, 1)),
        "dal": barre[0].data, "al": barre[-1].data,
    }


def rendimenti(barre: list[Barra]) -> dict[str, float]:
    """{data: rendimento giornaliero} sulle chiusure."""
    return {
        barre[i].data: barre[i].chiusura / barre[i - 1].chiusura - 1.0
        for i in range(1, len(barre)) if barre[i - 1].chiusura > 0
    }


def beta(titolo: dict[str, float], indice: dict[str, float], sedute: int = SEDUTE_BETA) -> float | None:
    """Beta sulle date comuni, ultime `sedute`; None sotto 120 coppie."""
    comuni = sorted(set(titolo) & set(indice))[-sedute:]
    if len(comuni) < 120:
        return None
    x = np.array([indice[d] for d in comuni])
    y = np.array([titolo[d] for d in comuni])
    v = float(np.var(x, ddof=1))
    return float(np.cov(x, y, ddof=1)[0, 1] / v) if v > 0 else None


def correlazioni(serie: dict[str, dict[str, float]], sedute: int = SEDUTE_CORRELAZIONE) -> dict:
    """Matrice di correlazione dei rendimenti sulle ultime `sedute` comuni.

    {"titoli": [...], "matrice": [[...]], "sedute": n}; None sotto 30 sedute
    comuni o con meno di due titoli."""
    titoli = sorted(serie)
    if len(titoli) < 2:
        return {"titoli": titoli, "matrice": None, "sedute": 0}
    comuni = sorted(set.intersection(*(set(serie[t]) for t in titoli)))[-sedute:]
    if len(comuni) < 30:
        return {"titoli": titoli, "matrice": None, "sedute": len(comuni)}
    m = np.array([[serie[t][d] for d in comuni] for t in titoli])
    c = np.corrcoef(m)
    return {"titoli": titoli, "matrice": [[round(float(v), 3) for v in r] for r in c],
            "sedute": len(comuni)}


def posizioni_effettive(pesi: list[float], matrice: list[list[float]] | None) -> float | None:
    """Quante posizioni indipendenti valgono, dati i pesi assoluti e la
    correlazione: (somma dei pesi)^2 / somma_ij w_i w_j rho_ij. Una sola
    posizione = 1; N posizioni perfettamente correlate = 1; N indipendenti di
    pari peso = N."""
    if matrice is None or not pesi:
        return None
    w = np.abs(np.asarray(pesi, dtype=float))
    den = float(w @ np.asarray(matrice) @ w)
    return round(float(w.sum() ** 2 / den), 2) if den > 0 else None


# ─── Le barre ──────────────────────────────────────────────────────────────

_CACHE_YAHOO: dict[str, tuple[float, list[Barra]]] = {}
_TTL_YAHOO = 12 * 3600


def _barre_catalogo(db: Session, stock_id: int) -> list[Barra]:
    from app.services.plan_outcome_service import _tutte_le_barre  # noqa: PLC0415
    return [Barra(b.data, b.alto, b.basso, b.chiusura) for b in _tutte_le_barre(db, stock_id)]


def _barre_yahoo(simbolo: str) -> list[Barra]:
    """Per gli strumenti eToro che non stanno nel catalogo (TECL, per esempio):
    dieci anni da Yahoo, in memoria per 12 ore. Best-effort."""
    adesso = time.monotonic()
    c = _CACHE_YAHOO.get(simbolo)
    if c and adesso - c[0] < _TTL_YAHOO:
        return c[1]
    try:
        from app.services.ohlcv_service import _yf_download  # noqa: PLC0415
        df = _yf_download([simbolo], period="10y")
        if df is None or df.empty:
            return []
        if simbolo in getattr(df.columns, "levels", [[]])[0]:
            df = df[simbolo]
        df = df.dropna(subset=["High", "Low", "Close"])
        barre = [Barra(str(i)[:10], float(r.High), float(r.Low), float(r.Close))
                 for i, r in df.iterrows()]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[rischio] storia di {simbolo} non disponibile: {e}")
        return []
    _CACHE_YAHOO[simbolo] = (adesso, barre)
    return barre


def _barre_indice(simbolo: str) -> list[Barra]:
    try:
        from app.services import market_detail_service  # noqa: PLC0415
        d = market_detail_service.get_detail(simbolo, "1d")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[rischio] indice {simbolo} non disponibile: {e}")
        return []
    if d is None:
        return []
    return [Barra(str(b.date)[:10], b.high, b.low, b.close) for b in d.bars]


# ─── L'assemblatore ────────────────────────────────────────────────────────

@dataclass
class _Strumento:
    chiave: str
    ticker: str
    nome: str | None
    settore: str | None
    industria: str | None
    barre: list[Barra] = field(default_factory=list)


def rischio(db: Session) -> dict:
    """Il quadro del rischio delle posizioni aperte. Vedi il modulo."""
    righe = db.execute(
        select(EtoroPosizione, EtoroStrumento, Stock)
        .join(EtoroStrumento, EtoroStrumento.instrument_id == EtoroPosizione.instrument_id)
        .outerjoin(Stock, Stock.id == EtoroStrumento.stock_id)
        .where(EtoroPosizione.chiusa_il.is_(None))
    ).all()
    conto = db.get(EtoroConto, 1)
    valore_conto = conto.valore_totale if conto else None

    strumenti: dict[int, _Strumento] = {}
    for _p, s, st in righe:
        if s.instrument_id in strumenti:
            continue
        ticker = (st.ticker if st else None) or s.simbolo or f"#{s.instrument_id}"
        strumenti[s.instrument_id] = _Strumento(
            chiave=ticker, ticker=ticker, nome=(st.name if st else None) or s.nome,
            settore=st.sector if st else None, industria=st.industry if st else None,
            barre=_barre_catalogo(db, st.id) if st else (_barre_yahoo(s.simbolo) if s.simbolo else []),
        )

    indici = {sym: rendimenti(_barre_indice(sym)) for sym in INDICI}
    posizioni = []
    gare: dict[tuple, dict | None] = {}
    esposizione_sottostante: dict[str, float] = defaultdict(float)
    esposizione_settore: dict[str, float] = defaultdict(float)
    scenario: dict[str, dict[float, float]] = {sym: dict.fromkeys(SHOCK, 0.0) for sym in INDICI}
    scenario_coperto: dict[str, float] = dict.fromkeys(INDICI, 0.0)
    esposizione_totale = 0.0
    betas: dict[str, dict[str, float | None]] = {}

    for p, s, _st in righe:
        stru = strumenti[s.instrument_id]
        barre = stru.barre
        prezzo = p.prezzo_corrente or (barre[-1].chiusura if barre else None)
        a = atr(barre)
        rng = range_tipico(barre)
        segno = 1.0 if p.lato == "long" else -1.0
        esp = float(p.esposizione_usd or 0.0)
        esposizione_totale += abs(esp)

        dist = distanza_dallo_stop(prezzo or 0.0, p.stop, p.lato, a, rng)
        target_pct = None
        if p.target and prezzo:
            target_pct = ((p.target - prezzo) if p.lato == "long" else (prezzo - p.target)) / prezzo
        gara = None
        if dist["pct"] is not None and dist["pct"] > 0:
            chiave = (stru.chiave, p.lato, round(dist["pct"], 4),
                      round(target_pct, 4) if target_pct and target_pct > 0 else None)
            if chiave not in gare:
                gare[chiave] = primo_passaggio(
                    barre, p.lato, dist["pct"], target_pct if target_pct and target_pct > 0 else None)
            gara = gare[chiave]

        etichetta, molt, industria = SOTTOSTANTI.get(stru.ticker, (stru.ticker, 1.0, stru.industria))
        esposizione_sottostante[etichetta] += segno * esp * molt
        esposizione_settore[industria or stru.settore or "Non classificato"] += segno * esp * abs(molt)

        if stru.chiave not in betas:
            r = rendimenti(barre)
            betas[stru.chiave] = {sym: beta(r, indici[sym]) for sym in INDICI}
        for sym in INDICI:
            b = betas[stru.chiave][sym]
            if b is None:
                continue
            scenario_coperto[sym] += abs(esp)
            for sh in SHOCK:
                scenario[sym][sh] += segno * esp * b * sh

        posizioni.append({
            "position_id": p.position_id, "ticker": stru.ticker, "nome": stru.nome,
            "lato": p.lato, "leva": p.leva, "prezzo": prezzo, "stop": p.stop, "target": p.target,
            "esposizione_usd": esp, "margine_usd": p.margine_usd,
            "distanza_stop_pct": _pct(dist["pct"]),
            "distanza_stop_atr": _r(dist["atr"], 2),
            "distanza_stop_sedute": _r(dist["sedute_tipiche"], 1),
            "distanza_target_pct": _pct(target_pct),
            "primo_passaggio": gara,
            "storia_barre": len(barre),
            "beta": {INDICI[k]: _r(v, 2) for k, v in betas[stru.chiave].items()},
        })

    serie = {k: rendimenti(v.barre) for k, v in
             {s.chiave: s for s in strumenti.values()}.items() if v.barre}
    corr = correlazioni(serie)
    pesi_per_titolo: dict[str, float] = defaultdict(float)
    for p in posizioni:
        pesi_per_titolo[p["ticker"]] += abs(p["esposizione_usd"])
    eff = posizioni_effettive([pesi_per_titolo[t] for t in corr["titoli"]], corr["matrice"]) \
        if corr["matrice"] else (1.0 if len(pesi_per_titolo) == 1 else None)

    return {
        "calcolato_il": datetime.now(UTC).isoformat(),
        "valore_conto": valore_conto,
        "esposizione_totale": round(esposizione_totale, 2),
        "leva_effettiva": round(esposizione_totale / valore_conto, 2) if valore_conto else None,
        "posizioni": posizioni,
        "per_sottostante": _ordina(esposizione_sottostante),
        "per_settore": _ordina(esposizione_settore),
        "scenario": [
            {"indice": INDICI[sym], "shock_pct": sh * 100, "pnl_usd": round(v, 2),
             "esposizione_coperta": round(scenario_coperto[sym], 2)}
            for sym in INDICI for sh, v in scenario[sym].items()
        ],
        "correlazione": corr,
        "posizioni_effettive": eff,
    }


def _ordina(d: dict[str, float]) -> list[dict]:
    return [{"nome": k, "usd": round(v, 2)} for k, v in sorted(d.items(), key=lambda kv: -abs(kv[1]))]


def _pct(v: float | None) -> float | None:
    return None if v is None or not math.isfinite(v) else round(v * 100, 2)


def _r(v: float | None, n: int) -> float | None:
    return None if v is None or not math.isfinite(v) else round(v, n)
