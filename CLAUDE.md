# Finance-Alert: Project notes for the agent

Persistent notes accumulated across sessions so we don't waste time
re-discovering recurring problems and patterns. **Read this before doing
anything else in this repo.**

---

## ⚠️ Backend restart: ignore the OLD task's "failed" notification

**The most common time-waster.** Every backend restart produces a misleading
"Background command failed" notification. Internalize once and stop chasing it.

### What happens
1. I `taskkill //PID <old> //F` to kill the previous uvicorn
2. I start a fresh uvicorn with `run_in_background: true` (new task id)
3. ~10–30s later a notification arrives:
   ```
   <task-id>OLD_ID</task-id>
   <status>failed</status>
   <summary>Background command "Restart backend" failed with exit code 1</summary>
   ```

### What it actually means
The notification's `task-id` is the **OLD** task — the one whose process I just
killed. Uvicorn exiting because of `taskkill /F` returns a non-zero exit code,
so the background-task wrapper marks the OLD task "failed". This is the kill
ack, not a problem with the NEW backend.

### What to do
**Ignore the notification.** Verify the new backend is up via:
```bash
until curl -sf http://127.0.0.1:8000/api/health 2>nul | grep -q "ok"; do sleep 1; done
```
If health returns OK, everything is fine. The kill-and-restart sequence is
working as intended.

### What NOT to do
- Don't read the failure output as if it's the new backend's startup error
- Don't try to "fix" it
- Don't restart again on the assumption that the start failed
- Don't apologize to the user about the failure — it's expected

### Canonical restart sequence
```
1. netstat -ano | findstr :8000 | findstr LISTENING   # get PID
2. taskkill //PID <PID> //F                            # ignore old-task fail
3. uvicorn ... (run_in_background: true)               # new task
4. curl /api/health until 200                          # confirm new task up
```

### Watch out: orphaned uvicorn workers (the "fix doesn't work" trap)

`uvicorn --reload` forks two processes: the *reloader* (parent, listed
by `tasklist`) and the *worker* (child, spawned via
`multiprocessing.spawn`). Killing only the reloader's PID leaves the
worker alive on Windows — it keeps the listening socket bound and
serves requests with **stale code**. Symptoms:
- You fix a bug, restart backend, request still returns the pre-fix
  500 / wrong response.
- `netstat -ano | findstr :8000` shows 2-3 LISTENING entries (Windows
  allows multiple binders via `SO_REUSEADDR`).
- `tasklist | findstr <old-pid>` says the PID doesn't exist (it's the
  dead reloader).
- TestClient via Python (in-process) works fine — proves the fixed
  code is correct, but uvicorn isn't running it.

If you suspect this, find orphan workers via:
```bash
wmic process where "Name='python.exe'" get ProcessId,ParentProcessId,CommandLine
```
The orphans look like `python.exe -c "from multiprocessing.spawn import
spawn_main; spawn_main(parent_pid=<dead-reloader-pid>, ...)"`. Kill
each by its `ProcessId` (the worker's, not the parent's).

Then re-verify with `netstat`: a healthy state has exactly ONE LISTENING
entry on 8000.

### `git pull` does NOT trigger `uvicorn --reload` on Windows

