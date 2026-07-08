import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { SearchParams, SortDir, StockSortBy } from "@/api/stocks";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ColumnVisibilityButton,
} from "@/components/ui/column-visibility-menu";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  useColumnVisibility, type ColumnDef,
} from "@/hooks/useColumnVisibility";
import { useStockFilters, useStockSearch } from "@/hooks/useStockSearch";
import { ExportCsvButton } from "@/components/stocks/ExportCsvButton";
import { IndexPanoramaCard } from "@/components/stocks/IndexPanoramaCard";
import {
  SCREENER_COLS,
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
  "profitability", "sustainability", "growth", "value", "sentiment",
  "tech_composite", "tech_trend", "tech_momentum", "tech_structure",
  "tech_volume", "tech_rel_strength",
  // Phase A: metrics-backed server-sortable columns.
  "price", "change_pct", "rsi14", "vol_ratio", "vol_today",
  // Espressione SQL: distanza % dal massimo 52w (SCR-2).
  "pct_off_high",
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

/** Parse an arbitrary nullable number (no 0-100 clamp). Used for the
 *  unbounded ranges: price, Δ% (can be negative), market cap, volume, RSI. */
function parseNullableNumber(raw: string | null): number | null {
  if (raw == null || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/** A URL bool param is "active" only when literally "true" (matches the
 *  serializer below). */
function parseBoolParam(raw: string | null): boolean {
  return raw === "true";
}

/** Signals recency window from the URL: the explicit `signals_within_days`
 *  param (1..90 int) wins; legacy `has_signals=true` links (pre-window)
 *  map to the backend default of 7 days; anything else = filter off. */
function parseSignalsWindow(searchParams: URLSearchParams): number | null {
  const raw = searchParams.get("signals_within_days");
  if (raw != null) {
    const n = Number(raw);
    if (Number.isInteger(n) && n >= 1 && n <= 90) return n;
  }
  return parseBoolParam(searchParams.get("has_signals")) ? 7 : null;
}

/** 1-based `page` URL param → 0-based internal index. Garbage/absent → 0. */
function parsePageParam(raw: string | null): number {
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 ? n - 1 : 0;
}

function parseSortBy(raw: string | null): TableSortKey {
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

/** Stale threshold for the metrics as-of hint: the EOD metrics are persisted
 *  once per scan (~daily), so anything older than ~26h means a skipped/failed
 *  scan and the screener's price/RSI/vol columns are a day behind. */
const METRICS_STALE_MS = 26 * 60 * 60 * 1000;

/** Muted "metriche al HH:MM" hint next to the table header — the shared
 *  as-of of every stock_metrics row (one computed_at per refresh). Turns
 *  amber when older than the stale threshold. Hidden when the backend has
 *  no metrics yet (fresh install / pre-scan). */
function MetricsAsOf({ iso }: { iso: string | null | undefined }) {
  if (!iso) return null;
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return null;
  const stale = Date.now() - dt.getTime() > METRICS_STALE_MS;
  const time = dt.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  const sameDay = dt.toDateString() === new Date().toDateString();
  const label = sameDay
    ? `metriche al ${time}`
    : `metriche al ${dt.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" })} ${time}`;
  return (
    <span
      className={stale
        ? "text-xs text-amber-600 dark:text-amber-400"
        : "text-xs text-muted-foreground"}
      title="Ultimo aggiornamento delle metriche EOD (persistite a fine scan)"
    >
      {label}
    </span>
  );
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
  // Page index (0-based) initialized from the URL so back-nav / shared links
  // land on the same page instead of silently resetting to page 1.
  const [page, setPage] = useState(() => parsePageParam(searchParams.get("page")));
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
    excludeEtf: parseBoolParam(searchParams.get("exclude_etf")),
    minScore: parseMinScore(searchParams.get("min_score")),
    scoreMax: parseNullableScore(searchParams.get("score_max")),
    profitabilityMin: parseNullableScore(searchParams.get("profitability_min")),
    sustainabilityMin: parseNullableScore(searchParams.get("sustainability_min")),
    growthMin: parseNullableScore(searchParams.get("growth_min")),
    valueMin: parseNullableScore(searchParams.get("value_min")),
    sentimentMin: parseNullableScore(searchParams.get("sentiment_min")),
    techMin: parseNullableScore(searchParams.get("tech_min")),
    postures: parseListParam(searchParams, "posture").filter((v) => ["Forte", "Neutro", "Debole"].includes(v)),
    marketCapMin: parseNullableNumber(searchParams.get("market_cap_min")),
    marketCapMax: parseNullableNumber(searchParams.get("market_cap_max")),
    rsiMin: parseNullableScore(searchParams.get("rsi_min")),
    rsiMax: parseNullableScore(searchParams.get("rsi_max")),
    aboveEma50: parseBoolParam(searchParams.get("above_ema50")),
    aboveEma200: parseBoolParam(searchParams.get("above_ema200")),
    near52wHigh: parseBoolParam(searchParams.get("near_52w_high")),
    near52wLow: parseBoolParam(searchParams.get("near_52w_low")),
    signalsWithinDays: parseSignalsWindow(searchParams),
    priceMin: parseNullableNumber(searchParams.get("price_min")),
    priceMax: parseNullableNumber(searchParams.get("price_max")),
    changeMin: parseNullableNumber(searchParams.get("change_min")),
    changeMax: parseNullableNumber(searchParams.get("change_max")),
    volSpike: parseBoolParam(searchParams.get("vol_spike")),
    volRatioMin: parseNullableNumber(searchParams.get("vol_ratio_min")),
    volumeMin: parseNullableNumber(searchParams.get("volume_min")),
  }));
  const [sortBy, setSortBy] = useState<TableSortKey>(() =>
    parseSortBy(searchParams.get("sort_by")),
  );
  const [sortDir, setSortDir] = useState<SortDir>(() =>
    parseSortDir(searchParams.get("sort_dir")),
  );

  // Pagination resets when filters / sort / page-size actually CHANGE (the
  // new view would otherwise overshoot the result set) — but NOT on mount,
  // or the page parsed from the URL would be clobbered on back-nav.
  const skipFirstReset = useRef(true);
  useEffect(() => {
    if (skipFirstReset.current) {
      skipFirstReset.current = false;
      return;
    }
    setPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, state, sortBy, sortDir, pageSize]);

  // Persist state to URL when it changes (for shareable links). The page
  // number is serialized too (1-based, omitted on page 1) so back-nav
  // restores the exact view.
  useEffect(() => {
    const sp = new URLSearchParams();
    if (q.trim()) sp.set("q", q.trim());
    state.indexCodes.forEach((v) => sp.append("index", v));
    state.sectors.forEach((v) => sp.append("sector", v));
    state.industries.forEach((v) => sp.append("industry", v));
    state.exchanges.forEach((v) => sp.append("exchange", v));
    state.countries.forEach((v) => sp.append("country", v));
    state.riskTiers.forEach((v) => sp.append("risk", v));
    if (state.excludeEtf) sp.set("exclude_etf", "true");
    if (state.minScore != null) sp.set("min_score", String(state.minScore));
    if (state.scoreMax != null) sp.set("score_max", String(state.scoreMax));
    if (state.profitabilityMin != null) sp.set("profitability_min", String(state.profitabilityMin));
    if (state.sustainabilityMin != null) sp.set("sustainability_min", String(state.sustainabilityMin));
    if (state.growthMin != null) sp.set("growth_min", String(state.growthMin));
    if (state.valueMin != null) sp.set("value_min", String(state.valueMin));
    if (state.sentimentMin != null) sp.set("sentiment_min", String(state.sentimentMin));
    if (state.techMin != null) sp.set("tech_min", String(state.techMin));
    state.postures.forEach((v) => sp.append("posture", v));
    if (state.marketCapMin != null) sp.set("market_cap_min", String(state.marketCapMin));
    if (state.marketCapMax != null) sp.set("market_cap_max", String(state.marketCapMax));
    if (state.rsiMin != null) sp.set("rsi_min", String(state.rsiMin));
    if (state.rsiMax != null) sp.set("rsi_max", String(state.rsiMax));
    if (state.aboveEma50) sp.set("above_ema50", "true");
    if (state.aboveEma200) sp.set("above_ema200", "true");
    if (state.near52wHigh) sp.set("near_52w_high", "true");
    if (state.near52wLow) sp.set("near_52w_low", "true");
    if (state.signalsWithinDays != null) {
      sp.set("has_signals", "true");
      sp.set("signals_within_days", String(state.signalsWithinDays));
    }
    if (state.priceMin != null) sp.set("price_min", String(state.priceMin));
    if (state.priceMax != null) sp.set("price_max", String(state.priceMax));
    if (state.changeMin != null) sp.set("change_min", String(state.changeMin));
    if (state.changeMax != null) sp.set("change_max", String(state.changeMax));
    if (state.volSpike) sp.set("vol_spike", "true");
    if (state.volRatioMin != null) sp.set("vol_ratio_min", String(state.volRatioMin));
    if (state.volumeMin != null) sp.set("volume_min", String(state.volumeMin));
    if (sortBy !== "ticker") sp.set("sort_by", sortBy);
    if (sortDir !== "asc") sp.set("sort_dir", sortDir);
    if (pageSize !== 50) sp.set("page_size", String(pageSize));
    if (page > 0) sp.set("page", String(page + 1));
    setSearchParams(sp, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, state, sortBy, sortDir, pageSize, page]);

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

  // Breadth-tile click handler. The tile already resolved toggle semantics
  // (it sends either the predicate patch or its cleared form), so we just
  // merge into state — the URL-mirror useEffect resets paging.
  const handleTileFilter = (patch: Partial<FiltersState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  };

  // Column show/hide for the desktop table — lifted here so the toolbar
  // "Colonne" button and the table's header right-click menu share ONE
  // persisted state (localStorage key "colvis:screener").
  const { isVisible: isColumnVisible, toggle: toggleColumn } = useColumnVisibility(
    "screener",
    SCREENER_COLS as unknown as ColumnDef[],
  );

  const market = useMarketSummary();
  const singleIndexCode = state.indexCodes.length === 1 ? state.indexCodes[0] : null;
  const singleIndexBreadth = singleIndexCode
    ? (market.data?.by_index ?? []).find((i) => i.code === singleIndexCode) ?? null
    : null;

  const filtersQ = useStockFilters();
  // As of Phase A every column the table sorts on (incl. change_pct) is
  // server-sortable via the stock_metrics join — no more client-side sort
  // hack. sortBy is a TableSortKey which is now a strict subset of
  // StockSortBy, so it forwards directly.
  // L'oggetto params è estratto in una costante perché lo condividono la
  // search della pagina E l'export CSV "tutti i filtrati" (che lo rilancia
  // con limit alto/offset 0) — un divario fra i due esporterebbe righe
  // diverse da quelle mostrate.
  const apiParams: SearchParams = {
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
    market_cap_min: state.marketCapMin ?? undefined,
    market_cap_max: state.marketCapMax ?? undefined,
    rsi_min: state.rsiMin ?? undefined,
    rsi_max: state.rsiMax ?? undefined,
    above_ema50: state.aboveEma50 || undefined,
    above_ema200: state.aboveEma200 || undefined,
    near_52w_high: state.near52wHigh || undefined,
    near_52w_low: state.near52wLow || undefined,
    has_signals: state.signalsWithinDays != null || undefined,
    signals_within_days: state.signalsWithinDays ?? undefined,
    price_min: state.priceMin ?? undefined,
    price_max: state.priceMax ?? undefined,
    change_min: state.changeMin ?? undefined,
    change_max: state.changeMax ?? undefined,
    vol_spike: state.volSpike || undefined,
    vol_ratio_min: state.volRatioMin ?? undefined,
    volume_min: state.volumeMin ?? undefined,
    exclude_etf: state.excludeEtf || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    limit: pageSize,
    offset: page * pageSize,
  };
  const searchQ = useStockSearch(apiParams);

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

      {/* Index panorama header (shown when exactly 1 index is selected).
          Its breadth tiles are clickable filter toggles wired to FiltersState. */}
      {singleIndexBreadth && (
        <IndexPanoramaCard
          data={singleIndexBreadth}
          filters={state}
          onTileFilter={handleTileFilter}
        />
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
          {/* Entry point visibile per mostrare/nascondere le colonne — il
              right-click sull'header resta, ma da solo era inscopribile. */}
          <ColumnVisibilityButton
            columns={SCREENER_COLS as unknown as ColumnDef[]}
            isVisible={isColumnVisible}
            toggle={toggleColumn}
          />
          {/* Export CSV: pagina corrente (dati in memoria) oppure tutti i
              filtrati (stesso apiParams, limit alto). Valori raw. */}
          <ExportCsvButton
            items={items}
            searchParams={apiParams}
            total={total}
            isColumnVisible={isColumnVisible}
          />
          <MetricsAsOf iso={searchQ.data?.metrics_computed_at} />
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
            isColumnVisible={isColumnVisible}
            onToggleColumn={toggleColumn}
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
