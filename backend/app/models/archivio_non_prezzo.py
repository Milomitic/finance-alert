"""L'archivio PUNTUALE dei dati che non vengono dai prezzi (fase 4).

Una riga per (titolo, fonte, giorno): cio' che si sapeva di quel titolo quel
giorno — analisti, stime, sorprese sugli utili, scoperto, insider, volatilita'
implicita delle opzioni.

⚠️ Perche' esiste. Sette studi dicono che le variabili ricavate dai prezzi
sono esaurite, e che solo informazione ortogonale puo' cambiare il verdetto
sulla direzione. Ma quasi tutta quell'informazione arriva solo come «valore di
adesso»: yfinance restituisce il consenso di OGGI, lo scoperto di OGGI. Per un
modello e' come non averla, perche' per addestrarlo servono i valori com'erano
QUEL giorno, e nessuno li ha conservati. Questa tabella comincia a farlo; il suo
valore cresce solo col tempo, ed e' la ragione per cui va accesa adesso.

`osservato_il` e' l'istante in cui il dato e' stato SCARICATO, non quello in
cui e' stato archiviato: un fondamentale scaricato sabato e archiviato lunedi'
e' un fatto di sabato.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

#: Le fonti. Costanti e non stringhe sparse: la colonna ha una lunghezza.
FONTE_FONDAMENTALI = "fondamentali"
FONTE_OPZIONI = "opzioni"
FONTI: frozenset[str] = frozenset({FONTE_FONDAMENTALI, FONTE_OPZIONI})


class ArchivioNonPrezzo(Base):
    __tablename__ = "archivio_non_prezzo"
    __table_args__ = (
        UniqueConstraint("stock_id", "fonte", "giorno", name="uq_archivio_non_prezzo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fonte: Mapped[str] = mapped_column(String(16), nullable=False)
    giorno: Mapped[date] = mapped_column(Date, nullable=False)
    osservato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: JSON compatto, una versione per fonte (`versione` dentro il payload).
    dati: Mapped[str] = mapped_column(Text, nullable=False)
