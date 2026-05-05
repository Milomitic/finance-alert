import { useState } from "react";

import { type AlertListParams } from "@/api/alerts";
import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { AlertFilters } from "@/components/AlertFilters";
import { AlertsTable } from "@/components/AlertsTable";
import { RulesPanel } from "@/components/rules/RulesPanel";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAlertsList } from "@/hooks/useAlerts";
import { useBulkAlerts } from "@/hooks/useAlertMutations";

const PAGE_SIZE = 50;

/* ─── AlertsPage layout (V3) ─────────────────────────────────────────────
 *
 * Top: title + count + "Esporta CSV"
 *
 * Body: 2-column grid on lg+
 *   ┌─────────────────────────┐  ┌──────────────────┐
 *   │  AlertFilters           │  │  RulesPanel      │
 *   │  (left, fluid 1fr)      │  │  (right, 480px)  │
 *   └─────────────────────────┘  └──────────────────┘
 *
 * What CHANGED from V2:
 *   - Manual scan trigger + ScanStatusCard moved to the dashboard
 *     (HeroStrip → ScanTriggerCard); progress now lives in the persistent
 *     ScanProgressToast (mounted in Layout, bottom-right).
 *   - "Invia digest" button moved to ScanTriggerCard alongside the scan
 *     trigger (both are admin-style on-demand jobs).
 *   - The right-column slot is repurposed: was ScanStatusCard, now RulesPanel
 *     (the standalone /rules page is gone — rules + alerts compose better
 *     on the same screen, since you tune rules based on the alerts they
 *     produce).
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

  const list = useAlertsList({ ...filters, offset: page * PAGE_SIZE });
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
        <h2 className="text-2xl font-semibold">Alerts</h2>
        <p className="text-sm text-muted-foreground">
          {total} alert totali con i filtri attuali
        </p>
      </div>

      {/* Filters (left) + Rules (right). Right-column 480px is the same
          size the old ScanStatusCard occupied — the rules panel inherits
          that slot wholesale. Stacks vertically on narrow viewports. */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_480px] gap-3 items-start">
        <AlertFilters value={filters} onChange={(v) => { setPage(0); setFilters(v); }} />
        <RulesPanel />
      </div>

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
          {list.isLoading && <div className="p-6 text-sm text-muted-foreground">Caricamento…</div>}
          {!list.isLoading && items.length === 0 && (
            <div className="p-6 text-sm text-muted-foreground text-center">
              Nessun alert con questi filtri.
            </div>
          )}
          {items.length > 0 && (
            <AlertsTable
              alerts={items}
              selectedIds={selectedIds}
              onSelect={onSelect}
              onSelectAll={onSelectAll}
              onRowClick={setOpenDetail}
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
