"""Tiene calde le risposte della home (FA-179, fase B).

Ogni minuto ricalcola il riepilogo e il paniere dei mercati, cosi' nessuna
richiesta li trova freddi: ne' dopo un rilascio, ne' dopo ore senza traffico.
Un guasto di una delle due non ferma l'altra, e lascia servita la risposta di
prima.
"""
from __future__ import annotations

from loguru import logger


def run_riscalda_cache_home() -> None:
    from app.api.dashboard import CACHE_RIEPILOGO  # noqa: PLC0415
    from app.api.market import CACHE_PANIERE  # noqa: PLC0415

    for cache in (CACHE_RIEPILOGO, CACHE_PANIERE):
        try:
            cache.rinfresca()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[riscalda_cache_home] {cache.nome}: {e}")
