# Unified Signals — Phase U1a (backend): total rule-engine cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Remove the atomic/composite rule engine from the backend entirely so signals are the only alert source — code, API, models, DB tables, and historical rule alerts all gone.

**Architecture:** Subtractive refactor in a safe order — first stop evaluating rules (scan), then adapt the read-side services to a signals-only world, then delete rule code/models, and ONLY THEN run the destructive migration (so the ORM models and DB schema never disagree mid-flight). Frontend cleanup is a separate follow-up plan (`U1a-frontend`).

**Tech Stack:** FastAPI, SQLAlchemy 2 (SQLite), Alembic, pytest.

**Conventions:** tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; full suite `... tests/ -q`. Alembic `./.venv/Scripts/alembic.exe ...`. After each task the FULL suite must stay green (this is a refactor — green suite is the safety net). Signals (the 5 detectors) must keep firing throughout.

**Mapped footprint (verified):**
- Package `app/rules/` (12 files) + `app/rules/registry.py:RULES` + `composite.py`.
- Models `app/models/rule.py` (`Rule`, `RuleState`); `Alert.rule_id` FK column.
- API routers `app/api/rules.py`, `rule_catalog.py`, `rule_preview.py`, `rule_performance.py` (registered in `app/main.py`).
- Services referencing rules: `scan_service`, `alert_service`, `stats_service` (already outer-joins+derives since 1c), `notifier_service` (already uses derive_rule_kind), `stock_detail_service`, `rule_performance_service`, `rule_compaction_service`.
- Schemas `app/schemas/rule.py`; `app/schemas/alert.py` (`rule_id`).
- Scripts `app/scripts/bootstrap_rules.py`, `bootstrap.py` (rule seeding).
- The score system (`StockScoreCard`, `scoreMeta`, `score_service`) is SEPARATE — DO NOT TOUCH.

---

### Task 1: scan_universe → signals-only

**Files:**
- Modify: `backend/app/services/scan_service.py`
- Test: `backend/tests/test_scan_emits_signal_alerts.py` (exists — must still pass), `backend/tests/test_scan_service.py` (existing rule-scan tests will be removed/adapted)

- [ ] **Step 1: Adapt the scan**
Remove the rule-evaluation machinery, keep the OHLCV load + `evaluate_signals`. Delete: imports `Rule, RuleState` (from `app.models`), `from app.rules.composite import ...`, `from app.rules.registry import RULES`; the helpers `_load_global_rules`, `_resolve_effective_rule`, `_get_or_create_state`; and inside `scan_universe` the `global_rules = _load_global_rules(...)` block + the entire `for kind, candidate_global in global_rules.items():` loop + its RuleState edge-trigger + the `Alert(rule_id=...)` creation. Keep the per-stock OHLCV load and the existing signals sub-phase:
```python
            # Signal engine — the only alert source.
            try:
                result.alerts_fired += evaluate_signals(db, stock, ohlcv)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[scan] signals failed for {stock.ticker}: {e}")
```
Keep the loop's progress callbacks + the per-stock `db.commit()` / state persistence at the loop tail. Update the module docstring to "Daily scan: fetch OHLCV per stock, run the signal engine, fire edge-deduped signal alerts."

- [ ] **Step 2: Adapt/remove rule-scan tests**
In `backend/tests/test_scan_service.py`, delete tests that asserted rule-alert firing / RuleState edge-trigger. Keep/adapt any that assert the scan runs + commits. `test_scan_emits_signal_alerts.py` stays as-is (signals path).

