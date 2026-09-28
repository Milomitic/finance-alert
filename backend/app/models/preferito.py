"""I titoli preferiti: una lista sola, senza regole (FA-112).

⚠️ NON sono le watchlist tolte il 2026-05-12 (`8cad26c5`, migrazione
`e0489f561198`). Quelle erano liste per tema, dodici, ognuna con le PROPRIE
regole di scansione (il «Tier 2»), e complicavano la scansione per una
funzione che nessuno usava cosi'. Questa e' una stella: un insieme di titoli,
nessuna regola, nessun effetto sul motore.

A cosa servono: accorciare il percorso piu' frequente dell'app, cioe' aprire
un titolo (~16 volte al giorno), e dire alla lista dei segnali, al digest e
alla notifica per singolo segnale quali titoli contano (FA-113).

Globali e non per utente, come le posizioni: l'app ha un utente solo, e una
colonna `user_id` che nessuno legge sarebbe la forma di un'intenzione, non di
un bisogno.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Preferito(Base):
    __tablename__ = "preferiti"

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    aggiunto_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
