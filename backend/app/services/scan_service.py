"""Daily alert scan: fetch OHLCV, evaluate rules with Tier 1/Tier 2 resolution,
fire alerts on edge transitions (False -> True)."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    OhlcvDaily,
    Rule,
    RuleState,
    Stock,
    WatchlistItem,
)
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


def scan_universe(db: Session) -> ScanResult:
    """Scan all stocks, evaluate global rules with Tier 2 overrides, fire edge alerts."""
    result = ScanResult()
    stocks = db.execute(select(Stock)).scalars().all()
    global_rules = _load_global_rules(db)
    tier2 = _load_tier2_overrides_by_stock(db)
    if not global_rules:
        logger.warning("[scan] no Tier 1 rules configured; skipping scan")
        return result

    for stock in stocks:
        ohlcv = _load_ohlcv(db, stock.id)
        if ohlcv is None or len(ohlcv) < 2:
            result.stocks_skipped += 1
            continue
        result.stocks_scanned += 1
        last_close = float(ohlcv["close"].iloc[-1])

        for kind in global_rules.keys():
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
            now = datetime.now(timezone.utc)
            if state is None:
                if new_eval:
                    snapshot = rule_obj.snapshot(ohlcv, eff_params)
                    db.add(
                        Alert(
                            rule_id=global_rule.id,
                            stock_id=stock.id,
                            trigger_price=last_close,
                            snapshot=json.dumps(snapshot),
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
                    snapshot = rule_obj.snapshot(ohlcv, eff_params)
                    db.add(
                        Alert(
                            rule_id=global_rule.id,
                            stock_id=stock.id,
                            trigger_price=last_close,
                            snapshot=json.dumps(snapshot),
                        )
                    )
                    result.alerts_fired += 1
                state.last_evaluation = new_eval
                state.last_evaluated_at = now
                result.states_updated += 1

    logger.info(
        f"[scan] complete: scanned={result.stocks_scanned} skipped={result.stocks_skipped} "
        f"alerts={result.alerts_fired}"
    )
    return result
