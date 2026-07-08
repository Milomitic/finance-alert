import { Archive, ArchiveRestore, ArrowDown, ArrowUp, ArrowUpDown, Check, Clock, X } from "lucide-react";
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
import { useSignalCalibration } from "@/hooks/useSignalCalibration";
import {
  daysBetween,
  formatShortDate,
  isDelayedDetection,
} from "@/lib/alertDates";
import { PROBABILITA_TOOLTIP, isSignalKind, snapshotForza, snapshotProbabilita } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/** Toggleable columns for the non-embedded alerts table.
 *  Checkbox + Titolo are always-on (identity + selection).
 *  The old single "Confidenza" column was split into "Forza" (pattern
 *  strength, tone-colored) + "Prob." (historical hit-rate, neutral). */
const ALERTS_COLS = [
  { id: "data_segnale", label: "Data segnale" },
  { id: "rilevato",    label: "Rilevato" },
  { id: "regola",      label: "Regola" },
  { id: "catena",      label: "Catena" },
  { id: "natura",      label: "Natura" },
  { id: "tono",        label: "Tono" },
  { id: "orizzonte",   label: "Orizzonte" },
  { id: "forza",       label: "Forza" },
  { id: "probabilita", label: "Prob." },
  { id: "esito",       label: "Esito" },
] as const;

/** Horizon label + tone classes (plain string-literal Record so Tailwind's
 *  purger keeps the classes — see CLAUDE.md tone-class rule). */
