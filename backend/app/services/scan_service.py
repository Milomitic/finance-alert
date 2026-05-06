"""Daily alert scan: fetch OHLCV, evaluate rules with Tier 1/Tier 2 resolution,
fire alerts on edge transitions (False -> True)."""
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    OhlcvDaily,
    Rule,
    RuleState,
    Stock,
    WatchlistItem,
)
from app.rules.composite import evaluate_expression, snapshot_expression
from app.rules.registry import RULES


@dataclass
class ScanResult:
    stocks_scanned: int = 0
    stocks_skipped: int = 0
    alerts_fired: int = 0
    states_updated: int = 0


def _load_global_rules(db: Session) -> dict[str, Rule]:
    """Return {kind: Rule} for all Tier 1 (watchlist_id IS NULL) rules."""
    rows = db.execute(select(Rule).where(Rule.watchlist_id.is_(None))).scalars().all()
    return {r.kind: r for r in rows}


def _load_tier2_overrides_by_stock(db: Session) -> dict[int, dict[str, Rule]]:
    """Build {stock_id: {kind: Rule}} for all Tier 2 rules across all watchlists.

    If a stock is in multiple watchlists with conflicting overrides for the same kind,
    the most-restrictive wins: disabled > enabled-with-params > (no override).
    """
    rows = db.execute(
        select(Rule, WatchlistItem.stock_id)
        .join(WatchlistItem, WatchlistItem.watchlist_id == Rule.watchlist_id)
        .where(Rule.watchlist_id.isnot(None))
    ).all()
    out: dict[int, dict[str, Rule]] = {}
    for rule, stock_id in rows:
        existing = out.setdefault(stock_id, {}).get(rule.kind)
        if existing is None:
            out[stock_id][rule.kind] = rule
            continue
        # Conflict resolution: disabled > enabled
        if not rule.enabled and existing.enabled:
            out[stock_id][rule.kind] = rule
    return out


