"""Le chiusure di borsa per festivita' e le mezze giornate (FA-205).

Prima nessun pezzo dell'app sapeva che una borsa e' chiusa per festa: il
26/11/2026 (Ringraziamento) New York risultava in seduta e il giorno dopo il
pre-market leggeva una seduta inesistente.

Copertura, dichiarata: solo NYSE/Nasdaq, dal comunicato ufficiale di NYSE/ICE
«2026, 2027 and 2028 Holiday and Early Closings Calendar» (dicembre 2025). Le
altre borse restano senza calendario delle festivita' finche' le date non
sono verificate sulle fonti ufficiali: le fonti secondarie consultate il
28/11/2026 si contraddicevano (il 31 dicembre a Milano). Meglio nessun dato
di un dato sbagliato che spegne una seduta vera.

⚠️ Un elenco scritto a mano scade in silenzio (la lezione dell'elenco macro
che finiva il 31 agosto). `test_chiusure_borsa` fallisce da dicembre se
l'anno dopo non c'e'.
"""
from __future__ import annotations

from datetime import date, time

#: regione (come in `live_quote_service._MARKET_HOURS_LOCAL`) -> giorni chiusi.
CHIUSURE: dict[str, frozenset[date]] = {
    "US": frozenset({
        # 2026
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
        date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
        # 2027
        date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
        date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
    }),
}

#: regione -> giorno -> ora di chiusura anticipata (ora locale della borsa).
CHIUSURE_ANTICIPATE: dict[str, dict[date, time]] = {
    "US": {
        date(2026, 11, 27): time(13, 0), date(2026, 12, 24): time(13, 0),
        date(2027, 11, 26): time(13, 0),
    },
}

#: Gli anni che l'elenco copre per regione: oltre, si torna a «nessuna festa nota».
ANNI_COPERTI: dict[str, tuple[int, int]] = {"US": (2026, 2027)}


def chiusa(regione: str, giorno: date) -> bool:
    """La borsa della regione e' chiusa tutto il giorno per festivita'."""
    return giorno in CHIUSURE.get(regione, frozenset())


def chiusura_anticipata(regione: str, giorno: date) -> time | None:
    """L'ora (locale) di chiusura anticipata, o None se il giorno e' normale."""
    return CHIUSURE_ANTICIPATE.get(regione, {}).get(giorno)
