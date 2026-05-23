import { Clock } from "lucide-react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { AlertKindChip, AlertToneCell } from "@/components/AlertChips";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TableSearchInput } from "@/components/ui/table-search-input";
import {
  daysBetween,
  formatDayMonth,
  formatShortDate,
  isDelayedDetection,
} from "@/lib/alertDates";
import { cn } from "@/lib/utils";

interface Props {
  alerts: Alert[];
  selectedIds: Set<number>;
  onSelect: (id: number, selected: boolean) => void;
  onSelectAll: (selected: boolean) => void;
  onRowClick: (alert: Alert) => void;
  /** Inline ticker/name search folded into the Ticker column header.
   *  Filters server-side via the AlertListParams `q` param. */
  q: string;
  onQueryChange: (v: string) => void;
  /** Embedded mode for surfaces that show the alerts of a single
   *  stock (e.g. the StockAlertsHistoryCard on the stock-detail page).
   *  When true:
   *    - The select-all + per-row checkboxes are hidden (no bulk
   *      operations on a per-stock view).
   *    - The Ticker column header omits the search input and renders
   *      a plain "Ticker" label.
   *    - The Ticker + Nome columns are dropped entirely — they would
   *      repeat the same value on every row in this mode.
   *  Default false (the canonical alerts-page layout). */
  embedded?: boolean;
}

