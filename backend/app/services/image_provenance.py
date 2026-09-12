"""Che cosa questa immagine puo' dimostrare di se'.

⚠️ Nasce da un difetto vero, non da un'esigenza teorica. Il livello Docker che
scarica le patch di sicurezza Debian e' rimasto INERTE per 24 giorni (19 agosto
- 12 settembre 2026): CI costruisce con `cache-from: type=gha` e quel `RUN` non
nominava niente di variabile, quindi buildkit ne riusava il livello a ogni
build. Era scritto bene, documentato in venti righe, e non girava. Se ne e'
accorto trivy rompendo la pipeline con 12 CVE — 3 CRITICAL — tutte gia'
corrette a monte da Debian.

La lezione, registrata in CLAUDE.md: **la cache non distingue «identico» da
«ancora valido»**, e un livello di patch di sicurezza e' l'unico posto dove i
due non coincidono.

Questo modulo legge l'asserzione positiva che chiude il buco. Il Dockerfile
scrive `/etc/image-provenance.json` DENTRO lo stesso `RUN` delle patch: se il
livello non gira, la data resta vecchia e diventa visibile alla CI, ai test e
al cruscotto. Controllare `CACHED` nel log della build osserverebbe il
PROCESSO — dipenderebbe dal formato di buildkit e sarebbe illeggibile da dentro
l'app; questo osserva l'ARTEFATTO.

Proprietario unico della regola di eta' e della soglia. `platform_health` lo
consuma, non lo re-implementa.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

#: Percorso scritto dal Dockerfile. Sovrascrivibile solo nei test.
PROVENANCE_PATH = Path("/etc/image-provenance.json")

#: Oltre questi giorni l'archivio di sicurezza letto dall'immagine e' vecchio
#: abbastanza da meritare una segnalazione.
#:
#: Sette e non uno: l'immagine si ricostruisce a ogni push, quindi una soglia
#: piu' stretta suonerebbe per un weekend tranquillo e insegnerebbe a ignorare
#: la spia — che e' il modo in cui una spia smette di funzionare. Sette giorni
#: sono anche il punto oltre il quale una CVE pubblicata nel frattempo ha avuto
#: tempo di contare davvero.
STALE_AFTER_DAYS = 7

#: Il default di `ARG APT_SECURITY_DATE` nel Dockerfile. Compare quando
#: qualcuno costruisce a mano senza passare il build-arg.
_IGNOTO = "unknown"


@dataclass(frozen=True)
class Provenance:
    """Le due date impresse nell'immagine. `None` significa NON SO."""

    apt_security_date: date | None
    #: ⚠️ L'istante in cui il LIVELLO delle patch e' stato costruito, non
    #: l'immagine. Quando la cache lo riusa — ogni push dello stesso giorno —
    #: due immagini diverse riportano lo stesso valore, ed e' voluto: la
    #: granularita' scelta e' giornaliera. Il nome lo dice, perche' `built_at`
    #: sarebbe stato letto come data dell'immagine.
    apt_layer_built_at: datetime | None


def _as_date(raw: object) -> date | None:
    if not isinstance(raw, str) or not raw or raw == _IGNOTO:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _as_datetime(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw or raw == _IGNOTO:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def read_provenance(path: Path | str | None = None) -> Provenance | None:
    """Le date scritte nell'immagine, o `None` se non c'e' niente da leggere.

    ⚠️ Restituisce `None` e non una data finta quando il file manca — in
    sviluppo manca sempre. Una data inventata qui sarebbe PEGGIO dell'assenza,
    perche' verrebbe letta come prova di freschezza; e' la stessa regola che
    `fx_service` applica alle valute non risolvibili.
    """
    p = Path(path) if path is not None else PROVENANCE_PATH
    try:
        dati = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning(f"provenienza immagine illeggibile ({p}): {exc}")
        return None
    if not isinstance(dati, dict):
        return None
    return Provenance(
        apt_security_date=_as_date(dati.get("apt_security_date")),
        apt_layer_built_at=_as_datetime(dati.get("apt_layer_built_at")),
    )


def apt_age_days(apt_date: date | None, *, oggi: date | None = None) -> int | None:
    """Da quanti giorni e' stato letto l'archivio di sicurezza."""
    if apt_date is None:
        return None
    riferimento = oggi or datetime.now(UTC).date()
    return (riferimento - apt_date).days


def is_stale(apt_date: date | None, *, oggi: date | None = None) -> bool | None:
    """`True` stantia, `False` fresca, `None` ignota.

    ⚠️ Tre stati e non due. Collassare `None` su `False` direbbe «va tutto
    bene» proprio quando non si sa nulla, ed e' la distinzione fra assenza e
    zero che questo progetto applica ovunque.
    """
    eta = apt_age_days(apt_date, oggi=oggi)
    if eta is None:
        return None
    return eta > STALE_AFTER_DAYS
