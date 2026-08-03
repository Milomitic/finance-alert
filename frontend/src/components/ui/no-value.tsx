import { cn } from "@/lib/utils";

/* How a missing number is shown, so that it stays a missing number.
 *
 * The rule this exists to enforce is narrower than "never render a blank",
 * and it is the one that matters: NEVER INVENT A VALUE. The dashboard's index
 * ticker used to print "0.00%" whenever a quote was absent, which is not an
 * empty cell — it is a fabricated fact. The reader sees "Nasdaq 0.00%" and
 * concludes the index did not move, when in truth nothing was known about it.
 * An em-dash is honest; a zero is a quiet lie, and a confident one.
 *
 * So a value is shown, or its absence is shown WITH ITS REASON. `hint` is what
 * turns the second case from a dead end into information — "not traded yet
 * today", "source unreachable" — and it reaches both the tooltip and the
 * screen reader.
 */
export function NoValue({
  hint = "Dato non disponibile",
  className,
}: {
  hint?: string;
  className?: string;
}) {
  return (
    <span
      title={hint}
      aria-label={hint}
      className={cn("text-muted-foreground/70 tabular-nums", className)}
    >
      n/d
    </span>
  );
}

/** True when a number is safe to display. Rejects null, undefined, NaN and
 *  Infinity — the last two arrive from divisions on absent upstream data and
 *  render as literal "NaN%" if nobody checks. */
export function hasValue(v: number | null | undefined): v is number {
  return v != null && Number.isFinite(v);
}
