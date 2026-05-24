# Confluence Score — Design

**Goal:** Surface multi-signal agreement ("confluence") on a ticker as a single
read-only lens, without altering the individual signal alerts.

**Status:** Implemented 2026-05-24.

## Problem
Each detector emits its own `Alert`. A ticker that is, say, broadly bearish
shows up as N separate same-direction rows (e.g. LI: structure_break +
trend_pullback + volume_breakout, all bear). That is redundant in the feed and
hides the most useful fact: *how many independent detectors agree, and how
strongly*.

## Decision: aggregate at read-time, keep the atoms
The individual detector alerts remain the atomic, calibratable units (each has
its own invalidation + playbook + per-type calibration). Confluence is a pure
presentation layer computed on demand over existing `Alert` rows — no new
model, no migration, fully tunable/removable.

Rejected: literally merging the chains of multiple detectors into one. Different
detectors have different invalidations, horizons and evidence; a merged "chain"
loses that and the chart markers stop making sense. Confluence is expressed by
*counting + weighting* agreeing signals, not by destroying them.

## Algorithm (agreed parameters)
- **Window:** active alerts — not archived, `signal_date` within
  `settings.signal_max_age_days` (default 7).
- **Grouping:** by ticker, then split by direction (bull/bear from snapshot tone).
- **Strength per direction:** `min(100, max(confidence) + BONUS*(n-1))`,
  `BONUS = 8`. Rewards confluence without a weak signal diluting a strong one.
  (Note: saturates at 100 for strong multi-signal clusters; ranking breaks ties
  by `n_signals`.)
- **Prevailing direction:** the stronger side.
- **Contested:** both sides present AND `|bull_strength - bear_strength| < 25`.
- A cluster needs **>= 2** agreeing signals (a lone signal is not a confluence).

## Backend
- `app/services/confluence_service.py` — `compute_confluence(db, days)` →
  `list[ConfluenceCluster]` (dataclasses: cluster + components), sorted by
  `(strength, n_signals)` desc.
- `app/schemas/confluence.py` — `ConfluenceOut` / `ConfluenceComponentOut`.
- `GET /api/alerts/confluence?days=7` (clamped 1-30) in `app/api/alerts.py`.
- Tests: `tests/test_confluence_service.py` (grouping, scoring, contested,
  cap-at-100, >=2 gate, stale-window exclusion).

## Frontend
- `api/alerts.ts` — `confluence(days)` + `Confluence` / `ConfluenceComponent`.
- `hooks/useAlerts.ts` — `useConfluence(days, enabled)`.
- `components/ConfluenceView.tsx` — expandable cluster rows (identity,
  direction chip, strength bar, signal count, "Conteso" badge); expanding lists
  component signals as tone-colored chips linking to the stock page.
- `pages/AlertsPage.tsx` — "Lista ↔ Confluenza" toggle; default Lista.
- `components/dashboard/ConfluenceCard.tsx` — "Top confluenze" mini-panel on the
  home dashboard.

## Unchanged
Individual signals, their chains/charts/playbooks/invalidations, per-type
calibration, and dedup. Confluence is strictly additive.
