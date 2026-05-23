# Signal Engine — Phase 1c Implementation Plan (enriched alert UI + backend consistency)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Render `signal:*` alerts richly (confidence + tone + event-chain timeline + factor bars + invalidation + cited sources) instead of a raw-JSON dump, and make the backend surfaces consistent (Telegram digest labels signals; dashboard alerts-by-day / top-stocks count signals).

**Architecture:** Frontend — extend `lib/alertMeta.ts` to understand the `signal:<name>` kind convention (label/icon/tone) and add a `SignalSnapshotView` component the `AlertDetailDialog` renders for signal alerts. The shared `AlertKindChip`/`AlertToneChip` already call `getAlertMeta`, so the feed/table chips fix themselves once `getAlertMeta` handles signals. Backend — `notifier_service` and `stats_service` switch from the Rule inner-join (which drops signal alerts) to deriving the kind via `derive_rule_kind`.

**Tech Stack:** React 19 + Vite + TS (vitest for pure-logic tests; `npm run build` = tsc typecheck + vite build for components); FastAPI + SQLAlchemy + pytest.

**Conventions:** backend tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; frontend logic tests `cd frontend && npm run test -- --run <path>`; frontend typecheck/build `cd frontend && npm run build`. Keep new source ASCII-only. **After 1c lands, rebuild `frontend/dist` and tell the user to hard-reload (the app is served from dist on :8000).**

**Snapshot shape for signal alerts** (written by `signal_scan_service`): `{tone: "bull"|"bear", confidence: int 0-100, chain: [{date, label, detail}], factors: {name: float 0-1}, invalidation: {level: float, reason: str} | null, sources: [str]}`.

---

### Task 1: Frontend types + alertMeta signal handling

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/lib/alertMeta.ts`
- Test: `frontend/src/lib/alertMeta.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/lib/alertMeta.test.ts
import { describe, expect, it } from "vitest";
import type { Alert } from "@/api/types";
import { getAlertMeta, getSnapshotHeadline, isSignalKind } from "@/lib/alertMeta";

function signalAlert(over: Partial<Alert> = {}): Alert {
  return {
    id: 1, rule_id: null, rule_kind: "signal:volume_breakout", stock_id: 1,
    ticker: "AAA", name: "AAA Co", triggered_at: "2026-05-01T00:00:00Z",
    signal_date: "2026-05-01", trigger_price: 10,
    snapshot: { tone: "bull", confidence: 82, chain: [{ date: "2026-05-01", label: "Breakout bull", detail: "" }] },
    read_at: null, archived_at: null, ...over,
  } as Alert;
}

describe("signal alert metadata", () => {
  it("isSignalKind recognises the signal: prefix", () => {
    expect(isSignalKind("signal:volume_breakout")).toBe(true);
    expect(isSignalKind("rsi_oversold")).toBe(false);
    expect(isSignalKind(null)).toBe(false);
  });

  it("derives a bullish tone + friendly label for a bull signal", () => {
    const meta = getAlertMeta(signalAlert());
    expect(meta.tone).toBe("bullish");
    expect(meta.label.toLowerCase()).toContain("breakout");
  });

  it("derives a bearish tone from snapshot.tone", () => {
    const meta = getAlertMeta(signalAlert({ snapshot: { tone: "bear", confidence: 70, chain: [] } }));
    expect(meta.tone).toBe("bearish");
  });

  it("headline summarises confidence + chain length", () => {
    const h = getSnapshotHeadline("signal:volume_breakout",
      { confidence: 82, chain: [{ date: "x", label: "y" }, { date: "z", label: "w" }] });
    expect(h).toContain("82");
  });
});
```

- [ ] **Step 2: Run, verify fail**

Run: `cd frontend && npm run test -- --run src/lib/alertMeta.test.ts`
Expected: FAIL — `isSignalKind` not exported.

- [ ] **Step 3: Widen the types in `types.ts`**

Find the `Alert` interface and the `RuleKind` type. Change `rule_id: number;` to `rule_id: number | null;` (signal alerts have no rule). After the `RuleKind` union add a signal-kind type and widen `Alert.rule_kind`:

```ts
/** Signal-engine alerts use the "signal:<detector-name>" convention for
 *  rule_kind (e.g. "signal:volume_breakout"); they have rule_id === null. */
