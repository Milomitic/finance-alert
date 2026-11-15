"""Giornate di mercato (FA-152): un giorno con cento segnali nello stesso verso
e' il mercato visto cento volte, non cento notizie sui titoli.

Misurato in produzione su 150 giorni (2026-11-15): nascono in mediana 36
segnali ribassisti e 51 rialzisti al giorno, con punte di 104 e 161 — il 1°
luglio 161 rialzisti, il 5 novembre 104 ribassisti. In quei giorni la lista
dell'universo e' una pagina intera dello stesso fatto.

La regola, per VERSO e non sul totale: un giorno e' «di mercato» se i
segnali nati quel giorno in un verso superano il 95° percentile dei
`FINESTRA` giorni feriali precedenti (zeri compresi), e comunque almeno
`MINIMO`. Il giorno stesso non entra nella propria soglia. Sotto
`STORIA_MINIMA` giorni di storia non si comprime niente: una soglia su
cinque osservazioni non e' un percentile.

⚠️ Comprimere e' una scelta di LETTURA. Gli alert restano, il magazzino li
misura, e i segnali sui titoli in posizione o fra i preferiti restano sempre
visibili riga per riga: e' sui tuoi titoli che un segnale va letto anche in
un giorno di mercato. Il giorno e' quello di NASCITA (`emitted_at`), lo
stesso che usa il filtro per data della lista.
"""
from __future__ import annotations

import math
import time as _time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.db_json import json_text
from app.models import Alert

FINESTRA = 60
PERCENTILE = 0.95
MINIMO = 60
STORIA_MINIMA = 20
#: Quanto indietro si cercano le giornate da comprimere.
ORIZZONTE_GIORNI = 120
_VERSI = ("bull", "bear")
_TTL = 600.0

_tono = json_text(Alert.snapshot, "tone")


@dataclass(frozen=True)
class Giornata:
    giorno: date
    tono: str
    segnali: int
    soglia: int


def _feriali_prima(g: date, n: int) -> list[date]:
    out: list[date] = []
    d = g - timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


def _percentile(valori: list[int], q: float) -> float:
    """Interpolazione lineare, come `percentile_cont` di Postgres."""
    v = sorted(valori)
    pos = (len(v) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def giornate(conteggi: dict[tuple[date, str], int], *, dal: date,
             prima_storia: date) -> list[Giornata]:
    """Le giornate di mercato a partire da `dal`, dai conteggi per (giorno,
    verso). `prima_storia` e' il primo giorno da cui i conteggi esistono:
    prima di quello uno zero non e' un giorno vuoto, e' un dato che manca.
    Pura."""
    out: list[Giornata] = []
    for (g, tono), n in sorted(conteggi.items()):
        if g < dal or tono not in _VERSI or n <= MINIMO:
            continue
        storia = [d for d in _feriali_prima(g, FINESTRA) if d >= prima_storia]
        if len(storia) < STORIA_MINIMA:
            continue
        soglia = max(MINIMO, math.ceil(_percentile(
            [conteggi.get((d, tono), 0) for d in storia], PERCENTILE)))
        if n > soglia:
            out.append(Giornata(giorno=g, tono=tono, segnali=n, soglia=soglia))
    return out


def _giorno(quando: datetime) -> date:
    return (quando if quando.tzinfo is None else quando.astimezone(UTC)).date()


_cache: dict[str, tuple[float, list[Giornata]]] = {}


def recenti(db: Session, *, oggi: date | None = None) -> list[Giornata]:
    """Le giornate di mercato degli ultimi `ORIZZONTE_GIORNI`, in cache 10'."""
    oggi = oggi or datetime.now(UTC).date()
    chiave = oggi.isoformat()
    hit = _cache.get(chiave)
    if hit and _time.monotonic() - hit[0] < _TTL:
        return hit[1]
    dal = oggi - timedelta(days=ORIZZONTE_GIORNI)
    inizio = dal - timedelta(days=FINESTRA * 2)
    righe = db.execute(
        select(Alert.emitted_at, _tono)
        .where(Alert.emitted_at >= datetime.combine(inizio, time.min, UTC), _tono.in_(_VERSI))
    ).all()
    conteggi: dict[tuple[date, str], int] = defaultdict(int)
    for quando, tono in righe:
        conteggi[(_giorno(quando), tono)] += 1
    prima = db.execute(select(Alert.emitted_at).order_by(Alert.emitted_at).limit(1)).scalar()
    prima_storia = max(inizio, _giorno(prima)) if prima else oggi
    out = giornate(dict(conteggi), dal=dal, prima_storia=prima_storia)
    _cache.clear()
    _cache[chiave] = (_time.monotonic(), out)
    return out


def clausola_esclusione(elenco: list[Giornata]):
    """La condizione SQL che toglie dalla lista gli alert di quelle giornate,
    nel loro verso. None se non c'e' niente da togliere."""
    if not elenco:
        return None
    return ~or_(*(
        and_(
            Alert.emitted_at >= datetime.combine(g.giorno, time.min, UTC),
            Alert.emitted_at < datetime.combine(g.giorno + timedelta(days=1), time.min, UTC),
            # ⚠️ coalesce: un alert senza tono (di prezzo) darebbe NULL, e NOT
            # NULL e' NULL — la riga sparirebbe dalla lista in silenzio.
            func.coalesce(_tono, "") == g.tono,
        )
        for g in elenco
    ))
