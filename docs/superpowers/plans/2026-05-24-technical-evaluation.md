# Technical Evaluation implementation plan

> Spec: docs/superpowers/specs/2026-05-24-technical-evaluation-design.md
> Backend: cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q
> Frontend: cd frontend && npm run build

## TA1 - backend core (model + migration + service + scan + tests)
- Create app/models/technical_score.py: TechnicalScore (stock_id unique,
  composite, trend, momentum, structure, volume, rel_strength, signals nullable,
  posture, computed_at, breakdown). Export from app/models/__init__.
- Alembic migration creating technical_scores (down_revision = current head).
- Create app/services/technical_score_service.py:
  - per-stock dimension functions (trend/momentum/structure/volume) from OHLCV
    using app/indicators (ema, rsi, macd, bb, adx, atr), each returning 0-100.
  - compute_partial(ohlcv) -> dict of the 4 price dims + the raw blended return.
  - finalize: given all blended returns, percentile -> rel_strength; composite
    (weighted) + posture; upsert TechnicalScore rows.
- Wire into scan_universe: collect per-stock partials in the loop, then a
  finalize pass computes rel_strength + composite and upserts.
- Tests: dimension monotonicity (uptrend -> high trend; downtrend -> low),
  rel_strength percentile ordering, composite + posture thresholds, upsert.

## TA2 - signals facet + API exposure
- Add a capped signals bonus to the composite from recent Alerts (tone/confidence).
- Extend stock search service + schema with a TechnicalScoreRef (composite +
  dims + posture); add sortable columns + filters (compose like the pillars).
- Extend stock detail response with the technical score.

## TA3 - frontend
- Screener: "Tecnico" column + toggleable sub-dimension columns + sort + filters.
- Stock detail: "Valutazione tecnica" card (dimension bars + posture + signals badge).
- Build + verify + rebuild dist.

## Verification
Full backend suite green after TA1/TA2; frontend build clean after TA3; a scan
smoke test confirms technical_scores rows are populated.