export function AlertsTable({
  alerts,
  selectedIds,
  onSelect,
  onSelectAll,
  onRowClick,
  q,
  onQueryChange,
  embedded = false,
}: Props) {
  const allSelected = alerts.length > 0 && alerts.every((a) => selectedIds.has(a.id));
  // Embedded mode drops checkbox + Ticker + Nome + Rilevato + Archivio
  // columns. Backend pre-filters archived alerts on the stock-detail
  // endpoint, and on a per-stock view the Rilevato (detection
  // timestamp) column adds noise — Data segnale alone is the relevant
  // "when did this fire" date. colSpan tracks the remaining column
  // count.
  const colSpan = embedded ? 4 : 8;

  // Per user spec: header cells at 1rem (text-base), body rows at
  // 0.875rem (text-sm) — uniform across all cells. Table root sits at
  // text-sm so every body cell inherits without per-cell overrides;
  // each <TableHead> bumps to text-base for the header band only.
  return (
    <Table className={embedded ? "text-[13.5px] [&_td]:py-1 [&_td]:px-2 [&_th]:h-8 [&_th]:px-2 [&_th]:text-[13.5px]" : "text-sm"}>
      <TableHeader>
        <TableRow>
          {!embedded && (
            <TableHead className="w-8 text-base">
              <Checkbox
                checked={allSelected}
                onCheckedChange={(checked) => onSelectAll(!!checked)}
              />
            </TableHead>
          )}
          <TableHead className="text-base" title="Data della barra di mercato in cui la regola è scattata">
            Data segnale
          </TableHead>
          {!embedded && (
            <TableHead className="text-base" title="Quando il sistema ha registrato l'alert">
              Rilevato
            </TableHead>
          )}
          {!embedded && (
            /* Titolo column: logo + ticker (top) / company name (below),
               like the dashboard cards. Holds the inline ticker/name search. */
            <TableHead className="text-base">
              <div className="flex items-center gap-2 min-w-0">
                <span className="shrink-0">Titolo</span>
                <TableSearchInput
                  value={q}
                  onChange={onQueryChange}
                  placeholder="cerca ticker o nome…"
                  ariaLabel="Filtra per ticker o nome"
                  className="flex-1 max-w-[200px]"
                />
              </div>
            </TableHead>
          )}
          <TableHead className="text-base">Regola</TableHead>
          <TableHead className="text-base" title="Direzione semantica dell'alert (rialzista / ribassista / neutra)">
            Tono
          </TableHead>
          <TableHead className="text-base text-right">Prezzo</TableHead>
          {!embedded && (
            <TableHead className="text-base" title="Confidenza del segnale (0-100)">
              Confidenza
            </TableHead>
          )}
        </TableRow>
      </TableHeader>
      <TableBody>
        {alerts.length === 0 && (
          <TableRow>
            <TableCell
              colSpan={colSpan}
              className="text-center text-muted-foreground py-8"
            >
              {q.trim()
                ? `Nessun risultato per "${q}".`
                : "Nessun alert con questi filtri."}
            </TableCell>
          </TableRow>
        )}
        {alerts.map((a) => (
          <TableRow key={a.id} className="cursor-pointer" onClick={() => onRowClick(a)}>
            {!embedded && (
              <TableCell onClick={(e) => e.stopPropagation()}>
                <Checkbox
                  checked={selectedIds.has(a.id)}
                  onCheckedChange={(c) => onSelect(a.id, !!c)}
                />
              </TableCell>
            )}
            {/* Signal date: when the market actually crossed the rule's
                threshold. Bold + tabular so it reads as the primary date —
                this is the one that matters for "when did the indicator
                fire". Backwards-compat: legacy rows have signal_date=null
                and we fall back to "—" with a tip explaining why. */}
            <TableCell className="font-semibold tabular-nums">
              {a.signal_date ? (
                formatShortDate(a.signal_date)
              ) : (
                <span
                  className="text-muted-foreground italic font-normal"
                  title="Alert legacy creato prima dell'introduzione della data segnale"
                >
                  —
                </span>
              )}
            </TableCell>
            {/* Detection timestamp: when the scan job created the row.
                Highlighted with an orange clock when noticeably later than
                the signal (≥1 calendar day) so the user sees at a glance
                that the system noticed a backfilled signal. Hidden in
                embedded mode (per-stock view) — the signal date alone
                is enough context there. */}
            {!embedded && (
              <TableCell className="text-muted-foreground tabular-nums">
                {(() => {
                  const delayed = isDelayedDetection(a.triggered_at, a.signal_date);
                  const delta = daysBetween(a.triggered_at, a.signal_date);
                  return (
                    <span
                      className="inline-flex items-center gap-1"
                      title={
                        delayed && delta != null
                          ? `Il sistema ha rilevato il segnale ${delta}g dopo la barra di mercato. Possibile backfill o scan saltato.`
                          : "Quando lo scan ha registrato l'alert"
                      }
                    >
                      {delayed && (
                        <Clock className="h-3 w-3 text-amber-600 dark:text-amber-400 shrink-0" />
                      )}
                      {formatDayMonth(a.triggered_at)}
                    </span>
                  );
                })()}
              </TableCell>
            )}
            {!embedded && (
              /* Titolo cell: logo + ticker (link, top) over company name
                 (below), dashboard-card style. stopPropagation on the link so
                 it navigates instead of bubbling to the row (which opens the
                 alert popup). */
              <TableCell>
                <div className="flex items-center gap-2 min-w-0">
                  <StockLogo ticker={a.ticker ?? ""} size="xs" />
                  <div className="min-w-0">
                    {a.ticker ? (
                      <Link
                        to={`/stocks/${encodeURIComponent(a.ticker)}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-semibold hover:underline block leading-tight"
                        title={`Vai al dettaglio di ${a.ticker}`}
                      >
                        {a.ticker}
                      </Link>
                    ) : (
                      <span className="font-semibold">—</span>
                    )}
                    {a.name && (
                      <div
                        className="text-xs text-muted-foreground truncate max-w-[200px] leading-tight"
                        title={a.name}
                      >
                        {a.name}
                      </div>
                    )}
                  </div>
                </div>
              </TableCell>
            )}
            <TableCell>
              <AlertKindChip alert={a} />
            </TableCell>
            <TableCell>
              <AlertToneCell alert={a} />
            </TableCell>
            <TableCell className="text-right tabular-nums font-semibold">
              ${a.trigger_price}
            </TableCell>
            {!embedded && (
              <TableCell>
                {(() => {
                  // Signal alerts carry confidence (0-100) in the snapshot.
                  // Show it as a percentage + a reliability bar coloured by
                  // value (rose < 50, amber 50-69, emerald >= 70) so the
                  // table reads conviction at a glance. Non-signal/price
                  // alerts have no confidence -> em dash.
                  const conf = (a.snapshot as Record<string, unknown> | undefined)?.confidence;
                  if (typeof conf !== "number") {
                    return <span className="text-muted-foreground">—</span>;
                  }
                  const pct = Math.max(0, Math.min(100, Math.round(conf)));
                  const bar =
                    pct >= 70 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-rose-500";
                  const txt =
                    pct >= 70
                      ? "text-emerald-600 dark:text-emerald-400"
                      : pct >= 50
                        ? "text-amber-600 dark:text-amber-400"
                        : "text-rose-600 dark:text-rose-400";
                  return (
                    <div className="flex items-center gap-2" title={`Confidenza ${pct}%`}>
                      <span className={cn("text-xs font-semibold tabular-nums w-9 text-right", txt)}>
                        {pct}%
                      </span>
                      <div className="h-1.5 w-16 rounded-full bg-muted overflow-hidden">
                        <div className={cn("h-full rounded-full", bar)} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })()}
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ToneChip + Kind badge moved into the shared `AlertChips` module so
// the alerts table, the stock-detail history card, and the popup all
// render identical chips. See `frontend/src/components/AlertChips.tsx`.
