"""I modelli in prova silenziosa, uno per addestramento.

Una riga per (nome, versione): si tengono tutte, perche' ogni punteggio fissato
su un alert porta la versione con cui e' stato calcolato, e per valutarlo
bisogna poter dire quale modello l'ha prodotto. Il servizio carica l'ULTIMA
riga per nome. Motivazione in `app.ml`.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ModelloOmbra(Base):
    __tablename__ = "modelli_ombra"
    __table_args__ = (UniqueConstraint("nome", "versione", name="uq_modelli_ombra_nome_versione"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: "volatilita" | "selezione"
    nome: Mapped[str] = mapped_column(String(32), nullable=False)
    versione: Mapped[str] = mapped_column(String(32), nullable=False)
    addestrato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    #: Il GBM serializzato piu' l'elenco dei nomi delle variabili, in JSON.
    artefatto: Mapped[str] = mapped_column(Text, nullable=False)
    #: Le misure fuori campione dell'addestramento (anno tenuto da parte), JSON.
    metriche: Mapped[str | None] = mapped_column(Text, nullable=True)
