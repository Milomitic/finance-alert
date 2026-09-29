"""Le novita' sui titoli seguiti gia' mandate su Telegram (2026-09-29).

Serve a una cosa sola: che ogni novita' — un cambio di giudizio di un
analista, un acquisto di un insider, una trimestrale pubblicata — parta UNA
volta. La cache dei fondamentali si rinnova a giorni alterni o peggio, quindi
un fatto del lunedi' puo' affiorare il giovedi': una finestra sulle date
dell'evento o lo perderebbe o lo ripeterebbe. Vedi `novita_titoli_service`.

La chiave e' lo SHA-1 dell'identita' del fatto, non il fatto: l'identita'
comprende nomi di banche e di insider di lunghezza qualunque, e una colonna a
lunghezza fissa li troncherebbe su Postgres (CLAUDE.md, «SQLite ignora
VARCHAR(n)»).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class NovitaNotificata(Base):
    __tablename__ = "novita_notificate"

    chiave: Mapped[str] = mapped_column(String(40), primary_key=True)
    notificata_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
