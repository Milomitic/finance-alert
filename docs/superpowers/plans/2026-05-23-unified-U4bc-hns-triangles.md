# Unified Signals — Phase U4b/U4c: Head-and-Shoulders + Triangles

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Two more geometric families on the existing scaffold — Head-and-Shoulders (top + inverse) and Ascending/Descending Triangles — by EXTENDING `extract_chart_patterns` to emit new `chart_pattern` variants. The generic `ChartPattern` detector already confirms any such event via its neckline break, so no detector logic changes (only its label map grows).

**Architecture:** Additive. `extract_chart_patterns` gains H&S + triangle detection (pivot-based); each emits `chart_pattern` with `{pattern, neckline, direction}`. `ChartPattern.detect` is reused unchanged (it reads `payload["neckline"]` + tone, confirms the break) — only `_PATTERN_IT` gains labels. Full suite stays green (622 passed / 1 skipped at start).

**Tech Stack:** Python 3.11, pandas, pytest. Reuses `find_pivots` + the `ChartPattern` detector.

**Conventions:** tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; ASCII-only.

**Geometry:**
- *Inverse H&S (bull):* last 3 pivot LOWS [s1, head, s2] with `head` the lowest, shoulders `s1≈s2` (within `_HNS_TOL`); neckline = the highest HIGH between s1 and s2; completes on a close ABOVE neckline.
- *H&S top (bear):* last 3 pivot HIGHS [s1, head, s2] with `head` the highest, shoulders `s1≈s2`; neckline = the lowest LOW between; completes on close BELOW neckline.
- *Ascending triangle (bull):* recent pivot HIGHS roughly flat (within `_TRI_TOL`) + pivot LOWS rising; neckline = mean of the flat highs (resistance); break above = bull.
- *Descending triangle (bear):* recent pivot LOWS roughly flat + pivot HIGHS falling; neckline = mean of the flat lows (support); break below = bear.

---

### Task 1: Head-and-Shoulders (top + inverse) in extract_chart_patterns

**Files:**
- Modify: `backend/app/signals/chart_patterns.py`
- Modify: `backend/app/signals/detectors/chart_pattern.py` (label map only)
- Test: `backend/tests/signals/test_chart_patterns.py` (add tests)

- [ ] **Step 1: Add failing tests** to `backend/tests/signals/test_chart_patterns.py` (it has a `_df(closes)` helper):
```python
def _inverse_hns():
    # left shoulder low ~92, head low ~88, right shoulder low ~92, neckline highs ~100,
    # then break above 100.
    seg = (
        [100, 96, 92, 96, 100]        # down to left shoulder (92) and back up (neckline ~100)
        + [100, 95, 90, 88, 90, 95, 100]   # down to head (88) and back up
        + [100, 96, 92, 96, 100]      # down to right shoulder (92) and back up
        + [101, 103, 105]             # break above neckline
    )
    return _df([100] * 6 + seg)


def test_inverse_head_shoulders_emitted():
    evs = extract_chart_patterns(_inverse_hns(), pivot_w=2)
    assert any(e.type == "chart_pattern" and e.direction == "bull"
               and e.payload.get("pattern") == "inverse_head_shoulders" for e in evs)
```

- [ ] **Step 2: Run, verify fail** — no inverse_head_shoulders event yet.

- [ ] **Step 3: Implement** — add an H&S block to `extract_chart_patterns` (after the double top/bottom blocks, before `return out`). Add a module constant `_HNS_TOL = 0.05`:
```python
    # Inverse H&S (bull): last 3 pivot lows, head lowest, shoulders ~equal.
    if len(lows) >= 3:
        s1, head, s2 = lows[-3], lows[-2], lows[-1]
        l1, lh, l2 = low.iloc[s1], low.iloc[head], low.iloc[s2]
        if lh < l1 and lh < l2 and l1 > 0 and abs(l2 - l1) / l1 <= _HNS_TOL \
                and (s2 - s1) <= _MAX_SEP:
            necks = [high.iloc[h] for h in highs if s1 < h < s2]
            if necks:
                neckline = float(max(necks))
                out.append(Event(_iso(dates.iloc[s2]), "chart_pattern", "bull",
                                 magnitude=float(min(1.0, (neckline - lh) / neckline)) if neckline else None,
                                 payload={"pattern": "inverse_head_shoulders", "neckline": neckline,
                                          "head": float(lh)}))
    # H&S top (bear): last 3 pivot highs, head highest, shoulders ~equal.
    if len(highs) >= 3:
        s1, head, s2 = highs[-3], highs[-2], highs[-1]
        h1, hh, h2 = high.iloc[s1], high.iloc[head], high.iloc[s2]
        if hh > h1 and hh > h2 and h1 > 0 and abs(h2 - h1) / h1 <= _HNS_TOL \
                and (s2 - s1) <= _MAX_SEP:
            necks = [low.iloc[lo] for lo in lows if s1 < lo < s2]
            if necks:
                neckline = float(min(necks))
                out.append(Event(_iso(dates.iloc[s2]), "chart_pattern", "bear",
                                 magnitude=float(min(1.0, (hh - neckline) / hh)) if hh else None,
                                 payload={"pattern": "head_shoulders", "neckline": neckline,
                                          "head": float(hh)}))
```
In `chart_pattern.py` add to `_PATTERN_IT`: `"inverse_head_shoulders": "Testa-spalle inverso", "head_shoulders": "Testa-spalle"`.

