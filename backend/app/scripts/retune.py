"""Score-retune ORCHESTRATOR — read-only proposal-diff reporter (human-in-the-loop).

WHAT THIS IS
════════════
The periodic, validated, human-in-the-loop score-retuning loop has ONE
deliverable: a PROPOSAL a human reviews before committing. This script is the
thin orchestration + formatting layer for that loop. For each tunable family it
prints, side by side:

    current params   →   candidate params   +   the OUT-OF-SAMPLE gate verdict

…and then STOPS. It is the read-only "should we even consider this change?"
instrument — NOT an auto-tuner. See docs/runbooks/score-retune-loop.md for the
full procedure, the anti-overfit guardrails, and how to apply an ACCEPTED
proposal by hand.

WHAT THIS IS *NOT*
══════════════════
  • It does NOT write any production param (PILLAR_WEIGHTS, ramp/curve anchors,
    score_v2 delta) — those live in source the human edits deliberately.
  • It does NOT regenerate or overwrite app/data/signal_calibration.json — that
    is the existing harness's job (`signal_detector_outcomes --emit-map`), run
    by the human once a proposal passes review.
  • It does NOT git add / commit / push. Ever.
  • It does NOT recompute stock_scores or fire signals.
  • It reuses the existing measurement harnesses (entry_ic_report,
    signal_factor_outcomes, signal_detector_outcomes) — it never re-implements
    their IC / outcome math.

THE THREE TUNABLE FAMILIES (mirrors the runbook)
════════════════════════════════════════════════
  A. Fundamental pillar weights + per-component ramp anchors
        validated by  → entry_ic_report rank-IC (--validate-prof-retune etc.)
        gate metric    → composite rank-IC, OOS (disjoint train/test stocks)
  B. Signal per-factor curve anchors + score_v2 delta
        validated by  → signal_factor_outcomes (per-factor hit-rate distribution)
                          + signal_detector_outcomes (detector conjunction)
        gate metric    → detector base-rate spread / per-factor monotonic edge
  C. Probabilità base rates / calibration model
        validated by  → OOS Brier score of the calibration map vs realised hits
        gate metric    → Brier (LOWER is better), candidate vs baseline, OOS

THE GATE (the iron rule, in code)
═════════════════════════════════
`passes_oos_gate(baseline, candidate, *, min_rel_improvement)` encodes the
project's standing discipline: REJECT the change unless it is CLEARLY better
OUT-OF-SAMPLE. "Clearly" = a candidate must beat the baseline by at least
`min_rel_improvement` in RELATIVE terms on the held-out (test) stocks — a flat
or worse OOS result is rejected, NaN is rejected. Precedents this rule encodes
(all from the 3-lens cleanup): the momentum pillar was REMOVED (counter-
predictive OOS), the trade-playbook tbs% base rate was DATA-REJECTED (narrower
spread + undefined for 6/14 detectors), and the old single `confidence` was
shown ~flat vs realised outcome.

USAGE
═════
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.retune
      --family {pillars,signals,probability,all}   (default: all)
      --run                 re-run the underlying harness live (slow; reads DB).
                            Omit to read the latest cached artifact / committed
                            params only (fast, fully offline-safe).
      --min-rel-improvement F   relative OOS improvement required to PASS
                                (default 0.05 = "5% better OOS").
      --json                emit the proposal as JSON instead of the table.

Read-only. Touches no production tables for writes; opens a read DB session
only when `--run` is passed (to invoke a harness). Exit code is always 0 — a
FAILED gate is a finding to report to the human, not a process error.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# The gate — the one piece of real logic in this script, unit-tested in
# tests/test_retune_gate.py. Everything else is orchestration + formatting.
# ─────────────────────────────────────────────────────────────────────────────


def passes_oos_gate(
    baseline_metric: float,
    candidate_metric: float,
    *,
    min_rel_improvement: float,
    lower_is_better: bool = False,
) -> bool:
    """Return True iff the candidate is CLEARLY better than the baseline
    OUT-OF-SAMPLE, by at least `min_rel_improvement` in relative terms.

    This is the iron rule of the retune loop made executable: a change is
    REJECTED unless it clears the bar on held-out (test) stocks. The default
    orientation is higher-is-better (e.g. rank-IC); pass `lower_is_better=True`
    for metrics where smaller wins (e.g. Brier score).

    Semantics (higher-is-better):
        required = baseline * (1 + min_rel_improvement)
        pass     = candidate >= required

    NaN-safety (the whole point of gating on measured OOS numbers): if EITHER
    metric is NaN/inf, the gate FAILS — an unmeasurable result can never be
    "clearly better". `min_rel_improvement` is taken as |value| (a negative bar
    would invert the rule into "accept anything", which is exactly the mistake
    this gate exists to prevent).

    Zero / sign-change handling: relative improvement is undefined when the
    baseline is ~0, and meaningless when the metrics straddle 0 (e.g. a baseline
    IC of -0.01 vs a candidate +0.01 is a 200% "improvement" by naive ratio but
    we should judge it on the absolute crossing). So when |baseline| is below a
    tiny epsilon, OR the two metrics have opposite signs, we require the
    candidate to beat the baseline by an ABSOLUTE margin of `min_rel_improvement`
    (treated as an absolute-points bar in that degenerate regime) AND be on the
    correct side of zero. This keeps the rule conservative exactly where ratios
    lie.
    """
    rel = abs(min_rel_improvement)

    # Any non-finite metric → cannot be "clearly better" → reject.
    if not (math.isfinite(baseline_metric) and math.isfinite(candidate_metric)):
        return False

    # Normalise to a higher-is-better comparison so we write the rule once.
    base = -baseline_metric if lower_is_better else baseline_metric
    cand = -candidate_metric if lower_is_better else candidate_metric

    def _gte(x: float, threshold: float) -> bool:
        """`x >= threshold`, robust to float round-off at the inclusive
        boundary (`required` is a product, so an exact-bar candidate like
        0.05*1.05 can land 1 ULP under). A tiny relative+absolute tolerance
        keeps the boundary inclusive without loosening the substantive bar."""
        tol = 1e-9 + 1e-9 * abs(threshold)
        return x >= threshold - tol

    eps = 1e-9
    # Degenerate ratio regime: baseline ~0, or a sign change between the two.
    if abs(base) < eps or (base > 0) != (cand > 0):
        # Require an ABSOLUTE-points improvement and the correct side of zero.
        return (cand > 0) and _gte(cand - base, rel)

    # Normal regime: relative improvement against a same-sign, non-zero base.
    if base > 0:
        required = base * (1.0 + rel)
        return _gte(cand, required)
    # base < 0 (both negative, higher-is-better still): "better" = closer to 0,
    # i.e. cand must be at least `rel` of the way up from base toward 0.
    required = base * (1.0 - rel)  # base negative → required is less-negative
    return _gte(cand, required)


# ─────────────────────────────────────────────────────────────────────────────
# Proposal data model (pure; serialisable). The orchestrator builds a list of
# these per family and the formatter renders them. A ParamDelta with
# candidate == current is a NO-OP row (shown for transparency / coverage).
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ParamDelta:
    """One tunable parameter: its name, current value, and proposed candidate."""

    name: str
    current: Any
    candidate: Any

    @property
    def changed(self) -> bool:
        return self.current != self.candidate


@dataclass
class FamilyProposal:
    """A retune proposal for one tunable family + its OOS gate verdict."""

    family: str
    metric_name: str            # e.g. "composite rank-IC @252d (OOS)"
    lower_is_better: bool
    baseline_metric: float      # measured on the TEST (held-out) stocks
    candidate_metric: float
    min_rel_improvement: float
    deltas: list[ParamDelta] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    measured: bool = False      # True if --run produced a live metric; False = placeholder

    @property
    def verdict(self) -> bool:
        return passes_oos_gate(
            self.baseline_metric,
            self.candidate_metric,
            min_rel_improvement=self.min_rel_improvement,
            lower_is_better=self.lower_is_better,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = "PASS" if self.verdict else "FAIL"
        d["changed_params"] = [pd.name for pd in self.deltas if pd.changed]
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Family A — fundamental pillar weights.
# Current params are read LIVE from the production source of truth
# (score_service.PILLAR_WEIGHTS) so the diff can never drift from reality. The
# candidate, when not measured live, is seeded equal to current (a NO-OP
# proposal) — the human supplies a real candidate by editing the seed below or
# wiring `--run` to entry_ic_report once a hypothesis exists.
# ─────────────────────────────────────────────────────────────────────────────


def _build_pillars_proposal(*, run: bool, min_rel: float) -> FamilyProposal:
    from app.services.score_service import PILLAR_WEIGHTS

    current = dict(PILLAR_WEIGHTS)
    # Seed: equal candidate = NO-OP. The runbook explains how to populate a real
    # candidate (a hypothesis from the IC study) and validate it OOS.
    candidate = dict(current)

    deltas = [
        ParamDelta(name=f"pillar_weight.{k}", current=current[k], candidate=candidate[k])
        for k in current
    ]

    notes = [
        "Validate with: entry_ic_report --validate-prof-retune (or a new "
        "--validate-<pillar>-retune) — composite rank-IC, OLD vs NEW weights.",
        "OOS discipline: split TRAIN/TEST on DISJOINT stocks; gate on the TEST "
        "rank-IC at the SLOW horizon (252d) for value/quality pillars.",
        "Precedent: the profitability pillar was re-tuned (gross_margin 0.14→0.30, "
        "roa 0.18→0.26) ONLY after the IC study flipped its 1y IC positive.",
    ]

    baseline_metric = float("nan")
    candidate_metric = float("nan")
    measured = False
    if run:
        baseline_metric, candidate_metric, extra = _run_pillar_ic()
        notes.extend(extra)
        measured = math.isfinite(baseline_metric) and math.isfinite(candidate_metric)

    return FamilyProposal(
        family="pillars",
        metric_name="composite rank-IC @252d (OOS, disjoint test stocks)",
        lower_is_better=False,
        baseline_metric=baseline_metric,
        candidate_metric=candidate_metric,
        min_rel_improvement=min_rel,
        deltas=deltas,
        notes=notes,
        measured=measured,
    )


def _run_pillar_ic() -> tuple[float, float, list[str]]:
    """Hook for the live pillar-IC validation. Intentionally a thin shim: the
    real OLD-vs-NEW composite-IC math already lives in
    entry_ic_report._validate_prof_retune (which PRINTS its table). Rather than
    duplicate or screen-scrape it, this orchestrator records that the human
    should run that harness directly and read the NEW-OLD dIC row. Returns NaN
    placeholders + a pointer note so the gate correctly reports 'unmeasured →
    FAIL' until a real candidate hypothesis is wired in."""
    return (
        float("nan"),
        float("nan"),
        [
            "[--run] pillar IC is measured by entry_ic_report's own validators "
            "(they print the OLD-vs-NEW dIC table). Run e.g. "
            "`python -m app.scripts.entry_ic_report --validate-prof-retune --us-only` "
            "and read the NEW-OLD row; feed those two IC numbers back as "
            "baseline/candidate to re-check the gate here.",
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Family B — signal per-factor curve anchors + score_v2 delta.
# Current params: the score_v2 soft-min delta (a single global tunable) is read
# live from base.py. Per-factor curve anchors are per-detector literals spread
# across the detectors (owned by other agents) — we DON'T import/mutate them;
# we point the human at the harness that grounds them.
# ─────────────────────────────────────────────────────────────────────────────


def _build_signals_proposal(*, run: bool, min_rel: float) -> FamilyProposal:
    from app.signals.detectors.base import _V2_DELTA

    current_delta = float(_V2_DELTA)
    candidate_delta = current_delta  # NO-OP seed

    deltas = [
        ParamDelta(name="score_v2.delta", current=current_delta, candidate=candidate_delta),
        # Per-factor curve anchors are documented as a family but not mutated
        # here (owned by the detectors). Shown as an informational row.
        ParamDelta(
            name="concave/log_saturate anchors (per detector)",
            current="grounded by signal_factor_outcomes ANCHORS",
            candidate="grounded by signal_factor_outcomes ANCHORS",
        ),
    ]

    notes = [
        "Validate anchors with: signal_factor_outcomes (per-factor bucketed "
        "hit-rate + suggested 0.45/0.75/0.88 ANCHORS) — anchors must be in the "
        "UNITS PASSED TO THE CURVE (read the factor formula, not raw ADX/RSI).",
        "Validate the conjunction with: signal_detector_outcomes (detector "
        "base-rate spread + 'is current confidence predictive?' band table).",
        "Prefer MONOTONIC/interpretable curve shapes; resist anchors that only "
        "fit one regime. Forza ceiling is 0.99 by design — 100 is unreachable.",
    ]

    baseline_metric = float("nan")
    candidate_metric = float("nan")
    measured = False
    if run:
        notes.append(
            "[--run] factor/detector outcomes are reported by "
            "signal_factor_outcomes / signal_detector_outcomes (they print "
            "bucketed tables). Read the per-factor monotonic flag + the detector "
            "base-rate spread; this orchestrator does not re-derive them."
        )

    return FamilyProposal(
        family="signals",
        metric_name="per-factor monotonic hit-rate + detector base-rate spread",
        lower_is_better=False,
        baseline_metric=baseline_metric,
        candidate_metric=candidate_metric,
        min_rel_improvement=min_rel,
        deltas=deltas,
        notes=notes,
        measured=measured,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Family C — Probabilità base rates / calibration model.
# Current params: the COMMITTED artifact app/data/signal_calibration.json (read
# via calibration_map, never re-derived). A "candidate" artifact (e.g. a fresh
# --emit-map written to a scratch path) can be diffed against it; the gate
# metric is OOS Brier (lower is better).
# ─────────────────────────────────────────────────────────────────────────────


def _build_probability_proposal(
    *, run: bool, min_rel: float, candidate_path: Path | None,
) -> FamilyProposal:
    from app.signals.calibration_map import load_calibration

    current_map = load_calibration()
    current_rates = _calibration_rates(current_map)

    if candidate_path is not None and candidate_path.exists():
        cand_map = load_calibration(candidate_path)
        candidate_rates = _calibration_rates(cand_map)
        cand_src = str(candidate_path)
    else:
        candidate_rates = dict(current_rates)  # NO-OP seed
        cand_src = "(no candidate artifact — seeded equal to current)"

    detectors = sorted(set(current_rates) | set(candidate_rates))
    deltas = [
        ParamDelta(
            name=f"base_rate.{d}",
            current=current_rates.get(d),
            candidate=candidate_rates.get(d),
        )
        for d in detectors
    ]

    notes = [
        f"Current artifact: app/data/signal_calibration.json (version="
        f"{current_map.version}). Candidate: {cand_src}.",
        "Regenerate a candidate with: signal_detector_outcomes --emit-map "
        "(writes the JSON). Diff it here; commit the regenerated artifact "
        "ONLY after the OOS Brier gate passes.",
        "Gate metric = OOS Brier (lower=better): fit base rates on TRAIN stocks, "
        "score realised hits on DISJOINT TEST stocks. A fit_signal_calibration "
        "OOS-Brier harness is the intended validator (see runbook §C).",
        "Precedent: the trade-playbook tbs% base rate was DATA-REJECTED "
        "(narrower spread than absHit + undefined for 6/14 detectors) — absHit "
        "stayed. The gate exists to make that kind of rejection automatic.",
    ]

    baseline_metric = float("nan")
    candidate_metric = float("nan")
    measured = False
    if run:
        notes.append(
            "[--run] OOS Brier is not yet wired into this orchestrator (no "
            "fit_signal_calibration harness exists). Until it does, the "
            "probability gate reports 'unmeasured → FAIL' — by design: an "
            "unvalidated calibration change must not pass."
        )

    return FamilyProposal(
        family="probability",
        metric_name="OOS Brier of the calibration map (lower is better)",
        lower_is_better=True,
        baseline_metric=baseline_metric,
        candidate_metric=candidate_metric,
        min_rel_improvement=min_rel,
        deltas=deltas,
        notes=notes,
        measured=measured,
    )


def _calibration_rates(cmap) -> dict[str, float]:
    """Pull {detector: base_rate} out of a CalibrationMap without reaching into
    private internals beyond the one dict the loader exposes for iteration."""
    rates: dict[str, float] = {}
    detectors = getattr(cmap, "_detectors", {}) or {}
    for name in detectors:
        rates[name] = cmap.base_rate(name)
    return rates


# ─────────────────────────────────────────────────────────────────────────────
# Formatting.
# ─────────────────────────────────────────────────────────────────────────────


def _fmt_val(v: Any) -> str:
    if isinstance(v, float):
        if not math.isfinite(v):
            return "n/a"
        return f"{v:.4f}"
    if v is None:
        return "—"
    return str(v)


def _fmt_metric(v: float) -> str:
    return "n/a (unmeasured)" if not math.isfinite(v) else f"{v:+.4f}"


def _ellipsize(s: str, width: int) -> str:
    """Trim a string to `width`, marking truncation, so it fits its column."""
    return s if len(s) <= width else s[: width - 1] + "…"


def _print_proposal(p: FamilyProposal) -> None:
    print()
    print("=" * 86)
    print(f"  PROPOSAL DIFF — family: {p.family.upper()}")
    print("=" * 86)

    changed = [d for d in p.deltas if d.changed]
    print(f"  parameters: {len(p.deltas)} total, {len(changed)} changed")
    print(f"  {'param':<46}{'current':>18}{'candidate':>18}")
    print("  " + "-" * 82)
    for d in p.deltas:
        mark = "*" if d.changed else " "
        name = d.name if len(d.name) <= 44 else d.name[:43] + "…"
        cur = _ellipsize(_fmt_val(d.current), 17)
        cand = _ellipsize(_fmt_val(d.candidate), 17)
        print(f"{mark} {name:<46}{cur:>18}{cand:>18}")

    print()
    print(f"  OOS gate metric : {p.metric_name}")
    arrow = "lower=better" if p.lower_is_better else "higher=better"
    print(f"  direction       : {arrow}")
    print(f"  baseline (TEST) : {_fmt_metric(p.baseline_metric)}")
    print(f"  candidate (TEST): {_fmt_metric(p.candidate_metric)}")
    print(f"  min rel. improve: {p.min_rel_improvement:.1%}")
    measured = "measured" if p.measured else "NOT measured (placeholder)"
    verdict = "PASS — clearly better OOS" if p.verdict else "FAIL — REJECT (not clearly better OOS)"
    print(f"  metric status   : {measured}")
    print(f"  VERDICT         : {verdict}")

    if p.notes:
        print()
        print("  how to validate / notes:")
        for n in p.notes:
            print(f"    • {n}")
    print()


def _print_header() -> None:
    print()
    print("#" * 86)
    print("#  SCORE-RETUNE ORCHESTRATOR — READ-ONLY PROPOSAL DIFF (human-in-the-loop)")
    print("#  This tool proposes; it does NOT apply, regenerate artifacts, or commit.")
    print("#  Review each PASS by hand, then follow docs/runbooks/score-retune-loop.md.")
    print("#" * 86)


def build_proposals(
    *, family: str, run: bool, min_rel: float, candidate_calibration: Path | None,
) -> list[FamilyProposal]:
    proposals: list[FamilyProposal] = []
    if family in ("pillars", "all"):
        proposals.append(_build_pillars_proposal(run=run, min_rel=min_rel))
    if family in ("signals", "all"):
        proposals.append(_build_signals_proposal(run=run, min_rel=min_rel))
    if family in ("probability", "all"):
        proposals.append(
            _build_probability_proposal(
                run=run, min_rel=min_rel, candidate_path=candidate_calibration
            )
        )
    return proposals


def run(
    *, family: str, run_live: bool, min_rel: float, as_json: bool,
    candidate_calibration: Path | None,
) -> None:
    proposals = build_proposals(
        family=family, run=run_live, min_rel=min_rel,
        candidate_calibration=candidate_calibration,
    )

    if as_json:
        payload = {
            "tool": "app.scripts.retune",
            "read_only": True,
            "applied": False,
            "min_rel_improvement": min_rel,
            "proposals": [p.to_dict() for p in proposals],
        }
        print(json.dumps(payload, indent=2, default=str))
        return

    _print_header()
    for p in proposals:
        _print_proposal(p)

    n_pass = sum(1 for p in proposals if p.verdict)
    print("=" * 86)
    print(f"  SUMMARY: {n_pass}/{len(proposals)} families PASS the OOS gate.")
    print("  A PASS is a CANDIDATE for review, not an approval. Nothing was applied.")
    print("  Next: review the diff, re-run the cited harness on disjoint test stocks,")
    print("  and only then edit the param / regenerate the artifact by hand + commit")
    print("  with the OOS metrics in the message.")
    print("=" * 86)
    print()


def main(argv: list[str] | None = None) -> int:
    # The report uses a few Unicode glyphs (em-dash, bullet, arrows) like the
    # sibling harness scripts. On Windows the default console codepage is cp1252,
    # which raises UnicodeEncodeError when the output is piped/redirected. Force
    # UTF-8 on stdout/stderr so the tool is safe under any capture; degrade
    # quietly if the stream can't be reconfigured (older Python / odd streams).
    import contextlib
    import sys

    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    ap = argparse.ArgumentParser(
        description="Read-only score-retune proposal-diff reporter (human-in-the-loop)."
    )
    ap.add_argument(
        "--family",
        choices=["pillars", "signals", "probability", "all"],
        default="all",
        help="which tunable family to report (default: all)",
    )
    ap.add_argument(
        "--run",
        action="store_true",
        help="re-run the underlying harness live (slow, reads DB). Omit to use "
        "the latest committed params/artifact only (fast, offline-safe).",
    )
    ap.add_argument(
        "--min-rel-improvement",
        type=float,
        default=0.05,
        help="relative OOS improvement required to PASS the gate (default 0.05).",
    )
    ap.add_argument(
        "--candidate-calibration",
        type=str,
        default=None,
        help="path to a candidate signal_calibration.json to diff against the "
        "committed one (probability family).",
    )
    ap.add_argument("--json", action="store_true", help="emit the proposal as JSON.")
    args = ap.parse_args(argv)

    cand_path = Path(args.candidate_calibration) if args.candidate_calibration else None
    run(
        family=args.family,
        run_live=args.run,
        min_rel=args.min_rel_improvement,
        as_json=args.json,
        candidate_calibration=cand_path,
    )
    # Always 0: a FAILED gate is a finding to report, not a process error.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
