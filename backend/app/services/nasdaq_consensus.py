"""Il calendario economico di Nasdaq: i consensi dei rilasci PASSATI (2026-10-11).

Forexfactory pubblica solo la settimana in corso, quindi il previsto di un
rilascio di agosto non si legge piu' da li'. L'API pubblica del calendario di
Nasdaq (`api.nasdaq.com/api/calendar/economicevents?date=...`) risponde per
qualunque giorno, anche anni indietro, con dato uscito, consenso e precedente.

⚠️ Due righe con lo STESSO nome. Il CPI di un giorno compare due volte come
«CPI»: una e' la variazione sul mese (0,4%), l'altra sull'anno (3,4%), e nessun
campo le distingue — nemmeno l'ordine, che cambia da un giorno all'altro (per il
PPI la riga annua viene prima). Le assegna `assegna`, confrontandole con le
variazioni della serie FRED; dove FRED non c'e', la variazione mensile e' la
piu' piccola delle due in valore assoluto.

⚠️ L'API data ogni evento al giorno DOPO. Le buste paga di venerdi' 5
settembre 2025 si leggono con `date=2025-09-06`, il CPI che Forexfactory da' al
14 ottobre 2026 con `date=2026-10-15`. `eventi_del_giorno(g)` chiede quindi
g + 1: chi la chiama ragiona nel giorno vero del rilascio, e un riempimento
che salta i fine settimana non perde le uscite del venerdi' (2026-10-11: le
prime 344 righe erano tutte un giorno avanti, e buste paga e disoccupazione
quasi assenti).

⚠️ Senza un User-Agent da browser l'API non risponde. Non e' un accesso
riservato: e' lo stesso JSON che la pagina pubblica del calendario legge.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import requests

_URL = "https://api.nasdaq.com/api/calendar/economicevents"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}
_TIMEOUT = 20.0

#: Quale variazione misura il consenso PRINCIPALE di un'etichetta:
#: «periodo» (CPI m/m, PIL q/q), «anno» (HICP y/y), «livello» (un tasso, un
#: indice di fiducia, le buste paga come variazione assoluta in migliaia).
Misura = Literal["periodo", "anno", "livello"]

#: etichetta del nostro calendario -> (paese Nasdaq, nome dell'evento, misura).
#: Le stesse etichette di `forexfactory_consensus._FF_LABEL_MAP`, e la misura
#: principale e' la STESSA di Forexfactory, cosi' che le righe delle due fonti
#: si confrontino fra loro.
NASDAQ_MAP: dict[str, tuple[str, str, Misura]] = {
    "US CPI release":             ("United States", "CPI", "periodo"),
    "US PPI release":             ("United States", "PPI", "periodo"),
    "US NFP / Non-Farm Payrolls": ("United States", "Nonfarm Payrolls", "livello"),
    "US Unemployment Rate":       ("United States", "Unemployment Rate", "livello"),
    "FOMC rate decision":         ("United States", "Fed Interest Rate Decision", "livello"),
    # Una riga sola: la variazione trimestrale ANNUALIZZATA, come «GDP q/q» di
    # Forexfactory. Le tre stime di un trimestre escono in tre giorni diversi;
    # `per_periodo` assegna al trimestre la prima, cioe' l'anticipata.
    "US GDP (real)":              ("United States", "GDP", "periodo"),
    "US Retail Sales":            ("United States", "Retail Sales", "periodo"),
    "ISM Manufacturing PMI":      ("United States", "ISM Manufacturing PMI", "livello"),
    "ISM Services PMI":           ("United States", "ISM Non-Manufacturing PMI", "livello"),
    # La stima flash esce a inizio mese, la definitiva a meta': entrambe «CPI».
    # Il consenso di Forexfactory e' sull'anno, e cosi' qui.
    "Eurozone HICP flash":        ("Euro Zone", "CPI", "anno"),
    "ECB Deposit Facility Rate":  ("Euro Zone", "Deposit Facility Rate", "livello"),
    "UK CPI release":             ("United Kingdom", "CPI", "anno"),
    "BoE Bank Rate":              ("United Kingdom", "BoE Interest Rate Decision", "livello"),
    "BoJ policy rate":            ("Japan", "BoJ Interest Rate Decision", "livello"),
}


@dataclass(frozen=True)
class NasdaqEvento:
    paese: str
    nome: str
    #: Le stringhe come le pubblica la fonte («0.4%», «29K»), None se vuote.
    actual: str | None
    consensus: str | None
    previous: str | None


def _pulisci(v: object) -> str | None:
    if not isinstance(v, str):
        return None
    s = html.unescape(v).replace("\xa0", " ").strip()
    return s or None


def eventi_del_giorno(giorno: date, *, sessione: requests.Session | None = None) -> list[NasdaqEvento]:
    """Gli eventi usciti il giorno `giorno`. Solleva su un errore di rete o di
    formato: chi riempie la storia deve sapere che quel giorno manca, non
    leggerlo vuoto."""
    get = (sessione or requests).get
    richiesta = giorno + timedelta(days=1)  # la fonte data al giorno dopo: vedi sopra
    r = get(_URL, params={"date": richiesta.isoformat()}, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    corpo = r.json()
    righe = ((corpo or {}).get("data") or {}).get("rows") or []
    return [
        NasdaqEvento(
            paese=str(x.get("country") or ""),
            nome=str(x.get("eventName") or ""),
            actual=_pulisci(x.get("actual")),
            consensus=_pulisci(x.get("consensus")),
            previous=_pulisci(x.get("previous")),
        )
        for x in righe
    ]


def _valore(e: NasdaqEvento) -> float | None:
    from app.services.forexfactory_consensus import parse_numeric

    for raw in (e.actual, e.consensus, e.previous):
        v = parse_numeric(raw)
        if v is not None:
            return v
    return None


def assegna(
    righe: list[NasdaqEvento],
    misura: Misura,
    fred: tuple[float | None, float | None] | None = None,
) -> tuple[NasdaqEvento | None, NasdaqEvento | None]:
    """(riga della misura principale, riga sull'anno) fra le righe di un nome.

    `fred` = (variazione sul periodo, sull'anno) dell'ultima osservazione FRED
    prima del rilascio. Una riga sola e' sempre la misura principale: e' il
    caso del PIL, la cui unica riga e' annualizzata e non somiglia a nessuna
    delle due variazioni FRED — confrontarla sceglierebbe quella sbagliata.
    """
    if not righe:
        return None, None
    if misura == "livello" or len(righe) == 1:
        return righe[0], None
    a, b = righe[0], righe[1]
    va, vb = _valore(a), _valore(b)
    if va is None or vb is None:
        # Una delle due e' vuota: non c'e' niente da riconoscere, e l'altra resta
        # la sola misura nota.
        return (b if va is None else a), None
    fp, fa = fred if fred is not None else (None, None)
    if fp is not None and fa is not None:
        a_periodo = abs(va - fp) + abs(vb - fa) <= abs(vb - fp) + abs(va - fa)
    elif fp is not None:
        a_periodo = abs(va - fp) <= abs(vb - fp)
    elif fa is not None:
        a_periodo = abs(vb - fa) <= abs(va - fa)
    else:
        a_periodo = abs(va) <= abs(vb)
    periodo, anno = (a, b) if a_periodo else (b, a)
    if misura == "anno":
        return anno, None
    return periodo, anno
