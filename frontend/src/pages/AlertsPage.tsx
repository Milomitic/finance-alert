import { useState } from "react";

import { type AlertListParams } from "@/api/alerts";
import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { AlertFilters } from "@/components/AlertFilters";
import { AlertsInsightCard } from "@/components/AlertsInsightCard";
import { AlertsTable } from "@/components/AlertsTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAlertsList, useConfluence } from "@/hooks/useAlerts";
import { useBulkAlerts } from "@/hooks/useAlertMutations";

const PAGE_SIZE = 50;

/* ─── AlertsPage layout ─────────────────────────────────────────────────
 *
 * Top: title + count
 * Body: AlertFilters + AlertsTable + pagination + detail dialog
 *
 * Rule management UI removed: the rule engine was deleted backend-side.
 * Alerts are now signals-only.
 */
export default function AlertsPage() {
  const [filters, setFilters] = useState<AlertListParams>({
    archived: false,
    limit: PAGE_SIZE,
    offset: 0,
  });
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [openDetail, setOpenDetail] = useState<Alert | null>(null);
  const [sortBy, setSortBy] = useState("triggered_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const list = useAlertsList({
    ...filters,
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

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Segnali</h2>
        <p className="text-sm text-muted-foreground">
          {total} segnali totali con i filtri attuali
        </p>
      </div>

      <AlertFilters value={filters} onChange={(v) => { setPage(0); setFilters(v); }} />

      {/* Confluence digest — always visible above the table (replaced the old
          list/confluence view toggle). */}
      <AlertsInsightCard clusters={conf.data ?? []} loading={conf.isLoading} />

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
