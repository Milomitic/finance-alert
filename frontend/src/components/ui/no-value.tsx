import { InfoHint } from "@/components/ui/info-hint";
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
  hint,
  className,
}: {
  hint?: string;
  className?: string;
}) {
  // ⚠️ Il motivo non sta piu' in `title=` (B-75): su un telefono un `title`
  // non si apre mai, e `aria-label` su uno span senza ruolo non e' letto in
  // modo affidabile. Il segno e' «—», come nei 268 punti che lo scrivono a
  // mano, invece di «n/d»: un segno solo per lo stesso fatto. Il motivo e'
  // testo per i lettori di schermo e, quando c'e', un aiuto che si apre al
  // tocco.
  const motivo = hint ?? "Dato non disponibile";
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-muted-foreground tabular-nums", className)}>
      <span aria-hidden>—</span>
      <span className="sr-only">{motivo}</span>
      {hint && <InfoHint label="dato assente" text={hint} />}
    </span>
  );
}

