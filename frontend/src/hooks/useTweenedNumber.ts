import { useEffect, useRef, useState } from "react";

/**
 * Smoothly interpolate a numeric value toward a moving target using
 * requestAnimationFrame. Returns the current animated value.
 *
 * When `target` changes, kicks off a new tween from whatever value is
 * currently on screen (not from the previous target) — so chained
 * fast updates feel continuous rather than restart-jumpy.
 *
 * Easing: cubic ease-out (1 - (1-t)^3). Fast initial acceleration
 * with a gentle landing — feels "live data settling" rather than
 * "linear robot count-up".
 *
 * First-render behavior: snaps to the initial target with no tween,
 * because tweening from 0 to e.g. 173.45 on mount is visually noisy
 * and irrelevant to the user (the price was already that, you just
 * arrived on the page).
 *
 * Cleanup: cancels the in-flight RAF on unmount or new target so we
 * never have orphan animation loops driving a setState on unmounted
 * components.
 */
export function useTweenedNumber(
  target: number | null | undefined,
  durationMs = 350,
): number | null {
  const [shown, setShown] = useState<number | null>(
    target != null && Number.isFinite(target) ? target : null,
  );
  const animRef = useRef<number>(0);
  const fromRef = useRef<number>(0);
  const startRef = useRef<number>(0);
  const shownRef = useRef<number | null>(shown);
  shownRef.current = shown;

  useEffect(() => {
    if (target == null || !Number.isFinite(target)) {
      setShown(null);
      return;
    }
    // First time / coming from null: snap, no tween.
    if (shownRef.current == null) {
      setShown(target);
      return;
    }
    if (target === shownRef.current) return;

    fromRef.current = shownRef.current;
    startRef.current = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startRef.current;
      const t = Math.min(1, elapsed / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      const current = fromRef.current + (target - fromRef.current) * eased;
      if (t >= 1) {
        setShown(target);
        return;
      }
      setShown(current);
      animRef.current = requestAnimationFrame(tick);
    };

    cancelAnimationFrame(animRef.current);
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [target, durationMs]);

  return shown;
}
