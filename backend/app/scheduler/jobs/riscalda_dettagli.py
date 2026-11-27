"""Tiene calde le pagine di dettaglio che si aprono davvero (FA-181).

Ogni cinque minuti, e all'avvio: il dettaglio giornaliero dei titoli seguiti
(posizioni e preferiti) e quello degli strumenti del paniere della home.
Misurato il 27/11: un titolo a freddo fino a 3 s, un indice 3,7 s; dalla
memoria qualche decina di millisecondi. Cinque minuti stanno dentro i 15 della
cache delle barre e dell'eta' limite della cache dei dettagli, quindi una
pagina seguita non e' mai fredda. Un guasto su un titolo non ferma gli altri.
"""
from __future__ import annotations

from loguru import logger


def titoli_da_riscaldare() -> list[str]:
    from sqlalchemy import select  # noqa: PLC0415

    from app.core import db as core_db  # noqa: PLC0415
    from app.models import Stock  # noqa: PLC0415
    from app.services import rilevanza_service  # noqa: PLC0415

    with core_db.SessionLocal() as db:
        ids = list(rilevanza_service.titoli_rilevanti(db))
        if not ids:
            return []
        return sorted(set(db.execute(select(Stock.ticker).where(Stock.id.in_(ids))).scalars()))


def run_riscalda_dettagli() -> None:
    from app.api.market import LIVE_ASSET_DEFINITIONS  # noqa: PLC0415
    from app.api.stocks import riscalda_dettaglio  # noqa: PLC0415
    from app.services import market_detail_service  # noqa: PLC0415

    try:
        titoli = titoli_da_riscaldare()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[riscalda_dettagli] elenco dei titoli seguiti: {e}")
        titoli = []
    for t in titoli:
        try:
            riscalda_dettaglio(t, "1d")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[riscalda_dettagli] {t}: {e}")
    for simbolo, *_ in LIVE_ASSET_DEFINITIONS:
        try:
            market_detail_service.get_detail(simbolo, "1d")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[riscalda_dettagli] {simbolo}: {e}")
