import { usePriceFlash } from "@/hooks/usePriceFlash";
import { useTweenedNumber } from "@/hooks/useTweenedNumber";
import { cn } from "@/lib/utils";

interface Props {
  value: number | null | undefined;
  /** Render the numeric value to a string. Receives the *currently
   *  displayed* number (which may be the in-flight tween value), not
   *  necessarily the target. Common pattern: `(v) => $${v.toFixed(2)}`. */
  format: (v: number) => string;
  /** Fallback text when value is null/NaN. Default em-dash. */
  fallback?: string;
  className?: string;
  /** Disable smooth number tween — keep snap-to-new behavior. Useful
   *  for list rows with many simultaneous flashes (cheaper rendering)
   *  or when the format is non-monotonic (e.g. percentages flipping
   *  sign mid-tween would look weird). */
  noTween?: boolean;
  /** Show a small ▲/▼ tick arrow inline during the flash window. */
  showArrow?: boolean;
  /** Override the flash duration in ms. Default 800. */
  flashMs?: number;
  /** Override the tween duration in ms. Default 350. */
  tweenMs?: number;
}

/**
 * Wall-Street ticker-style price display.
 *
 * Two synchronized effects on every value change:
 *   1. **Background flash**: brief tinted box (emerald on uptick, rose
 *      on downtick) fading via a CSS color transition over `flashMs`.
 *   2. **Number tween** (unless `noTween`): the displayed number
 *      smoothly interpolates between the old and new value using a
 *      cubic ease-out over `tweenMs`. Disabled by default for the
 *      first render and during null transitions.
 *
 * Why the wrapping `<span>` has horizontal padding + negative margin:
 * the tinted background needs to extend slightly beyond the digits for
 * a "highlighter" feel without affecting layout flow. `-mx-1` cancels
 * the visual `px-1` so neighboring text doesn't shift on flash.
 *
 * Composition: usePriceFlash drives the color, useTweenedNumber drives
 * the displayed value. They observe the SAME `value` prop independently
 * so the tween runs even while the flash is fading — the two animations
 * compose cleanly.
 */
export function FlashValue({
  value,
  format,
  fallback = "—",
  className,
  noTween,
  showArrow,
  flashMs = 800,
  tweenMs = 350,
}: Props) {
  const dir = usePriceFlash(value, flashMs);
  const tweened = useTweenedNumber(noTween ? null : value, tweenMs);
  // When tween is disabled OR temporarily null (mid-state), fall back
  // to the raw target value so the user sees something coherent.
  const display = noTween || tweened == null ? value : tweened;
  const formatted =
    display != null && Number.isFinite(display) ? format(display) : fallback;

  return (
    <span
      className={cn(
        "inline-block transition-colors duration-700 rounded px-1 -mx-1",
        dir === "up" &&
          "bg-emerald-500/25 text-emerald-700 dark:text-emerald-300",
        dir === "down" &&
          "bg-rose-500/25 text-rose-700 dark:text-rose-300",
        className,
      )}
    >
      {showArrow && dir === "up" && (
        <span className="text-emerald-500 dark:text-emerald-400 text-[0.7em] mr-0.5 align-middle">
          ▲
        </span>
      )}
      {showArrow && dir === "down" && (
        <span className="text-rose-500 dark:text-rose-400 text-[0.7em] mr-0.5 align-middle">
          ▼
        </span>
      )}
      {formatted}
    </span>
  );
}
