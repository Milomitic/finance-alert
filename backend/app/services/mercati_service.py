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

from datetime import date, datetime

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
