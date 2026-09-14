"""Le due funzioni d'orario di `live_quote_service`, che nessuno eseguiva mai.

⚠️ Il cancello del codice mai eseguito le ha segnalate a turno — `_is_premarket`
in una corsa, `_today_session_open_epoch` in quella prima — e due funzioni dello
stesso modulo che si scambiano lo stato di copertura fra due corse sono la firma
di una dipendenza dall'OROLOGIO.

La causa, misurata sui test e non dedotta: **ogni riferimento esistente le
SOSTITUISCE**. Otto fra `monkeypatch.setattr` e `patch(...)`, e nessuna
chiamata reale. La loro copertura veniva quindi solo dall'esecuzione incidentale
dentro qualche altro test, e quella dipende dall'ora: a riga 740
`allow_remote_today_fetch and _is_premarket(ticker)` corto-circuita, e la
condizione a valle legge l'orologio.

⚠️ E' la stessa famiglia del `raising=False` che crea un attributo nuovo invece
di sostituire quello vero: **il finto nasconde che l'originale non gira mai.**
Una funzione sostituita ovunque non e' verificata da nessuno, e il cancello
diceva la verita'.

Qui il tempo si INIETTA dove la firma lo permette, e dove non lo permette si
asserisce una proprieta' vera a qualunque ora — mai «gira adesso e vediamo».
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.live_quote_service import (
    _exchange_region,
    _is_premarket,
    _today_session_open_epoch,
)

_NY = ZoneInfo("America/New_York")


def _a_new_york(anno: int, mese: int, giorno: int, ora: int, minuto: int = 0) -> datetime:
    """Un istante espresso in ora di NEW YORK, reso in UTC.

    ⚠️ Si costruisce sull'ora LOCALE e non sull'UTC di proposito: la finestra
    pre-mercato e' definita in ora locale, quindi un caso scritto in UTC
    misurerebbe una cosa diversa a gennaio e a luglio senza dirlo — ed e'
    proprio la consapevolezza dell'ora legale che questa funzione promette."""
    return datetime(anno, mese, giorno, ora, minuto, tzinfo=_NY).astimezone(UTC)


# ─── 1. _is_premarket ─────────────────────────────────────────────────────


@pytest.mark.parametrize("ticker", ["VOD.L", "ENI.MI", "0700.HK", "7203.T"])
def test_a_non_US_listing_is_never_premarket(ticker: str) -> None:
    """La prima riga della funzione, e non e' una formalita': la finestra
    04:00-09:30 e' quella di NEW YORK, quindi applicarla a Londra o Tokyo
    scambierebbe il cambio del giorno con un numero preso da un'altra borsa."""
    assert _exchange_region(ticker) != "US"
    # Un'ora che per un titolo americano SAREBBE pre-mercato.
    assert _is_premarket(ticker, _a_new_york(2026, 3, 10, 6)) is False


def test_the_window_opens_at_four_and_closes_at_the_bell() -> None:
    """I due bordi, ed entrambi contano: `_US_PREMARKET_START_LOCAL <= local <
    apertura`. Sotto il primo non c'e' pre-mercato, dal secondo in poi c'e' il
    mercato vero e il cambio del giorno torna a essere quello ordinario."""
    g = (2026, 3, 10)  # un martedi'
    assert _is_premarket("AAPL", _a_new_york(*g, 3, 59)) is False
    assert _is_premarket("AAPL", _a_new_york(*g, 4, 0)) is True     # bordo incluso
    assert _is_premarket("AAPL", _a_new_york(*g, 9, 29)) is True
    assert _is_premarket("AAPL", _a_new_york(*g, 9, 30)) is False   # bordo escluso
    assert _is_premarket("AAPL", _a_new_york(*g, 15, 0)) is False


@pytest.mark.parametrize("giorno", [7, 8])  # sabato e domenica
def test_the_weekend_has_no_premarket(giorno: int) -> None:
    """Marzo 2026: il 7 e' sabato, l'8 domenica. Senza questa guardia il
    cambio del giorno verrebbe sostituito da un prezzo pre-mercato che nessuno
    ha scambiato, perche' la borsa e' chiusa."""
    assert _is_premarket("AAPL", _a_new_york(2026, 3, giorno, 6)) is False


