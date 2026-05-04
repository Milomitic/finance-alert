import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { SortDir, StockSortBy } from "@/api/stocks";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useStockFilters, useStockSearch } from "@/hooks/useStockSearch";
import { IndexPanoramaCard } from "@/components/stocks/IndexPanoramaCard";
import {
  StockBrowserTable,
  type TableSortKey,
} from "@/components/stocks/StockBrowserTable";
import {
  StockFiltersCard,
  type FiltersState,
} from "@/components/stocks/StockFiltersCard";
import { useMarketSummary } from "@/hooks/useMarketSummary";

const PAGE_SIZE = 50;

const VALID_SORT_BY = new Set<StockSortBy>([
  "ticker", "name", "market_cap", "sector", "exchange",
]);

function parseListParam(searchParams: URLSearchParams, name: string): string[] {
  return searchParams.getAll(name);
}

function parseSortBy(raw: string | null): TableSortKey {
  if (raw === "change_pct") return "change_pct";
  if (raw && VALID_SORT_BY.has(raw as StockSortBy)) return raw as StockSortBy;
  return "ticker";
}

function parseSortDir(raw: string | null): SortDir {
  return raw === "desc" ? "desc" : "asc";
}

export default function StocksBrowserPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(0);

  // Load initial state from URL once
  const [state, setState] = useState<FiltersState>(() => ({
    indexCodes: parseListParam(searchParams, "index"),
    sectors: parseListParam(searchParams, "sector"),
    exchanges: parseListParam(searchParams, "exchange"),
    countries: parseListParam(searchParams, "country"),
  }));
  const [sortBy, setSortBy] = useState<TableSortKey>(() =>
    parseSortBy(searchParams.get("sort_by")),
  );
  const [sortDir, setSortDir] = useState<SortDir>(() =>
    parseSortDir(searchParams.get("sort_dir")),
  );

  // Persist state to URL when it changes (for shareable links)
  useEffect(() => {
    const sp = new URLSearchParams();
    state.indexCodes.forEach((v) => sp.append("index", v));
    state.sectors.forEach((v) => sp.append("sector", v));
    state.exchanges.forEach((v) => sp.append("exchange", v));
    state.countries.forEach((v) => sp.append("country", v));
    if (sortBy !== "ticker") sp.set("sort_by", sortBy);
    if (sortDir !== "asc") sp.set("sort_dir", sortDir);
    setSearchParams(sp, { replace: true });
    setPage(0); // reset pagination on filter / sort change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, sortBy, sortDir]);

  // Click handler: same column flips direction; new column picks a sensible
  // default (asc for text columns, desc for numeric) and resets paging.
  const handleSortChange = (col: TableSortKey) => {
    if (col === sortBy) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(col);
      setSortDir(col === "ticker" || col === "name" || col === "sector" || col === "exchange"
        ? "asc"
        : "desc");
    }
  };

  const market = useMarketSummary();
  const singleIndexCode = state.indexCodes.length === 1 ? state.indexCodes[0] : null;
  const singleIndexBreadth = singleIndexCode
    ? (market.data?.by_index ?? []).find((i) => i.code === singleIndexCode) ?? null
    : null;

  const filtersQ = useStockFilters();
  // change_pct isn't a server-sortable column; when the user picks it we
  // ask the server for ticker-asc and let the table re-order the page
  // client-side. This is documented in the table component.
  const serverSortBy: StockSortBy = sortBy === "change_pct" ? "ticker" : sortBy;
  const serverSortDir: SortDir = sortBy === "change_pct" ? "asc" : sortDir;
  const searchQ = useStockSearch({
    index: state.indexCodes.length > 0 ? state.indexCodes : undefined,
    sector: state.sectors.length > 0 ? state.sectors : undefined,
    exchange: state.exchanges.length > 0 ? state.exchanges : undefined,
    country: state.countries.length > 0 ? state.countries : undefined,
    sort_by: serverSortBy,
    sort_dir: serverSortDir,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const items = searchQ.data?.items ?? [];
  const total = searchQ.data?.total ?? 0;
  const hasMore = searchQ.data?.has_more ?? false;
  const showingFrom = items.length > 0 ? page * PAGE_SIZE + 1 : 0;
  const showingTo = page * PAGE_SIZE + items.length;
  const totalIndices = filtersQ.data?.indices.length ?? 0;
  const totalCountries = filtersQ.data?.countries.length ?? 0;

  return (
    <div className="space-y-4">
      {/* Header summary */}
      <Card>
        <CardContent className="p-4 flex items-center gap-4">
          <div>
            <h2 className="text-2xl font-bold">Universe browser</h2>
            <p className="text-sm text-muted-foreground">
              {total > 0 ? `${total.toLocaleString()} stock` : "—"} monitorati ·{" "}
              {totalIndices} indici · {totalCountries} paesi
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Filters */}
      <StockFiltersCard
        state={state}
        onChange={setState}
        filters={filtersQ.data}
      />

      {/* Index panorama header (shown when exactly 1 index is selected) */}
      {singleIndexBreadth && (
        <IndexPanoramaCard data={singleIndexBreadth} />
      )}

      {/* Results */}
      {searchQ.isLoading && !searchQ.data ? (
        <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">Caricamento…</CardContent></Card>
      ) : searchQ.isError ? (
        <Card><CardContent className="p-8 text-center text-sm text-destructive">Errore nel caricamento</CardContent></Card>
      ) : (
        <>
          <StockBrowserTable
            items={items}
            sortBy={sortBy}
            sortDir={sortDir}
            onSortChange={handleSortChange}
          />
          {/* Pagination */}
          {(page > 0 || hasMore) && (
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                {showingFrom}–{showingTo} di {total.toLocaleString()}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm" variant="outline" disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  ← Precedente
                </Button>
                <Button
                  size="sm" variant="outline" disabled={!hasMore}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Successiva →
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
