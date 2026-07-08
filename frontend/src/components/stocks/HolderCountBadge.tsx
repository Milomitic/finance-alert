import { Building2 } from "lucide-react";

/** Smart-money badge: "N fondi" chip shown next to a ticker/name when
 *  at least one tracked institutional/superinvestor holds the stock in
 *  its latest 13F. Deliberately muted (informational, not a signal) and
 *  hidden entirely on 0/null — an absent badge IS the zero state.
 *
 *  Data source: GET /api/institutionals/holder-counts (batch, via
 *  useHolderCounts) — callers pass the single count for their row. */
export function HolderCountBadge({ count }: { count: number | null | undefined }) {
  if (!count) return null;
  return (
    <span
      className="inline-flex items-center gap-1 rounded bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground shrink-0"
      title={`${count} fondi istituzionali/superinvestor tracciati detengono il titolo nell'ultimo 13F disponibile`}
    >
      <Building2 className="h-3 w-3" />
      {count} fondi
    </span>
  );
}