`uvicorn --reload` uses `watchfiles` (inotify-equivalent). On Windows
when files are touched by an external process — `git pull`, `git
checkout`, an editor like VSCode swapping the file via temp+rename —
the change events are **frequently missed**. The file mtime updates
on disk but the worker keeps serving the old in-memory bytecode.
Symptom that just bit us: pull lands a fix, browser polls /quote,
flashes the right value once (cached layer), then reverts to the
pre-fix value (worker's stale code).

**Quick check:**
```bash
# File mtime
stat -c '%y' backend/app/services/<file>.py
# Worker creation time
wmic process where "Name='python.exe'" get ProcessId,CreationDate,CommandLine
```
If the worker (the `spawn_main` row) is OLDER than the file, the
auto-reload missed the event. Solution: run the canonical restart
sequence above. Do NOT trust `--reload` after a pull — it's not free
to verify and the failure is silent.

### Agent operating rule: restart backend always, frontend only if stale after F5

**The asymmetry is real.** Both `uvicorn --reload` (watchfiles) and Vite
(chokidar) can drop file-change events on Windows — but the failure
modes are nothing alike:

| | Detection on miss | Recovery |
|---|---|---|
| Vite | User notices stale page | **F5 → fresh bundle from disk, free** |
| uvicorn | API still returns stale data, user thinks "fix didn't work" | None — module bytecode is in worker memory, MUST kill the worker |

So the agent's restart discipline is asymmetric:

1. **Backend Python edit (`backend/app/**`)** — ALWAYS restart uvicorn
   with the canonical kill-tree + spawn sequence above, immediately
   after the edit. There is no F5 for the backend; a missed reload
   means hours of debugging a phantom.

2. **Frontend file edit (`frontend/src/**`, `vite.config.ts`, etc.)** —
   trust Vite HMR by default. If the user reports the change not
   showing AFTER an F5, then restart Vite (port 5173). HMR + F5
   covers ~99% of cases; the explicit restart is the rare fallback.

Backend restart sequence (already documented above; applies verbatim
to in-session Edit tool changes, not just `git pull`).

Frontend restart sequence (only when F5 doesn't cut it):
```bash
netstat -ano | findstr :5173 | findstr LISTENING
taskkill //PID <PID> //T //F
cd frontend && npm run dev   # run_in_background: true
# Vite prints "Local: http://localhost:5173" + binds to ::1 (IPv6)
# Smoke-test via http://localhost:5173/ NOT http://127.0.0.1:5173/
```

Why this rule is conservative on the backend, relaxed on the frontend:
restart cost is the same ~1-3s either way, but the COST OF NOT RESTARTING
is asymmetric — silent stale-code on backend, visible-stale-page on
frontend (user notices instantly, F5s, problem solved).

### ⚠️ FastAPI serves a pre-built frontend bundle on :8000 — rebuild after every FE commit

`backend/app/main.py` mounts `frontend/dist/` and serves it as the SPA shell
when present. So the same app exists at TWO URLs simultaneously:

| URL | Source | Picks up source edits? | When the user reports "non funziona" |
|---|---|---|---|
| http://localhost:**5173**/ | Vite dev server (`npm run dev`) | ✅ via HMR | F5 |
| http://localhost:**8000**/ | FastAPI serving `frontend/dist/` static files | ❌ NEVER — needs `npm run build` | **REBUILD DIST FIRST**, then hard-reload |

**The user defaults to testing on :8000 in this repo.** Two losses on this in
recent sessions (recompute button + scan-toast sub-phases): edits land,
backend reloads, agent says "F5 to see it", user says "still old". Root
cause every time: dist wasn't rebuilt.

#### Post-commit hygiene checklist (run after EVERY commit that touches `frontend/`)

Treat this as a hard pre-condition for telling the user "ready". Skip it →
the user wastes a round-trip telling you the page is still old.

```bash
# 1. Did this commit touch any frontend source?
git diff --name-only HEAD~1 HEAD | grep -qE '^frontend/(src|public|index\.html|vite\.config|package(-lock)?\.json|tsconfig)' && echo "FE touched — must rebuild" || echo "FE untouched — skip rebuild"

# 2. If touched, compare dist freshness vs the most-recently-edited FE source:
stat -c '%y' frontend/dist/index.html
stat -c '%y' $(git diff --name-only HEAD~1 HEAD | grep '^frontend/src/' | head -1)

# 3. Rebuild if dist is older:
cd frontend && npm run build
# Expected: "✓ built in ~1s" + new index.html + new hashed assets.

# 4. Sanity-check that the new strings actually landed in the bundle. Vite
#    minifies, so grep individual string literals (not full sentences):
grep -c "<distinctive-string-from-your-change>" frontend/dist/assets/index-*.js
# Expect 1+ matches. Zero = the change isn't in the bundle and you have a
# stale build.

# 5. Tell the user to hard-refresh (Ctrl+Shift+R / Cmd+Shift+R), NOT plain F5.
#    Browsers cache hashed assets aggressively; soft reload may keep the old
#    bundle. The hash in the filename changes on each build, so a hard
#    reload always pulls the new one.
```

#### Worktree pitfall: `frontend/node_modules/.bin/` may be broken in a worktree

The git worktree's `node_modules` often has the package directories but
missing `.bin/` symlinks (Windows + worktree edge case). Symptom:

```bash
$ npm run build
> tsc -b && vite build
"tsc" non è riconosciuto come comando interno o esterno...

$ ls node_modules/.bin/
ls: cannot access 'node_modules/.bin/': No such file or directory
```

`tsc` lives at `node_modules/typescript/bin/tsc` — the package is there, just
the .bin shim is missing. Fix: `npm install` from the frontend dir. It's
fast (~10s on warm cache) and only needs to run once per worktree session.

```bash
cd frontend && npm install     # restores .bin/ symlinks
cd frontend && npm run build   # now works
```

#### Why "just run `npm run build`" isn't enough — typical agent failure modes

| Agent shortcut | What goes wrong | Fix |
|---|---|---|
| "Source edited, F5 should work" | User is on :8000 → bundle is from last build → no F5 helps | Always rebuild after FE edits |
| `npm run build` in worktree → tsc not found | `.bin/` broken | `npm install` first |
| Build "succeeds" with TS errors | `npm run build` = `tsc -b && vite build`. tsc errors stop the build entirely | Read the tail; if there are TS errors NOT from your change, they're pre-existing — but a build error from YOUR change must be fixed before declaring done |
| User refreshes with F5, still sees old | Browser cached the hashed asset. Each `npm run build` mints a new hash; the index.html points to the new file, but the F5'd page may have already had the old index in memory | Tell the user "hard reload" (Ctrl+Shift+R) not "F5" |

#### TL;DR rule

Anything touching `frontend/` → **commit → rebuild dist → verify strings are in bundle → THEN tell user to hard-reload**.
Anything touching `backend/app/**` → **commit → restart uvicorn → verify /api/health → THEN tell user**.
Both? Do both.

---

## Database migrations (alembic)

- Migration files live in `backend/alembic/versions/`
- Generate with: `./.venv/Scripts/alembic.exe revision -m "<name>"`
  (the file is empty — fill in `upgrade()` and `downgrade()` manually)
- Apply with: `./.venv/Scripts/alembic.exe upgrade head`
- The DB engine is SQLite; use `op.batch_alter_table(...)` for column changes
  (SQLite doesn't support `ALTER COLUMN` natively)

---

## Catalog has duplicate ticker rows

59 tickers (AAPL, AMZN, UCG.MI, etc.) have **two rows** in the `stocks` table
because two ingestion paths inserted the same logical ticker. Code that looks
up a stock by ticker MUST tolerate this:

```python
# WRONG — will raise MultipleResultsFound
stock = db.execute(select(Stock).where(Stock.ticker == ticker)).scalar_one_or_none()

# RIGHT — picks any matching row, all are equivalent for read-only paths
stock = db.execute(
    select(Stock).where(Stock.ticker == ticker).limit(1)
).scalars().first()
```

The dedup of these rows is queued as a separate background task. Until then,
treat duplicates as a fact of life on read paths.

---

## Frontend tone classes (Tailwind purger)

Tone-class maps in `lib/alertMeta.ts` and similar files MUST stay as plain
string-literal `Record<Tone, string>` maps. **Do not refactor to template-
string composition** — Tailwind's build-time class purger only sees literals,
and a refactor will silently strip all the tone classes from the prod build.
The bug is invisible in dev.

---

## Test commands

- **Backend**: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q`
  (281+ tests, runs in ~5s)
- **Frontend build/typecheck**: `cd frontend && npm run build`
  (also: `npx tsc -b` for type-only check)
- **Single test file**: append the file path to the pytest command

---

## Stock detail card layout (the one that always tries to break)

The 3-card row (Fundamentals · Valuation · News) uses:
- Grid: `lg:grid-cols-3 gap-3` (default `items-stretch`, NOT `items-start`)
- Each card: `h-full overflow-hidden flex flex-col`
- FundamentalsCard sets the row's natural height (no internal scroll on its
  tables — per user constraint)
- MicroDataCard + NewsCard scroll internally via `flex-1 min-h-0 overflow-y-auto`
- **NewsCard is wrapped in `<div className="relative h-full">` with the Card
  positioned `absolute inset-0`** — so its 25-item content doesn't inflate
  the row. Don't undo this.

---

## Indicator periods adapt to range

The bundle keys in the API response (`sma20`/`sma50`/`sma200`, `rsi14`) are
**slot names**, not literal periods. The actual periods are in
`indicators.periods` (`sma_fast`, `sma_mid`, `sma_slow`, `rsi`, etc.) and
adapt to the range_key:

| Range | sma_fast/mid/slow | rsi | bb |
|-------|-------------------|-----|-----|
| 1m    | 5/10/20           | 7   | 10  |
| 3m    | 10/20/50          | 14  | 20  |
| 6m    | 20/50/100         | 14  | 20  |
| 1y    | 20/50/200         | 14  | 20  |
| all   | 50/100/200        | 21  | 50  |

UI labels (IndicatorToggles, ResizableSection labels) read the live periods,
not the static defaults. Don't hard-code "SMA 200" / "RSI(14)" in new code —
read from `indicators.periods`.

---

## Alert dual-timestamp model

Every alert has two dates (since commit `e22bec5`):
- `signal_date` (Date): bar where the rule's condition matched
- `triggered_at` (DateTime): wall-clock when the row was created

The two diverge meaningfully on backfill / weekend / skipped scans. UI
distinguishes them via `lib/alertDates.ts:isDelayedDetection` (≥ 1 calendar
day delta → orange clock chip + "in ritardo" label).

Legacy alerts predate the column → `signal_date = null`. UI falls back to
`triggered_at` and shows "—" or "n/d · legacy" for the signal slot.

---

## Read/unread alert system was removed

`Alert.read_at` still exists in the DB and API for back-compat, but the UI
doesn't surface it anymore (no badges, no filters, no bulk actions). Don't
re-add it without the user explicitly asking. The `archived_at` axis is
still active.

---

## Typed upstream error hierarchy (`app/core/errors.py`)

Upstream-fetch failures are tagged with one of three subclasses of
`UpstreamError(message, *, source, op)`:

- `UpstreamTimeout` — network timeout (retryable)
- `RateLimitError` — 429 / "too many requests" (retryable with backoff)
- `UpstreamUnavailable` — 5xx / malformed body (NOT retryable — re-fetch would
  just hit the same problem)

Routers catch the base `UpstreamError` for warning-level structured logging
(`logger.warning(f"upstream {e.source}.{e.op} failed: {e}")`), then fall back to
`except Exception` only as a defensive last-resort.

When adding a new external fetch:
1. Wrap raw network calls so they raise the appropriate typed exception (see
   `_normalize_yf_error` in `stock_fundamentals_service.py` for the pattern).
2. Apply `@with_backoff(retries=N, base_delay=..., max_delay=..., on=(UpstreamTimeout, RateLimitError))`
   from `app/services/_retry.py` to get exponential backoff with jitter.
3. Catch `UpstreamError` in any consumer router and either return a graceful
   fallback (e.g. cached EOD, secondary provider) or surface a 503 — never let
   it 500.

The retry decorator only retries the typed errors listed in `on=`. Passing
`UpstreamUnavailable` there would waste cycles on non-recoverable failures.

---

## Two-tier cache: in-memory L1 + persistent L2 (`fetch_cache` table)

`stock_fundamentals_service` and `stock_news_service` use a two-layer cache:

- **L1**: in-process dict (`_CACHE`) — microsecond hits.
- **L2**: `fetch_cache` table (one row per `(ticker, kind)`, JSON payload) —
  survives backend restarts. Read by service on L1 miss; written on every
  successful upstream fetch. Hydrated into L1 at app startup (`lifespan`).

The flow on every `get_fundamentals(ticker)` / `get_news(ticker)`:
```
L1 hit + fresh        → return immediately (microseconds)
L1 miss / stale → L2 hit + fresh → hydrate L1 + return (single DB query)
both miss / stale     → upstream fetch → UPSERT L2 + L1 → return
```

**Don't bypass L2.** If you write a new service that reads `_CACHE` directly
(e.g. the calendar aggregator does this — see
`backend/app/services/calendar_service.py`), document it explicitly and be
aware that on a fresh process boot before any consumer has triggered
hydration, `_CACHE` may still be empty for a few seconds — call
`hydrate_l1_from_db()` if you need an immediate-read guarantee.

**`clear_cache()` clears BOTH layers** (it used to clear only L1; that was
test-isolation hostile). Calling it from production code wipes the persisted
rows too. If you really want to discard only the in-memory cache (e.g. to
simulate a process restart in a test), poke `_CACHE.clear()` directly.

**Don't persist error rows.** Both services intentionally skip the L2 write
when the upstream fetch returned an error — a transient yfinance failure
shouldn't poison the cache for 24h across restarts.

The third in-memory cache (`live_quote_service`) is **NOT** backed by L2
because its TTL is 10 seconds — a 30s-old quote is worse than re-fetching,
and the persistence overhead would dominate.
