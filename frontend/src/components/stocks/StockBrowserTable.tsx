import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import type { StockSortBy, SortDir } from "@/api/stocks";
import type { StockSearchItem } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { TableSearchInput } from "@/components/ui/table-search-input";
import { useMarketSummary } from "@/hooks/useMarketSummary";
import { RISK_LABEL, RISK_TONE, scoreColor } from "@/lib/scoreMeta";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

/** Sort options offered in the mobile card view (no clickable column
 *  headers there). Mirrors the desktop table's sortable columns. */
const MOBILE_SORT_OPTIONS: { key: TableSortKey; label: string }[] = [
  { key: "ticker", label: "Ticker" },
  { key: "name", label: "Nome" },
  { key: "composite", label: "Score" },
  { key: "change_pct", label: "Δ%" },
  { key: "market_cap", label: "Mkt Cap" },
  { key: "sector", label: "Settore" },
  { key: "industry", label: "Industry" },
  { key: "exchange", label: "Exchange" },
];

/** All sortable columns the table renders. `change_pct` is client-side only
 *  (Δ% comes from the market-stats snapshot, not the Stock table) — the
 *  others map to `StockSortBy` and are sorted server-side across the full
 *  result set. */
export type TableSortKey = StockSortBy | "change_pct";

interface Props {
  items: StockSearchItem[];
  sortBy: TableSortKey;
  sortDir: SortDir;
  /** Called when the user clicks a sortable header. The parent decides
   *  whether to flip direction, switch column, or push to URL. */
  onSortChange: (key: TableSortKey) => void;
  /** Inline ticker/name filter — folded into the Ticker column header
   *  so the user filters the table from the same row that labels it.
   *  Replaces the standalone search field that used to live in the
   *  filters card. */
  q: string;
  onQueryChange: (v: string) => void;
}

function fmtMc(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

// Currency symbols for the "Prezzo" column. Falls back to the ISO code
// when a symbol isn't widely recognized — better to show "HKD 18.40"
// than "? 18.40" or just a number.
const CURRENCY_SYMBOL: Record<string, string> = {
  USD: "$", EUR: "€", GBP: "£", JPY: "¥", CHF: "CHF",
  CAD: "C$", AUD: "A$", HKD: "HK$", CNY: "¥", KRW: "₩",
};

function fmtClose(v: number | null | undefined, currency: string | undefined): string {
  if (v == null) return "—";
  const sym = currency ? CURRENCY_SYMBOL[currency] ?? `${currency} ` : "";
  // Penny stocks need 4 decimals, the rest 2. Avoids hiding a 0.0234
  // close behind a "0.02" rounding.
  const digits = v < 1 ? 4 : 2;
  return `${sym}${v.toFixed(digits)}`;
}

interface HeaderProps {
  column: TableSortKey;
  label: string;
  align?: "left" | "right";
  sortBy: TableSortKey;
  sortDir: SortDir;
  onClick: (col: TableSortKey) => void;
  /** Some columns (change_pct) only sort the current page. We surface this
   *  in the title attribute so power users know why their Δ% sort doesn't
   *  walk the universe. */
  clientOnly?: boolean;
}

function SortableHeader({
  column, label, align = "left", sortBy, sortDir, onClick, clientOnly,
}: HeaderProps) {
  const active = sortBy === column;
  return (
    <th className={cn("px-3 py-1.5 text-base", align === "right" ? "text-right" : "text-left")}>
      <button
        type="button"
        onClick={() => onClick(column)}
        title={clientOnly ? "Ordina la pagina corrente (lato client)" : undefined}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground transition-colors uppercase tracking-wide font-semibold",
          active && "text-foreground",
          align === "right" && "ml-auto",
        )}
      >
        <span>{label}</span>
        {active && sortDir === "desc" && <ArrowDown className="h-3 w-3" />}
        {active && sortDir === "asc" && <ArrowUp className="h-3 w-3" />}
        {!active && <ArrowUpDown className="h-3 w-3 opacity-30" />}
      </button>
    </th>
  );
}