export type SignalKind = `signal:${string}`;
```

Change `rule_kind: RuleKind | null;` to `rule_kind: RuleKind | SignalKind | null;`.

Add a typed shape for the signal snapshot (after the `Alert` interface):

```ts
export interface SignalChainStep {
  date: string;
  label: string;
  detail?: string;
}

export interface SignalSnapshot {
  tone: "bull" | "bear";
  confidence: number; // 0..100
  chain: SignalChainStep[];
  factors?: Record<string, number>;
  invalidation?: { level?: number; reason?: string } | null;
  sources?: string[];
}
```

- [ ] **Step 4: Extend `alertMeta.ts`**

Add `Layers` and `GitBranch` to the lucide import line at the top (alongside the existing icons). Then add, after the `getAlertKindMeta` function:

```ts
/** True when the alert kind is a signal-engine kind ("signal:<name>"). */
export function isSignalKind(rule_kind: string | null | undefined): boolean {
  return typeof rule_kind === "string" && rule_kind.startsWith("signal:");
}

/** Friendly label + icon per signal detector name (the part after "signal:").
 *  Tone is NOT here — it comes from the snapshot's bull/bear field. */
const SIGNAL_META: Record<string, { label: string; icon: LucideIcon }> = {
  volume_breakout: { label: "Volume Breakout", icon: Zap },
  trend_pullback: { label: "Trend + Pullback", icon: TrendingUp },
  rsi_divergence: { label: "Divergenza RSI", icon: Activity },
  squeeze_expansion: { label: "Squeeze + Espansione", icon: ChevronsUp },
  high52_momentum: { label: "Massimo 52 settimane", icon: ArrowUpToLine },
};

