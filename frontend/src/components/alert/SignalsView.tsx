import { Download, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { alerts as alertsApi, type AlertListParams } from "@/api/alerts";
import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { SignalStatsSection } from "@/components/alert/SignalStatsSection";
import { AlertFilters } from "@/components/AlertFilters";
import { AlertsInsightCard } from "@/components/AlertsInsightCard";
import { AlertsTable } from "@/components/AlertsTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { useAlertsList, useConfluence } from "@/hooks/useAlerts";
import { useBulkAlerts, usePatchAlert } from "@/hooks/useAlertMutations";
import {
  esitoNascostoDallArchivio, filtersFromSearch, searchFromState,
} from "@/lib/alertFilters";

const PAGE_SIZE = 50;

/* ─── La lista dei segnali ───────────────────────────────────────────────
 *
 * Efficacia → confluenze → filtri → tabella → paginazione → dettaglio.
 *
 * ⚠️ Era `pages/AlertsPage.tsx`, cioe' la pagina intera. Dal 2026-09-19 e' una
 * delle tre schede di quella destinazione — In formazione, Segnali, Esiti — e
 * il titolo con l'intestazione vivono nel contenitore. Qui resta la lista.
 *
 * La UI delle regole non c'e' piu': il motore a regole e' stato tolto dal
 * backend, e gli alert sono soltanto segnali.
 */
export function SignalsView() {
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
    // Same reasoning as probability_min above: sorting by Probabilità ordered
    // rows by DETECTOR (the value is a per-detector constant), so the sort was
    // removed. An old link asking for it falls back to the default instead of
    // producing an order nothing on screen can explain.
    //
    // ⚠️ `triggered_at` cade nello stesso ripiego dal 2026-09-23: era
    // l'ordine predefinito e la colonna che lo esprimeva non c'e' piu'. Quel
    // campo e' l'ULTIMA REVISIONE, quindi ordinarci sopra portava in cima ogni
    // giorno i segnali che PERSISTONO invece di quelli nuovi. La lista mostra
    // il giorno in cui l'alert e' comparso, e ci si ordina sopra.
    () => {
      const sb = searchParams.get("sort_by");
      return sb && sb !== "probability" && sb !== "triggered_at" ? sb : "emissione";
    },
  );
  const [sortDir, setSortDir] = useState<"asc" | "desc">(() =>
    searchParams.get("sort_dir") === "asc" ? "asc" : "desc",
  );

  // State → URL. `replace: true` so per-keystroke filter edits don't spam
  // the history stack; back-nav returns to the PAGE the user came from,
  // with this URL still carrying the final working set.
  useEffect(() => {
    // ⚠️ `setSearchParams` con una funzione: leggere `searchParams` dal corpo
    // lo renderebbe una dipendenza dell'effetto, che riscrive proprio quel
    // valore — un ciclo. La forma funzionale riceve i parametri correnti
    // senza doverli dichiarare.
    setSearchParams(
      (correnti) => searchFromState(filters, page, sortBy, sortDir, correnti),
      { replace: true },
    );
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
        <p className="text-sm text-muted-foreground">
          {total} segnali totali con i filtri attuali
        </p>
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

      {/* Le statistiche di efficacia, spostate qui da Diagnostica (2026-09-16):
          tutti gli esiti maturati, non la pagina ne' i filtri della tabella. */}
      <SignalStatsSection />

      {/* Confluence digest — always visible above the table (replaced the old
          list/confluence view toggle). Cluster rows drill down into the table. */}
      <AlertsInsightCard
        clusters={conf.data ?? []}
        loading={conf.isLoading}
        onTickerSelect={selectTicker}
      />

      {/* ⚠️ I filtri stanno SOTTO le confluenze e SOPRA la tabella, e l'ordine
          e' una scelta di lettura, non estetica.
          Le confluenze sono un digest: si leggono per prime e si clicca un
          cluster per restringere la tabella. Con i filtri in cima, il primo
          controllo della pagina agiva su una tabella che il lettore non aveva
          ancora visto. Ora i tre blocchi seguono cio' che si fa: guarda il
          quadro, restringi, leggi le righe — e il controllo sta accanto a cio'
          che governa. */}
      <AlertFilters value={filters} onChange={(v) => { setPage(0); setFilters(v); }} />

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

      {/* ⚠️ Perche' filtrando «Azzeccato» si vedevano cinque righe.
          Un segnale viene archiviato DA SOLO appena l'esito matura e la data
          esce dalla finestra delle confluenze, e per ogni detector con
          orizzonte da 21 o 63 sedute le due cose accadono nella stessa
          passata di scansione: in produzione 5.312 dei 5.313 esiti maturati
          stanno su alert archiviati. Il numero a schermo misurava la regola di
          archiviazione, non il motore — e niente lo diceva. */}
      {esitoNascostoDallArchivio(filters) && (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-2 p-3">
            <p className="min-w-0 flex-1 text-sm text-muted-foreground">
              Un segnale viene <strong>archiviato da solo</strong> appena il suo esito matura:
              con i soli attivi ne resta a schermo una manciata, e il conteggio descrive la
              regola di archiviazione invece del motore.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setPage(0);
                setFilters((f) => ({ ...f, include_archived: true }));
              }}
            >
              Mostra anche gli archiviati
            </Button>
          </CardContent>
        </Card>
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
