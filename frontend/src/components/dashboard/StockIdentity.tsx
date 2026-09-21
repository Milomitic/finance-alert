import { StockLogo } from "@/components/dashboard/StockLogo";

interface Props {
  ticker: string;
  name?: string | null;
  /** `pila` (default): ticker sopra, nome sotto. `riga`: ticker e nome
   *  sulla stessa riga, e il nome sparisce su telefono. */
  forma?: "pila" | "riga";
}

/**
 * Canonical "ticker + name" identity block used across dashboard rows.
 *
 * Renders the StockLogo followed by either:
 *   - `pila`: a two-line stack — ticker small bold, name extra-small muted
 *     and truncated, with the full name as a hover-title fallback;
 *   - `riga`: ticker and name on ONE line.
 *
 * Single source of truth so TopMovers, 52w&Volume, Alerts (Top stocks
 * + Feed) and Top Picks all share exactly the same visual treatment.
 * Was previously inline-copied in each card with subtle drift
 * (text-[0.7647rem] vs text-sm, text-[0.6765rem] vs text-[0.7059rem], etc.) — this
 * component locks the copies together.
 *
 * ⚠️ `riga` is what the home cards use (2026-09-21, user request): one line
 * per row instead of two makes every list on the page denser, and the name
 * is dropped below `sm`, where a phone row has room for the ticker and the
 * numbers but not for «Hyperliquid Strategies Inc.». The ticker is
 * `shrink-0` and the NAME truncates: when room runs out the identity stays
 * and the decoration gives way — the rule this repo learned three times.
 *
 * Note on flex semantics: the wrapper div is `flex-1 min-w-0` so it
 * fills the row's free space *and* lets the inner `truncate` actually
 * shrink. Callers must place this between a fixed-width logo and any
 * shrink-0 right-side meta cluster; row-level `min-w-0` is also
 * required on the row's flex container (see CLAUDE.md, recurring
 * Tailwind/Flexbox gotcha).
 */
export function StockIdentity({ ticker, name, forma = "pila" }: Props) {
  if (forma === "riga") {
    return (
      <>
        <StockLogo ticker={ticker} size="xs" />
        <div className="flex min-w-0 flex-1 items-baseline gap-1.5">
          <span className="shrink-0 text-sm font-bold tabular-nums leading-tight">{ticker}</span>
          {name && (
            <span
              className="hidden min-w-0 truncate text-[0.7647rem] leading-tight text-muted-foreground sm:block"
              title={name}
            >
              {name}
            </span>
          )}
        </div>
      </>
    );
  }
  return (
    <>
      <StockLogo ticker={ticker} size="xs" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold tabular-nums leading-tight">
          {ticker}
        </div>
        {name && (
          <div
            className="text-[0.7059rem] text-muted-foreground truncate leading-tight"
            title={name}
          >
            {name}
          </div>
        )}
      </div>
    </>
  );
}
