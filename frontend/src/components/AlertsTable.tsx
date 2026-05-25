import { ArrowDown, ArrowUp, ArrowUpDown, Clock } from "lucide-react";
import { type MouseEvent, useState } from "react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { AlertKindChip, AlertNatureCell, AlertToneCell } from "@/components/AlertChips";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Checkbox } from "@/components/ui/checkbox";
import { ColumnVisibilityMenu } from "@/components/ui/column-visibility-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TableSearchInput } from "@/components/ui/table-search-input";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import {
  daysBetween,
  formatShortDate,
  isDelayedDetection,
} from "@/lib/alertDates";
import { cn } from "@/lib/utils";

/** Toggleable columns for the non-embedded alerts table.
 *  Checkbox + Titolo are always-on (identity + selection). */
const ALERTS_COLS = [
  { id: "data_segnale", label: "Data segnale" },
  { id: "rilevato",    label: "Rilevato" },
  { id: "regola",      label: "Regola" },
  { id: "catena",      label: "Catena" },
  { id: "natura",      label: "Natura" },
  { id: "tono",        label: "Tono" },
  { id: "confidenza",  label: "Confidenza" },
  { id: "prezzo",      label: "Prezzo" },
] as const;

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
  /** Active sort column key (non-embedded only). */
  sortBy?: string;
  /** Active sort direction (non-embedded only). */
  sortDir?: "asc" | "desc";
  /** Called when a sortable header is clicked (non-embedded only). */
  onSort?: (col: string) => void;
}

/** Small local sortable column header — same pattern as StockBrowserTable
 *  and BreadthMatrixTable but scoped to AlertsTable so we avoid an
 *  unrelated cross-component refactor. */
