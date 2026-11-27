"""FA-191: lo stato delle borse e il prossimo cambio."""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.services import sessioni_borsa as sb

ET = ZoneInfo("America/New_York")


def _ny(a, m, g, hh, mm):
    return datetime(a, m, g, hh, mm, tzinfo=ET).astimezone(UTC)


def _fase(regione, adesso):
    return sb.stato(regione, adesso)


def test_le_fasi_di_new_york():
    assert _fase("US", _ny(2026, 11, 30, 8, 0))["fase"] == "pre"
    s = _fase("US", _ny(2026, 11, 30, 10, 0))
    assert s["fase"] == "seduta" and s["fino_alle"] == _ny(2026, 11, 30, 16, 0).isoformat()
    assert _fase("US", _ny(2026, 11, 30, 17, 0))["fase"] == "after"
    notte = _fase("US", _ny(2026, 11, 30, 22, 0))
    assert notte["fase"] == "chiusa" and notte["prossima_fase"] == "pre"
    assert notte["dalle"] == _ny(2026, 12, 1, 4, 0).isoformat()


def test_dopo_il_ringraziamento_si_salta_la_festa_e_la_mezza_giornata_chiude_alle_13():
    vigilia = _fase("US", _ny(2026, 11, 25, 21, 0))
    assert vigilia["dalle"] == _ny(2026, 11, 27, 4, 0).isoformat()      # il 26 e' festa
    s = _fase("US", _ny(2026, 11, 27, 10, 0))
    assert s["fino_alle"] == _ny(2026, 11, 27, 13, 0).isoformat()


def test_il_fine_settimana_porta_al_lunedi_e_le_borse_senza_calendario_lo_dicono():
    sab = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
    tokyo = _fase("JP", sab)
    assert tokyo["fase"] == "chiusa" and tokyo["prossima_fase"] == "seduta"
    assert tokyo["dalle"] == datetime(2026, 11, 30, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")).astimezone(UTC).isoformat()
    borse = {b["regione"]: b for b in sb.sessioni(sab)["borse"]}
    assert borse["US"]["festivita_note"] is True and borse["JP"]["festivita_note"] is False
    assert [b["nome"] for b in sb.sessioni(sab)["borse"]] == ["Tokyo", "Hong Kong", "Europa", "Londra", "New York"]
