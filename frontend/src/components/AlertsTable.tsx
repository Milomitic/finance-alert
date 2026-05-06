import { Clock } from "lucide-react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { AlertKindChip, AlertToneCell } from "@/components/AlertChips";
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
  formatDateTime,
  formatShortDate,
  isDelayedDetection,
} from "@/lib/alertDates";

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
  // When embedded the "Ticker" column is dropped along with checkbox +
  // Nome — the colSpan for the empty-state row needs to match the
  // remaining column count or the message gets squeezed into one cell.
  const colSpan = embedded ? 6 : 9;

  // Bumped one notch above the shared Table's default text-sm: the alert
  // listing is the page's primary content, not auxiliary metadata, so it
  // earns the larger reading size. Header stays text-sm to preserve the
  // visual hierarchy (label-vs-value); meta cells (timestamp, name,
  // status) move from text-xs to text-sm so they're still slightly
  // smaller than the primary cells but more comfortable to read.
  return (
    <Table className="text-base">
      <TableHeader>
        <TableRow>
          {!embedded && (
            <TableHead className="w-8">
              <Checkbox
                checked={allSelected}
                onCheckedChange={(checked) => onSelectAll(!!checked)}
              />
            </TableHead>
          )}
          <TableHead className="text-sm" title="Data della barra di mercato in cui la regola è scattata">
            Data segnale
          </TableHead>
          <TableHead className="text-sm" title="Quando il sistema ha registrato l'alert">
            Rilevato
          </TableHead>
          {!embedded && (
            <>
              {/* Ticker column: sortable label is just text (this table
                  doesn't support sorting) + the inline ticker/name
                  search input. */}
              <TableHead className="text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="shrink-0">Ticker</span>
                  <TableSearchInput
                    value={q}
                    onChange={onQueryChange}
                    placeholder="cerca ticker o nome…"
                    ariaLabel="Filtra per ticker o nome"
                    className="flex-1 max-w-[200px]"
                  />
                </div>
              </TableHead>
              <TableHead className="text-sm">Nome</TableHead>
            </>
          )}
          <TableHead className="text-sm">Regola</TableHead>
          <TableHead className="text-sm" title="Direzione semantica dell'alert (rialzista / ribassista / neutra)">
            Tono
          </TableHead>
          <TableHead className="text-sm text-right">Prezzo</TableHead>
          <TableHead className="text-sm">Archivio</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {alerts.length === 0 && (
          <TableRow>
            <TableCell
              colSpan={colSpan}
              className="text-center text-sm text-muted-foreground py-8"
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
            <TableCell className="text-sm font-semibold tabular-nums">
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
                that the system noticed a backfilled signal. */}
            <TableCell className="text-sm text-muted-foreground tabular-nums">
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
                    {formatDateTime(a.triggered_at)}
                  </span>
                );
              })()}
            </TableCell>
            {!embedded && (
              <>
                {/* Ticker cell: stopPropagation so the click navigates to
                    the stock detail page instead of bubbling up to the
                    row's onClick (which opens the alert popup). */}
                <TableCell className="font-semibold">
                  {a.ticker ? (
                    <Link
                      to={`/stocks/${encodeURIComponent(a.ticker)}`}
                      onClick={(e) => e.stopPropagation()}
                      className="hover:underline"
                      title={`Vai al dettaglio di ${a.ticker}`}
                    >
                      {a.ticker}
                    </Link>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground truncate max-w-[240px]" title={a.name ?? ""}>
                  {a.name ?? "—"}
                </TableCell>
              </>
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
            <TableCell className="text-sm">
              {a.archived_at ? "🗄 Archiviato" : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ToneChip + Kind badge moved into the shared `AlertChips` module so
// the alerts table, the stock-detail history card, and the popup all
// render identical chips. See `frontend/src/components/AlertChips.tsx`.
