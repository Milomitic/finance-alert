"""I match che i cancelli dello scan hanno SCARTATO, col loro esito.

⚠️ Perche' esiste. Lo scan emette un alert solo se il match passa tre cancelli
— Forza minima, allineamento al trend, follow-through — e fino al 2026-09-24
di cio' che non passava non restava traccia. Quindi l'effetto di un cancello
non era misurabile dal vivo PER COSTRUZIONE: si osservavano solo gli esiti di
cio' che passava, e un cancello che scarta i segnali migliori sarebbe stato
indistinguibile da uno che scarta i peggiori.

Lo studio del 2026-09-23 l'ha misurato sulla storia, e ha trovato che la
soglia di Forza non ordina gli esiti e che il cancello del trend scarta, se
qualcosa, segnali un po' MIGLIORI. La storia pero' e' un replay col codice di
oggi; questa tabella e' la conferma dal vivo, fuori campione per costruzione.

L'esito si misura con la STESSA aritmetica del magazzino degli alert
(`signal_outcome_service._label`): eccesso sulla mediana dell'universo
all'orizzonte del detector, dalla barra del segnale. Due metodi diversi
renderebbero incomparabili le due popolazioni, che e' l'unica cosa che questa
tabella serve a confrontare.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SignalCandidate(Base):
    """UN match scartato da almeno un cancello, e poi il suo esito."""

    __tablename__ = "signal_candidates"
    __table_args__ = (
        # ⚠️ Una riga per (titolo, detector, verso, data del segnale), imposta
        # dal DATABASE: lo scan gira piu' volte al giorno sullo stesso match, e
        # righe doppie conterebbero due volte la stessa osservazione.
        SAIndex("ix_signal_candidates_unico", "stock_id", "detector", "tone", "signal_date",
                unique=True),
        SAIndex("ix_signal_candidates_attesa", "matured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    detector: Mapped[str] = mapped_column(String(64), nullable=False)
    tone: Mapped[str] = mapped_column(String(8), nullable=False)  # bull | bear
    #: La barra del match, come `alerts.signal_date`: da qui parte l'esito.
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: L'ultima barra che lo scan aveva quando l'ha visto.
    bar_date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    strength: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Quali cancelli ha passato. Almeno uno e' falso, altrimenti sarebbe un
    #: alert. Tutti e tre e non il «primo che fallisce»: un match scartato per
    #: la Forza puo' anche contraddire il trend, e sapere quale dei due lo
    #: avrebbe fermato da solo e' la domanda che la tabella esiste per fare.
    passa_forza: Mapped[bool] = mapped_column(Boolean, nullable=False)
    passa_trend: Mapped[bool] = mapped_column(Boolean, nullable=False)
    passa_follow: Mapped[bool] = mapped_column(Boolean, nullable=False)
    factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # ─── L'esito, scritto dalla maturazione ───────────────────────────────
    horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fwd_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    mkt_neutral_excess: Mapped[float | None] = mapped_column(Float, nullable=True)
    mkt_neutral_hit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    method_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Il contesto del titolo alla barra del match (`contesto_emissione`) e i
    #: punteggi dei modelli in ombra (`app.ml.ombra`), JSON. Gli stessi che un
    #: alert fissa in `first_contesto` / `first_ombra`: senza, il modello di
    #: selezione — che sceglie fra TUTTI i match, prima dei cancelli — non si
    #: potrebbe valutare sulla popolazione per cui e' fatto.
    contesto: Mapped[str | None] = mapped_column(Text, nullable=True)
    ombra: Mapped[str | None] = mapped_column(Text, nullable=True)