const HORIZON_META: Record<string, { label: string; cls: string }> = {
  short:  { label: "Breve", cls: "bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300" },
  medium: { label: "Medio", cls: "bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300" },
  long:   { label: "Lungo", cls: "bg-teal-100 text-teal-700 dark:bg-teal-950/50 dark:text-teal-300" },
};

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
  /** Per-row archive/unarchive action (non-embedded only). When provided, a
   *  hover-visible icon appears at the row end; clicking it toggles the
   *  archived state without opening the detail dialog. */
  onArchiveToggle?: (alert: Alert) => void;
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
  onArchiveToggle,
}: Props) {
  const allSelected = alerts.length > 0 && alerts.every((a) => selectedIds.has(a.id));

  // Per-detector calibration table for the Prob.-cell honesty marker. ONE
  // cached fetch (react-query staleTime 1h, shared with the signal popup and
  // the Settings page) — the lookup below is a plain dict access per row.
  const { data: calibration } = useSignalCalibration();

  /** Honesty tag for an alert's detector (coinflip / negative / edge / null).
   *  Null while the calibration table is loading or for non-signal alerts. */
  const calibrationTag = (rule_kind: string | null | undefined) => {
    if (!calibration || !isSignalKind(rule_kind)) return null;
    const detector = (rule_kind as string).slice("signal:".length);
    return calibration.detectors[detector]?.tag ?? null;
  };

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
  // compact set — Rilevato | Regola | Tono | Forza | Prob. | Prezzo — while the
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
  const showOrizzonte = embedded || isVisible("orizzonte");
  const showForza = embedded || isVisible("forza");
  const showProbabilita = embedded || isVisible("probabilita");
  const showEsito = embedded || isVisible("esito");
  // Archive action column: always-on when the callback is wired (full page),
  // never in embedded mode — like the checkbox, it's an action, not data,
  // so it doesn't participate in the column-visibility menu.
  const showArchive = !embedded && !!onArchiveToggle;

  // colSpan for the empty-state row must match the visible column count.
  const colSpan = [
    showCheckbox, showDataSegnale, showRilevato, showTitolo, showRegola,
    showCatena, showNatura, showTono, showOrizzonte, showForza, showProbabilita,
    showEsito, showArchive,
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
                title="Quando il sistema ha registrato il segnale"
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={onSort}
              />
            ) : (
              <TableHead className="text-base" title="Quando il sistema ha registrato il segnale">
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
            <TableHead className="text-base" title="Direzione semantica del segnale (rialzista / ribassista / neutra)">
              Tono
            </TableHead>
          )}
          {showOrizzonte && (
            <TableHead className="text-base" title="Orizzonte temporale del segnale (breve / medio / lungo)">
              Orizzonte
            </TableHead>
          )}
          {showForza && (
            onSort ? (
              <SortableHeader
                column="strength"
                label="Forza"
                align="right"
                title="Forza del pattern (0-100)"
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={onSort}
              />
            ) : (
              <TableHead className="text-base text-right" title="Forza del pattern (0-100)">
                Forza
              </TableHead>
            )
          )}
          {showProbabilita && (
            onSort ? (
              <SortableHeader
                column="probability"
                label="Prob."
                align="right"
                title={PROBABILITA_TOOLTIP}
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={onSort}
              />
            ) : (
              <TableHead className="text-base text-right" title={PROBABILITA_TOOLTIP}>
                Prob.
              </TableHead>
            )
          )}
          {showEsito && (
            <TableHead
              className="text-base"
              title="Esito realizzato del segnale all'orizzonte di riferimento: verde = direzione azzeccata, rosso = mancata, … = in maturazione"
            >
              Esito
            </TableHead>
          )}
          {showArchive && (
            /* Action column — empty header, fixed narrow width. */
            <TableHead className="w-10 text-base" aria-label="Azioni" />
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
                : "Nessun segnale con questi filtri."}
            </TableCell>
          </TableRow>
        )}
        {alerts.map((a) => (
          <TableRow key={a.id} className="cursor-pointer group" onClick={() => onRowClick(a)}>
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
                    title="Segnale legacy creato prima dell'introduzione della data segnale"
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
            {/* Orizzonte — temporal horizon of the signal (breve/medio/lungo),
                from snapshot.horizon. Non-signal / legacy rows show an em dash. */}
            {showOrizzonte && (
              <TableCell>
                {(() => {
                  const hz = (a.snapshot as Record<string, unknown> | undefined)?.horizon;
                  const meta = typeof hz === "string" ? HORIZON_META[hz] : undefined;
                  if (!meta) return <span className="text-muted-foreground">—</span>;
                  return (
                    <span className={cn("inline-block px-1.5 py-0.5 rounded text-xs font-medium", meta.cls)}>
                      {meta.label}
                    </span>
                  );
                })()}
              </TableCell>
            )}
            {/* Forza — pattern strength (0-100). Coloured percentage
                (rose < 50, amber 50-69, emerald >= 70) with a strength bar on
                the full page. Embedded (narrow card) shows just the % to save
                width. Non-signal / price alerts have no Forza → em dash. */}
            {showForza && (
              <TableCell>
                {(() => {
                  const forza = snapshotForza(a.snapshot as Record<string, unknown> | undefined);
                  if (forza == null) {
                    return <div className="text-right"><span className="text-muted-foreground">—</span></div>;
                  }
                  const pct = Math.max(0, Math.min(100, forza));
                  const bar =
                    pct >= 70 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-rose-500";
                  const txt =
                    pct >= 70
                      ? "text-emerald-600 dark:text-emerald-400"
                      : pct >= 50
                        ? "text-amber-600 dark:text-amber-400"
                        : "text-rose-600 dark:text-rose-400";
                  return (
                    <div className="flex items-center justify-end gap-2" title={`Forza ${pct}%`}>
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
            {/* Probabilità — historical hit-rate (0-100). Rendered in a NEUTRAL
                info treatment (slate text / sky bar) so it reads as a different
                axis from the tone-colored Forza. Legacy alerts lacking it show
                an em dash. */}
            {showProbabilita && (
              <TableCell>
                {(() => {
                  const prob = snapshotProbabilita(a.snapshot as Record<string, unknown> | undefined);
                  if (prob == null) {
                    return <div className="text-right"><span className="text-muted-foreground">—</span></div>;
                  }
                  const pct = Math.max(0, Math.min(100, prob));
                  // Honesty marker: tiny amber/red dot when the detector's
                  // beta-stripped calibration says coinflip / negative — same
                  // copy as the badge in SignalSnapshotView, in dot form.
                  const tag = calibrationTag(a.rule_kind);
                  return (
                    <div className="flex items-center justify-end gap-2" title={`Probabilità ${pct}% — ${PROBABILITA_TOOLTIP}`}>
                      {tag === "coinflip" && (
                        <span
                          className="h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0"
                          title="Storicamente ~50/50 al netto del mercato: nessun edge direzionale dimostrato"
                        />
                      )}
                      {tag === "negative" && (
                        <span
                          className="h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0"
                          title="Edge storico NEGATIVO al netto del mercato: segnale anti-predittivo"
                        />
                      )}
                      <span className="text-sm font-semibold tabular-nums w-10 text-right text-slate-700 dark:text-slate-300">
                        {pct}%
                      </span>
                      {!embedded && (
                        <div className="h-2 w-16 rounded-full bg-muted overflow-hidden">
                          <div className="h-full rounded-full bg-sky-500 dark:bg-sky-400" style={{ width: `${pct}%` }} />
                        </div>
                      )}
                    </div>
                  );
                })()}
              </TableCell>
            )}
            {/* Esito — realized outcome from the signal_outcomes warehouse.
                Green check chip "+X.X%" on hit, red x chip on miss, muted "…"
                while the horizon is still maturing, blank for legacy rows
                without a signal_date (they never mature). */}
            {showEsito && (
              <TableCell>
                {(() => {
                  const hit = a.outcome_hit;
                  if (hit != null) {
                    const fwd = a.outcome_fwd_return;
                    const pct =
                      fwd != null ? `${fwd >= 0 ? "+" : ""}${(fwd * 100).toFixed(1)}%` : "";
                    const hz = a.outcome_horizon_days;
                    const title = `Esito a ${hz ?? "?"}gg: ${hit ? "direzione azzeccata" : "direzione mancata"}${pct ? ` (${pct})` : ""}`;
                    return (
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-semibold tabular-nums",
                          hit
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
                            : "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
                        )}
                        title={title}
                      >
                        {hit ? <Check className="h-3 w-3 shrink-0" /> : <X className="h-3 w-3 shrink-0" />}
                        {pct}
                      </span>
                    );
                  }
                  const pending = isSignalKind(a.rule_kind) && !!a.signal_date;
                  if (pending) {
                    return (
                      <span
                        className="text-muted-foreground"
                        title="Esito in maturazione: l'orizzonte del segnale non è ancora trascorso"
                      >
                        …
                      </span>
                    );
                  }
                  return null;
                })()}
              </TableCell>
            )}
            {/* Archivia/Disarchivia — hover-visible icon at the row end.
                stopPropagation on the CELL (same pattern as the checkbox
                cell) so a click never opens the detail dialog. */}
            {showArchive && (
              <TableCell onClick={(e) => e.stopPropagation()} className="w-10">
                <button
                  type="button"
                  onClick={() => onArchiveToggle?.(a)}
                  title={a.archived_at ? "Disarchivia segnale" : "Archivia segnale"}
                  aria-label={a.archived_at ? "Disarchivia segnale" : "Archivia segnale"}
                  className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                >
                  {a.archived_at ? (
                    <ArchiveRestore className="h-4 w-4" />
                  ) : (
                    <Archive className="h-4 w-4" />
                  )}
                </button>
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
