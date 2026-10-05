"""Il conto eToro dell'utente, letto in sola lettura (FA-124).

Tre tabelle, tutte scritte SOLO da `etoro_portafoglio_service.sincronizza`:

- `etoro_strumenti`: l'anagrafica degli strumenti eToro che l'utente ha
  toccato, con l'abbinamento al catalogo. eToro identifica ogni strumento con
  un numero proprio; il ticker del catalogo si ricava, e l'abbinamento ha uno
  stato perche' un abbinamento sbagliato sembra giusto (vedi il servizio).
- `etoro_posizioni`: una riga per posizione eToro, aperta o chiusa. P/L,
  margine ed esposizione sono quelli che eToro calcola (`unrealizedPnL`), nella
  valuta del conto: l'app non li ricalcola, perche' con leva, CFD e cambio la
  formula e' di eToro (`pnlVersion`) e una copia locale divergerebbe in
  silenzio.
- `etoro_conto`: una riga sola, l'ultima fotografia dei totali del conto.

⚠️ Nessuna colonna `user_id`, come per posizioni e preferiti: l'app ha un
utente solo, e la chiave eToro e' la sua.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EtoroStrumento(Base):
    __tablename__ = "etoro_strumenti"

    instrument_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    simbolo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nome: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: Il tipo di eToro: Stocks, ETF, Crypto, Commodity, Indices, ...
    tipo: Mapped[str | None] = mapped_column(String(24), nullable=True)
    exchange_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Il titolo del catalogo, SOLO se l'abbinamento e' automatico o confermato.
    stock_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="SET NULL"), nullable=True
    )
    #: Un candidato trovato ma non abbastanza sicuro: aspetta una conferma.
    candidato_stock_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="SET NULL"), nullable=True
    )
    #: "automatico" | "manuale" | "da_confermare" | "assente"
    abbinamento: Mapped[str] = mapped_column(String(16), nullable=False)
    #: In almeno una watchlist eToro inclusa, all'ultima lettura (FA-125).
    in_watchlist: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0", default=False)
    aggiornato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EtoroPosizione(Base):
    __tablename__ = "etoro_posizioni"

    position_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("etoro_strumenti.instrument_id"), nullable=False, index=True
    )
    #: Il copy trading che l'ha aperta; None = aperta dall'utente.
    mirror_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: "long" | "short"
    lato: Mapped[str] = mapped_column(String(5), nullable=False)
    leva: Mapped[int] = mapped_column(Integer, nullable=False)
    #: "cfd" | "reale" | "swap" | "crypto_margine" | "future" | "altro"
    regolamento: Mapped[str] = mapped_column(String(16), nullable=False)
    aperta_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Nella valuta dello strumento.
    prezzo_apertura: Mapped[float] = mapped_column(Float, nullable=False)
    unita: Mapped[float] = mapped_column(Float, nullable=False)
    #: `amount`: investimento iniziale piu' il margine aggiunto, in USD.
    importo_usd: Mapped[float] = mapped_column(Float, nullable=False)
    investimento_iniziale_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: None = stop o target disattivati su eToro.
    stop: Mapped[float | None] = mapped_column(Float, nullable=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Overnight e dividendi pagati o ricevuti, in USD (negativo = rimborso).
    commissioni_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    # ── L'ultima lettura di `unrealizedPnL`, nella valuta del conto ──
    pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    margine_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    esposizione_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    prezzo_corrente: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: L'ultima sincronizzazione che l'ha vista aperta.
    vista_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # ── La chiusura, dallo storico di eToro ──
    chiusa_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    prezzo_chiusura: Mapped[float | None] = mapped_column(Float, nullable=True)
    profitto_netto_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: "stop" | "target" | "chiusa" | "non_trovata"
    motivo_chiusura: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notificata: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class EtoroConto(Base):
    """Una riga sola (id=1): l'ultima fotografia dei totali del conto."""

    __tablename__ = "etoro_conto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aggiornato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valuta: Mapped[str | None] = mapped_column(String(3), nullable=True)
    #: `credit`: la cassa disponibile per nuove posizioni, in USD.
    credito_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    valore_totale: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_aperto: Mapped[float | None] = mapped_column(Float, nullable=True)
    guadagno_giorno: Mapped[float | None] = mapped_column(Float, nullable=True)
    guadagno_giorno_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class EtoroPatrimonioGiorno(Base):
    """Il valore del conto a fine giornata (FA-127): una riga per giorno di Roma.

    «storico» = la fotografia di fine giornata di eToro (`/balances/history`,
    conto Trading), che eToro conserva per 12 mesi: per questo si salva, e
    dopo un anno questa tabella e' l'unica copia. «vivo» = la riga di oggi,
    riscritta a ogni sincronizzazione finche' il giorno non si chiude.
    """

    __tablename__ = "etoro_patrimonio"

    giorno: Mapped[date] = mapped_column(Date, primary_key=True)
    valore: Mapped[float] = mapped_column(Float, nullable=False)
    cassa: Mapped[float | None] = mapped_column(Float, nullable=True)
    investito: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_aperto: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: "storico" | "vivo"
    fonte: Mapped[str] = mapped_column(String(8), nullable=False)
    aggiornato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EtoroPuntoIntraday(Base):
    """Il valore del conto durante il giorno, per la curva di «oggi» (FA-127).
    Un punto al minuto al massimo; si tengono tre giorni."""

    __tablename__ = "etoro_patrimonio_intraday"

    istante: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    valore: Mapped[float] = mapped_column(Float, nullable=False)
    guadagno_giorno: Mapped[float | None] = mapped_column(Float, nullable=True)


class EtoroOperazione(Base):
    """Un'operazione chiusa, dallo storico di eToro (FA-127, base di FA-128).

    Serve al rendimento senza versamenti: il P/L generato in un periodo e' la
    somma dei profitti chiusi piu' la variazione del P/L aperto, e non dipende
    da quanto si e' versato o prelevato."""

    __tablename__ = "etoro_operazioni"

    position_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    #: Senza FK: lo storico porta strumenti che il portafoglio non ha mai letto.
    instrument_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    aperta_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chiusa_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    lato: Mapped[str] = mapped_column(String(5), nullable=False)
    leva: Mapped[int] = mapped_column(Integer, nullable=False)
    prezzo_apertura: Mapped[float | None] = mapped_column(Float, nullable=True)
    prezzo_chiusura: Mapped[float | None] = mapped_column(Float, nullable=True)
    investimento_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    profitto_netto_usd: Mapped[float] = mapped_column(Float, nullable=False)
    commissioni_usd: Mapped[float | None] = mapped_column(Float, nullable=True)


class EtoroCatalogo(Base):
    """I titoli del catalogo che si possono negoziare su eToro (FA-126).

    Una riga per titolo trovato, rifatta ogni settimana chiedendo a eToro i
    simboli del catalogo (non il contrario: eToro ne ha oltre 40.000, misurato
    il 2026-10-06). Un titolo assente qui non e' negoziabile su eToro, o lo e'
    con un simbolo che nessuna variante indovina."""

    __tablename__ = "etoro_catalogo"

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    instrument_id: Mapped[int] = mapped_column(Integer, nullable=False)
    simbolo: Mapped[str] = mapped_column(String(32), nullable=False)
    nome: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tipo: Mapped[str | None] = mapped_column(String(24), nullable=True)
    verificato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
