"""Le rotte del frontend, lette dal server: proprietario unico (FA-114).

Due consumatori hanno bisogno di ridurre un percorso del browser a un'etichetta
di cardinalita' limitata: il RUM (`api/rum.py`, etichetta Prometheus) e il
contatore d'uso delle pagine (`uso_pagine_service`, chiave di una tabella).
Una query string, un ticker o uno slug non devono MAI diventare un'etichetta.

⚠️ E' un GEMELLO delle rotte di `frontend/src/App.tsx`, e un gemello invecchia
in silenzio: `tests/test_rotte_gemelle.py` legge App.tsx e le schede delle
due pagine a viste e fallisce se divergono. Il RUM aveva la sua lista a mano,
ed era gia' indietro: nominava `/health` e `/settings`, che oggi sono solo
reindirizzamenti, e non `/diagnostics` — le cui misure finivano sotto `/other`.
"""
from __future__ import annotations

#: Le pagine con un percorso fisso.
ROTTE_STATICHE: frozenset[str] = frozenset({
    "/", "/login", "/alerts", "/positions", "/diagnostics", "/calendar",
    "/stocks", "/sectors", "/institutionals",
})

#: Percorsi che il router rimanda altrove. Il RUM misura la pagina d'arrivo;
#: il contatore NON li conta, perche' il cambio di rotta verso la destinazione
#: arriva subito dopo e li conterebbe due volte.
REINDIRIZZAMENTI: dict[str, str] = {
    "/health": "/diagnostics",
    "/settings": "/diagnostics",
    "/setups": "/alerts",
}

#: Prefisso -> nome del parametro, per le pagine `/<prefisso>/<valore>`.
ROTTE_DINAMICHE: dict[str, str] = {
    "stocks": "ticker",
    "markets": "symbol",
    "sectors": "name",
    "macro": "seriesId",
    "institutionals": "slug",
}

#: Le pagine con viste nel parametro `vista`: (vista di riposo, viste ammesse).
#: ⚠️ Stessa regola del frontend: un valore sconosciuto apre la vista di riposo.
VISTE: dict[str, tuple[str, tuple[str, ...]]] = {
    "/alerts": ("segnali", ("formazione", "segnali", "esiti")),
    "/diagnostics": ("piattaforma", ("piattaforma", "motore")),
}

ALTRO = "/other"


def _pulito(percorso: str) -> str:
    return percorso.split("?", 1)[0].split("#", 1)[0].rstrip("/") or "/"


def rotta(percorso: str) -> str:
    """L'etichetta del RUM: i reindirizzamenti portano alla pagina d'arrivo,
    tutto cio' che non e' una rotta nota diventa `/other`."""
    p = _pulito(percorso)
    p = REINDIRIZZAMENTI.get(p, p)
    if p in ROTTE_STATICHE:
        return p
    parti = p.split("/")
    if len(parti) == 3 and parti[0] == "" and parti[1] in ROTTE_DINAMICHE and parti[2]:
        return f"/{parti[1]}/:{ROTTE_DINAMICHE[parti[1]]}"
    return ALTRO


def rotta_uso(percorso: str, vista: str | None = None) -> str | None:
    """La chiave del contatore d'uso, o None se il passaggio non va contato.

    Diversa da `rotta` in due punti: un reindirizzamento non si conta (lo
    conta la destinazione), e le pagine a viste portano la vista, perche'
    «quante volte si apre In formazione» e' proprio la domanda da fare.
    """
    p = _pulito(percorso)
    if p in REINDIRIZZAMENTI or p == "/login":
        return None
    base = rotta(p)
    if base in VISTE:
        riposo, ammesse = VISTE[base]
        return f"{base}?vista={vista if vista in ammesse else riposo}"
    return base
