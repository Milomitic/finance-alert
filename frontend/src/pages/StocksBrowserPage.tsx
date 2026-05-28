import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { SortDir, StockSortBy } from "@/api/stocks";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
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

/** Allowed page sizes shown in the dropdown. 25 / 50 / 100 / 200. */
const PAGE_SIZES = [25, 50, 100, 200] as const;
type PageSize = (typeof PAGE_SIZES)[number];

const VALID_SORT_BY = new Set<StockSortBy>([
  "ticker", "name", "market_cap", "sector", "industry", "exchange", "composite",
]);

const VALID_RISK = new Set(["conservative", "moderate", "aggressive"] as const);

function parseListParam(searchParams: URLSearchParams, name: string): string[] {
  return searchParams.getAll(name);
}

function parseRiskList(searchParams: URLSearchParams): FiltersState["riskTiers"] {
  return searchParams
    .getAll("risk")
    .filter((v): v is FiltersState["riskTiers"][number] =>
      VALID_RISK.has(v as FiltersState["riskTiers"][number]),
    );
}

function parseNullableScore(raw: string | null): number | null {
  if (raw == null || raw === "") return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0 || n > 100) return null;
  return n;
}

// Keep backward-compat alias used below
const parseMinScore = parseNullableScore;

function parseSortBy(raw: string | null): TableSortKey {
  if (raw === "change_pct") return "change_pct";
  if (raw && VALID_SORT_BY.has(raw as StockSortBy)) return raw as StockSortBy;
  return "ticker";
}

function parseSortDir(raw: string | null): SortDir {
  return raw === "desc" ? "desc" : "asc";
}

function parsePageSize(raw: string | null): PageSize {
  const n = Number(raw);
  if (PAGE_SIZES.includes(n as PageSize)) return n as PageSize;
  return 50;
}

/** Inline pagination strip rendered above AND below the table. Same shape
 *  in both spots so it feels symmetric. Hidden when there's only one page. */
function PaginationStrip({
  page, pageSize, total, hasMore, onPrev, onNext, showCount,
}: {
  page: number;
  pageSize: number;
  total: number;
  hasMore: boolean;
  onPrev: () => void;
  onNext: () => void;
  /** Whether to show the "X-Y di Z" range (omit on the bottom strip if you
   *  prefer a cleaner footer; we show on both for clarity). */
  showCount?: boolean;
}) {
  if (page === 0 && !hasMore) return null;
  const showingFrom = total > 0 ? page * pageSize + 1 : 0;
  const showingTo = Math.min(total, page * pageSize + pageSize);
  return (
    <div className="flex items-center justify-between gap-2 px-1">
      {showCount ? (
        <span className="text-xs text-muted-foreground tabular-nums">
          {showingFrom}–{showingTo} di {total.toLocaleString()}
        </span>
      ) : (
        <span />
      )}
      <div className="flex gap-2">
        <Button
          size="sm" variant="outline" disabled={page === 0}
          onClick={onPrev}
        >
          ← Precedente
        </Button>
        <Button
          size="sm" variant="outline" disabled={!hasMore}
          onClick={onNext}
        >
          Successiva →
        </Button>
      </div>
    </div>
  );
}

