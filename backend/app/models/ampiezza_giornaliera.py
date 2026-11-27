"""L'ampiezza di mercato giorno per giorno (FA-188, acceso nell'ondata A).

`market_snapshot` tiene UNA riga, l'ultima scansione: verificato il
2026-11-27, la storia dell'ampiezza non esisteva. Senza storia non c'e'
percentile («il 49% dei titoli sopra la EMA200: e' tanto o poco?»), e la
storia comincia solo da quando si archivia — per questo l'archivio e' stato
acceso prima della tessera che lo legge.

Una riga per (giorno, ambito). `ambito` e' «universo» o il codice di un
indice del catalogo. Il giorno e' quello UTC del calcolo: le due scansioni
quotidiane (chiusura europea e statunitense) cadono nello stesso giorno UTC e
l'ultima sostituisce la prima, cioe' resta la fotografia a mercati chiusi.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

UNIVERSO = "universo"


class AmpiezzaGiornaliera(Base):
    __tablename__ = "ampiezza_giornaliera"
    __table_args__ = (UniqueConstraint("giorno", "ambito", name="uq_ampiezza_giorno_ambito"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    giorno: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ambito: Mapped[str] = mapped_column(String(32), nullable=False)
    titoli: Mapped[int] = mapped_column(Integer, nullable=False)
    avanzano: Mapped[int] = mapped_column(Integer, nullable=False)
    scendono: Mapped[int] = mapped_column(Integer, nullable=False)
    sopra_ema50_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sopra_ema200_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi_sopra_70: Mapped[int] = mapped_column(Integer, nullable=False)
    rsi_sotto_30: Mapped[int] = mapped_column(Integer, nullable=False)
    var_media_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    scritto_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
