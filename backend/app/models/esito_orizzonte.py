"""L'esito di un alert a PIU' orizzonti, con un controllo casuale abbinato.

⚠️ Perche' esiste accanto a `signal_outcomes`. Quella tabella misura ogni alert
all'orizzonte del SUO detector, e per i detector a 63 sedute sei mesi di
magazzino sono due finestre indipendenti: il verdetto resta «non concludente»
per costruzione, non per mancanza di segnali. Misurati anche a 1, 5 e 21
sedute, gli stessi alert danno decine di finestre (FA-138).

`signal_outcomes` non si tocca: ha cinque consumatori (cubo, curva equity,
drift, setup, auto-archiviazione) e resta la fonte dell'orizzonte proprio.

Due riferimenti per ogni riga, perche' rispondono a domande diverse:

- **la mediana dell'universo** (come `signal_outcomes`): il segnale ha battuto
  il titolo tipico di quel giorno?
- **il controllo** (FA-139): la mediana di cinque titoli dello stesso giorno e
  della stessa fascia di volatilita'. Sotto ipotesi nulla il colpo vale 50%
  ESATTI qualunque sia la forma della distribuzione — il titolo e i suoi
  cinque controlli sono sei estrazioni scambiabili, e la probabilita' che il
  primo stia sopra la mediana degli altri cinque e' 3/6. La mediana
  dell'universo non distingue «il segnale sbaglia» da «i titoli volatili quel
  mese sono andati diversamente»; il controllo si'.

L'ancora e' il giorno in cui l'alert e' COMPARSO (`first_emitted_at`), non
`signal_date`, che la revisione riscrive: e' il giorno del prezzo d'ingresso e
del piano, cioe' il momento in cui il segnale era utilizzabile.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EsitoOrizzonte(Base):
    __tablename__ = "esiti_orizzonti"
    __table_args__ = (
        SAIndex("ux_esiti_orizzonti_alert_h", "alert_id", "orizzonte", unique=True),
        SAIndex("ix_esiti_orizzonti_detector", "detector"),
        SAIndex("ix_esiti_orizzonti_ancora", "ancora"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[int] = mapped_column(Integer, nullable=False)
    detector: Mapped[str] = mapped_column(String(64), nullable=False)
    tono: Mapped[str] = mapped_column(String(8), nullable=False)
    #: Il giorno della prima emissione (ripiego dichiarato: `signal_date` per
    #: i pochi alert che precedono `first_emitted_at`).
    ancora: Mapped[date] = mapped_column(Date, nullable=False)
    #: In sedute.
    orizzonte: Mapped[int] = mapped_column(Integer, nullable=False)

    ingresso: Mapped[float] = mapped_column(Float, nullable=False)
    uscita: Mapped[float] = mapped_column(Float, nullable=False)
    rendimento: Mapped[float] = mapped_column(Float, nullable=False)

    #: Rendimento mediano dell'universo (solo societa') allo stesso orizzonte.
    mediana_universo: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Eccesso sulla mediana col segno del tono; positivo = a favore.
    eccesso_mediana: Mapped[float | None] = mapped_column(Float, nullable=True)
    colpo_mediana: Mapped[int | None] = mapped_column(Integer, nullable=True)

    #: Mediana dei rendimenti dei controlli; NULL quando la fascia di quel
    #: giorno non ne aveva abbastanza (un controllo piu' piccolo cambierebbe
    #: il 50% dell'ipotesi nulla).
    controllo: Mapped[float | None] = mapped_column(Float, nullable=True)
    controlli_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eccesso_controllo: Mapped[float | None] = mapped_column(Float, nullable=True)
    colpo_controllo: Mapped[int | None] = mapped_column(Integer, nullable=True)

    metodo: Mapped[str] = mapped_column(String(16), nullable=False)
    maturato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
