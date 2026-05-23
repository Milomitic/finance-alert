# Annotated Chart — Phase P2: OHLCV endpoint + SignalChartSvg + popup integration

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Render the static annotated SVG chart in the signal detail popup, using the P1 `annotations`. Spec: `docs/superpowers/specs/2026-05-23-signal-annotated-chart-design.md`.

**Architecture:** A lightweight `GET /api/stocks/{ticker}/ohlcv` endpoint serves the recent daily bars; `useSignalOhlcv` fetches lazily when the popup opens; `SignalChartSvg` draws the close line + level lines + shape polyline + numbered chain markers; `AlertDetailDialog` renders it for signal alerts.

**Tech Stack:** FastAPI/SQLAlchemy + pytest; React/Vite/TS (hand-drawn SVG, like the existing `MiniSpark`).

**Conventions:** backend tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; frontend `cd frontend && npm run build` (rebuilds dist).

---

### Task P2-T1: lightweight OHLCV endpoint

**Files:**
- Modify: `backend/app/api/stocks.py` (new route)
- Test: `backend/tests/test_api_ohlcv.py`

- [ ] **Step 1: Write the failing test** — seed a stock + N daily bars; `GET /api/stocks/{ticker}/ohlcv?bars=5` returns the last 5 bars ascending with date/open/high/low/close.
```python
# backend/tests/test_api_ohlcv.py  (use the project's existing TestClient + auth fixtures pattern)
from datetime import date
from app.models import Stock, OhlcvDaily


def test_ohlcv_window(client, db, auth_headers):  # adapt fixture names to the repo
    s = Stock(ticker="OHL", exchange="NASDAQ", name="Ohl", country="US")
    db.add(s); db.flush()
    for i in range(1, 9):
        db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 4, i),
                          open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1000))
    db.commit()
    r = client.get("/api/stocks/OHL/ohlcv?bars=5", headers=auth_headers)
    assert r.status_code == 200
    bars = r.json()
    assert len(bars) == 5
    assert bars[0]["date"] < bars[-1]["date"]  # ascending
    assert {"date", "open", "high", "low", "close"} <= bars[0].keys()
```
(Read an existing `tests/test_api_*` to copy the exact TestClient/auth fixture usage.)

- [ ] **Step 2: Run, verify fail** — 404 (route absent).

- [ ] **Step 3: Implement** — add to `app/api/stocks.py` (reuse the existing `OhlcvBarOut` schema):
```python
@router.get("/{ticker}/ohlcv", response_model=list[OhlcvBarOut])
def get_ohlcv_window(
    ticker: str,
    bars: int = 120,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[OhlcvBarOut]:
    """Recent daily OHLCV window for the annotated signal chart. Tolerates the
    catalog's duplicate-ticker rows (picks any matching stock)."""
    bars = max(10, min(bars, 400))
    stock = db.execute(
        select(Stock).where(Stock.ticker == ticker).limit(1)
    ).scalars().first()
    if stock is None:
        return []
    rows = db.execute(
        select(OhlcvDaily).where(OhlcvDaily.stock_id == stock.id)
        .order_by(OhlcvDaily.date.desc()).limit(bars)
    ).scalars().all()
    rows = list(reversed(rows))  # ascending for the chart
    return [OhlcvBarOut(date=str(b.date), open=float(b.open), high=float(b.high),
                        low=float(b.low), close=float(b.close)) for b in rows]
```
(Confirm `OhlcvBarOut`'s exact fields by reading its schema — match them; it's used by `/detail`. If it requires `volume`, include it.)

- [ ] **Step 4: Run + commit** — targeted + full suite green; `import app.main` clean.
```bash
git add backend/app/api/stocks.py backend/tests/test_api_ohlcv.py
git commit -m "feat(api): GET /stocks/{ticker}/ohlcv window for the signal chart"
```

---

### Task P2-T2: useSignalOhlcv hook + api client

**Files:**
- Modify: `frontend/src/api/stocks.ts` (add `ohlcv(ticker, bars)`)
- Create: `frontend/src/hooks/useSignalOhlcv.ts`
- Test: `cd frontend && npm run build`