- [ ] **Step 3: Run**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_scan_emits_signal_alerts.py tests/test_scan_service.py -q` → green. Then full suite (some rule tests elsewhere may now fail — they're removed in later tasks; note them).

- [ ] **Step 4: Commit**
```bash
git add backend/app/services/scan_service.py backend/tests/test_scan_service.py
git commit -m "refactor(scan): signals-only scan (drop rule evaluation)"
```

---

### Task 2: alert_service + schemas/alert → signals-only kind

**Files:**
- Modify: `backend/app/services/alert_service.py`, `backend/app/schemas/alert.py`
- Test: `backend/tests/test_alert_service.py`, `backend/tests/test_signal_alert_visibility.py`

- [ ] **Step 1: Adapt**
In `alert_service.py`: drop the `Rule` import + the LEFT JOIN to `Rule` in `list_alerts`; `rule_kind` now derives purely from `signal_name` (`f"signal:{signal_name}"` or None). Keep `derive_rule_kind(rule_kind=None, signal_name)` callable for back-compat but it's only ever called with rule_kind=None now. The `rule_kind` filter in `_apply_filters` now matches `Alert.signal_name`-derived kinds: filter by `("signal:" || signal_name) == rule_kind` (or strip the `signal:` prefix and compare `signal_name`). In `schemas/alert.py`: remove the `rule_id` field from `AlertOut` (or keep optional but unused — prefer remove); `rule_kind` stays.

- [ ] **Step 2: Tests** — update assertions that expected rule-based `rule_kind`; assert signal alerts serialize with `signal:<name>`. Run those test files green.

- [ ] **Step 3: Commit**
```bash
git add backend/app/services/alert_service.py backend/app/schemas/alert.py backend/tests/test_alert_service.py backend/tests/test_signal_alert_visibility.py
git commit -m "refactor(alerts): signals-only rule_kind derivation"
```

---

### Task 3: stock_detail_service + notifier_service → signals-only

**Files:**
- Modify: `backend/app/services/stock_detail_service.py`, `backend/app/services/notifier_service.py`
- Test: their existing tests

- [ ] **Step 1: Adapt**
`stock_detail_service`: drop the `Rule` join in the alerts-history query; emit `(alert, derive_rule_kind(None, alert.signal_name))`. `notifier_service`: it already calls `derive_rule_kind(rule.kind if rule else None, a.signal_name)`; since rules are gone, simplify to `derive_rule_kind(None, a.signal_name) or "unknown"` and drop the `rules_by_id` lookup + `Rule` import.

- [ ] **Step 2: Tests + Step 3: Commit**
Run the relevant tests green.
```bash
git add backend/app/services/stock_detail_service.py backend/app/services/notifier_service.py backend/tests/
git commit -m "refactor(alerts): stock-detail + digest signals-only"
```

---

### Task 4: rule_performance → signal performance

**Files:**
- Modify/rename: `backend/app/services/rule_performance_service.py` → keep filename but key by `signal_name`; `backend/app/api/rule_performance.py`
- Test: `backend/tests/test_rule_performance*.py`

- [ ] **Step 1: Adapt**
The forward-return efficacy currently groups by `rule_kind` (via Rule). Re-key it by `signal_name` (the alert's signal). Replace any `join(Rule)` / `Rule.kind` with `Alert.signal_name` and label the output kind as `signal:<name>`. The API response field `rule_kind` becomes the `signal:<name>` string (keep the field name to avoid a frontend churn in this backend-only phase; the frontend cleanup plan renames the UI copy).

- [ ] **Step 2: Tests + Step 3: Commit**
```bash
git add backend/app/services/rule_performance_service.py backend/app/api/rule_performance.py backend/tests/
git commit -m "refactor(perf): forward-return efficacy keyed by signal_name"
```

---

### Task 5: Remove rule API routers + unregister

**Files:**
- Delete: `backend/app/api/rules.py`, `backend/app/api/rule_catalog.py`, `backend/app/api/rule_preview.py`
- Modify: `backend/app/main.py` (remove their `include_router` lines + imports)
- Modify: `backend/app/schemas/rule.py` → delete
- Test: delete `backend/tests/test_rules_api.py`, `test_rule_catalog*.py`, `test_rule_preview*.py` if present

- [ ] **Step 1: Delete + unregister**
Remove the three routers, their imports + `app.include_router(...)` lines in `main.py`, and `schemas/rule.py`. Grep `backend/app` for any remaining import of the deleted modules and fix.

- [ ] **Step 2: Run**
`cd backend && ./.venv/Scripts/python.exe -c "import app.main"` → imports clean (no ModuleNotFoundError). Full suite (rule-API tests removed).

- [ ] **Step 3: Commit**
```bash
git add -A backend/app/api/ backend/app/main.py backend/app/schemas/ backend/tests/
git commit -m "refactor(api): remove rule + rule-catalog + rule-preview routers"
```

---

### Task 6: Remove app/rules/ package + rule scripts/services

**Files:**
- Delete: `backend/app/rules/` (entire package), `backend/app/scripts/bootstrap_rules.py`, `backend/app/services/rule_compaction_service.py`
- Modify: `backend/app/scripts/bootstrap.py` (remove rule-seeding calls), any scheduler hook calling `rule_compaction_service`

- [ ] **Step 1: Delete + fix references**
Remove the package + scripts + compaction service. Grep `backend/app` for `app.rules`, `bootstrap_rules`, `rule_compaction` and remove every reference (e.g. a scheduler job in `app/main.py` lifespan or a scheduler module). Confirm nothing imports them.

- [ ] **Step 2: Run** — `import app.main` clean + full suite green.

- [ ] **Step 3: Commit**
```bash
git add -A backend/app/
git commit -m "refactor: delete app/rules package + rule bootstrap/compaction"
```

---

### Task 7: Remove Rule/RuleState models + Alert.rule_id

**Files:**
- Delete: `backend/app/models/rule.py`
- Modify: `backend/app/models/__init__.py` (drop `Rule`, `RuleState` exports), `backend/app/models/alert.py` (drop `rule_id` column + its index + the FK)
- Test: full suite

- [ ] **Step 1: Edit models**
Remove `rule.py`; remove `Rule`/`RuleState` from `models/__init__.py`. In `alert.py` delete the `rule_id` mapped_column + `ix_alerts_rule_id` from `__table_args__` + the `ForeignKey` import if now unused. The `db` test fixture builds the schema from metadata, so removing the model column means tests immediately reflect a rule_id-free Alert.

- [ ] **Step 2: Run** — full suite green (any remaining `Alert(rule_id=...)` in tests must be fixed to drop that kwarg; grep tests for `rule_id=`).

- [ ] **Step 3: Commit**
```bash
git add backend/app/models/ backend/tests/
git commit -m "refactor(models): remove Rule/RuleState + Alert.rule_id"
```

---

### Task 8: Destructive migration (delete rule history + drop columns/tables)

**Files:**
- Create: `backend/alembic/versions/<rev>_drop_rule_engine.py`

- [ ] **Step 1: Generate + fill**
`cd backend && ./.venv/Scripts/alembic.exe revision -m "drop rule engine"`. Fill `upgrade()` (SQLite batch mode; order matters — delete data, drop FK column, drop child table before parent):
```python
def upgrade() -> None:
    # 1. Delete historical rule-based alerts (signal alerts have rule_id IS NULL).
    op.execute("DELETE FROM alerts WHERE rule_id IS NOT NULL")
    # 2. Drop Alert.rule_id (index + column) via batch (SQLite table rebuild).
    with op.batch_alter_table("alerts") as b:
        b.drop_index("ix_alerts_rule_id")
        b.drop_column("rule_id")
    # 3. Drop rule_states (child) then rules (parent).
    op.drop_table("rule_states")
    op.drop_table("rules")

