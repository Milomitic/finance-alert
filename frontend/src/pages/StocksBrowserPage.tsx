import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useStockFilters, useStockSearch } from "@/hooks/useStockSearch";
import { IndexPanoramaCard } from "@/components/stocks/IndexPanoramaCard";
import { StockBrowserTable } from "@/components/stocks/StockBrowserTable";
import { StockSearchBar, type SearchState } from "@/components/stocks/StockSearchBar";
import { useMarketSummary } from "@/hooks/useMarketSummary";

const PAGE_SIZE = 50;

function parseListParam(searchParams: URLSearchParams, name: string): string[] {
  return searchParams.getAll(name);
}

export default function StocksBrowserPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(0);

  // Load initial state from URL once
  const [state, setState] = useState<SearchState>(() => ({
    q: searchParams.get("q") ?? "",
    indexCodes: parseListParam(searchParams, "index"),
    sectors: parseListParam(searchParams, "sector"),
    exchanges: parseListParam(searchParams, "exchange"),
    countries: parseListParam(searchParams, "country"),
  }));

  // Persist state to URL when it changes (for shareable links)
  useEffect(() => {
    const sp = new URLSearchParams();
    if (state.q) sp.set("q", state.q);
    state.indexCodes.forEach((v) => sp.append("index", v));
    state.sectors.forEach((v) => sp.append("sector", v));
    state.exchanges.forEach((v) => sp.append("exchange", v));
    state.countries.forEach((v) => sp.append("country", v));
    setSearchParams(sp, { replace: true });
    setPage(0);   // reset pagination on filter change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  const market = useMarketSummary();
  const singleIndexCode = state.indexCodes.length === 1 ? state.indexCodes[0] : null;
  const singleIndexBreadth = singleIndexCode
    ? (market.data?.by_index ?? []).find((i) => i.code === singleIndexCode) ?? null
    : null;

  const filtersQ = useStockFilters();
  const searchQ = useStockSearch({
    q: state.q || undefined,
    index: state.indexCodes.length > 0 ? state.indexCodes : undefined,
    sector: state.sectors.length > 0 ? state.sectors : undefined,
    exchange: state.exchanges.length > 0 ? state.exchanges : undefined,
    country: state.countries.length > 0 ? state.countries : undefined,
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

      {/* Search + filters */}
      <Card>
        <CardContent className="p-4">
          <StockSearchBar
            state={state}
            onChange={setState}
            filters={filtersQ.data}
          />
        </CardContent>
      </Card>

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
          <StockBrowserTable items={items} />
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