function signalMeta(rule_kind: string): { label: string; icon: LucideIcon } {
  const name = rule_kind.slice("signal:".length);
  return SIGNAL_META[name] ?? { label: name.replace(/_/g, " "), icon: Bell };
}
```

Modify `getAlertMeta` so signal alerts derive tone from the snapshot and a friendly label from `SIGNAL_META`. Replace the body's first lines:

```ts
export function getAlertMeta(alert: Alert): AlertKindMeta {
  // Signal-engine alert: friendly label from the detector name, tone from the
  // snapshot's bull/bear field (the kind string itself carries no direction).
  if (isSignalKind(alert.rule_kind)) {
    const { label, icon } = signalMeta(alert.rule_kind as string);
    const snapTone = (alert.snapshot as Record<string, unknown> | undefined)?.tone;
    const tone: AlertTone =
      snapTone === "bull" ? "bullish" : snapTone === "bear" ? "bearish" : "neutral";
    return { label, icon, tone };
  }
  if (alert.rule_kind) return getAlertKindMeta(alert.rule_kind);
  // ... (existing price-alert direction logic stays unchanged below)
```

(Leave the rest of `getAlertMeta` — the price-alert `direction` branch — exactly as it is.)

In `getSnapshotHeadline`, handle signal kinds FIRST (before the switch):

```ts
export function getSnapshotHeadline(
  rule_kind: string | null | undefined,
  snap: Record<string, unknown> | null | undefined,
): string | null {
  if (!snap) return null;
  if (isSignalKind(rule_kind)) {
    const conf = snap["confidence"];
    const chain = snap["chain"];
    const nEvents = Array.isArray(chain) ? chain.length : 0;
    const confTxt = typeof conf === "number" ? `Confidenza ${Math.round(conf)}%` : "Segnale";
    return nEvents > 0 ? `${confTxt} · ${nEvents} eventi` : confTxt;
  }
  const get = (k: string): unknown => snap[k];
  // ... (existing fmt + switch unchanged)
```

- [ ] **Step 5: Run tests + typecheck**

Run: `cd frontend && npm run test -- --run src/lib/alertMeta.test.ts` (expect 4 pass).
Run: `cd frontend && npm run build` (tsc must pass — confirm no type errors from the widened types).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/lib/alertMeta.ts frontend/src/lib/alertMeta.test.ts
git commit -m "feat(signals-ui): alertMeta understands signal:<name> kinds + types"
```

---

### Task 2: SignalSnapshotView component + AlertDetailDialog integration

**Files:**
- Create: `frontend/src/components/SignalSnapshotView.tsx`
- Modify: `frontend/src/components/AlertDetailDialog.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/SignalSnapshotView.tsx
import { BookOpen, ShieldAlert } from "lucide-react";

import type { SignalSnapshot } from "@/api/types";
import { TONE_TEXT, type AlertTone } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* Human labels for the per-detector confidence sub-factors. Unknown keys
 * fall back to the raw name (with underscores spaced) so a new detector's
 * factor still renders legibly before this map is updated. */
const FACTOR_LABELS: Record<string, string> = {
  breakout_strength: "Forza breakout",
  volume_strength: "Forza volume",
  trend_alignment: "Allineamento trend",
  trend_strength: "Forza trend",
  resume: "Ripresa",
  divergence_amplitude: "Ampiezza divergenza",
  extremity: "Estremita RSI",
  trend_context: "Contesto trend",
  tightness: "Compressione",
  expansion_strength: "Forza espansione",
  proximity: "Vicinanza max 52w",
  trend: "Trend",
  momentum: "Momentum",
};

/** Renders a signal-engine alert's snapshot: confidence bar, the dated event
 *  chain as a timeline, the [0,1] factor sub-scores, the invalidation level,
 *  and the cited sources. Reads the loosely-typed snapshot dict defensively
 *  (older/partial payloads must not crash the dialog). */
export function SignalSnapshotView({ snapshot }: { snapshot: Record<string, unknown> }) {
  const s = snapshot as Partial<SignalSnapshot>;
  const tone: AlertTone =
    s.tone === "bull" ? "bullish" : s.tone === "bear" ? "bearish" : "neutral";
  const confidence = typeof s.confidence === "number" ? Math.round(s.confidence) : null;
  const chain = Array.isArray(s.chain) ? s.chain : [];
  const factors =
    s.factors && typeof s.factors === "object" ? (s.factors as Record<string, number>) : {};
  const sources = Array.isArray(s.sources) ? s.sources : [];
  const inv = s.invalidation ?? null;
  const barColor =
    tone === "bullish" ? "bg-emerald-500" : tone === "bearish" ? "bg-rose-500" : "bg-slate-400";

  return (
    <div className="space-y-4">
      {confidence != null && (
        <div className="flex items-center gap-3">
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
            Confidenza
          </span>
          <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
            <div className={cn("h-full rounded-full", barColor)} style={{ width: `${confidence}%` }} />
          </div>
          <span className={cn("text-sm font-bold tabular-nums", TONE_TEXT[tone])}>{confidence}%</span>
        </div>
      )}

      {chain.length > 0 && (
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            Catena di eventi
          </div>
          <ol className="relative border-l border-border/60 ml-2 space-y-3">
            {chain.map((step, i) => (
              <li key={`${step.date}-${i}`} className="ml-4 relative">
                <span className="absolute -left-[1.39rem] mt-1 h-3 w-3 rounded-full bg-primary/70 border-2 border-background" />
                <div className="text-sm font-semibold">{step.label}</div>
                {step.detail && <div className="text-xs text-muted-foreground">{step.detail}</div>}
                <div className="text-[11px] text-muted-foreground/70 tabular-nums">{step.date}</div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {Object.keys(factors).length > 0 && (
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            Fattori di confidenza
          </div>
          <div className="space-y-1.5">
            {Object.entries(factors).map(([k, v]) => {
              const pct = Math.round(Math.max(0, Math.min(1, typeof v === "number" ? v : 0)) * 100);
              return (
                <div key={k} className="flex items-center gap-2">
                  <span className="w-36 text-xs text-foreground/70 shrink-0 truncate" title={FACTOR_LABELS[k] ?? k}>
                    {FACTOR_LABELS[k] ?? k}
                  </span>
                  <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-sky-500/70 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-9 text-right text-[11px] tabular-nums text-muted-foreground">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {inv && (inv.level != null || inv.reason) && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-300/60 bg-amber-50/50 dark:bg-amber-950/20 p-2.5">
          <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-amber-800 dark:text-amber-300">Invalidazione</span>
            {inv.level != null && (
              <span className="tabular-nums">
                {" "}a ${typeof inv.level === "number" ? inv.level.toFixed(2) : String(inv.level)}
              </span>
            )}
            {inv.reason && (
              <div className="text-amber-700/80 dark:text-amber-400/80">{inv.reason}</div>
            )}
          </div>
        </div>
      )}

      {sources.length > 0 && (
        <div className="flex items-start gap-2 text-[11px] text-muted-foreground">
          <BookOpen className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <div>{sources.join(" · ")}</div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Integrate into `AlertDetailDialog.tsx`**

Add the imports near the top:
```tsx
import { SignalSnapshotView } from "@/components/SignalSnapshotView";
import { isSignalKind } from "@/lib/alertMeta";
```
(`isSignalKind` is added to the existing `@/lib/alertMeta` import — merge it into that import statement rather than duplicating.)

In the SNAPSHOT section, branch on signal kind. Replace the snapshot body block (the `{hasResolvedRows ? (...) : hasRawData ? (...) : (...)}` expression) so signals render the rich view:

```tsx
          {isSignalKind(alert.rule_kind) ? (
            <SignalSnapshotView snapshot={alert.snapshot ?? {}} />
          ) : hasResolvedRows ? (
            <div className="rounded-lg border border-border/60 px-3 py-1">
              {resolution.rows.map((r) => (
                <SnapshotRow key={r.label} {...r} />
              ))}
            </div>
          ) : hasRawData ? (
            <pre className="rounded-lg border border-border/60 bg-muted/40 dark:bg-muted/15 p-3 text-xs overflow-auto max-h-48 leading-relaxed">
              {JSON.stringify(alert.snapshot, null, 2)}
            </pre>
          ) : (
            <div className="rounded-lg border border-dashed border-border/60 p-3 text-xs text-muted-foreground italic text-center">
              Nessun dato di snapshot per questo alert.
            </div>
          )}
```

Also gate the "raw JSON" toggle so it still works for signals (a power-user escape hatch). Change the two `{hasResolvedRows && hasRawData && ...}` conditions to `{(hasResolvedRows || isSignalKind(alert.rule_kind)) && hasRawData && ...}` so the toggle shows for signal alerts too. And update the section title to read "Dettaglio segnale" for signals:

```tsx
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            {isSignalKind(alert.rule_kind) ? "Dettaglio segnale" : "Snapshot del trigger"}
          </div>
```

- [ ] **Step 3: Typecheck + build**

Run: `cd frontend && npm run build`
Expected: tsc passes, vite builds. No type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SignalSnapshotView.tsx frontend/src/components/AlertDetailDialog.tsx
git commit -m "feat(signals-ui): rich SignalSnapshotView (chain + confidence + factors + invalidation + sources)"
```

---

### Task 3: Backend consistency — digest labeling + stats include signals

**Files:**
- Modify: `backend/app/services/notifier_service.py`
- Modify: `backend/app/services/stats_service.py`
- Test: `backend/tests/test_signal_surfaces.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_signal_surfaces.py
from datetime import date
import json
from app.models import Alert, Stock
from app.services import stats_service


def _signal_alert(db, ticker="SIGSURF", d=date(2026, 5, 1)):
    s = Stock(ticker=ticker, exchange="NASDAQ", name="Sig Surf", country="US")
    db.add(s); db.flush()
    db.add(Alert(rule_id=None, stock_id=s.id, trigger_price=10.0, signal_date=d,
                 signal_name="volume_breakout",
                 snapshot=json.dumps({"tone": "bull", "confidence": 80, "chain": []})))
    db.commit()
    return s


def test_alerts_by_day_counts_signal_alerts(db):
    s = _signal_alert(db)
    points = stats_service.get_alerts_by_day(db, days=400)
    total = sum(p.count for p in points)
    assert total >= 1
    # the signal kind appears in the by_kind breakdown
    kinds = set()
    for p in points:
        kinds.update(p.by_kind.keys())
    assert any(k.startswith("signal:") for k in kinds)
```

(If `get_alerts_by_day`'s signature differs — e.g. it takes no `days` kwarg — adapt the call to match the real signature; the assertion is what matters: signal alerts are counted and carry a `signal:` kind.)

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_signal_surfaces.py -q`
Expected: FAIL — signal alerts excluded by the inner join (total 0 / no signal kind).

- [ ] **Step 3: Fix `stats_service.py`**

Find every `.join(Rule, ...)` in `get_alerts_by_day` and `get_top_stocks` (around lines 137 and 206). Change each `.join(Rule, Rule.id == Alert.rule_id)` to `.outerjoin(Rule, Rule.id == Alert.rule_id)`. Where the query selects `Rule.kind` and groups/labels by it, coalesce the signal name so signal rows get a `signal:<name>` kind instead of NULL. The cleanest SQL-side approach:

```python
from sqlalchemy import case, func
# kind expression used in SELECT / GROUP BY:
kind_expr = func.coalesce(
    Rule.kind,
    "signal:" + func.coalesce(Alert.signal_name, "unknown"),
).label("rule_kind")
```

Use `kind_expr` wherever the query previously used `Rule.kind` for the by-kind breakdown, and `.outerjoin` so NULL-rule rows survive. (SQLite supports string concatenation via `+` in SQLAlchemy through `concat`/`||`; if `+` raises, use `func.concat` or the Python-side fallback below.)

If the SQL-side coalesce is awkward in this codebase's query shape, an acceptable alternative is to keep the outer join and derive the kind in Python when building each point's `by_kind` dict:

```python
from app.services.alert_service import derive_rule_kind
kind = derive_rule_kind(row.rule_kind, row.signal_name)
```

(ensure the SELECT also pulls `Alert.signal_name`). Pick whichever fits the existing query; the observable contract is: signal alerts are counted and grouped under `signal:<name>`.

- [ ] **Step 4: Fix `notifier_service.py` digest labeling**

In `build_digest_message`, the kind is currently `rules_by_id.get(a.rule_id).kind if ... else "unknown"`. Import and use the shared helper so signal alerts read their `signal:<name>` kind:

```python
from app.services.alert_service import derive_rule_kind
# where the digest formats each alert:
rule = rules_by_id.get(a.rule_id)
kind = derive_rule_kind(rule.kind if rule else None, a.signal_name)
```

Add a small test in the same `test_signal_surfaces.py` asserting the digest text for a signal alert contains `"signal:volume_breakout"` (or the friendly rendering the digest uses) and not `"unknown"`. (Inspect `build_digest_message`'s signature/output to assert correctly.)

- [ ] **Step 5: Run tests + full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_signal_surfaces.py -q` (expect pass).
Then: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q` — full suite green (watch existing stats/notifier tests: rule alerts still join their Rule and their kind is unchanged because outer join returns the same row when a match exists).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/stats_service.py backend/app/services/notifier_service.py backend/tests/test_signal_surfaces.py
git commit -m "feat(signals): count signal alerts in dashboard stats + label them in the digest"
```

---

## Self-review notes
- Spec coverage (design §7 "UI enriched alert"): chain timeline ✓, confidence badge ✓, tone ✓, invalidation ✓, cited sources ✓ (T2); kind label/tone across feed+table+dialog via getAlertMeta ✓ (T1); digest + dashboard consistency ✓ (T3). The signal-kind FILTER in AlertFilters is intentionally deferred (lower value; the feed already shows signals) — noted as a future tweak.
- Type consistency: `SignalKind`, `SignalSnapshot`, `isSignalKind`, `getAlertMeta`, `getSnapshotHeadline`, `SignalSnapshotView`, `derive_rule_kind` used consistently across tasks.
- No placeholders: every step has real code; T3 Step 3 offers an SQL-side and a Python-side approach because the exact `stats_service` query shape must be read at implementation time — both are fully specified.
- Defensive rendering: `SignalSnapshotView` reads the loosely-typed snapshot with guards so partial/legacy payloads can't crash the dialog. ✓
- Post-merge: rebuild `frontend/dist` (FE changed) and tell the user to hard-reload.

## Follow-up (optional, not blocking)
- AlertFilters: add `signal:*` kinds to the rule-kind filter dropdown + `_apply_filters` matching, when the user wants to filter the feed by signal type.
