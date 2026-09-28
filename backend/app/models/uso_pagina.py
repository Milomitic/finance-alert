"""Quante volte si apre ogni pagina, per giorno (FA-114).

Una riga per (giorno, rotta). La rotta e' GIA' ridotta da `app.core.rotte`:
niente ticker, slug o query string, solo la forma della pagina — e per le
pagine a viste, la vista.

Esiste perche' l'analisi del 2026-09-26 ha dovuto ricostruire l'uso dai log,
e interrogare 30 giorni di Loki lo ha mandato in OOM. Qui la stessa risposta e'
una SELECT su poche centinaia di righe.

⚠️ Il giorno e' quello di ROMA, dove sta chi usa l'app: una sera italiana dopo
le 22 non deve finire nel giorno dopo, come succederebbe in UTC d'estate.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UsoPagina(Base):
    __tablename__ = "uso_pagine"

    giorno: Mapped[date] = mapped_column(Date, primary_key=True)
    #: La piu' lunga oggi e' «/diagnostics?vista=piattaforma», 29 caratteri.
    rotta: Mapped[str] = mapped_column(String(48), primary_key=True)
    aperture: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
