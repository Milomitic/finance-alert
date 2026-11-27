"""La pagina Mercati oltre la fotografia del giorno (FA-184, FA-185).

    panoramica()          i rendimenti per periodo di ogni strumento del
                          paniere, alla chiusura giornaliera
    statistiche(simbolo)  rendimenti, volatilita', distanza dai massimi,
                          cali e calendario mensile di uno strumento

I numeri vengono da `app/stats` (proprietari unici, condivisi con lo Studio) e
le serie dal dettaglio mercati (`market_detail_service`, storia completa in
cache e scaldata ogni cinque minuti dal job di FA-181).

⚠️ La variazione di OGGI non sta qui: e' quella viva del paniere. Questi
numeri sono «alla chiusura del» giorno che dichiarano, e lo dicono.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from loguru import logger

from app.core.cache_fresca import CacheFresca
from app.stats import calendario as cal
from app.stats import drawdown as dd
from app.stats import rendimenti as rd

#: Sedute in un anno, per strumento: le cripto scambiano tutti i giorni.
SEDUTE_ANNO = {"crypto": 365}
SEDUTE_52S = {"crypto": 365}


def _serie(simbolo: str) -> tuple[list[date], list[float]] | None:
    from app.services import market_detail_service  # noqa: PLC0415

    d = market_detail_service.get_detail(simbolo, "1d")
    if d is None or not d.bars:
        return None
    date_: list[date] = []
    chiusure: list[float] = []
    for b in d.bars:
        g = b.date.date() if isinstance(b.date, datetime) else b.date
        if b.close and b.close > 0:
            date_.append(g)
            chiusure.append(float(b.close))
    return (date_, chiusure) if len(chiusure) >= 2 else None


def _anno(categoria: str) -> int:
    return SEDUTE_ANNO.get(categoria, 252)


def riga_panoramica(simbolo: str, nome: str, categoria: str, bandiera: str | None) -> dict | None:
    s = _serie(simbolo)
    if s is None:
        return None
    date_, c = s
    anno = _anno(categoria)
    s52 = SEDUTE_52S.get(categoria, 252)
    massimo = rd.distanza_dal_massimo(date_, c, s52)
    minimo = rd.distanza_dal_minimo(date_, c, s52)
    posizione = None
    if massimo and minimo and massimo["valore"] > minimo["valore"]:
        posizione = (c[-1] - minimo["valore"]) / (massimo["valore"] - minimo["valore"])
    ema200 = rd.ema_ultima(c, 200)
    return {
        "symbol": simbolo, "name": nome, "category": categoria, "flag": bandiera,
        "ultima_chiusura": c[-1], "data_chiusura": date_[-1].isoformat(),
        "rendimenti": rd.rendimenti_per_periodo(date_, c),
        "massimo_52s": massimo, "minimo_52s": minimo, "posizione_52s": posizione,
        "dal_massimo_storico": rd.distanza_dal_massimo(date_, c),
        "vol_20g": rd.volatilita_annua(c, 20, anno),
        "vol_1a": rd.volatilita_annua(c, min(anno, len(c) - 1), anno),
        "distanza_ema200": (c[-1] / ema200 - 1.0) if ema200 else None,
    }


def calcola_panoramica() -> dict:
    from app.api.market import LIVE_ASSET_DEFINITIONS  # noqa: PLC0415

    righe = []
    for simbolo, nome, categoria, bandiera, _future in LIVE_ASSET_DEFINITIONS:
        try:
            r = riga_panoramica(simbolo, nome, categoria, bandiera)
        except Exception as e:  # noqa: BLE001 — uno strumento non ferma gli altri
            logger.warning(f"[panoramica] {simbolo}: {e}")
            r = None
        if r is not None:
            righe.append(r)
    ultima = max((r["data_chiusura"] for r in righe), default=None)
    return {"alla_chiusura_del": ultima, "strumenti": righe}


#: Cinque minuti: le serie giornaliere cambiano a fine seduta, e il job dei
#: dettagli le tiene calde con la stessa cadenza.
CACHE_PANORAMICA: CacheFresca[dict] = CacheFresca("panoramica", 300, calcola_panoramica, eta_limite_s=30 * 60)


# ─── FA-186: la composizione di un indice ──────────────────────────────────

#: Il simbolo di mercato -> (codice dell'indice nel catalogo, nota da
#: dichiarare). Solo gli indici di cui il catalogo ha i costituenti.
INDICE_DEL_MERCATO: dict[str, tuple[str, str | None]] = {
    "^GSPC": ("SP500", None),
    "^DJI": ("DJI", None),
    "^IXIC": ("NDX", "I titoli del Nasdaq-100, non i circa 3.000 del Composite."),
    "^STOXX50E": ("EUSTX50", None),
    "FTSEMIB.MI": ("FTSEMIB", None),
    "^HSI": ("HSI30", None),
    "^N225": ("N225", "I titoli principali del Nikkei presenti nel catalogo, non tutti i 225."),
}
#: Indici pesati sul PREZZO: per loro un «contributo stimato sulla
#: capitalizzazione» sarebbe sbagliato, quindi non si calcola.
PESATI_SUL_PREZZO = frozenset({"DJI", "N225"})
QUANTI_ESTREMI = 5


def composizione(db, simbolo: str) -> dict | None:
    """L'ampiezza, i settori, i migliori e i peggiori dei costituenti di un
    indice, alla scansione piu' recente. None se lo strumento non ha
    costituenti nel catalogo."""
    from sqlalchemy import select  # noqa: PLC0415

    from app.models import Index, Stock, StockIndex  # noqa: PLC0415
    from app.models.stock_metrics import StockMetrics  # noqa: PLC0415
    from app.services import market_stats_service  # noqa: PLC0415
    from app.services.fx_service import to_usd  # noqa: PLC0415

    voce = INDICE_DEL_MERCATO.get(simbolo)
    if voce is None:
        return None
    codice, nota = voce
    indice = db.execute(select(Index).where(Index.code == codice)).scalars().first()
    if indice is None:
        return None
    righe = db.execute(
        select(Stock.id, Stock.ticker, Stock.name, Stock.sector, Stock.market_cap, Stock.currency,
               StockMetrics.change_pct, StockMetrics.computed_at)
        .join(StockIndex, StockIndex.stock_id == Stock.id)
        .outerjoin(StockMetrics, StockMetrics.stock_id == Stock.id)
        .where(StockIndex.index_id == indice.id)
    ).all()
    if not righe:
        return None

    _snap, payload = market_stats_service.get_latest_snapshot_payload(db)
    amp = next((i for i in (payload or {}).get("by_index", []) if i.get("code") == codice), None)

    pesato_cap = codice not in PESATI_SUL_PREZZO
    cap = {r.id: to_usd(r.market_cap, r.currency) for r in righe if r.market_cap}
    cap_totale = sum(v for v in cap.values() if v) or None

    titoli = []
    for r in righe:
        peso = (cap.get(r.id) or 0) / cap_totale if (pesato_cap and cap_totale) else None
        titoli.append({
            "ticker": r.ticker, "nome": r.name, "settore": r.sector or "Altro",
            "var_pct": r.change_pct, "peso_pct": peso * 100 if peso is not None else None,
            "contributo_pp": (peso * r.change_pct) if (peso is not None and r.change_pct is not None) else None,
        })
    con_var = [t for t in titoli if t["var_pct"] is not None]
    ordinati = sorted(con_var, key=lambda t: t["var_pct"], reverse=True)

    per_settore: dict[str, list[dict]] = {}
    for t in titoli:
        per_settore.setdefault(t["settore"], []).append(t)
    settori = []
    for nome, ts in per_settore.items():
        var = [t["var_pct"] for t in ts if t["var_pct"] is not None]
        pesi = [t["peso_pct"] for t in ts if t["peso_pct"] is not None]
        settori.append({"settore": nome, "titoli": len(ts),
                        "var_media_pct": sum(var) / len(var) if var else None,
                        "peso_pct": sum(pesi) if (pesato_cap and pesi) else None})
    settori.sort(key=lambda x: (x["peso_pct"] if x["peso_pct"] is not None else x["titoli"]), reverse=True)

    calcolato = max((r.computed_at for r in righe if r.computed_at), default=None)
    return {
        "indice": {"code": codice, "nome": indice.name, "titoli_nel_catalogo": len(righe), "nota": nota,
                   "pesato_sul_prezzo": not pesato_cap},
        "ampiezza": {
            "avanzano": amp.get("advancers", 0) if amp else sum(1 for t in con_var if t["var_pct"] > 0),
            "scendono": amp.get("decliners", 0) if amp else sum(1 for t in con_var if t["var_pct"] < 0),
            "sopra_ema50_pct": amp.get("pct_above_ema50") if amp else None,
            "sopra_ema200_pct": amp.get("pct_above_ema200") if amp else None,
            "nuovi_massimi_52s": amp.get("new_52w_highs", 0) if amp else 0,
            "nuovi_minimi_52s": amp.get("new_52w_lows", 0) if amp else 0,
            "rsi_sopra_70": amp.get("rsi_overbought_count", 0) if amp else 0,
            "rsi_sotto_30": amp.get("rsi_oversold_count", 0) if amp else 0,
            "var_media_pct": amp.get("avg_change_pct") if amp else None,
        },
        "settori": settori,
        "migliori": ordinati[:QUANTI_ESTREMI],
        "peggiori": list(reversed(ordinati[-QUANTI_ESTREMI:])) if len(ordinati) > QUANTI_ESTREMI else [],
        "alla_scansione_del": calcolato.isoformat() if calcolato else None,
    }


# ─── FA-187: il confronto normalizzato ─────────────────────────────────────

#: I periodi del confronto, in giorni di calendario all'indietro.
PERIODI_CONFRONTO: dict[str, int | None] = {
    "1m": 30, "3m": 91, "6m": 182, "ytd": None, "1a": 365, "3a": 365 * 3, "5a": 365 * 5, "10a": 365 * 10,
}
MAX_SIMBOLI = 6
#: Oltre questi punti si tiene un giorno ogni k (piu' l'ultimo): un grafico
#: largo 800 px non disegna 2.600 punti diversi, e la risposta resta piccola.
MAX_PUNTI = 800


class SimboloSconosciuto(Exception):
    def __init__(self, simbolo: str):
        super().__init__(simbolo)
        self.simbolo = simbolo


def confronto(db, simboli: list[str], periodo: str) -> dict:
    """Le serie dei simboli in base 100 dalla prima data comune del periodo.

    Allineamento: l'unione delle date dal punto di partenza, con l'ultima
    chiusura nota portata avanti (le cripto scambiano il sabato, gli indici
    no: il sabato un indice «resta» al venerdi'). Il punto di partenza e' la
    prima data, dentro il periodo, in cui TUTTI hanno una chiusura: cosi'
    ogni linea parte da 100 lo stesso giorno."""
    from app.services import studio_service  # noqa: PLC0415

    serie: dict[str, dict[date, float]] = {}
    for s in simboli:
        sr = studio_service.serie_di(db, s)
        if sr is None or len(sr.chiusure) < 2:
            raise SimboloSconosciuto(s)
        serie[s] = {g: c for g, c in zip(sr.date, sr.chiusure, strict=True) if c > 0}
    ultima = min(max(v) for v in serie.values())
    giorni = PERIODI_CONFRONTO[periodo]
    inizio = date(ultima.year - 1, 12, 31) if giorni is None else ultima - timedelta(days=giorni)
    tutte = sorted({g for v in serie.values() for g in v if inizio <= g <= ultima})
    # La prima data in cui tutti hanno una chiusura nota (alla data o prima).
    # Ricerca binaria: ^GSPC ha 25 mila sedute dal 1927, e una scansione
    # lineare per ogni data candidata costava centinaia di milioni di
    # confronti quando un simbolo comincia tardi (ETH su dieci anni).
    from bisect import bisect_right  # noqa: PLC0415

    ordinate = {s: sorted(v) for s, v in serie.items()}

    def nota(s: str, g: date) -> float | None:
        i = bisect_right(ordinate[s], g)
        return serie[s][ordinate[s][i - 1]] if i else None

    partenza = next((g for g in tutte if all(nota(s, g) is not None for s in simboli)), None)
    if partenza is None:
        return {"date": [], "serie": {s: [] for s in simboli}, "riepilogo": {}, "dal": None, "al": None}
    giorni_validi = [g for g in tutte if g >= partenza]
    valori: dict[str, list[float]] = {s: [] for s in simboli}
    ultimo: dict[str, float] = {s: nota(s, partenza) for s in simboli}
    base = dict(ultimo)
    for g in giorni_validi:
        for s in simboli:
            c = serie[s].get(g)
            if c is not None:
                ultimo[s] = c
            valori[s].append(ultimo[s] / base[s] * 100.0)
    riepilogo = {}
    for s in simboli:
        v = valori[s]
        picco, peggiore = v[0], 0.0
        for x in v:
            picco = max(picco, x)
            peggiore = min(peggiore, x / picco - 1.0)
        riepilogo[s] = {"rendimento": v[-1] / 100.0 - 1.0, "peggior_calo": peggiore}
    passo = max(1, -(-len(giorni_validi) // MAX_PUNTI))
    indici = list(range(0, len(giorni_validi), passo))
    if indici[-1] != len(giorni_validi) - 1:
        indici.append(len(giorni_validi) - 1)
    return {
        "date": [giorni_validi[i].isoformat() for i in indici],
        "serie": {s: [round(valori[s][i], 3) for i in indici] for s in simboli},
        "riepilogo": riepilogo,
        "dal": partenza.isoformat(), "al": giorni_validi[-1].isoformat(),
    }


def statistiche(simbolo: str, categoria: str) -> dict | None:
    s = _serie(simbolo)
    if s is None:
        return None
    date_, c = s
    anno = _anno(categoria)
    s52 = SEDUTE_52S.get(categoria, 252)
    return {
        "symbol": simbolo, "data_chiusura": date_[-1].isoformat(), "dal": date_[0].isoformat(),
        "rendimenti": rd.rendimenti_per_periodo(date_, c),
        "vol_20g": rd.volatilita_annua(c, 20, anno),
        "vol_1a": rd.volatilita_annua(c, min(anno, len(c) - 1), anno),
        "massimo_52s": rd.distanza_dal_massimo(date_, c, s52),
        "minimo_52s": rd.distanza_dal_minimo(date_, c, s52),
        "dal_massimo_storico": rd.distanza_dal_massimo(date_, c),
        "calo_corrente": dd.calo_corrente(date_, c),
        "calo_massimo_1a": dd.calo_massimo(date_, c, s52),
        "calo_massimo_5a": dd.calo_massimo(date_, c, s52 * 5),
        "calo_massimo_storico": dd.calo_massimo(date_, c),
        "calendario": cal.calendario_mensile(date_, c),
    }
