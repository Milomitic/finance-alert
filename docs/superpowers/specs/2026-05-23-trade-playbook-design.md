# Trade Playbook (signal action plan) - design

Date: 2026-05-23
Status: approved (brainstorm)

## Goal
Turn each detected signal into a plain, rule-based action plan shown in the
alert detail popup: action, entry, stop, targets, reward-to-risk, expected
duration, and a risk-based position size + leverage. Educational, not advice.

## Approach: rules + structure, frontend-derived
Everything needed already lives in the alert (snapshot + trigger_price), so the
playbook is computed on the client (a lib module) with no backend change, no
migration and no re-scan. It works on existing alerts immediately. ATR is not
needed because targets use R-multiples (R = entry-to-stop distance).

Inputs:
- entry  = alert.trigger_price
- stop   = snapshot.invalidation.level (required; without it no full plan)
- side   = snapshot.tone (bull -> long, bear -> short)
- levels = snapshot.annotations.levels (resistance/support/neckline/breakout)
- family = snapshot via the alert signal_name
- confidence (0-100)

## Outputs
- Action: Long / Short; conviction label from confidence (>=75 entry, 60-74 cautious, else watch).
- Entry: around trigger_price.
- Stop: invalidation.level. R = abs(entry - stop).
- Targets (hybrid R + structure): TP1 = nearest favorable structural level
  beyond about 1R if present, else entry + 2R; TP2 = entry + 3R.
- Reward-to-risk: abs(target - entry) / R for each target.
- Expected duration: rule map by family
  - momentum/breakout: a few days to 2-3 weeks
  - reversal: swing, 1-3 weeks
  - chart pattern: weeks (scales with the figure)
  - fundamental (pead/analyst/insider): weeks to months
- Position size + leverage (risk-based):
  - risk_budget pct scales with confidence: 0.5 pct at 60 -> 1.5 pct at 100 (clamped).
  - stop_distance pct = R / entry * 100.
  - position fraction = risk_budget / stop_distance; leverage = same value capped at 3x.
  - below 1x -> note "no leverage needed, use N pct of capital".
- Disclaimer: educational technical estimate, not financial advice.

## Edge cases
- No invalidation level -> show a short note instead of the plan.
- Short framing mirrors long (stop above, targets below).
- Structural target filtered by side (resistance above for long, support below for short).

## Tunable constants (frontend)
RISK_FLOOR=0.5, RISK_CEIL=1.5, MAX_LEVERAGE=3, TP1_R=2, TP2_R=3.

## UI
New "Piano operativo" section in AlertDetailDialog for signal alerts that have a
stop; a short note otherwise. Compact grid + disclaimer, tone-colored.

## Out of scope (later)
Outcome calibration (turning confidence into a backtested probability) and any
account/portfolio personalization.
