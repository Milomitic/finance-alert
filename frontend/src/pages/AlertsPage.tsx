import { Download, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { alerts as alertsApi, type AlertListParams } from "@/api/alerts";
import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { AlertFilters } from "@/components/AlertFilters";
import { AlertsInsightCard } from "@/components/AlertsInsightCard";
import { AlertsTable } from "@/components/AlertsTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { useAlertsList, useConfluence } from "@/hooks/useAlerts";
import { useBulkAlerts, usePatchAlert } from "@/hooks/useAlertMutations";

const PAGE_SIZE = 50;

/* ─── URL ⇄ state (filters + sort + page) ────────────────────────────────
 *
 * The working set (filters, sort, page) is serialized into the URL search
 * params so back-navigation and shared links restore exactly what the user
 * was looking at. Only non-default values are written, keeping URLs short.
 * AlertListParams is flat strings/numbers, so the mapping is 1:1.
 */

/** Parse a 0-100 numeric param; anything else → undefined (ignored). */
function numParam(sp: URLSearchParams, key: string): number | undefined {
  const raw = sp.get(key);
  if (raw == null || raw === "") return undefined;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 && n <= 100 ? n : undefined;
}

function filtersFromSearch(sp: URLSearchParams): AlertListParams {
  const s = (k: string) => sp.get(k) || undefined;
  return {
    archived: sp.get("archived") === "true",
    ticker: s("ticker"),
    q: s("q"),
    rule_kind: s("rule_kind"),
    tone: s("tone"),
    nature: s("nature"),
    outcome: s("outcome"),
    horizon: s("horizon"),
    date_from: s("date_from"),
    date_to: s("date_to"),
    strength_min: numParam(sp, "strength_min"),
    probability_min: numParam(sp, "probability_min"),
  };
}

function searchFromState(
  filters: AlertListParams,
  page: number,
  sortBy: string,
  sortDir: "asc" | "desc",
): URLSearchParams {
  const sp = new URLSearchParams();
  if (filters.ticker) sp.set("ticker", filters.ticker);
  if (filters.q) sp.set("q", filters.q);
  if (filters.rule_kind) sp.set("rule_kind", filters.rule_kind);
  if (filters.tone) sp.set("tone", filters.tone);
  if (filters.nature) sp.set("nature", filters.nature);
  if (filters.outcome) sp.set("outcome", filters.outcome);
  if (filters.horizon) sp.set("horizon", filters.horizon);
  if (filters.date_from) sp.set("date_from", filters.date_from);
  if (filters.date_to) sp.set("date_to", filters.date_to);
  if (filters.strength_min != null) sp.set("strength_min", String(filters.strength_min));
  if (filters.probability_min != null) sp.set("probability_min", String(filters.probability_min));
  if (filters.archived) sp.set("archived", "true");
  if (page > 0) sp.set("page", String(page + 1)); // 1-based in the URL
  if (sortBy !== "triggered_at") sp.set("sort_by", sortBy);
  if (sortDir !== "desc") sp.set("sort_dir", sortDir);
  return sp;
}

/* ─── AlertsPage layout ─────────────────────────────────────────────────
 *
 * Top: title + count
 * Body: AlertFilters + AlertsTable + pagination + detail dialog
 *
 * Rule management UI removed: the rule engine was deleted backend-side.
 * Alerts are now signals-only.
 */
export default function AlertsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  // Hydrate the working set from the URL once on mount (lazy initializers);
  // afterwards the effect below keeps the URL in sync with the state.
  const [filters, setFilters] = useState<AlertListParams>(() =>
    filtersFromSearch(searchParams),
  );
  const [page, setPage] = useState(() => {
    const p = Number(searchParams.get("page"));
    return Number.isInteger(p) && p > 1 ? p - 1 : 0;
  });
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [openDetail, setOpenDetail] = useState<Alert | null>(null);
  const [sortBy, setSortBy] = useState(
    () => searchParams.get("sort_by") ?? "triggered_at",
  );
  const [sortDir, setSortDir] = useState<"asc" | "desc">(() =>
    searchParams.get("sort_dir") === "asc" ? "asc" : "desc",
  );

  // State → URL. `replace: true` so per-keystroke filter edits don't spam
  // the history stack; back-nav returns to the PAGE the user came from,
  // with this URL still carrying the final working set.
  useEffect(() => {
    setSearchParams(searchFromState(filters, page, sortBy, sortDir), {
      replace: true,
    });
  }, [filters, page, sortBy, sortDir, setSearchParams]);

  const list = useAlertsList({
    ...filters,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    sort_by: sortBy,
    sort_dir: sortDir,
  });

  const handleSort = (col: string) => {
    if (col === sortBy) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(col);
      // Ticker sorts ascending by default; all others default desc.
      setSortDir(col === "ticker" ? "asc" : "desc");
    }
    setPage(0);
  };
  // Confluence is always fetched now (no more view toggle) — it feeds the
  // insight card that sits above the table.
  const conf = useConfluence(7);
  const bulk = useBulkAlerts();
  const patchAlert = usePatchAlert();

  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const onSelect = (id: number, sel: boolean) => {
    const next = new Set(selectedIds);
    if (sel) next.add(id);
    else next.delete(id);
    setSelectedIds(next);
  };

  const onSelectAll = (sel: boolean) => {
    setSelectedIds(sel ? new Set(items.map((a) => a.id)) : new Set());
  };

  const doBulk = async (action: "archive" | "unarchive") => {
    if (selectedIds.size === 0) return;
    await bulk.mutateAsync({ ids: Array.from(selectedIds), action });
    setSelectedIds(new Set());
  };

  // Confluence drill-down: clicking a cluster in the insight card filters
  // the table below to that ticker (exact-match `ticker` param, so it also
  // flows into the CSV export and the URL).
  const selectTicker = (t: string) => {
    setPage(0);
    setFilters((f) => ({ ...f, ticker: t }));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Segnali</h2>
          <p className="text-sm text-muted-foreground">
            {total} segnali totali con i filtri attuali
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            // Same-origin GET with cookie auth: navigating to the URL triggers
            // the CSV download. Export respects the CURRENT filters (without
            // pagination — the endpoint streams every matching row).
            const { limit: _l, offset: _o, ...exportParams } = filters;
            window.location.assign(alertsApi.exportCsvUrl(exportParams));
          }}
          title="Esporta i segnali filtrati in CSV"
        >
          <Download className="h-4 w-4 mr-1.5" /> Esporta CSV
        </Button>
      </div>

      <AlertFilters value={filters} onChange={(v) => { setPage(0); setFilters(v); }} />

      {/* Confluence digest — always visible above the table (replaced the old
          list/confluence view toggle). Cluster rows drill down into the table. */}
      <AlertsInsightCard
        clusters={conf.data ?? []}
        loading={conf.isLoading}
        onTickerSelect={selectTicker}
      />

      {/* Drill-down chip: shows the cluster ticker currently filtering the
          table, with an X to go back to the full list. */}
      {filters.ticker && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">filtro attivo:</span>
          <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted px-2 py-0.5 text-xs font-semibold">
            {filters.ticker}
            <button
              type="button"
              onClick={() => {
                setPage(0);
                setFilters((f) => ({ ...f, ticker: undefined }));
              }}
              className="opacity-70 hover:opacity-100 transition-opacity"
              aria-label="Rimuovi filtro ticker"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        </div>
      )}

      {selectedIds.size > 0 && (
        <Card>
          <CardContent className="flex items-center gap-2 p-3">
            <span className="text-sm">{selectedIds.size} selezionati</span>
            <Button size="sm" onClick={() => doBulk("archive")}>Archivia</Button>
            <Button size="sm" onClick={() => doBulk("unarchive")}>Disarchivia</Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {/* Always render AlertsTable — even with 0 rows — so the
              ticker/name search input in its header stays visible and
              the user can adjust the query that's filtering things to
              empty. The empty-state message renders inside the tbody. */}
          {list.isLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Caricamento…</div>
          ) : list.isError ? (
            <QueryError
              message="dei segnali"
              onRetry={() => list.refetch()}
              isRetrying={list.isFetching}
              className="p-6"
            />
          ) : (
            <AlertsTable
              alerts={items}
              selectedIds={selectedIds}
              onSelect={onSelect}
              onSelectAll={onSelectAll}
              onRowClick={setOpenDetail}
              q={filters.q ?? ""}
              onQueryChange={(v) => {
                setPage(0);
                setFilters({ ...filters, q: v || undefined });
              }}
              sortBy={sortBy}
              sortDir={sortDir}
              onSort={handleSort}
              onArchiveToggle={(a) =>
                patchAlert.mutate({ id: a.id, archived: a.archived_at == null })
              }
            />
          )}
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span>Pagina {page + 1} di {totalPages}</span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Precedente
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page + 1 >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Successiva
            </Button>
          </div>
        </div>
      )}

      <AlertDetailDialog alert={openDetail} onClose={() => setOpenDetail(null)} />
    </div>
  );
}