def test_the_window_follows_DAYLIGHT_SAVING_not_a_fixed_UTC_offset() -> None:
    """⚠️ Il motivo per cui la funzione converte in ora locale invece di
    sottrarre cinque ore.

    Le 06:00 di New York sono le 11:00 UTC d'inverno e le 10:00 UTC d'estate.
    Una soglia scritta in UTC sarebbe giusta per meta' anno e sbagliata di
    un'ora per l'altra meta', cioe' il difetto comparirebbe due volte l'anno e
    si correggerebbe da solo — la forma piu' difficile da trovare."""
    inverno = _a_new_york(2026, 1, 13, 6)   # EST
    estate = _a_new_york(2026, 7, 14, 6)    # EDT
    assert inverno.hour == 11 and estate.hour == 10, "le due date non attraversano l'ora legale"
    assert _is_premarket("AAPL", inverno) is True
    assert _is_premarket("AAPL", estate) is True


# ─── 2. _today_session_open_epoch ─────────────────────────────────────────


def test_an_unmapped_suffix_falls_through_to_US_and_that_is_deliberate() -> None:
    """⚠️ Scrivendo questo test avevo asserito `None`, e il test mi ha corretto.

    `_exchange_region` fa cadere OGNI suffisso sconosciuto su `"US"`, e il suo
    docstring dichiara che non e' cosmetico: la guardia sulla barra di oggi
    dell'ingest si appoggia a `_is_market_open`, quindi un titolo di Tokyo
    giudicato sugli orari di New York farebbe persistere come chiusa una seduta
    ancora in corso. La regola operativa che ne segue e' «tenere la mappa
    completa su ogni borsa del catalogo», non «rendere None sull'ignoto».

    Ne consegue che il `return None` di `_today_session_open_epoch` e' un ramo
    DIFENSIVO che nessun cammino raggiunge attraverso `_exchange_region` — una
    delle famiglie che questo progetto riconosce a vista. Si fissa quindi il
    comportamento vero, non quello che sembrava ragionevole."""
    assert _exchange_region("XYZ.ZZZ") == "US"
    epoch = _today_session_open_epoch("XYZ.ZZZ")
    assert epoch is not None
    assert datetime.fromtimestamp(epoch, tz=_NY).hour == 9


def test_the_session_open_is_todays_bell_in_the_exchange_timezone() -> None:
    """⚠️ La funzione legge l'orologio da sola e la firma non permette di
    iniettarlo, quindi si asserisce una proprieta' vera a QUALUNQUE ora invece
    di fissare un valore: l'epoch reso, riconvertito nel fuso della borsa, e'
    l'apertura di OGGI.

    Fissare un numero richiederebbe di congelare il tempo, e un test che gira
    solo con l'orologio fermo e' esattamente cio' che ha reso queste due
    funzioni invisibili al cancello."""
    epoch = _today_session_open_epoch("AAPL")
    assert epoch is not None
    apertura = datetime.fromtimestamp(epoch, tz=_NY)
    oggi_a_ny = datetime.now(_NY).date()
    assert apertura.date() == oggi_a_ny
    assert (apertura.hour, apertura.minute, apertura.second) == (9, 30, 0)


@pytest.mark.parametrize(
    ("ticker", "fuso", "campana"),
    [("VOD.L", "Europe/London", (8, 0)),
     ("ENI.MI", "Europe/Berlin", (9, 0)),
     ("0700.HK", "Asia/Hong_Kong", (9, 30))],
)
def test_each_region_gets_its_OWN_bell(ticker: str, fuso: str, campana: tuple) -> None:
    """⚠️ Il pavimento sul test sopra: senza, una funzione che rendesse SEMPRE
    l'apertura di New York lo soddisferebbe per i titoli americani e sarebbe
    sbagliata per i 312 titoli del catalogo che non sono quotati li'."""
    epoch = _today_session_open_epoch(ticker)
    assert epoch is not None
    apertura = datetime.fromtimestamp(epoch, tz=ZoneInfo(fuso))
    assert (apertura.hour, apertura.minute) == campana