export default function StocksBrowserPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<PageSize>(() =>
    parsePageSize(searchParams.get("page_size")),
  );

  // Inline ticker/name search query. Lives separate from FiltersState
  // because the FiltersState contract intentionally has no q field
  // (the navbar global search used to cover this case). Now folded
  // into the Ticker column header — shared shape with the calendar
  // earnings table and the alerts page.
  const [q, setQ] = useState<string>(() => searchParams.get("q") ?? "");

  // Load initial state from URL once
  const [state, setState] = useState<FiltersState>(() => ({
    indexCodes: parseListParam(searchParams, "index"),
    sectors: parseListParam(searchParams, "sector"),
    industries: parseListParam(searchParams, "industry"),
    exchanges: parseListParam(searchParams, "exchange"),
    countries: parseListParam(searchParams, "country"),
    riskTiers: parseRiskList(searchParams),
    minScore: parseMinScore(searchParams.get("min_score")),
    scoreMax: parseNullableScore(searchParams.get("score_max")),
    profitabilityMin: parseNullableScore(searchParams.get("profitability_min")),
    sustainabilityMin: parseNullableScore(searchParams.get("sustainability_min")),
    growthMin: parseNullableScore(searchParams.get("growth_min")),
    valueMin: parseNullableScore(searchParams.get("value_min")),
    sentimentMin: parseNullableScore(searchParams.get("sentiment_min")),
    techMin: parseNullableScore(searchParams.get("tech_min")),
    postures: parseListParam(searchParams, "posture").filter((v) => ["Forte", "Neutro", "Debole"].includes(v)),
  }));
  const [sortBy, setSortBy] = useState<TableSortKey>(() =>
    parseSortBy(searchParams.get("sort_by")),
  );
  const [sortDir, setSortDir] = useState<SortDir>(() =>
    parseSortDir(searchParams.get("sort_dir")),
  );

  // Persist state to URL when it changes (for shareable links). Pagination
  // resets on every filter / sort / page-size change since the new view
  // would otherwise overshoot the result set.
  useEffect(() => {
    const sp = new URLSearchParams();
    if (q.trim()) sp.set("q", q.trim());
    state.indexCodes.forEach((v) => sp.append("index", v));
    state.sectors.forEach((v) => sp.append("sector", v));
    state.industries.forEach((v) => sp.append("industry", v));
    state.exchanges.forEach((v) => sp.append("exchange", v));
    state.countries.forEach((v) => sp.append("country", v));
    state.riskTiers.forEach((v) => sp.append("risk", v));
    if (state.minScore != null) sp.set("min_score", String(state.minScore));
    if (state.scoreMax != null) sp.set("score_max", String(state.scoreMax));
    if (state.profitabilityMin != null) sp.set("profitability_min", String(state.profitabilityMin));
    if (state.sustainabilityMin != null) sp.set("sustainability_min", String(state.sustainabilityMin));
    if (state.growthMin != null) sp.set("growth_min", String(state.growthMin));
    if (state.valueMin != null) sp.set("value_min", String(state.valueMin));
    if (state.sentimentMin != null) sp.set("sentiment_min", String(state.sentimentMin));
    if (state.techMin != null) sp.set("tech_min", String(state.techMin));
    state.postures.forEach((v) => sp.append("posture", v));
    if (sortBy !== "ticker") sp.set("sort_by", sortBy);
    if (sortDir !== "asc") sp.set("sort_dir", sortDir);
    if (pageSize !== 50) sp.set("page_size", String(pageSize));
    setSearchParams(sp, { replace: true });
    setPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, state, sortBy, sortDir, pageSize]);

  // Click handler: same column flips direction; new column picks a sensible
  // default (asc for text columns, desc for numeric) and resets paging.
  const handleSortChange = (col: TableSortKey) => {
    if (col === sortBy) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(col);
      // Numeric/score columns default to descending (highest first); text
      // columns default to ascending alphabetical.
      const isText = col === "ticker" || col === "name" || col === "sector" || col === "industry" || col === "exchange";
      setSortDir(isText ? "asc" : "desc");
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
    q: q.trim() || undefined,
    index: state.indexCodes.length > 0 ? state.indexCodes : undefined,
    sector: state.sectors.length > 0 ? state.sectors : undefined,
    industry: state.industries.length > 0 ? state.industries : undefined,
    exchange: state.exchanges.length > 0 ? state.exchanges : undefined,
    country: state.countries.length > 0 ? state.countries : undefined,
    risk: state.riskTiers.length > 0 ? state.riskTiers : undefined,
    min_score: state.minScore ?? undefined,
    score_max: state.scoreMax ?? undefined,
    profitability_min: state.profitabilityMin ?? undefined,
    sustainability_min: state.sustainabilityMin ?? undefined,
    growth_min: state.growthMin ?? undefined,
    value_min: state.valueMin ?? undefined,
    sentiment_min: state.sentimentMin ?? undefined,
    tech_min: state.techMin ?? undefined,
    posture: state.postures.length > 0 ? state.postures : undefined,
    sort_by: serverSortBy,
    sort_dir: serverSortDir,
    limit: pageSize,
    offset: page * pageSize,
  });

  const items = searchQ.data?.items ?? [];
  const total = searchQ.data?.total ?? 0;
  const hasMore = searchQ.data?.has_more ?? false;
  const totalIndices = filtersQ.data?.indices.length ?? 0;
  const totalCountries = filtersQ.data?.countries.length ?? 0;

  return (
    <div className="space-y-4">
      {/* Header summary — "Screener" label per user request; the route
          stays /stocks for URL stability + back-compat with shared links. */}
      <Card>
        <CardContent className="p-4 flex items-center gap-4">
          <div>
            <h2 className="text-2xl font-bold">Screener</h2>
            <p className="text-sm text-muted-foreground">
              {total > 0 ? `${total.toLocaleString()} stock` : "—"} con i filtri attuali ·{" "}
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

      {/* Toolbar above the table: page-size + top pagination. The page-size
          dropdown sits on the left so the user can choose density before
          paging; prev/next on the right matches the bottom strip's layout. */}
      <div className="flex items-center justify-between gap-2 px-1 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Righe per pagina</span>
          <Select
            value={String(pageSize)}
            onValueChange={(v) => setPageSize(Number(v) as PageSize)}
          >
            <SelectTrigger className="h-8 w-[80px] text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZES.map((n) => (
                <SelectItem key={n} value={String(n)}>{n}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <PaginationStrip
          page={page}
          pageSize={pageSize}
          total={total}
          hasMore={hasMore}
          onPrev={() => setPage((p) => Math.max(0, p - 1))}
          onNext={() => setPage((p) => p + 1)}
          showCount
        />
      </div>

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
            q={q}
            onQueryChange={setQ}
          />
          {/* Bottom pagination — symmetric with the toolbar's. Shows count
              again since this is what the user sees after scrolling through
              the table. */}
          <PaginationStrip
            page={page}
            pageSize={pageSize}
            total={total}
            hasMore={hasMore}
            onPrev={() => setPage((p) => Math.max(0, p - 1))}
            onNext={() => setPage((p) => p + 1)}
            showCount
          />
        </>
      )}
    </div>
  );
}
