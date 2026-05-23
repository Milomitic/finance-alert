# Technical Evaluation (continuous per-stock technical score) - design

Date: 2026-05-24
Status: approved (brainstorm)

## Goal
Give every stock a standing, in-depth technical evaluation (a 0-100 technical
score with sub-dimensions), computed every scan, persisted like the fundamental
StockScore, and surfaced in the screener and on the stock detail page. It is a
COMPLEMENT to the event-based signal engine: the score is the continuous STATE
("how does this stock look technically today"), signals are the EVENT/timing
layer on top. The two scores stay separate (no merge into one composite).

## Dimensions (each normalized 0-100)
- Trend: EMA alignment (price vs EMA50/EMA200), EMA200 slope, ADX strength.
- Momentum: RSI level, MACD histogram sign/slope, rate-of-change.
- Structure: position within the 52w range, distance from highs/lows,
  Bollinger/ATR volatility regime (squeeze vs expansion).
- Volume: short vs long average volume trend, OBV slope (accumulation).
- Relative strength: cross-sectional percentile of a blended 3/6/12 month
  return across the visible universe (IBD-style RS). Needs a second pass.
- Signals facet (TA2): recent signal activity (presence/tone/confidence from
  Alerts) as a small capped bonus + a badge, NOT a heavy weighted pillar.

## Composite + posture
composite = weighted mean of the 5 price dimensions
  Trend 0.28, Momentum 0.24, RelStrength 0.20, Structure 0.16, Volume 0.12
plus a capped signals bonus (TA2, about +/-5).
posture label from composite: >=66 Forte, 40-65 Neutro, <40 Debole.

## Storage
New table technical_scores (mirror of stock_scores), one row per stock:
stock_id (unique), composite, trend, momentum, structure, volume, rel_strength,
signals (nullable), posture, computed_at, breakdown (JSON text). Alembic migration.

## Computation
Inside scan_universe (it already loads OHLCV per stock). Per-stock dimensions
are computed in the main loop; relative strength is cross-sectional, so it is
assigned in a finalize pass (collect each stock blended return, then percentile).

## API + UI
- Extend the screener search response and the stock detail with the technical
  score (like StockScoreRef). New sortable columns + filters.
- Screener: a "Tecnico" composite column + optional toggleable sub-dimension
  columns, sortable and filterable like the 6 fundamental pillars.
- Stock detail: a "Valutazione tecnica" card (dimension bars) alongside the
  fundamental score card.

## Phases
- TA1 (backend core): model + migration + technical_score_service (5 price
  dimensions + relative strength) + wire into scan + tests.
- TA2 (signals facet + API): signals bonus/badge + expose in search + detail.
- TA3 (frontend): screener columns/filters + detail card.

## Out of scope
Outcome calibration; folding the technical score into the fundamental composite;
removing the fundamental momentum pillar (decided: keep it, different horizon).