- [ ] **Step 1: api client** — in `api/stocks.ts`, add to the `stocks` object:
```ts
ohlcv: (ticker: string, bars = 120) =>
  api<OhlcvBar[]>(`/api/stocks/${encodeURIComponent(ticker)}/ohlcv?bars=${bars}`),
```
(`OhlcvBar` type exists in `api/types.ts` — confirm its shape `{date,open,high,low,close,...}`; import/reuse it.)

- [ ] **Step 2: hook**
```ts
// frontend/src/hooks/useSignalOhlcv.ts
import { useQuery } from "@tanstack/react-query";
import { stocks } from "@/api/stocks";

/** Lazy daily-OHLCV window for the annotated signal chart. `enabled` gates
 *  the fetch so it only fires when a signal popup is open. */
export function useSignalOhlcv(ticker: string | null | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["signal-ohlcv", ticker],
    queryFn: () => stocks.ohlcv(ticker as string, 120),
    enabled: enabled && !!ticker,
    staleTime: 5 * 60_000,
  });
}
```

- [ ] **Step 3: Build + commit**
```bash
git add frontend/src/api/stocks.ts frontend/src/hooks/useSignalOhlcv.ts
git commit -m "feat(signals-ui): useSignalOhlcv hook + ohlcv api client"
```

---

### Task P2-T3: SignalChartSvg + AlertDetailDialog integration

**Files:**
- Create: `frontend/src/components/SignalChartSvg.tsx`
- Modify: `frontend/src/components/AlertDetailDialog.tsx`
- Test: `cd frontend && npm run build`

- [ ] **Step 1: Create `SignalChartSvg.tsx`** (hand-drawn SVG; close line + level lines + shape polyline + numbered chain markers):
```tsx
import type { SignalChainStep, SignalSnapshot } from "@/api/types";

interface Bar { date: string; close: number; }
interface Props {
  bars: Bar[];
  annotations: SignalSnapshot["annotations"];
  chain: SignalChainStep[];
  tone: "bull" | "bear" | "neutral";
}

const W = 640, H = 220, PAD_X = 8, PAD_T = 10, PAD_B = 18;

const LEVEL_STYLE: Record<string, { stroke: string; dash?: string }> = {
  neckline:   { stroke: "#6366f1" },
  breakout:   { stroke: "#0ea5e9" },
  support:    { stroke: "#16a34a" },
  resistance: { stroke: "#dc2626" },
  stop:       { stroke: "#d97706", dash: "4 3" },
};

export function SignalChartSvg({ bars, annotations, chain, tone }: Props) {
  if (!bars || bars.length < 2) {
    return (
      <div className="rounded-lg border border-dashed border-border/60 p-4 text-xs text-muted-foreground italic text-center">
        Grafico non disponibile per questo titolo.
      </div>
    );
  }
  const levels = annotations?.levels ?? [];
  const points = annotations?.points ?? [];
  const closes = bars.map((b) => b.close);
  const lvlPrices = levels.map((l) => l.price).filter((p) => Number.isFinite(p));
  const ptPrices = points.map((p) => p.price).filter((p) => Number.isFinite(p));
  const lo = Math.min(...closes, ...lvlPrices, ...ptPrices);
  const hi = Math.max(...closes, ...lvlPrices, ...ptPrices);
  const range = hi - lo || 1;
  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_T - PAD_B;
  const x = (i: number) => PAD_X + (i / (bars.length - 1)) * innerW;
  const y = (price: number) => PAD_T + (1 - (price - lo) / range) * innerH;

  // date -> bar index (nearest; clamp out-of-window to the edges).
  const idxByDate = new Map<string, number>();
  bars.forEach((b, i) => idxByDate.set(b.date.slice(0, 10), i));
  const firstDate = bars[0].date.slice(0, 10);
  const xForDate = (d: string): number => {
    const k = d.slice(0, 10);
    if (idxByDate.has(k)) return x(idxByDate.get(k)!);
    return k < firstDate ? x(0) : x(bars.length - 1); // clamp older→left, newer→right
  };
  const closeAtDate = (d: string): number | null => {
    const k = d.slice(0, 10);
    return idxByDate.has(k) ? bars[idxByDate.get(k)!].close : null;
  };

  const lineColor = tone === "bull" ? "#16a34a" : tone === "bear" ? "#dc2626" : "#64748b";
  const priceLine = closes.map((c, i) => `${x(i).toFixed(1)},${y(c).toFixed(1)}`).join(" ");
  const shape = points
    .map((p) => `${xForDate(p.date).toFixed(1)},${y(p.price).toFixed(1)}`)
    .join(" ");

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="overflow-visible" role="img"
         aria-label="Grafico annotato del segnale">
      {/* level lines */}
      {levels.map((l, i) => {
        const st = LEVEL_STYLE[l.kind] ?? { stroke: "#94a3b8" };
        const yy = y(l.price);
        return (
          <g key={`lvl-${i}`}>
            <line x1={PAD_X} y1={yy} x2={W - PAD_X} y2={yy} stroke={st.stroke}
                  strokeWidth={1} strokeDasharray={st.dash} opacity={0.8} />
            <text x={W - PAD_X} y={yy - 2} textAnchor="end" fontSize={9}
                  fill={st.stroke}>{l.label}</text>
          </g>
        );
      })}
      {/* pattern shape */}
      {points.length >= 2 && (
        <polyline points={shape} fill="none" stroke="#a855f7" strokeWidth={1.4}
                  strokeDasharray="3 2" opacity={0.9} />
      )}
      {/* price close line */}
      <polyline points={priceLine} fill="none" stroke={lineColor} strokeWidth={1.5}
                strokeLinejoin="round" />
      {/* numbered chain markers */}
      {chain.map((step, i) => {
        const c = closeAtDate(step.date);
        if (c == null) return null;
        const cx = xForDate(step.date), cy = y(c);
        return (
          <g key={`mk-${i}`}>
            <circle cx={cx} cy={cy} r={7} fill="#0f172a" opacity={0.85} />
            <text x={cx} y={cy + 3} textAnchor="middle" fontSize={9} fill="#fff"
                  fontWeight="bold">{i + 1}</text>
          </g>
        );
      })}
    </svg>
  );
}
```

