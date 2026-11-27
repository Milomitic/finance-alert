"""FA-205: le chiusure di borsa per festivita' e le mezze giornate."""
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.core import chiusure_borsa as cb
from app.services import live_quote_service as lq
from app.services import premarket_service as pm

ET = ZoneInfo("America/New_York")


def _et(a, m, g, hh, mm) -> datetime:
    return datetime(a, m, g, hh, mm, tzinfo=ET).astimezone(UTC)


def test_il_ringraziamento_e_chiuso_e_senza_pre_market():
    assert not lq._is_market_open("AAPL", _et(2026, 11, 26, 11, 0))
    assert not lq._is_premarket("AAPL", _et(2026, 11, 26, 8, 0))
    assert not pm.us_market_open_now(datetime(2026, 11, 26, 11, 0, tzinfo=ET))


def test_il_venerdi_dopo_chiude_alle_13():
    assert lq._is_premarket("AAPL", _et(2026, 11, 27, 9, 0))
    assert lq._is_market_open("AAPL", _et(2026, 11, 27, 12, 30))
    assert not lq._is_market_open("AAPL", _et(2026, 11, 27, 13, 30))
    assert not pm.us_market_open_now(datetime(2026, 11, 27, 13, 30, tzinfo=ET))


def test_un_giorno_normale_non_cambia():
    assert lq._is_market_open("AAPL", _et(2026, 11, 30, 15, 0))
    assert lq._is_premarket("AAPL", _et(2026, 11, 30, 8, 0))


def test_una_borsa_senza_calendario_non_e_chiusa_da_quello_americano():
    """Il 26/11 Milano lavora: il calendario NYSE non deve chiuderla."""
    berlino = datetime(2026, 11, 26, 11, 0, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(UTC)
    assert lq._is_market_open("UCG.MI", berlino)


def test_l_elenco_non_scade_in_silenzio():
    """Da dicembre serve l'anno dopo: un elenco scritto a mano scade senza
    avvisare (la lezione dell'elenco macro che finiva il 31 agosto)."""
    oggi = date.today()
    serve = oggi.year + (1 if oggi.month == 12 else 0)
    for regione, (_da, a) in cb.ANNI_COPERTI.items():
        assert a >= serve, f"aggiornare le chiusure {regione} per il {serve}"
        anni = {g.year for g in cb.CHIUSURE[regione]}
        assert set(range(_da, a + 1)) <= anni