export function StockBrowserTable({ items, sortBy, sortDir, onSortChange, q, onQueryChange }: Props) {
  const market = useMarketSummary();
  // Build ticker -> {change_pct, last_close, currency} maps from the
  // snapshot's treemap data. Single iteration produces all three so
  // every row's Prezzo + Δ% cells render without a per-ticker lookup.
  const { changeByTicker, closeByTicker, currencyByTicker } = useMemo(() => {
    const ch = new Map<string, number>();
    const cl = new Map<string, number>();
    const cc = new Map<string, string>();
    const treemap = market.data?.treemap ?? [];
    for (const leaf of treemap) {
      ch.set(leaf.ticker, leaf.change_pct);
      if (leaf.last_close != null) cl.set(leaf.ticker, leaf.last_close);
      if (leaf.currency) cc.set(leaf.ticker, leaf.currency);
    }
    return { changeByTicker: ch, closeByTicker: cl, currencyByTicker: cc };
  }, [market.data]);

  // change_pct is sorted client-side over the current page. Server-sorted
  // columns arrive already ordered, so we leave `items` untouched.
  const displayItems = useMemo(() => {
    if (sortBy !== "change_pct") return items;
    const dir = sortDir;
    return [...items].sort((a, b) => {
      const av = changeByTicker.get(a.stock.ticker) ?? -Infinity;
      const bv = changeByTicker.get(b.stock.ticker) ?? -Infinity;
      if (av < bv) return dir === "asc" ? -1 : 1;
      if (av > bv) return dir === "asc" ? 1 : -1;
      return 0;
    });
  }, [items, sortBy, sortDir, changeByTicker]);

  // The empty-state used to early-return a different layout, but that
  // hid the Ticker-header search input — making it impossible to
  // change the query that's filtering results down to zero. Now we
  // always render the table chrome (header + input) and show the
  // empty state INSIDE the tbody, same fix as the calendar earnings
  // table.
  return (
    <Card>
      <CardContent className="p-0">
        {/* ─── Mobile: stacked cards (no horizontal scroll on a phone).
            The desktop table's clickable column headers don't exist
            here, so search + sort move into a dedicated toolbar. ─── */}
        <div className="md:hidden">
          <div className="flex flex-col gap-2 border-b p-3">
            <TableSearchInput
              value={q}
              onChange={onQueryChange}
              placeholder="cerca ticker o nome…"
              ariaLabel="Filtra per ticker o nome"
              className="w-full"
            />
            <div className="flex items-center gap-2">
              <Select
                value={sortBy}
                onValueChange={(v) => onSortChange(v as TableSortKey)}
              >
                <SelectTrigger className="h-8 flex-1 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MOBILE_SORT_OPTIONS.map((o) => (
                    <SelectItem key={o.key} value={o.key}>
                      Ordina: {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 shrink-0"
                aria-label={`Direzione ordinamento: ${sortDir === "asc" ? "crescente" : "decrescente"}`}
                onClick={() => onSortChange(sortBy)}
              >
                {sortDir === "asc" ? (
                  <ArrowUp className="h-4 w-4" />
                ) : (
                  <ArrowDown className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
          {displayItems.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              Nessuno stock trovato.
              {q.trim()
                ? ` Nessun risultato per "${q}".`
                : " Prova a rimuovere qualche filtro."}
            </div>
          ) : (
            <ul className="divide-y divide-border/50">
              {displayItems.map((item) => {
                const s = item.stock;
                const change = changeByTicker.get(s.ticker);
                const flag = getStockFlagCode(s.country, s.ticker);
                const changeColor = change == null
                  ? "text-muted-foreground"
                  : change > 0 ? "text-green-600 dark:text-green-400"
                  : change < 0 ? "text-red-600 dark:text-red-400"
                  : "";
                const compositeCls = item.score.composite != null
                  ? scoreColor(item.score.composite)
                  : "text-muted-foreground";
                return (
                  <li key={s.id}>
                    <Link
                      to={`/stocks/${encodeURIComponent(s.ticker)}`}
                      className="block px-3 py-2.5 hover:bg-muted/40 transition-colors"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <StockLogo ticker={s.ticker} size="sm" />
                        <span className="font-semibold shrink-0">{s.ticker}</span>
                        <span className="text-sm text-muted-foreground truncate min-w-0 flex-1">
                          {s.name}
                        </span>
                        <span className={cn("text-base font-bold tabular-nums shrink-0", compositeCls)}>
                          {item.score.composite != null ? item.score.composite.toFixed(1) : "—"}
                        </span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs tabular-nums">
                        <span className={changeColor}>
                          Δ {change == null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                        </span>
                        <span className="text-muted-foreground">
                          {fmtClose(closeByTicker.get(s.ticker), currencyByTicker.get(s.ticker) ?? s.currency ?? undefined)}
                        </span>
                        <span className="text-muted-foreground">
                          MC {fmtMc(s.market_cap)}
                        </span>
                        <span className="inline-flex items-center gap-1 text-muted-foreground">
                          {flag && (
                            <img
                              src={`/flags/${flag}.svg`}
                              alt={s.country ?? ""}
                              width={14} height={10}
                              style={{ width: "14px", height: "10px", objectFit: "cover" }}
                              className="rounded-[1px] shadow-sm"
                            />
                          )}
                          {s.exchange}
                        </span>
                        {item.score.risk_tier && (
                          <span
                            className={cn(
                              "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider",
                              RISK_TONE[item.score.risk_tier],
                            )}
                          >
                            {RISK_LABEL[item.score.risk_tier]}
                          </span>
                        )}
                      </div>
                      {s.sector && (
                        <div className="mt-1 text-xs text-muted-foreground truncate">
                          {s.sector}
                          {s.industry ? ` · ${s.industry}` : ""}
                        </div>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* ─── Desktop/tablet: the full sortable table (scrolls
            horizontally inside its own container if it overflows). ─── */}
        <div className="hidden md:block overflow-x-auto">
          {/* Per user spec: rows at 0.875rem (text-sm), headers at 1rem
              (text-base via SortableHeader). Set the table root to
              text-sm so every body cell inherits without per-cell
              overrides; the per-cell `text-xs` on meta columns
              (exchange/sector/industry/Risk-fallback) was bumped to
              inherit too. */}
          <table className="w-full text-sm tabular-nums">
            <thead className="bg-muted/30 text-muted-foreground border-b">
              <tr>
                {/* Ticker column: sortable label + the inline ticker/name
                    search input. Replaces the previously-removed text
                    search field in the filters card. The input filters
                    server-side via the `q` URL param. */}
                <th className="px-3 py-1.5 text-left text-base">
                  <div className="flex items-center gap-2 min-w-0">
                    <button
                      type="button"
                      onClick={() => onSortChange("ticker")}
                      className={cn(
                        "inline-flex items-center gap-1 hover:text-foreground transition-colors uppercase tracking-wide font-semibold",
                        sortBy === "ticker" && "text-foreground",
                      )}
                    >
                      <span>Ticker</span>
                      {sortBy === "ticker" && sortDir === "desc" && <ArrowDown className="h-3 w-3" />}
                      {sortBy === "ticker" && sortDir === "asc" && <ArrowUp className="h-3 w-3" />}
                      {sortBy !== "ticker" && <ArrowUpDown className="h-3 w-3 opacity-30" />}
                    </button>
                    <TableSearchInput
                      value={q}
                      onChange={onQueryChange}
                      placeholder="cerca ticker o nome…"
                      ariaLabel="Filtra per ticker o nome"
                      className="flex-1 max-w-[260px]"
                    />
                  </div>
                </th>
                <SortableHeader column="name" label="Nome" sortBy={sortBy} sortDir={sortDir} onClick={onSortChange} />
                <SortableHeader column="exchange" label="Exchange" sortBy={sortBy} sortDir={sortDir} onClick={onSortChange} />
                <SortableHeader column="sector" label="Settore" sortBy={sortBy} sortDir={sortDir} onClick={onSortChange} />
                <SortableHeader column="industry" label="Industry" sortBy={sortBy} sortDir={sortDir} onClick={onSortChange} />
                {/* Prezzo column: last close in listing currency, sourced
                    from the market snapshot (treemap.last_close). Not
                    sortable — the snapshot doesn't ship absolute prices
                    in a comparable way (USD 200 vs JPY 18000). */}
                <th className="px-3 py-1.5 text-right text-base">
                  <span className="uppercase tracking-wide font-semibold">Prezzo</span>
                </th>
                <SortableHeader column="market_cap" label="Mkt Cap" align="right" sortBy={sortBy} sortDir={sortDir} onClick={onSortChange} />
                <SortableHeader column="change_pct" label="Δ%" align="right" sortBy={sortBy} sortDir={sortDir} onClick={onSortChange} clientOnly />
                <SortableHeader column="composite" label="Score" align="right" sortBy={sortBy} sortDir={sortDir} onClick={onSortChange} />
                <th className="px-3 py-1.5 text-base uppercase tracking-wide font-semibold">Risk</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && (
                <tr>
                  <td
                    colSpan={10}
                    className="px-4 py-10 text-center text-muted-foreground"
                  >
                    Nessuno stock trovato.
                    {q.trim()
                      ? ` Nessun risultato per "${q}".`
                      : " Prova a rimuovere qualche filtro."}
                  </td>
                </tr>
              )}
              {displayItems.map((item) => {
                const s = item.stock;
                const change = changeByTicker.get(s.ticker);
                const flag = getStockFlagCode(s.country, s.ticker);
                const changeColor = change == null
                  ? "text-muted-foreground"
                  : change > 0 ? "text-green-600 dark:text-green-400"
                  : change < 0 ? "text-red-600 dark:text-red-400"
                  : "";
                const compositeCls = item.score.composite != null
                  ? scoreColor(item.score.composite)
                  : "text-muted-foreground";
                return (
                  <tr
                    key={s.id}
                    className="border-b border-border/50 hover:bg-muted/40 transition-colors"
                  >
                    <td className="px-3 py-1.5">
                      {/* Logo size bumped from xs (28px) → sm (36px) per
                          user feedback ("aggiungi le icone delle stock")
                          + monogram fallback (in StockLogo) for HK/JP/KR
                          tickers the CDN doesn't carry, so EVERY row now
                          shows a logo. */}
                      <Link to={`/stocks/${encodeURIComponent(s.ticker)}`} className="inline-flex items-center gap-2 font-semibold hover:underline">
                        <StockLogo ticker={s.ticker} size="sm" />
                        <span>{s.ticker}</span>
                      </Link>
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground truncate max-w-[280px]">
                      <Link to={`/stocks/${encodeURIComponent(s.ticker)}`} className="hover:underline">
                        {s.name}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5">
                      <span className="inline-flex items-center gap-1.5">
                        {flag && (
                          <img
                            src={`/flags/${flag}.svg`}
                            alt={s.country ?? ""}
                            width={16} height={11}
                            style={{ width: "16px", height: "11px", objectFit: "cover" }}
                            className="rounded-[1px] shadow-sm"
                          />
                        )}
                        <span className="text-muted-foreground">{s.exchange}</span>
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground truncate max-w-[140px]">
                      {s.sector ?? "—"}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground truncate max-w-[160px]" title={s.industry ?? ""}>
                      {s.industry ?? "—"}
                    </td>
                    <td className="px-3 py-1.5 text-right font-semibold">
                      {fmtClose(closeByTicker.get(s.ticker), currencyByTicker.get(s.ticker) ?? s.currency ?? undefined)}
                    </td>
                    <td className="px-3 py-1.5 text-right">{fmtMc(s.market_cap)}</td>
                    <td className={cn("px-3 py-1.5 text-right", changeColor)}>
                      {change == null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                    </td>
                    <td className={cn("px-3 py-1.5 text-right font-bold", compositeCls)}>
                      {item.score.composite != null ? item.score.composite.toFixed(1) : "—"}
                    </td>
                    <td className="px-3 py-1.5">
                      {item.score.risk_tier ? (
                        <span
                          className={cn(
                            "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider",
                            RISK_TONE[item.score.risk_tier],
                          )}
                        >
                          {RISK_LABEL[item.score.risk_tier]}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
