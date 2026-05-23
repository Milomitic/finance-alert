# Follow-ups (deferred, not yet planned)

Durable backlog of ideas to revisit. Newest on top.

## Decouple stock-info fetch from signal computation
**Date:** 2026-05-23
Today the daily scan couples two things per stock: (a) **fetching/refreshing stock
information** (OHLCV, fundamentals, news, analyst/insider/earnings) and (b) **computing
signals** on that data. The user wants these **separable** so each can be run on its own,
not necessarily in lockstep — e.g. refresh data without re-running the signal engine, or
re-run signals on already-cached data without re-fetching.

Direction (to design later): split the scan into two independently-invocable phases/jobs —
a **data-refresh** pass and a **signal-evaluation** pass — with their own triggers
(scheduler entries + manual buttons) and clear boundaries. The signal engine already reads
OHLCV from `OhlcvDaily` and fundamentals cache-only (`get_fundamentals_cached`), so the
seam mostly exists; this is about making the two phases first-class and independently
runnable.

## Signal annotated chart (SVG in the detail popup)
Design approved + spec written (`docs/superpowers/specs/2026-05-23-signal-annotated-chart-design.md`).
Implementation deferred behind the tables/filters UX batch. Resume with writing-plans (P1 backend annotations).
