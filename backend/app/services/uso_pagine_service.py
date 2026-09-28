"""Il contatore d'uso delle pagine (FA-114): scrive un'apertura, legge il riepilogo.

La chiave arriva gia' ridotta da `app.core.rotte.rotta_uso`; qui non si
interpreta nessun percorso.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.uso_pagina import UsoPagina

ROMA = ZoneInfo("Europe/Rome")


def oggi_roma() -> date:
    return datetime.now(ROMA).date()


def registra(db: Session, rotta: str, *, oggi: date | None = None) -> None:
    """+1 sull'apertura di `rotta` nel giorno. Un solo INSERT ... ON CONFLICT:
    due richieste insieme non si perdono un incremento a vicenda, come
    succederebbe con una lettura seguita da una scrittura."""
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    giorno = oggi or oggi_roma()
    tabella = UsoPagina.__table__
    db.execute(
        insert(tabella)
        .values(giorno=giorno, rotta=rotta, aperture=1)
        .on_conflict_do_update(
            index_elements=["giorno", "rotta"],
            set_={"aperture": tabella.c.aperture + 1},
        )
    )
    db.commit()


@dataclass(frozen=True)
class UsoRotta:
    rotta: str
    ultimi_7: int
    ultimi_30: int
    ultimo_giorno: date


@dataclass(frozen=True)
class RiepilogoUso:
    #: Il primo giorno contato. ⚠️ Senza, «3 aperture in 30 giorni» su un
    #: contatore acceso da due giorni si leggerebbe come una pagina che nessuno
    #: usa: il denominatore viaggia col numero.
    dal: date | None
    oggi: date
    rotte: list[UsoRotta]


def riepilogo(db: Session, *, oggi: date | None = None) -> RiepilogoUso:
    """Aperture per rotta negli ultimi 7 e 30 giorni, oggi compreso, dalla
    piu' usata."""
    oggi = oggi or oggi_roma()
    da_30 = oggi - timedelta(days=29)
    da_7 = oggi - timedelta(days=6)
    righe = db.execute(
        select(
            UsoPagina.rotta,
            func.sum(UsoPagina.aperture).filter(UsoPagina.giorno >= da_7),
            func.sum(UsoPagina.aperture),
            func.max(UsoPagina.giorno),
        )
        .where(UsoPagina.giorno >= da_30, UsoPagina.giorno <= oggi)
        .group_by(UsoPagina.rotta)
    ).all()
    dal = db.execute(select(func.min(UsoPagina.giorno))).scalar()
    rotte = [
        UsoRotta(rotta=r, ultimi_7=int(s7 or 0), ultimi_30=int(s30 or 0), ultimo_giorno=u)
        for r, s7, s30, u in righe
    ]
    rotte.sort(key=lambda x: (-x.ultimi_30, -x.ultimi_7, x.rotta))
    return RiepilogoUso(dal=dal, oggi=oggi, rotte=rotte)
