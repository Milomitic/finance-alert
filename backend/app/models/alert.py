"""Alert events produced by the signal engine."""
import json
from datetime import UTC, date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Index as SAIndex,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _istante_utc(valore: object) -> datetime | None:
    if isinstance(valore, str) and valore:
        try:
            valore = datetime.fromisoformat(valore)
        except ValueError:
            return None
    if not isinstance(valore, datetime):
        return None
    # Convenzione del progetto: un istante senza fuso e' UTC. E si PORTA in UTC
    # uno che ne ha un altro, perche' SQLite scrive l'ora del quadrante e butta
    # il fuso: le 01:30 di Roma diventerebbero le 01:30 UTC.
    return valore.replace(tzinfo=UTC) if valore.tzinfo is None else valore.astimezone(UTC)


def nascita(snapshot: object, triggered_at: object) -> datetime:
    """L'istante in cui l'alert e' COMPARSO, dai campi con cui viene scritto.

    `snapshot.first_emitted_at` quando c'e' — la scansione lo fissa alla
    creazione e lo conserva a ogni revisione — altrimenti `triggered_at`, che
    su una riga mai rivista e' la creazione stessa (gli alert di prezzo, e
    quelli che precedono il campo), altrimenti adesso.

    E' la stessa regola con cui la migrazione `a9d4e7f1c2b8` ha riempito lo
    storico: colonna e snapshot non possono divergere, qualunque percorso
    scriva la riga — scansione, alert di prezzo, seme dell'e2e, test.
    """
    try:
        dati = json.loads(snapshot) if isinstance(snapshot, str) and snapshot else {}
    except ValueError:
        dati = {}
    if isinstance(dati, dict):
        dalla_scansione = _istante_utc(dati.get("first_emitted_at"))
        if dalla_scansione is not None:
            return dalla_scansione
    return _istante_utc(triggered_at) or datetime.now(UTC)


def _nascita_alla_creazione(context) -> datetime:
    riga = context.get_current_parameters()
    return nascita(riga.get("snapshot"), riga.get("triggered_at"))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        SAIndex("ix_alerts_triggered_at", "triggered_at"),
        SAIndex("ix_alerts_emitted_at", "emitted_at"),
        SAIndex("ix_alerts_stock_id", "stock_id"),
        SAIndex("ix_alerts_read_at", "read_at"),
        SAIndex("ix_alerts_archived_at", "archived_at"),
        SAIndex("ix_alerts_signal_name", "signal_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    # ⚠️ L'ULTIMA REVISIONE, non la creazione: finche' il segnale persiste ogni
    # scansione lo rivede e lo riscrive (80% degli alert almeno una volta, uno
    # 167). Per contare o datare gli alert si legge `emitted_at`.
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # La NASCITA dell'alert (FA-100): scritta alla creazione e mai piu' toccata,
    # perche' nessuna revisione la nomina. Ogni conteggio «alert nelle ultime N
    # ore» va fatto qui: su `triggered_at` contava anche tutti i segnali nati
    # prima e ancora vivi — digest del 24/09 «723 alert» contro 87 nati, KPI
    # del cruscotto 555 contro 71. Il default lato database serve alle INSERT
    # scritte a mano; quelle di SQLAlchemy passano da `nascita`.
    emitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=_nascita_alla_creazione, server_default=func.now(),
    )
    # The market-data bar date on which the rule's condition matched. This
    # may differ from `triggered_at`: the scan runs daily/on-demand, so the
    # bar with RSI=85 may have closed yesterday or last Friday while the
    # alert row is created when the scan runs today. Storing both dates
    # lets the UI distinguish "the indicator crossed threshold on Friday,
    # the system noticed Monday" — useful when a scan is missed or when
    # backfilling. Nullable for legacy rows from before this column existed.
    signal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Set on alerts produced by the signal engine (rule_id is then None).
    # The "kind" surfaced to the UI is derived as f"signal:{signal_name}".
    signal_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    # JSON snapshot of indicator values at trigger time, e.g.
    # {"rsi": 28.4, "period": 14, "threshold": 30}
    snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
