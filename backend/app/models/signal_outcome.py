"""Persistent labeled-outcome warehouse for signal alerts.

Append-only (mirrors KpiSnapshot): one row per signal alert, written ONCE its
forward horizon has fully elapsed in stored ohlcv_daily (so the forward close
exists — the only thing that "looks past" the signal). This collapses the three
near-duplicate forward-hit implementations (signal_drift_service._forward_hit —
since deleted, the drift monitor now reads this table —
signal_detector_outcomes._trade_playbook_hit, rule_performance_service) into one
source of truth, and turns every later validation (walk-forward CV, regime
conditioning, ranking, recalibration, score IC) from a multi-minute OHLCV replay
into a cheap SQL query.

No-look-ahead is structural: a row is created only when the forward bar already
exists, and the captured context (regime_at_signal) is computed from data
available AT the trigger bar.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index as SAIndex,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SignalOutcome(Base):
    """One matured signal's realised forward outcome (absolute + market-neutral)."""

    __tablename__ = "signal_outcomes"
    __table_args__ = (
        # One outcome row per alert (the maturation pass is idempotent on this).
        SAIndex("ix_signal_outcomes_alert", "alert_id", unique=True),
        SAIndex("ix_signal_outcomes_detector", "detector"),
        SAIndex("ix_signal_outcomes_signal_date", "signal_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[int] = mapped_column(Integer, nullable=False)
    detector: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    tone: Mapped[str] = mapped_column(String(8), nullable=False)  # bull | bear
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)

    entry_close: Mapped[float] = mapped_column(Float, nullable=False)
    forward_close: Mapped[float] = mapped_column(Float, nullable=False)
    fwd_return: Mapped[float] = mapped_column(Float, nullable=False)
    # Universe mean forward return over the SAME horizon ending the same day —
    # the market benchmark. Nullable when the universe map lacked the date.
    universe_mean_fwd: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Tone-signed market-neutral excess (fwd_return - universe_mean, flipped for
    # bear). Positive = the signal beat the market in its direction.
    mkt_neutral_excess: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Absolute directional hit (1/0): did close move the signalled way? This is
    # the metric the calibration base_rate is built on (parity check anchor).
    abs_hit: Mapped[int] = mapped_column(Integer, nullable=False)
    # Market-neutral hit (1/0): did it beat the universe mean in its direction?
    # The beta-stripped "skill" label. Nullable when no universe benchmark.
    mkt_neutral_hit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Causal regime at the trigger bar (close vs EMA200): bull | bear | flat.
    regime_at_signal: Mapped[str | None] = mapped_column(String(8), nullable=True)

    strength: Mapped[int | None] = mapped_column(Integer, nullable=True)
    probability: Mapped[int | None] = mapped_column(Integer, nullable=True)

    matured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
