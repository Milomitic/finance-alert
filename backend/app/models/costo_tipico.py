"""I costi tipici di un'operazione su eToro, per titolo (FA-142).

Frazioni del NOZIONALE, misurate con un preventivo di eToro in sola lettura.
Servono a dire quanto di un'attesa in R resta dopo i costi: un piano breve
con lo stop vicino paga in R molto piu' di uno lungo con lo stop lontano,
a parita' di costo in dollari.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CostoTipico(Base):
    __tablename__ = "costi_tipici"

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    #: Commissione d'apertura (eToro: `transactionFee`). Si assume uguale alla
    #: chiusura: il preventivo descrive solo l'apertura.
    commissione_pct: Mapped[float] = mapped_column(Float, nullable=False)
    #: Spread di mercato piu' ricarico, una volta.
    spread_pct: Mapped[float] = mapped_column(Float, nullable=False)
    #: Una notte alla leva `leva`, long e short. A leva 1 eToro non ne addebita
    #: (misurato il 2026-11-15 su AAPL e UCG.MI), quindi la leva 1 non ha colonna.
    notte_long_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    notte_short_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    leva: Mapped[int] = mapped_column(Integer, nullable=False)
    valuta: Mapped[str | None] = mapped_column(String(8), nullable=True)
    aggiornato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