- [ ] **Step 4: Run + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_chart_patterns.py tests/signals/ -q` → green. If the inverse-H&S fixture doesn't trigger (pivot sensitivity), adjust the FIXTURE so it has 3 clean pivot lows (head lowest) + neckline highs between.
```bash
git add backend/app/signals/chart_patterns.py backend/app/signals/detectors/chart_pattern.py backend/tests/signals/test_chart_patterns.py
git commit -m "feat(signals): Head-and-Shoulders (top + inverse) chart pattern"
```

---

### Task 2: Ascending / Descending Triangles in extract_chart_patterns

**Files:**
- Modify: `backend/app/signals/chart_patterns.py`
- Modify: `backend/app/signals/detectors/chart_pattern.py` (label map)
- Test: `backend/tests/signals/test_chart_patterns.py` (add a test)

- [ ] **Step 1: Add failing test**
```python
def _ascending_triangle():
    # flat highs ~110, rising lows; then break above 110.
    seg = []
    lows_floor = [95, 99, 103]   # rising lows
    for k in range(3):
        seg += [lows_floor[k], 106, 110, 106, lows_floor[k]]  # up to flat top 110, back to a higher low
    seg += [111, 113]            # break above the flat resistance
    return _df([100] * 6 + seg)


def test_ascending_triangle_emitted():
    evs = extract_chart_patterns(_ascending_triangle(), pivot_w=2)
    assert any(e.type == "chart_pattern" and e.direction == "bull"
               and e.payload.get("pattern") == "ascending_triangle" for e in evs)
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** — add a triangle block + constant `_TRI_TOL = 0.02`. Use the last 3 pivot highs + last 3 pivot lows:
```python
    # Ascending triangle (bull): flat highs + rising lows.
    if len(highs) >= 3 and len(lows) >= 3:
        h = [high.iloc[i] for i in highs[-3:]]
        lo3 = [low.iloc[i] for i in lows[-3:]]
        flat_highs = max(h) > 0 and (max(h) - min(h)) / max(h) <= _TRI_TOL
        rising_lows = lo3[0] < lo3[1] < lo3[2]
        if flat_highs and rising_lows:
            neckline = float(sum(h) / len(h))
            out.append(Event(_iso(dates.iloc[lows[-1]]), "chart_pattern", "bull",
                             magnitude=0.6,
                             payload={"pattern": "ascending_triangle", "neckline": neckline}))
        # Descending triangle (bear): flat lows + falling highs.
        flat_lows = min(lo3) > 0 and (max(lo3) - min(lo3)) / min(lo3) <= _TRI_TOL
        falling_highs = h[0] > h[1] > h[2]
        if flat_lows and falling_highs:
            neckline = float(sum(lo3) / len(lo3))
            out.append(Event(_iso(dates.iloc[highs[-1]]), "chart_pattern", "bear",
                             magnitude=0.6,
                             payload={"pattern": "descending_triangle", "neckline": neckline}))
```
In `chart_pattern.py` add to `_PATTERN_IT`: `"ascending_triangle": "Triangolo ascendente", "descending_triangle": "Triangolo discendente"`.

- [ ] **Step 4: Run + full suite + commit**
`cd backend && ./.venv/Scripts/python.exe -m pytest tests/signals/test_chart_patterns.py tests/signals/ -q` → green, then full suite. Tune the FIXTURE (not the geometry) if needed; relax shared-fixture count tests to `>= 1` if needed.
```bash
git add backend/app/signals/chart_patterns.py backend/app/signals/detectors/chart_pattern.py backend/tests/signals/test_chart_patterns.py backend/tests/
git commit -m "feat(signals): ascending/descending triangle chart patterns"
```

---

## Self-review notes
- Both families reuse the generic `ChartPattern` detector (neckline break) — only the extractor + label map grow. No new detector. ✓
- H&S: 3-pivot, head extreme, shoulders ~equal, neckline between. Triangles: flat line + trending opposite pivots. All pivot-based (no fragile line-fitting). ✓
- Symmetrical triangle / flags / wedges / cup&handle intentionally deferred (ambiguous direction / pole detection / fuzzier) — diminishing returns. ✓
- Type consistency: events stay `chart_pattern` with `{pattern, neckline, direction}`; detector unchanged. ✓

## Follow-up (optional tail)
- Symmetrical triangle, flags/pennants (pole + consolidation), wedges, cup-and-handle.
- B7 hidden divergence.
- UI: group the alert event-chain by `source` + show the pattern family chip.