function SortableHeader({
  column,
  label,
  align = "left",
  title,
  sortBy,
  sortDir,
  onSort,
}: {
  column: string;
  label: string;
  align?: "left" | "right";
  title?: string;
  sortBy: string;
  sortDir: "asc" | "desc";
  onSort: (col: string) => void;
}) {
  const active = sortBy === column;
  return (
    <th
      className={cn(
        "px-3 py-1.5 text-base font-medium",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        title={title}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground transition-colors",
          active && "text-foreground",
          align === "right" && "ml-auto",
        )}
      >
        <span>{label}</span>
        {active && sortDir === "desc" && <ArrowDown className="h-3 w-3" />}
        {active && sortDir === "asc" && <ArrowUp className="h-3 w-3" />}
        {!active && <ArrowUpDown className="h-3 w-3 opacity-30" />}
      </button>
    </th>
  );
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
  sortBy = "triggered_at",
  sortDir = "desc",
  onSort,
}: Props) {
  const allSelected = alerts.length > 0 && alerts.every((a) => selectedIds.has(a.id));

  // Column visibility — non-embedded only. Embedded mode has a fixed set
  // of columns (no menu, no toggles).
  const { isVisible, toggle } = useColumnVisibility("alerts", ALERTS_COLS as unknown as { id: string; label: string }[]);

  // Context-menu state for the column-visibility dropdown.
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState({ x: 0, y: 0 });

  function openColumnMenu(e: MouseEvent) {
    e.preventDefault();
    setMenuAnchor({ x: e.clientX, y: e.clientY });
    setMenuOpen(true);
  }

  // Per-column visibility resolved ONCE so the header and body stay in
  // lockstep. Embedded mode (the per-ticker history card) shows a fixed
  // compact set — Rilevato | Regola | Tono | Confidenza | Prezzo — while the
  // full alerts page honours the column-visibility menu. (Previous embedded
  // bug: the signal_date CELL rendered but its HEADER was gated `!embedded`,
  // so every header sat one column right of its data. Deriving both from the
  // same flag makes that drift impossible.)
  const showCheckbox = !embedded;
  const showDataSegnale = !embedded && isVisible("data_segnale");
  const showRilevato = embedded || isVisible("rilevato");
  const showTitolo = !embedded;
  const showRegola = embedded || isVisible("regola");
  const showCatena = !embedded && isVisible("catena");
  const showNatura = !embedded && isVisible("natura");
  const showTono = embedded || isVisible("tono");
  const showConfidenza = embedded || isVisible("confidenza");
  const showPrezzo = embedded || isVisible("prezzo");

  // colSpan for the empty-state row must match the visible column count.
  const colSpan = [
    showCheckbox, showDataSegnale, showRilevato, showTitolo, showRegola,
    showCatena, showNatura, showTono, showConfidenza, showPrezzo,
  ].filter(Boolean).length;

  // Per user spec: header cells at 1rem (text-base), body rows at
  // 0.875rem (text-sm) — uniform across all cells. Table root sits at
  // text-sm so every body cell inherits without per-cell overrides;
  // each <TableHead> bumps to text-base for the header band only.
  return (
    <>
      {/* Column-visibility context menu (non-embedded only) */}
      {!embedded && (
        <ColumnVisibilityMenu
          columns={ALERTS_COLS as unknown as { id: string; label: string }[]}
          isVisible={isVisible}
          toggle={toggle}
          open={menuOpen}
          onOpenChange={setMenuOpen}
          anchor={menuAnchor}
        />
      )}
      <Table className={embedded ? "text-[13.5px] [&_td]:py-1 [&_td]:px-2 [&_th]:h-8 [&_th]:px-2 [&_th]:text-[13.5px]" : "text-sm"}>
      <TableHeader>
        {/* Right-click anywhere on the header row opens the column-visibility
            menu (non-embedded only). The menu positions itself at the cursor. */}
        <TableRow onContextMenu={embedded ? undefined : openColumnMenu}>
          {showCheckbox && (
            <TableHead className="w-8 text-base">
              <Checkbox
                checked={allSelected}
                onCheckedChange={(checked) => onSelectAll(!!checked)}
              />
            </TableHead>
          )}
          {showDataSegnale && (
            onSort ? (
              <SortableHeader
                column="signal_date"
                label="Data segnale"
                title="Data della barra di mercato in cui la regola è scattata"
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={onSort}
              />
            ) : (
              <TableHead className="text-base" title="Data della barra di mercato in cui la regola è scattata">
                Data segnale
              </TableHead>
            )
          )}
          {showRilevato && (
            onSort ? (
              <SortableHeader
                column="triggered_at"
                label="Rilevato"
                title="Quando il sistema ha registrato l'alert"
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={onSort}
              />
            ) : (
              <TableHead className="text-base" title="Quando il sistema ha registrato l'alert">
                Rilevato
              </TableHead>
            )
          )}
          {showTitolo && (
            /* Titolo column: logo + ticker (top) / company name (below),
               like the dashboard cards. Holds the inline ticker/name search.
               Always visible — identity column. */
            onSort ? (
              <th className="px-3 py-1.5 text-base text-left font-medium">
                <div className="flex items-center gap-2 min-w-0">
                  <button
                    type="button"
                    onClick={() => onSort("ticker")}
                    className={cn(
                      "inline-flex items-center gap-1 hover:text-foreground transition-colors shrink-0",
                      sortBy === "ticker" && "text-foreground",
                    )}
                  >
                    <span>Titolo</span>
                    {sortBy === "ticker" && sortDir === "desc" && <ArrowDown className="h-3 w-3" />}
                    {sortBy === "ticker" && sortDir === "asc" && <ArrowUp className="h-3 w-3" />}
                    {sortBy !== "ticker" && <ArrowUpDown className="h-3 w-3 opacity-30" />}
                  </button>
                  <TableSearchInput
                    value={q}
                    onChange={onQueryChange}
                    placeholder="cerca ticker o nome…"
                    ariaLabel="Filtra per ticker o nome"
                    className="flex-1 max-w-[200px]"
                  />
                </div>
              </th>
            ) : (
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
            )
          )}
          {showRegola && (
            <TableHead className="text-base">Regola</TableHead>
          )}
          {showCatena && (
            <TableHead className="text-base">Catena</TableHead>
          )}
          {showNatura && (
            <TableHead className="text-base" title="Natura del segnale: continuazione del trend o inversione">
              Natura
            </TableHead>
          )}
          {showTono && (
            <TableHead className="text-base" title="Direzione semantica dell'alert (rialzista / ribassista / neutra)">
              Tono
            </TableHead>
          )}
          {showConfidenza && (
            onSort ? (
              <SortableHeader
                column="confidence"
                label="Confidenza"
                title="Confidenza del segnale (0-100)"
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={onSort}
              />
            ) : (
              <TableHead className="text-base" title="Confidenza del segnale (0-100)">
                Confidenza
              </TableHead>
            )
          )}
          {showPrezzo && (
            !embedded && onSort ? (
              <SortableHeader
                column="trigger_price"
                label="Prezzo"
                align="right"
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={onSort}
              />
            ) : (
              <TableHead className="text-base text-right">Prezzo</TableHead>
            )
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
            {showCheckbox && (
              <TableCell onClick={(e) => e.stopPropagation()}>
                <Checkbox
                  checked={selectedIds.has(a.id)}
                  onCheckedChange={(c) => onSelect(a.id, !!c)}
                />
              </TableCell>
            )}
            {/* Data segnale — non-embedded, toggleable */}
            {showDataSegnale && (
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
            )}
            {/* Rilevato (detection timestamp) — first column in embedded mode */}
            {showRilevato && (
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
                      {formatShortDate(a.triggered_at)}
                    </span>
                  );
                })()}
              </TableCell>
            )}
            {showTitolo && (
              /* Titolo cell: always visible (identity column). */
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
            {showRegola && (
              <TableCell>
                <AlertKindChip alert={a} />
              </TableCell>
            )}
            {showCatena && (
              <TableCell className="max-w-[260px]">
                {(() => {
                  const chain = (a.snapshot as Record<string, unknown> | undefined)?.chain;
                  if (!Array.isArray(chain) || chain.length === 0) {
                    return <span className="text-muted-foreground">—</span>;
                  }
                  const labels = (chain as { label?: string }[]).map((s) => s.label ?? "").filter(Boolean);
                  const summary = labels.join(" → ");
                  return (
                    <span className="text-xs text-muted-foreground truncate block" title={summary}>
                      {summary}
                    </span>
                  );
                })()}
              </TableCell>
            )}
            {showNatura && (
              <TableCell>
                <AlertNatureCell alert={a} size="sm" />
              </TableCell>
            )}
            {showTono && (
              <TableCell>
                <AlertToneCell alert={a} />
              </TableCell>
            )}
            {/* Confidenza — left of Prezzo. Signal alerts carry confidence
                (0-100) in the snapshot; show it as a coloured percentage
                (rose < 50, amber 50-69, emerald >= 70) with a reliability bar
                on the full page. Embedded (narrow card) shows just the % to
                save width. Non-signal / price alerts have no confidence. */}
            {showConfidenza && (
              <TableCell>
                {(() => {
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
                      <span className={cn("text-sm font-semibold tabular-nums w-10 text-right", txt)}>
                        {pct}%
                      </span>
                      {!embedded && (
                        <div className="h-2 w-16 rounded-full bg-muted overflow-hidden">
                          <div className={cn("h-full rounded-full", bar)} style={{ width: `${pct}%` }} />
                        </div>
                      )}
                    </div>
                  );
                })()}
              </TableCell>
            )}
            {showPrezzo && (
              <TableCell className="text-right tabular-nums font-semibold">
                ${a.trigger_price}
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
    </>
  );
}

// ToneChip + Kind badge moved into the shared `AlertChips` module so
// the alerts table, the stock-detail history card, and the popup all
// render identical chips. See `frontend/src/components/AlertChips.tsx`.