- [ ] **Step 2: Integrate into `AlertDetailDialog.tsx`** — for signal alerts only, render the chart between the hero strip and the snapshot section. Use `isSignalKind(alert.rule_kind)` (already imported). Fetch lazily:
```tsx
import { SignalChartSvg } from "@/components/SignalChartSvg";
import { useSignalOhlcv } from "@/hooks/useSignalOhlcv";
// inside the component (BEFORE the early-return guard, hooks run unconditionally):
const isSig = !!alert && isSignalKind(alert.rule_kind);
const ohlcvQ = useSignalOhlcv(alert?.ticker, isSig);
// in the JSX, for signal alerts, a section before the snapshot block:
{isSignalKind(alert.rule_kind) && (
  <div className="px-5 pt-4">
    <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
      Grafico del segnale
    </div>
    <SignalChartSvg
      bars={(ohlcvQ.data ?? []).map((b) => ({ date: b.date, close: b.close }))}
      annotations={(alert.snapshot as { annotations?: SignalSnapshot["annotations"] }).annotations}
      chain={((alert.snapshot as { chain?: SignalChainStep[] }).chain) ?? []}
      tone={((alert.snapshot as { tone?: string }).tone === "bull" ? "bull"
            : (alert.snapshot as { tone?: string }).tone === "bear" ? "bear" : "neutral")}
    />
  </div>
)}
```
(Place the hook with the other hooks at the top — `useState(showRaw)` is already there; React requires hooks before the `if (!alert) return`. Pass `alert?.ticker` + `enabled=isSig`.)

- [ ] **Step 3: Build + commit + rebuild dist**
`cd frontend && npm run build` → tsc clean + vite build OK (rebuilds dist).
```bash
git add frontend/src/components/SignalChartSvg.tsx frontend/src/components/AlertDetailDialog.tsx
git commit -m "feat(signals-ui): annotated SignalChartSvg in the detail popup"
```

---

## Self-review notes
- Endpoint is light (date+OHLC only), authed like the others, tolerant of duplicate tickers + missing data (empty list). ✓
- Hook fetches lazily (`enabled` = signal popup open). ✓
- SVG: y-scale includes levels+points so nothing clips; date→x maps to bars with edge-clamp for out-of-window dates; markers numbered to match the chain timeline; levels colored by kind, stop dashed; shape polyline from points. Degrades to a placeholder on empty bars. ✓
- Hooks run before the dialog's early-return (React rules). ✓
- After P2: rebuild dist + hard-reload → open a signal alert to see the annotated chart.
