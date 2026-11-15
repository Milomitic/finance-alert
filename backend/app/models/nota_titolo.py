"""La nota personale su un titolo (FA-156): una per titolo, testo libero."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

#: Lunghezza massima: e' un appunto, non un documento.
NOTA_MAX = 4000


class NotaTitolo(Base):
    __tablename__ = "note_titolo"

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    testo: Mapped[str] = mapped_column(Text, nullable=False)
    creata_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aggiornata_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