def downgrade() -> None:
    raise NotImplementedError("rule engine removal is irreversible (user-approved)")
```
(If `ix_alerts_rule_id` was already dropped by the model change reflecting into a prior autogenerate, adjust — inspect with `alembic.exe heads`/`current` first.)

- [ ] **Step 2: Apply**
`cd backend && ./.venv/Scripts/alembic.exe upgrade head` → success. Verify: `./.venv/Scripts/python.exe -c "from app.core.db import SessionLocal; from sqlalchemy import text; db=SessionLocal(); print(db.execute(text(\"SELECT count(*) FROM alerts WHERE rule_id IS NOT NULL\")).scalar() if False else 'rules table gone:', [r[0] for r in db.execute(text(\"SELECT name FROM sqlite_master WHERE type='table' AND name IN ('rules','rule_states')\"))])"` → empty list (tables gone).

- [ ] **Step 3: Commit**
```bash
git add backend/alembic/versions/
git commit -m "feat(db): drop rules/rule_states + Alert.rule_id, delete rule alert history"
```

---

### Task 9: Full-suite sweep + scan smoke

- [ ] **Step 1:** `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q` → all green. Grep `backend/app backend/tests` for residual `Rule`, `rule_id`, `app.rules`, `RuleState`, `global_rules` — none remain (except the score system's unrelated symbols + `rule_kind`/`derive_rule_kind` which stay as the signal-kind carrier).
- [ ] **Step 2: Scan smoke** — run `scan_universe(SessionLocal())` in-process on the real DB; confirm it completes and creates `signal_name`-bearing alerts (no rule references, no crash).
- [ ] **Step 3: Commit** any test fixups.
```bash
git add -A backend/
git commit -m "chore: signals-only backend green (rule engine fully removed)"
```

---

## Self-review notes
- Spec coverage (master spec §6 backend bullets): scan rule sub-phase removed (T1), alert_service/stats/notifier/stock_detail signals-only (T2/T3; stats+notifier already adapted in 1c-T3), rule_performance→signal (T4), rule APIs removed (T5), app/rules + scripts + compaction removed (T6), Rule/RuleState models + Alert.rule_id removed (T7), destructive migration incl. history (T8), green sweep (T9). Frontend is the separate U1a-frontend plan. ✓
- Order safety: code stops referencing rules (T1-T7) BEFORE the migration drops the DB structures (T8) — models and schema never disagree. ✓
- Scope guard: the SCORE system is explicitly out of scope; `rule_kind`/`derive_rule_kind` are kept as the signal-kind carrier (not rule artifacts). ✓
- No new behavior — this is removal; the green full suite + scan smoke are the safety net (TDD-by-regression). ✓

## Follow-up
`U1a-frontend` plan: remove `components/rules/`, `useRules`, `api/rules`, `EffectiveRulesCard`, `RuleExpressionNode`/`Rule`/`RuleKind` types, the rule cases in `alertMeta`, the rule-kind filter in `AlertFilters`, the RulesPanel mount in `AlertsPage`; rename "Efficacia regole"→"Efficacia segnali"; add a read-only "Catalogo segnali" view; rebuild dist.
