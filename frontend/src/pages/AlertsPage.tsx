import { useState } from "react";
import { Download, Loader2, PlayCircle, Send } from "lucide-react";

import { alerts as alertsApi, type AlertListParams } from "@/api/alerts";
import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { AlertFilters } from "@/components/AlertFilters";
import { AlertsTable } from "@/components/AlertsTable";
import { ScanStatusCard } from "@/components/ScanStatusCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAlertsList } from "@/hooks/useAlerts";
import {
  useBulkAlerts,
  useSendDigest,
  useTriggerScan,
} from "@/hooks/useAlertMutations";
import { useScanStatus } from "@/hooks/useScanStatus";

const PAGE_SIZE = 50;

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
  const triggerScan = useTriggerScan();
  const sendDigest = useSendDigest();
  const scanStatus = useScanStatus();
  const isScanning = scanStatus.data?.is_running ?? false;

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

  const exportCsv = () => {
    window.location.href = alertsApi.exportCsvUrl(filters);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Alerts</h2>
          <p className="text-sm text-muted-foreground">
            {total} alert totali con i filtri attuali
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => triggerScan.mutate()}
            disabled={isScanning || triggerScan.isPending}
            title={isScanning ? "Uno scan è già in corso" : "Avvia uno scan in background"}
          >
            {isScanning || triggerScan.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <PlayCircle className="h-4 w-4 mr-2" />
            )}
            {isScanning ? "Scan in corso…" : "Esegui scan ora"}
          </Button>
          <Button
            variant="outline"
            onClick={() => sendDigest.mutate()}
            disabled={sendDigest.isPending}
          >
            {sendDigest.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Send className="h-4 w-4 mr-2" />
            )}
            Invia digest ora
          </Button>
          <Button variant="outline" onClick={exportCsv}>
            <Download className="h-4 w-4 mr-2" /> Esporta CSV
          </Button>
        </div>
      </div>

      {/* Filters + Scan status side-by-side on wide viewports.
          Right column at 480px (was 360px) gives the scan-status card
          enough room for the title + Stop button on one line, plus a
          comfortable progress bar when running. The filters card has
          three short inputs and chip strip, so giving up that ~120px is
          a net win on density. Stacks vertically on narrow viewports. */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_480px] gap-3 items-start">
        <AlertFilters value={filters} onChange={(v) => { setPage(0); setFilters(v); }} />
        <ScanStatusCard status={scanStatus.data} isFetching={scanStatus.isFetching} />
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
