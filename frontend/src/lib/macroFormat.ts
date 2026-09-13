/* Formattazione dei valori macro: conosce la SCALA dichiarata nel payload,
 * che e' il difetto registrato in CLAUDE.md (159.1K su un valore gia' in
 * migliaia). Estratta dalla pagina */

export function formatMacroValue(
  v: number,
  valueKind: string,
  sourceScale?: string | null,
): string {
  if (!Number.isFinite(v)) return "—";
  if (valueKind === "pct" || valueKind === "yield") return `${v.toFixed(2)}%`;
  if (valueKind === "index") return v.toFixed(1);
  if (valueKind !== "level") return v.toFixed(2);

  const factor = sourceScale ? SCALE_FACTOR[sourceScale] : undefined;
  if (factor === undefined) {
    // Scale unknown. Show the stored number and apply NO transform: a suffix
    // here would be a claim about a magnitude we cannot resolve. The number
    // itself is still a true statement, so it is shown rather than hidden —
    // the same choice `lib/money.ts` makes when a currency is missing.
    return v.toLocaleString("it-IT", { maximumFractionDigits: 0 });
  }

  const real = v * factor;
  const abs = Math.abs(real);
  if (abs >= 1e12) return `${(real / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(real / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(real / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${(real / 1e3).toFixed(1)}K`;
  return real.toFixed(0);
}

/** How many base units one stored unit represents.
 *
 *  ⚠️ This is the whole point of the fix. A PAYEMS observation of 159100 is
 *  expressed in THOUSANDS, so it means 159.1 million people. The old
 *  formatter compacted the stored number directly and printed "159.1K" — a
 *  thousandfold understatement, rendered two inches below a card that says,
 *  verbatim, `Total Non-Farm Payrolls (thousands)`. The scale was in the
 *  payload and the formatter ignored it. */
const SCALE_FACTOR: Record<string, number> = {
  ones: 1,
  thousands: 1e3,
  millions: 1e6,
  billions: 1e9,
};
