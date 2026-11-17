import { Download } from "lucide-react";
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
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { QueryError } from "@/components/ui/query-error";
import { GiornateDiMercato } from "@/components/alert/GiornateDiMercato";
import { useAlertsList, useConfluence, useGiornateDiMercato } from "@/hooks/useAlerts";
import { useBulkAlerts, usePatchAlert } from "@/hooks/useAlertMutations";
import { useDetectorPerformance } from "@/hooks/useDetectorPerformance";
import {
  comprimeGiornate, esitoNascostoDallArchivio, filtersFromSearch, ORDINE_PREDEFINITO,
  searchFromState,
} from "@/lib/alertFilters";
import { filtriDellaGiornata } from "@/lib/giornateDiMercato";

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
      return sb && sb !== "probability" && sb !== "triggered_at" ? sb : ORDINE_PREDEFINITO;
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

  // FA-152: sull'universo le giornate di mercato escono dalla lista.
  const comprime = comprimeGiornate(filters);
  const giornate = useGiornateDiMercato(!filters.solo_rilevanti);
  const list = useAlertsList({
    ...filters,
    comprimi_giornate: comprime || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    sort_by: sortBy,
    sort_dir: sortDir,
  });

  const handleSort = (col: string) => {
    // La rilevanza e' un interruttore, non una colonna: un secondo tocco torna
    // all'ordine per nascita invece di mettere IN CIMA i titoli che non segui.
    if (col === "rilevanza" && sortBy === "rilevanza") {
      setSortBy("emissione");
      setSortDir("desc");
      setPage(0);
      return;
    }
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
  // La stessa query che `SignalStatsSection` legge da sola: react-query la
  // condivide per chiave, qui serve solo a sapere quando e' arrivata.
  const prestazioni = useDetectorPerformance();
  // Vero dal primo arrivo di tutte e tre in poi (un errore conta come
  // arrivo): solo il caricamento INIZIALE usa lo scheletro unico. Aggiornato
  // in render, come React documenta per lo stato che segue altro stato.
  const [haCaricato, setHaCaricato] = useState(false);
  const arrivate = [list, conf, prestazioni].every((q) => q.data !== undefined || q.isError);
  if (!haCaricato && arrivate) setHaCaricato(true);
  const primoCaricamento = !haCaricato;
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

      {/* ⚠️ Il PRIMO caricamento e' un blocco solo (FA-106). Statistiche,
          confluenze e tabella arrivano da tre chiamate diverse, ognuna sopra
          uno scheletro piu' basso del contenuto vero (statistiche +108px,
          confluenze +421): ognuna spingeva giu' quelle sotto, CLS 0,12 su un
          tablet. In produzione costano 0,18 / 0,49 / 0,39 s in parallelo,
          quindi aspettarle tutte vale circa la piu' lenta. I ricaricamenti
          dopo un filtro restano per sezione: partono da un clic. */}
      {primoCaricamento ? (
        <div key="scheletro" className="space-y-4" aria-busy="true">
          {/* Stesso ordine e stesse altezze della pagina vera (D-01): le
              confluenze chiuse sono una riga, l'efficacia sta in fondo. */}
          <CardSkeleton label="CONFLUENZE ATTIVE" rows={0} strongHeader className="h-[58px]" />
          <CardSkeleton label="SEGNALI" rows={12} strongHeader className="h-[640px]" />
          <CardSkeleton label="EFFICACIA DEI SEGNALI" rows={3} strongHeader className="h-[240px]" />
        </div>
      ) : (
      <div key="contenuto" className="space-y-4">
      {/* ⚠️ L'efficacia sta IN FONDO, sotto la tabella (D-01, A-37). Stava in
          cima e la tabella partiva a 1.335px su una finestra di 900 (misurato
          in produzione il 2026-11-17): la domanda di chi apre la pagina e'
          «cosa e' scattato», e l'efficacia — tutti gli esiti maturati, che
          cambiano in settimane — risponde a un'altra. */}
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

      {/* Il ticker filtrato ha il suo chip nella riga «Attivi» dei filtri:
          qui sotto ne stava una seconda copia (D-04). */}
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

      {!filters.solo_rilevanti && !filters.date_from && !filters.date_to && (
        <GiornateDiMercato
          giornate={giornate.data}
          comprime={comprime}
          onApri={(g) => { setPage(0); setFilters(filtriDellaGiornata(filters, g)); }}
          onMostraTutte={() => { setPage(0); setFilters({ ...filters, mostra_giornate: true }); }}
          onComprimi={() => { setPage(0); setFilters({ ...filters, mostra_giornate: undefined }); }}
        />
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
              // ⚠️ La lista parte dai titoli in posizione e fra i preferiti
              // (FA-136): vuota, deve dire che e' ristretta e come allargarla,
              // altrimenti si legge come «oggi non e' scattato niente».
              vuoto={filters.solo_rilevanti ? (
                <>
                  Nessun segnale sui tuoi titoli con questi filtri.{" "}
                  <button
                    type="button"
                    className="underline underline-offset-2 text-foreground"
                    onClick={() => {
                      setPage(0);
                      setFilters({ ...filters, solo_rilevanti: undefined });
                    }}
                  >
                    Mostra tutti i titoli
                  </button>
                </>
              ) : undefined}
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

      {/* Le statistiche di efficacia, spostate qui da Diagnostica (2026-09-16):
          tutti gli esiti maturati, non la pagina ne' i filtri della tabella. */}
      <SignalStatsSection />

      </div>
      )}

      <AlertDetailDialog alert={openDetail} onClose={() => setOpenDetail(null)} />
    </div>
  );
}
