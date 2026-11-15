"""Le uscite alternative del piano, misurate in prova silenziosa (FA-141).

Una riga per (alert, variante): la stessa geometria di `plan_outcomes` —
stesso ingresso, stesso stop iniziale, stesso target, stesso orizzonte — con
una regola d'uscita diversa. Nessun consumatore a schermo finche' il criterio
scritto in `docs/superpowers/specs/2026-11-15-uscite-in-ombra.md` non e'
soddisfatto.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PlanOutcomeOmbra(Base):
    __tablename__ = "plan_outcomes_ombra"
    __table_args__ = (
        SAIndex("ux_plan_outcomes_ombra_alert_variante", "alert_id", "variante", unique=True),
        SAIndex("ix_plan_outcomes_ombra_detector", "detector"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    detector: Mapped[str] = mapped_column(String(64), nullable=False)
    #: attuale | pareggio_1r | pareggio_05r | uscita_meta
    variante: Mapped[str] = mapped_column(String(16), nullable=False)
    #: tp1 | stop | pareggio | ambigua | uscita_meta | scaduto
    esito: Mapped[str] = mapped_column(String(16), nullable=False)
    r_multiple: Mapped[float] = mapped_column(Float, nullable=False)
    bars_to_outcome: Mapped[int] = mapped_column(Integer, nullable=False)
    #: `<PLAN_METHOD_VERSION>.<versione delle varianti>`: cambia se cambia il
    #: piano o la regola delle varianti, e la riga si rimisura.
    method_version: Mapped[str] = mapped_column(String(16), nullable=False)
    matured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
