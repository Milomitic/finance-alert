"""Setups — detector conditions converging, before the trigger fires.

Deliberately a SEPARATE table from `alerts`. A signal means "this condition
matched on bar X"; a setup means "this condition has NOT matched yet". Mixing
them would corrupt `signal_outcomes`, which labels forward returns from the
match date and is the single source of truth for whether the engine works.

The lifecycle is the point. A setup is not just a notification — it is a
falsifiable claim that resolves:

    active ──► converted   the detector fired; `lead_days` records how much
    │                      warning this setup actually gave
    └───────► expired      the conditions decayed without firing

Those two counts give the conversion rate, and `lead_days` gives the realised
lead time. Both are facts about the system, measurable from day one, requiring
no prediction of the market — which is exactly why this feature can ship
before any study exists to justify it.

One row per (stock, detector): a setup that keeps holding is UPDATED, not
duplicated, so `first_seen_at` stays the honest start of the wait.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

STATUS_ACTIVE = "active"
STATUS_CONVERTED = "converted"
STATUS_EXPIRED = "expired"

#: Perche' un episodio si e' chiuso senza convertire. ⚠️ `expire_stale_setups`
#: distingueva gia' le prime due — le contava separatamente nel log, col
#: commento che spiega perche' dicono cose diverse — e poi scriveva entrambe
#: come `expired` senza conservare quale. La distinzione era calcolata e
#: buttata via.
#: Le condizioni si sono sfaldate: il mercato e' andato oltre.
REASON_STALE = "stale"
#: Ha toccato il tetto d'attesa restando valido: un cancello che descrive uno
#: stato invece di dare un anticipo.
REASON_AGED = "aged"
#: E' sceso sotto la soglia di attenzione. ⚠️ Prima la riga veniva CANCELLATA,
#: quindi la prova che quella condizione si fosse mai formata spariva. Ora si
#: chiude — e resta FUORI dal denominatore del tasso di conversione, perche'
#: un setup ritirato non ha mai avuto l'occasione di convertire e contarlo
#: come fallimento misurerebbe il ricambio della shortlist.
REASON_DECAYED = "decayed"
#: La serie prezzi del titolo si e' fermata: non arrivera' nessuna barra che
#: possa far scattare o decadere questa condizione. ⚠️ E' la quarta ragione che
#: FA-061 aveva nominato — «dati insufficienti» — e che non fu costruita per
#: mancanza di popolazione. La popolazione e' comparsa misurando FA-071: nove
#: setup aperti su titoli morti, quattro dei quali IN SHORTLIST.
#:
#: ⚠️ Senza una ragione propria questi finirebbero in `stale`, che dice «le
#: condizioni si sono sfaldate»: falso, e falso nel modo peggiore — non sono
#: decadute, abbiamo smesso di poterle osservare. Conta come gli altri due nel
#: denominatore del tasso di conversione: l'occasione c'era, l'ha tolta il
#: titolo smettendo di quotare.
REASON_NO_DATA = "no_data"


class StockSetup(Base):
    __tablename__ = "stock_setups"
    __table_args__ = (
        # ⚠️ Un episodio APERTO per (stock, detector), non UNA RIGA per coppia.
        #
        # Il vincolo vecchio — `UniqueConstraint(stock_id, detector)` — rendeva
        # impossibile conservare piu' di un'attesa, quindi `upsert_setup`
        # riusava la riga azzerando `resolved_at`, `converted_alert_id` e
        # `lead_days`: «il setup convertito a giugno» smetteva di esistere nel
        # momento in cui la condizione si riformava. Misurato in produzione,
        # 2.050 setup su 2.050 coppie — i due numeri coincidevano per
        # costruzione (FA-061).
        #
        # L'indice PARZIALE dice la cosa che serviva davvero. Supportato da
        # entrambi i backend di questo progetto (SQLite dalla 3.8, Postgres da
        # sempre), quindi la clausola va data a tutti e due i dialetti: darla a
        # uno solo produrrebbe un indice NON unico sull'altro, cioe' il vincolo
        # sparirebbe in silenzio proprio dove conta.
        SAIndex(
            "uq_stock_setups_open_episode", "stock_id", "detector", unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        # The list view is "active, best convenience first".
        SAIndex("ix_stock_setups_status_convenience", "status", "convenience"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    # Which detector this anticipates. Not a FK — detectors are code, not rows.
    detector: Mapped[str] = mapped_column(String(64), nullable=False)
    # ⚠️ 16, non 8. `TONE_UNDETERMINED` ("undetermined") ha 12 caratteri, e con
    # `String(8)` ogni scansione in produzione e' crollata dalle 19:53 UTC del
    # 2026-09-14 per ~19 ore: Postgres rifiuta il valore, la sessione resta
    # abortita e il ciclo della scansione non avanza piu'. SQLite la lunghezza
    # di un VARCHAR NON la fa rispettare, quindi 2.456 test erano verdi.
    # `tests/test_setup_tone_entra_nella_colonna.py` lega i toni a questo numero.
    tone: Mapped[str] = mapped_column(String(16), nullable=False)

    # 0..1, how much of the gate chain holds. Never 1.0 — at 1.0 it is a signal.
    proximity: Mapped[float] = mapped_column(Float, nullable=False)
    # 0..100 ATTENTION score used for ordering. NOT a probability and never
    # presented as one — see app/signals/setups/base.py:convenience.
    convenience: Mapped[float] = mapped_column(Float, nullable=False)
    # Plain-language "what still has to happen" — the actionable part.
    missing: Mapped[str] = mapped_column(Text, nullable=False)
    # Distance from price to the trigger level, in ATR units. The per-SETUP
    # counterpart to `proximity` above, which is per-DETECTOR by construction:
    # two stocks at the same gate stage are not equally close to firing.
    # Nullable because some triggers are not price crossings at all
    # (squeeze_expansion waits on volatility), and because rows written before
    # this column existed have no value to backfill from.
    distance_atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    factors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    annotations_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_ACTIVE)
    #: Perche' si e' chiuso, quando non ha convertito. `None` su un episodio
    #: aperto e su uno convertito — li' lo status lo dice gia'.
    closed_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Whether this setup is currently in the surfaced shortlist (top N of its
    # detector). NOT a delete, deliberately: dropping the row would destroy
    # `first_seen_at`, and a setup oscillating around the cap boundary would
    # restart its clock every time it re-entered — quietly zeroing the one
    # number this feature is judged by.
    shortlisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set on conversion: the alert the setup turned into, and how many days of
    # warning it gave. `lead_days` is the number this whole feature exists to
    # produce — if it trends to 0, setups are not buying any time.
    converted_alert_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True
    )
    lead_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
