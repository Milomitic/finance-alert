"""L'ultima visita al cruscotto, per la riga «Dall'ultima visita» (2026-09-29).

Una riga sola: l'app ha un utente, come per preferiti e posizioni. Due istanti
e non uno, perche' il cruscotto si apre ~17 volte al giorno: se ogni apertura
fosse il riferimento, la riga direbbe quasi sempre «niente di nuovo dalle
14:52» di dieci minuti fa. Vedi `ultima_visita_service`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class VisitaCruscotto(Base):
    __tablename__ = "visite_cruscotto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: L'istante da cui la riga conta: l'apertura precedente a una pausa.
    riferimento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultima_apertura: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
