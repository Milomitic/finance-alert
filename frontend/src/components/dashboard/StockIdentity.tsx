import { StockLogo } from "@/components/dashboard/StockLogo";

interface Props {
  ticker: string;
  name?: string | null;
}

/**
 * Canonical "ticker + name" identity block used across dashboard rows.
 *
 * Renders the StockLogo followed by a two-line stack:
 *   - Ticker: small bold, tabular-nums
 *   - Name: extra-small muted, truncated with the full name as a
 *     hover-title fallback when it overflows
 *
 * Single source of truth so TopMovers, 52w&Volume, Alerts (Top stocks
 * + Feed) and Top Picks all share exactly the same visual treatment.
 * Was previously inline-copied in each card with subtle drift
 * (text-[13px] vs text-sm, text-[10px] vs text-[11px], etc.) — this
 * component locks the copies together.
 *
 * Note on flex semantics: the wrapper div is `flex-1 min-w-0` so it
 * fills the row's free space *and* lets the inner `truncate` actually
 * shrink. Callers must place this between a fixed-width logo and any
 * shrink-0 right-side meta cluster; row-level `min-w-0` is also
 * required on the row's flex container (see CLAUDE.md, recurring
 * Tailwind/Flexbox gotcha).
 */
export function StockIdentity({ ticker, name }: Props) {
  return (
    <>
      <StockLogo ticker={ticker} size="xs" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold tabular-nums leading-tight">
          {ticker}
        </div>
        {name && (
          <div
            className="text-[10px] text-muted-foreground truncate leading-tight"
            title={name}
          >
            {name}
          </div>
        )}
      </div>
    </>
  );
}
