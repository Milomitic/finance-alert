"""Quali regole hanno prodotto un'osservazione (2026-09-16).

Misurato prima di scriverlo: negli 8.554 alert del motore NESSUNO snapshot
portava una versione, una calibrazione o una build. C'erano timestamp e
contatori di revisione, che dicono QUANDO, non CON QUALI REGOLE. Una modifica
al motore mescolava quindi in silenzio le popolazioni di prima e di dopo, e
ogni confronto «e' migliorato?» leggeva una media fra due sistemi diversi.

Tre versioni, perche' cambiano per ragioni diverse e a ritmi diversi:

- `EMISSION_RULES_VERSION` — i cancelli che decidono se un alert nasce o si
  aggiorna (soglia di Forza, regime, follow-through, recenza, cooldown).
- `SETUP_CONVERSION_VERSION` — quando un setup si considera convertito.
- `OUTCOME_METHOD_VERSION` — come si etichetta un esito (orizzonte, riferimento
  dell'universo, colpo market-neutral).

⚠️ **Vanno cambiate A MANO quando cambia la regola che nominano**, nello stesso
commit. Nessun test puo' accorgersi che una regola e' cambiata e la versione
no: e' la stessa forma dei periodi degli indicatori, dove la fonte unica
esisteva e nessuno la importava. Il formato e' la data della modifica, cosi' la
versione dice anche da quando vale.

Lo storico resta senza versione (NULL, o nessuna chiave nello snapshot): non si
ricostruisce quale regola valesse, e dichiararlo e' la sola cosa onesta.

Modulo foglia senza dipendenze, per lo stesso motivo di `app/indicators/periods`:
chi deve scrivere la versione deve poterla importare senza portarsi dietro
mezzo stack.
"""
import os

#: Conversione per evento, verso compatibile, barra successiva all'apertura.
SETUP_CONVERSION_VERSION = "2026-09-16"
#: Etichetta dall'evento, mediana dell'universo senza ETF, prefiltro maturabili.
OUTCOME_METHOD_VERSION = "2026-09-16"
#: Primo stampo: le regole di emissione in vigore al 2026-09-16.
EMISSION_RULES_VERSION = "2026-09-16"


def build_sha() -> str | None:
    """Il commit dell'immagine in esecuzione (ARG GIT_SHA), None in sviluppo."""
    return os.environ.get("GIT_SHA") or None


def emission_stamp() -> dict[str, str | None]:
    """Quello che si scrive nello snapshot di un alert a ogni analisi."""
    return {"emission": EMISSION_RULES_VERSION, "build": build_sha()}
