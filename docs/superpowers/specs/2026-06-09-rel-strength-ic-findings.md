# Rel-strength IC study — findings (2026-06-09)

**Question (gates roadmap #4):** the Tecnico lens ranks trailing return into a
single UNIVERSE-wide percentile (`rel_strength`). #4 proposed adding a
SECTOR-relative percentile, on the hypothesis that sector beta contaminates the
universe rank. Does sector-relative ranking carry *incremental* edge?

**Method:** `app.scripts.rel_strength_ic` — no-look-ahead, from stored
ohlcv_daily. Per obs date, rank trailing return into universe + within-sector
percentiles; measure cross-sectional rank-IC of each vs forward return, plus the
PARTIAL IC of the sector rank after regressing out the universe rank (the
incremental edge). 700-stock sample.

| config | IC universe | IC sector | **IC sector PARTIAL** | decile spread uni |
|---|---|---|---|---|
| 63d → 21d | −0.003 (t −0.2) | −0.006 (t −0.6) | **+0.004 (t +0.76)** | +0.002 (t +0.5) |
| 126d → 63d | +0.019 (t +1.1) | +0.009 (t +0.6) | **−0.009 (t −1.4)** | +0.021 (t +2.1) |

## Verdict — #4 REJECTED (and it would have hurt)

- At the short horizon everything is ~flat (consistent with the session's
  coin-flip reality for short-term technicals).
- At the classic momentum horizon (126d→63d) **universe** rel-strength DOES have
  a modest real edge — the top-minus-bottom decile spread is +2.1%/63d (t 2.1).
  This is the genuine cross-sectional momentum the Tecnico lens already captures.
- **The sector PARTIAL IC is NEGATIVE (−0.009, t −1.4):** sector-relativizing
  *subtracts* from the universe rank. The momentum edge here is CROSS-SECTOR, so
  neutralizing to the sector removes part of it. Sector-relative ranking is not
  just unhelpful — it's mildly counterproductive.

**Decision: do NOT implement #4.** Keep the universe-wide `rel_strength`; it's
the correct design and the data validates it. The gate prevented a value-
destroying change — the intended outcome of validate-before-ship.

**Bonus (no action, just noted):** universe momentum (126d→63d) carries a real,
backtest-significant decile spread. The Tecnico lens already exposes it via
`rel_strength` (weight 0.20). No change warranted; flagged for future
conviction work if ever revisited (would need the purged walk-forward gate).

## Reproduce
```
cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.rel_strength_ic --sample 700 --step 42 --lookback 126 --horizon 63
```
