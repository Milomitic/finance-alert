"""Quali titoli contano per chi usa l'app (FA-113): proprietario unico.

Una posizione aperta conta piu' di un preferito, e un preferito piu' del resto
del catalogo. E' il criterio con cui la lista dei segnali si ordina, il digest
apre e la notifica per singolo segnale sceglie cosa mandare.

⚠️ Perche' la rilevanza e non la Forza. Nascono ~70 segnali al giorno, e lo
studio del 2026-09-23 dice che la Forza NON ordina gli esiti dentro nessun
detector: usarla per scegliere cosa notificare filtrava su un numero che non
distingue i segnali migliori. «Questo titolo lo segui» e' un criterio che la
misura non puo' smentire, perche' non pretende di prevedere niente.
"""
from __future__ import annotations

from sqlalchemy import case, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import Position
from app.models.preferito import Preferito

POSIZIONE = "posizione"
PREFERITO = "preferito"

#: Piu' alto = piu' rilevante. In SQL l'ordinamento decrescente li mette primi.
PESO: dict[str | None, int] = {POSIZIONE: 2, PREFERITO: 1, None: 0}


def _posizioni_aperte():
    return select(Position.stock_id).where(Position.closed_at.is_(None))


def _preferiti():
    return select(Preferito.stock_id)


def titoli_rilevanti(db: Session) -> dict[int, str]:
    """stock_id -> «posizione» o «preferito». Una posizione vince su un
    preferito dello stesso titolo."""
    out = {sid: PREFERITO for sid in db.execute(_preferiti()).scalars()}
    for sid in db.execute(_posizioni_aperte()).scalars():
        out[sid] = POSIZIONE
    return out


def peso_sql(stock_id: ColumnElement) -> ColumnElement:
    """Lo stesso peso di `PESO`, come espressione da mettere in un ORDER BY.
    Una sola regola, due forme: la lista pagina lato database e non puo'
    ordinare in Python."""
    return case(
        (stock_id.in_(_posizioni_aperte()), PESO[POSIZIONE]),
        (stock_id.in_(_preferiti()), PESO[PREFERITO]),
        else_=PESO[None],
    )


def filtro_rilevanti(stock_id: ColumnElement) -> ColumnElement:
    """Solo i titoli che contano: posizioni aperte o preferiti."""
    return stock_id.in_(_posizioni_aperte()) | stock_id.in_(_preferiti())
