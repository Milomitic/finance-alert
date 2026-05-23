# Trade Playbook implementation plan

> Frontend-only. Spec: docs/superpowers/specs/2026-05-23-trade-playbook-design.md

Goal: a frontend playbook module + a "Piano operativo" popup section.
Architecture: lib/tradePlaybook.ts (pure functions) + PlaybookView.tsx consumed
by AlertDetailDialog. Tech: React/TS; build via cd frontend && npm run build.

## Task T1: tradePlaybook.ts
Create frontend/src/lib/tradePlaybook.ts exporting buildPlaybook(snapshot, entry)
-> Playbook | null. Pure, no React.
- read stop/side/levels/confidence/name from the loosely-typed snapshot.
- return null when entry or the stop level is missing or not finite, or R <= 0.
- compute R, hybrid targets, reward-to-risk, duration (family map),
  risk pct / position pct / leverage (capped).
- export the Playbook type.

## Task T2: PlaybookView.tsx
Create frontend/src/components/PlaybookView.tsx rendering a Playbook: action +
conviction chip, entry/stop/targets grid with reward-to-risk, duration,
risk/leverage line, disclaimer. Tone-colored.

## Task T3: integrate into AlertDetailDialog
Import buildPlaybook + PlaybookView. For signal alerts, build the playbook from
alert.snapshot and alert.trigger_price and render a "Piano operativo" section
under the snapshot; if null, render a short note. Build + verify + rebuild dist.

## Verification
cd frontend && npm run build (tsc clean + dist). Grep new strings in the bundle.
