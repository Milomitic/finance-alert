"""Quanto spesso un segnale scatta comunque: il termine di paragone della conversione.

«Il 48% dei setup converte» non dice niente da solo (richiesta dell'utente,
2026-09-16). Se lo stesso segnale scattasse sul 45% dei titoli qualsiasi nello
stesso arco di tempo, il setup non annuncerebbe nulla; se scatta sul 16%, un
titolo con un setup lo vede scattare tre volte piu' spesso. Misurato quel giorno
in produzione: `trend_pullback` 48,7% contro 15,8%, `squeeze_expansion` 55,4%
contro 16,2%.

LA DEFINIZIONE. Il periodo dei setup si divide in finestre da 28 giorni NON
sovrapposte — 28 e' il tetto d'attesa di un setup (`setup_service._MAX_AGE_DAYS`),
cioe' il tempo massimo che un setup ha per convertire. Per ogni finestra si
contano i titoli con prezzi e, fra questi, quelli su cui il detector e' scattato
almeno una volta in quel verso. Il tasso di base e' la somma dei secondi sulla
somma dei primi.

⚠️ E' costruito per essere PRUDENTE, cioe' per non gonfiare il rapporto:

- la finestra di base e' sempre di 28 giorni, mentre un setup spesso ha avuto
  meno tempo (scade dopo dieci giorni senza essere rivisto): il titolo qualsiasi
  ha piu' occasioni del setup;
- la popolazione di base COMPRENDE i titoli che avevano un setup, cioe' proprio
  quelli dove il segnale scatta di piu';
- l'unica distorsione nel verso opposto: un alert che la scansione aggiorna
  resta una riga sola, quindi uno scatto ripetuto conta una volta. Per non
  perdere la finestra in cui la catena e' NATA si guarda anche
  `first_emitted_at`, oltre a `signal_date`.

⚠️ E un rapporto alto e' in parte ATTESO: un setup nasce dove le condizioni sono
quasi soddisfatte. Il confronto dice che la funzione fa cio' che dichiara —
annuncia davvero il segnale — non che il segnale annunciato renda. Quella e'
l'efficacia dei convertiti, misurata altrove.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db_json import json_text
from app.models import Alert, OhlcvDaily
from app.services.setup_service import _MAX_AGE_DAYS

#: Il tetto d'attesa di un setup, letto e non copiato: se il tetto cambia, la
#: finestra di paragone deve cambiare con lui.
WINDOW_DAYS = _MAX_AGE_DAYS
_DIREZIONI = ("bull", "bear")

_MEMO: dict[tuple, BaseRates | None] = {}


@dataclass(frozen=True)
class BaseRates:
    #: {(detector, tono): quota di titoli-finestra con almeno uno scatto}.
    #: Il tono "any" vale per i setup senza direzione: uno scatto in un verso
    #: qualsiasi.
    rates: dict[tuple[str, str], float]
    windows: int
    first_day: date
    last_day: date

    def for_tone_mix(self, detector: str, tone_counts: dict[str, int]) -> float | None:
        """Il tasso di base di un detector pesato sul mix di toni dei SUOI setup.

        Un detector con 90 setup rialzisti e 10 ribassisti si confronta con
        uno scatto rialzista nove volte su dieci: confrontarlo con il verso
        piu' frequente del mercato mescolerebbe due domande."""
        totale = sum(tone_counts.values())
        if not totale:
            return None
        somma = 0.0
        for tono, n in tone_counts.items():
            chiave = tono if tono in _DIREZIONI else "any"
            somma += n * self.rates.get((detector, chiave), 0.0)
        return somma / totale


def _giorno(v: object) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def base_firing_rates(db: Session, first_day: date, *, today: date | None = None) -> BaseRates | None:
    """Tassi di base sulle finestre COMPLETE da `first_day` in poi.

    None quando non c'e' ancora una finestra completa: un tasso misurato su una
    finestra a meta' confronterebbe 28 giorni di setup con meno giorni di
    mercato."""
    oggi = today or date.today()
    finestre: list[tuple[date, date]] = []
    inizio = first_day
    while inizio + timedelta(days=WINDOW_DAYS) <= oggi:
        finestre.append((inizio, inizio + timedelta(days=WINDOW_DAYS)))
        inizio += timedelta(days=WINDOW_DAYS)
    if not finestre:
        return None

    firma = (
        first_day, oggi,
        *db.execute(select(func.count(Alert.id), func.max(Alert.triggered_at))).one(),
    )
    if firma in _MEMO:
        return _MEMO[firma]

    fine = finestre[-1][1]
    universo = [
        db.execute(
            select(func.count(func.distinct(OhlcvDaily.stock_id)))
            .where(OhlcvDaily.date >= a, OhlcvDaily.date < b)
        ).scalar_one()
        for a, b in finestre
    ]

    colpiti: dict[tuple[str, str], list[set[int]]] = defaultdict(
        lambda: [set() for _ in finestre]
    )
    righe = db.execute(
        select(
            Alert.stock_id, Alert.signal_name, Alert.signal_date,
            json_text(Alert.snapshot, "tone"), json_text(Alert.snapshot, "first_emitted_at"),
        ).where(
            Alert.signal_name.is_not(None),
            Alert.signal_date.is_not(None),
            # Una catena aggiornata puo' essere nata fino a 28 giorni prima
            # della sua data attuale.
            Alert.signal_date >= first_day,
            Alert.signal_date < fine + timedelta(days=WINDOW_DAYS),
        )
    ).all()
    for stock_id, detector, signal_date, tono, nata in righe:
        if tono not in _DIREZIONI:
            continue
        giorni = {_giorno(signal_date), _giorno(nata)} - {None}
        for i, (a, b) in enumerate(finestre):
            if any(a <= g < b for g in giorni):
                colpiti[(detector, tono)][i].add(stock_id)
                colpiti[(detector, "any")][i].add(stock_id)

    denominatore = sum(universo)
    risultato = None
    if denominatore:
        risultato = BaseRates(
            rates={k: sum(len(s) for s in v) / denominatore for k, v in colpiti.items()},
            windows=len(finestre),
            first_day=first_day,
            last_day=fine,
        )
    _MEMO.clear()
    _MEMO[firma] = risultato
    return risultato
