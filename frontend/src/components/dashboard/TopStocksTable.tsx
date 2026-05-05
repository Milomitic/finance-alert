import { Link } from "react-router-dom";

import type { TopStock } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TONE_BG, getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

interface Props {
  data: TopStock[];
}

/* ─── TopStocksTable — "stocks with most alerts in the last 30 days" ────── */
/* Lives inside the AlertsCompactPanel "Top stocks" tab. V2 rework:
 *
 *   - Identity column merges ticker + name into one cell (logo · ticker
 *     bold · name muted). Was a 2-column split where the Nome column
 *     read "—" for any stock without a populated catalog name, leaving
 *     dead space. Merging means even nameless stocks still get a tidy
 *     ticker-only row instead of a half-empty pair of cells.
 *
 *   - "Regola top" column now renders the canonical rule-kind chip
 *     (icon + tone bg) used everywhere else in the app. Was a plain
 *     `<Badge variant="secondary">` with a 4-entry KIND_LABEL map that
 *     fell through to the raw underscore-cased kind string for any
 *     newer rule type — so users saw "bollinger_squeeze" alongside
 *     "RSI Oversold" in the same column. The shared `getAlertKindMeta`
 *     helper in `alertMeta.ts` covers all 11 kinds with proper labels +
 *     bullish/bearish/warning/neutral coloring.
 *
 *   - Removed the inner `<Card>` wrapper. The component is rendered
 *     inside AlertsCompactPanel's CardContent, so wrapping in another
 *     Card produced an awkward double-border. Lifted the heading
 *     "Top 10 stock (30gg)" into a small caption above the table.
 */
export function TopStocksTable({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-muted-foreground">
        Nessun alert nei 30 giorni.
      </div>
    );
  }

  return (
    <div>
      <div className="px-4 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        Top 10 stock (30 giorni)
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-xs">Stock</TableHead>
            <TableHead className="text-xs">Regola top</TableHead>
            <TableHead className="text-xs text-right pr-4">Alert</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((s) => {
            const meta = s.top_kind ? getAlertKindMeta(s.top_kind) : null;
            const Icon = meta?.icon;
            return (
              <TableRow key={s.stock_id} className="hover:bg-accent/30">
                {/* Identity cell: logo + ticker (link) + name. Single column
                    means no dead "—" cells when name is missing. */}
                <TableCell className="py-2">
                  <Link
                    to={`/stocks/${encodeURIComponent(s.ticker)}`}
                    className="flex items-center gap-2 group/row hover:underline"
                  >
                    <StockLogo ticker={s.ticker} size="xs" />
                    <div className="min-w-0">
                      <div className="text-sm font-bold tabular-nums leading-tight">
                        {s.ticker}
                      </div>
                      {s.name && (
                        <div
                          className="text-[11px] text-muted-foreground truncate leading-tight max-w-[220px]"
                          title={s.name}
                        >
                          {s.name}
                        </div>
                      )}
                    </div>
                  </Link>
                </TableCell>
                {/* Top rule cell: canonical chip with icon + tone (matches
                    the rest of the app — alerts page, stock detail card). */}
                <TableCell className="py-2">
                  {meta && Icon ? (
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold whitespace-nowrap",
                        TONE_BG[meta.tone],
                      )}
                      title={`Regola più frequente: ${meta.label}`}
                    >
                      <Icon className="h-3 w-3 shrink-0" />
                      {meta.label}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="py-2 text-right tabular-nums font-semibold pr-4">
                  {s.alert_count}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
