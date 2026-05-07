import { useEffect, useRef, useState } from "react";

export type FlashDirection = "up" | "down" | null;

/**
 * Wall-Street tick effect: detect price changes and surface a transient
 * direction signal so the consumer can flash-tint the value cell.
 *
 * Returns "up" | "down" | null. The non-null value persists for
 * `durationMs` after each change, then resets to null. A subsequent
 * change before the timer expires resets the timer with the new direction.
 *
 * Edge cases:
 * - First render: records the initial value WITHOUT firing a flash
 *   (otherwise pages mounting with cached data would all flash on load).
 * - null/NaN values: skipped — the previous value is preserved so the
 *   next real value compares against the last good one (avoids spurious
 *   flashes when a refresh transiently fails).
 *
 * Why useRef for the previous value: setState would cause a render loop
 * (effect runs after render, comparing to the just-set "previous" gives
 * always-equal). useRef holds the prior value across renders without
 * triggering re-renders.
 */
export function usePriceFlash(
  value: number | null | undefined,
  durationMs = 800,
): FlashDirection {
  const prev = useRef<number | null | undefined>(undefined);
  const [dir, setDir] = useState<FlashDirection>(null);

  useEffect(() => {
    const v = value;
    const p = prev.current;
    // First render: just record, no flash.
    if (p === undefined) {
      prev.current = v ?? null;
      return;
    }
    // Value vanished — leave prev alone so the next real value compares
    // against the last known good one.
    if (v == null || !Number.isFinite(v)) {
      return;
    }
    // Value appeared after a null/missing window — record but don't flash.
    if (p == null) {
      prev.current = v;
      return;
    }
    if (v === p) return;
    setDir(v > p ? "up" : "down");
    prev.current = v;
    const t = window.setTimeout(() => setDir(null), durationMs);
    return () => window.clearTimeout(t);
  }, [value, durationMs]);

  return dir;
}
