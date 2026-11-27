"""Lo stato delle borse e il prossimo cambio (FA-191).

Per ogni borsa: in che fase e' adesso (pre-market, in seduta, after-hours,
chiusa) e quando cambia. Le ore sono quelle di `live_quote_service` (un
proprietario solo), le festivita' quelle di `app.core.chiusure_borsa` dove ci
sono — e la risposta dice per quali borse ci sono.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core import chiusure_borsa

#: (regione, nome a schermo). L'ordine e' quello del giorno che comincia.
BORSE: tuple[tuple[str, str], ...] = (
    ("JP", "Tokyo"), ("HK", "Hong Kong"), ("EU", "Europa"), ("UK", "Londra"), ("US", "New York"),
)
#: Solo le borse USA hanno pre-market e after-hours nei dati dell'app.
_PRE_US = time(4, 0)
_AFTER_US = time(20, 0)


def _segmenti(regione: str, giorno: date) -> list[tuple[str, time, time]]:
    """Le fasi di un giorno di borsa, in ora locale, o nessuna se chiuso."""
    from app.services.live_quote_service import _MARKET_HOURS_LOCAL  # noqa: PLC0415

    if giorno.weekday() >= 5 or chiusure_borsa.chiusa(regione, giorno):
        return []
    _tz, (oh, om), (ch, cm) = _MARKET_HOURS_LOCAL[regione]
    chiusura = chiusure_borsa.chiusura_anticipata(regione, giorno) or time(ch, cm)
    fasi = [("seduta", time(oh, om), chiusura)]
    if regione == "US":
        fasi = [("pre", _PRE_US, time(oh, om)), *fasi, ("after", chiusura, _AFTER_US)]
    return fasi


def stato(regione: str, adesso: datetime) -> dict:
    """{"fase": "pre"|"seduta"|"after"|"chiusa", "fino_alle": ISO UTC | None,
    "prossima_fase": str | None, "dalle": ISO UTC | None}."""
    from app.services.live_quote_service import _MARKET_HOURS_LOCAL  # noqa: PLC0415

    tz = ZoneInfo(_MARKET_HOURS_LOCAL[regione][0])
    locale = adesso.astimezone(tz)
    for scarto in range(0, 12):
        giorno = locale.date() + timedelta(days=scarto)
        for fase, da, a in _segmenti(regione, giorno):
            inizio = datetime.combine(giorno, da, tz)
            fine = datetime.combine(giorno, a, tz)
            if inizio <= locale < fine:
                return {"fase": fase, "fino_alle": fine.astimezone(UTC).isoformat(),
                        "prossima_fase": None, "dalle": None}
            if locale < inizio:
                return {"fase": "chiusa", "fino_alle": None, "prossima_fase": fase,
                        "dalle": inizio.astimezone(UTC).isoformat()}
    return {"fase": "chiusa", "fino_alle": None, "prossima_fase": None, "dalle": None}


def sessioni(adesso: datetime | None = None) -> dict:
    adesso = adesso or datetime.now(UTC)
    return {
        "adesso": adesso.isoformat(),
        "borse": [{"regione": r, "nome": n, "festivita_note": r in chiusure_borsa.CHIUSURE, **stato(r, adesso)}
                  for r, n in BORSE],
    }
