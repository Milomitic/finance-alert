# Regime conditioning — PRELIMINARY observation (2026-06-09)

**Status: hypothesis-generating only. NOT actioned. Do not weight on this.**

Roadmap #8 asks whether per-detector hit rates should be conditioned on the
market regime (close vs EMA200 at the signal bar). With the signal_outcomes
warehouse now storing `regime_at_signal` next to `abs_hit`, this is a one-query
read — so here's a first look at the **787 currently-matured rows**.

### detector × regime
| detector | regime | hit | n |
|---|---|---|---|
| candle_reversal | bear | 56.0% | 325 |
| candle_reversal | bull | 52.5% | 406 |
| gap_and_go | bear | 41.7% | 24 |
| gap_and_go | bull | 50.0% | 32 |

### tone × regime
| tone | regime | hit | n |
|---|---|---|---|
| bull | bull | **43.4%** | 173 |
| bull | bear | 56.5% | 170 |
| bear | bull | 58.1% | 265 |
| bear | bear | 53.6% | 179 |

### Why this is NOT actionable yet
- **Single-detector skew:** candle_reversal is 731 of 787 rows. The tone×regime
  pattern is essentially one mean-reversion detector, not the engine.
- **Short-horizon only:** only H=5 detectors have matured. The 21/63-day
  detectors (most of the engine) aren't in the warehouse yet.
- **Thin cells, no market-neutral:** ~170/cell, absolute hit (credits beta).
- **Plausible artifact:** a *bull* mean-reversion (oversold bounce) failing in a
  *bull* regime makes mechanical sense — no oversold extreme to revert from. So
  the 43% cell may be a property of mean-reversion, not a general regime law.

### Decision
Record and wait. The proper #8 study is either (a) the warehouse maturing across
all horizons over the coming weeks, or (b) a no-look-ahead **replay** harness
(`regime_conditioned_outcomes`, reusing `signal_outcome_service`'s forward-hit +
EMA200 helpers) for a 10y sample. Only then, and only with a purged
walk-forward gate, would regime-conditioned base rates justify a calibration
change. Consistent with the standing rule: never flip production on thin /
in-sample / single-detector evidence.