def _load_ohlcv(db: Session, stock_id: int, limit: int = 260) -> pd.DataFrame | None:
    rows = (
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock_id)
            .order_by(OhlcvDaily.date.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    rows = rows[-limit:]
    return pd.DataFrame(
        {
            "date": [r.date for r in rows],
            "open": [float(r.open) for r in rows],
            "high": [float(r.high) for r in rows],
            "low": [float(r.low) for r in rows],
            "close": [float(r.close) for r in rows],
            "volume": [int(r.volume) for r in rows],
        }
    )


def _resolve_effective_rule(
    stock_id: int,
    kind: str,
    global_rules: dict[str, Rule],
    tier2: dict[int, dict[str, Rule]],
) -> tuple[Rule, dict[str, Any]] | None:
    """Resolve which rule (and which params) to apply for (stock, kind).

    Returns (global_rule, effective_params) — the global Rule object is always
    returned for state indexing, but params may come from Tier 2 override.
    Returns None if the rule should be skipped.
    """
    global_rule = global_rules.get(kind)
    if global_rule is None or not global_rule.enabled:
        return None
    override = tier2.get(stock_id, {}).get(kind)
    if override is None:
        return global_rule, json.loads(global_rule.params or "{}")
    if not override.enabled:
        return None
    return global_rule, json.loads(override.params or global_rule.params or "{}")


def _get_or_create_state(db: Session, rule_id: int, stock_id: int) -> RuleState | None:
    return db.execute(
        select(RuleState).where(
            RuleState.rule_id == rule_id, RuleState.stock_id == stock_id
        )
    ).scalar_one_or_none()


class ScanCancelled(RuntimeError):
    """Raised when the cancel_check callback returned True between iterations.
    The runner catches this and marks the ScanRun row as 'failed' with a clear
    user-cancel message (distinct from a crash)."""


def scan_universe(
    db: Session,
    *,
    on_progress: Callable[[int, int, "ScanResult"], None] | None = None,
    progress_every: int = 10,
    cancel_check: Callable[[], bool] | None = None,
) -> ScanResult:
    """Scan all stocks, evaluate global rules with Tier 2 overrides, fire edge alerts.

    on_progress, if provided, is called every `progress_every` stocks AND at start/end
    with (stocks_done, stocks_total, result_so_far). Use this to surface live progress
    to a UI (e.g. by updating a `scan_runs` row).

    cancel_check, if provided, is called at the same cadence as on_progress.
    When it returns True the loop raises ScanCancelled so the caller can mark
    the run as user-cancelled. The check is O(1) (in-memory set membership)
    so the overhead is negligible.
    """
    result = ScanResult()
    # Skip Chinese-mainland stocks entirely from alert generation. They
    # live in the catalog only to feed dashboard breadth + Asia mood
    # aggregation; the user doesn't want alerts for them. Mirrors the
    # filter in `services/stock_service._apply_filter`. NULL-tolerant
    # (`!=` is false for NULL in SQL) so test fixtures and legacy rows
    # without a country still scan normally.
    stocks = list(
        db.execute(
            select(Stock).where(
                or_(Stock.country.is_(None), Stock.country != "CN")
            )
        )
        .scalars()
        .all()
    )
    total = len(stocks)
    global_rules = _load_global_rules(db)
    tier2 = _load_tier2_overrides_by_stock(db)
    if not global_rules:
        logger.warning("[scan] no Tier 1 rules configured; skipping scan")
        if on_progress:
            on_progress(0, total, result)
        return result

    if on_progress:
        on_progress(0, total, result)

    for idx, stock in enumerate(stocks, start=1):
        # Cooperative cancel: bail out cleanly between iterations. We check at
        # the same cadence as on_progress to keep the overhead bounded; a per-
        # iteration check would be ~110× more frequent for the 1132-stock
        # universe but adds no real responsiveness for the user.
        if cancel_check is not None and (idx % progress_every == 1 or idx == 1):
            if cancel_check():
                logger.info(
                    f"[scan] cancel requested at idx={idx}/{total} — aborting cleanly"
                )
                raise ScanCancelled("Cancellato dall'utente")

        ohlcv = _load_ohlcv(db, stock.id)
        if ohlcv is None or len(ohlcv) < 2:
            result.stocks_skipped += 1
            if on_progress and (idx % progress_every == 0 or idx == total):
                on_progress(idx, total, result)
            continue
        result.stocks_scanned += 1
        last_close = float(ohlcv["close"].iloc[-1])
        # The market-data bar date on which the indicator condition matched.
        # Stored on every Alert row created in this iteration so the UI can
        # distinguish "signal occurred Friday" from "system recorded Monday".
        # Falls back to None if the date column is missing (defensive — should
        # never happen given _load_ohlcv always sets it).
        signal_bar_date = ohlcv["date"].iloc[-1] if "date" in ohlcv.columns else None

        for kind, candidate_global in global_rules.items():
            global_rule = candidate_global
            if not global_rule.enabled:
                continue
            if global_rule.expression:
                try:
                    expr = json.loads(global_rule.expression)
                    new_eval = evaluate_expression(expr, ohlcv)
                except Exception as e:  # noqa: BLE001
                    logger.exception(
                        f"[scan] composite eval crashed stock={stock.ticker} rule_id={global_rule.id}: {e}"
                    )
                    continue
                eff_params: dict[str, Any] = {}
                rule_obj = None  # signals "use composite snapshot below"
            else:
                resolved = _resolve_effective_rule(stock.id, kind, global_rules, tier2)
                if resolved is None:
                    continue
                global_rule, eff_params = resolved
                rule_obj = RULES.get(kind)
                if rule_obj is None:
                    continue
                try:
                    new_eval = rule_obj.evaluate(ohlcv, eff_params)
                except Exception as e:  # noqa: BLE001
                    logger.exception(f"[scan] eval crashed for stock={stock.ticker} kind={kind}: {e}")
                    continue

            state = _get_or_create_state(db, global_rule.id, stock.id)
            now = datetime.now(UTC)
            if state is None:
                if new_eval:
                    if rule_obj is not None:
                        snapshot = rule_obj.snapshot(ohlcv, eff_params)
                    else:
                        snapshot = snapshot_expression(json.loads(global_rule.expression), ohlcv)
                    db.add(
                        Alert(
                            rule_id=global_rule.id,
                            stock_id=stock.id,
                            trigger_price=last_close,
                            snapshot=json.dumps(snapshot),
                            signal_date=signal_bar_date,
                        )
                    )
                    result.alerts_fired += 1
                db.add(
                    RuleState(
                        rule_id=global_rule.id,
                        stock_id=stock.id,
                        last_evaluation=new_eval,
                        last_evaluated_at=now,
                    )
                )
                result.states_updated += 1
            else:
                if not state.last_evaluation and new_eval:
                    if rule_obj is not None:
                        snapshot = rule_obj.snapshot(ohlcv, eff_params)
                    else:
                        snapshot = snapshot_expression(json.loads(global_rule.expression), ohlcv)
                    db.add(
                        Alert(
                            rule_id=global_rule.id,
                            stock_id=stock.id,
                            trigger_price=last_close,
                            snapshot=json.dumps(snapshot),
                            signal_date=signal_bar_date,
                        )
                    )
                    result.alerts_fired += 1
                state.last_evaluation = new_eval
                state.last_evaluated_at = now
                result.states_updated += 1

        if on_progress and (idx % progress_every == 0 or idx == total):
            on_progress(idx, total, result)

    if on_progress:
        on_progress(total, total, result)

    logger.info(
        f"[scan] complete: scanned={result.stocks_scanned} skipped={result.stocks_skipped} "
        f"alerts={result.alerts_fired}"
    )
    return result
