import { ArrowDown, ArrowUp, ArrowUpDown, Building2, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import type { SectorStockRow } from "@/hooks/useSectorDetail";
import { fmtMarketCap, fmtNum } from "@/lib/sectorFormat";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

/* Score→text-color for the DETAIL page's tables — a bolder palette
 * (green/red, semibold on the top tier) kept LOCAL on purpose: the
 * overview hub uses a softer emerald/rose map and the two pages never
 * render together, so sharing would shift this table's colors. Literal
 * class strings per the Tailwind-purger rule (CLAUDE.md). */
function scoreColor(score: number | null): string {
  if (score === null) return "text-muted-foreground";
  if (score >= 70) return "text-green-600 dark:text-green-400 font-semibold";
  if (score >= 50) return "text-foreground";
  if (score >= 30) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

function CountryFlag({ country, ticker }: { country: string | null; ticker: string }) {
  // Best-effort flag rendering — mirrors StockHeader's pattern. If the
  // helper can't resolve a code (e.g. exotic suffix), render a short
  // country-code chip instead of a missing image.
  const code = getStockFlagCode(country ?? null, ticker);
  if (!code) {
    return country ? (
      <span className="text-[10px] text-muted-foreground uppercase tracking-wider tabular-nums">
        {country}
      </span>
    ) : (
      <span className="text-muted-foreground/60">—</span>
    );
  }
  return (
    <img
      src={`/flags/${code}.svg`}
      alt={country ?? ""}
      width={18}
      height={12}
      style={{ width: "18px", height: "12px", objectFit: "cover" }}
      className="rounded-sm shadow-sm shrink-0"
      title={country ?? code.toUpperCase()}
      aria-hidden
    />
  );
}

function StockRow({ row }: { row: SectorStockRow }) {
  return (
    <tr className="hover:bg-muted/30 transition-colors">
      {/* Identity = logo + ticker (link) + name muted underneath. Same
          treatment as the dashboard's TopStocksTable so a user moving
          between the two surfaces sees identical row chrome. */}
      <td className="px-2 py-1.5 min-w-0">
        <Link
          to={`/stocks/${encodeURIComponent(row.ticker)}`}
          className="flex items-center gap-2 hover:underline min-w-0"
        >
          <StockIdentity ticker={row.ticker} name={row.name} />
        </Link>
      </td>
      <td className="px-2 py-1.5 whitespace-nowrap">
        <CountryFlag country={row.country} ticker={row.ticker} />
      </td>
      <td className={cn("px-2 py-1.5 text-right tabular-nums", scoreColor(row.composite))}>
        {fmtNum(row.composite, 0)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">{fmtNum(row.pe, 1)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{fmtNum(row.pb, 2)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{fmtNum(row.roe, 1, "%")}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {fmtNum(row.revenue_growth, 1, "%")}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {fmtNum(row.dividend_yield, 2, "%")}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {fmtMarketCap(row.market_cap)}
      </td>
    </tr>
  );
}

export function PicksCard({
  title,
  rows,
  accent,
}: {
  title: string;
  rows: SectorStockRow[];
  accent: "green" | "red";
}) {
  const accentTone =
    accent === "green"
      ? "text-emerald-700 dark:text-emerald-300"
      : "text-rose-700 dark:text-rose-300";
  const Icon = accent === "green" ? TrendingUp : TrendingDown;
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Icon}
          label={title}
          tone={accentTone}
          className="mb-3"
        />
        {rows.length === 0 ? (
          <div className="text-sm text-muted-foreground py-3">
            Dati insufficienti
          </div>
        ) : (
          <table className="w-full text-sm tabular-nums">
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker} className="hover:bg-muted/30">
                  {/* Same Identity treatment as the main table → logo +
                      ticker + name muted under it. Visual rhythm matches
                      the dashboard's TopMovers/TopPicks list rows. */}
                  <td className="px-2 py-1.5 min-w-0">
                    <Link
                      to={`/stocks/${encodeURIComponent(r.ticker)}`}
                      className="flex items-center gap-2 hover:underline min-w-0"
                    >
                      <StockIdentity ticker={r.ticker} name={r.name} />
                    </Link>
                  </td>
                  <td
                    className={cn(
                      "px-2 py-1.5 text-right tabular-nums font-semibold whitespace-nowrap",
                      scoreColor(r.composite),
                    )}
                  >
                    {fmtNum(r.composite, 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

/* ─── SortableStocksTable ────────────────────────────────────────────────── */
/* Client-side sortable variant of the main "Tutte le aziende" table.
 * State lives here (not lifted) — sort is a pure view concern and the
 * page never needs to read it back. Sort columns map to the SectorStockRow
 * field; the comparator handles null-last consistently for both numeric
 * and string columns.
 *
 * UX:
 *   - Click header → set sort key (default desc for numeric, asc for
 *     ticker/country); same key → flip direction.
 *   - Active column shows an up/down chevron; inactive columns show a
 *     dim two-way arrow so the user knows they ARE clickable.
 *   - Default sort is composite DESC (mirrors top-picks ordering) so
 *     the table opens on the highest-score stocks first.
 */

type SortKey =
  | "ticker"
  | "country"
  | "composite"
  | "pe"
  | "pb"
  | "roe"
  | "revenue_growth"
  | "dividend_yield"
  | "market_cap";

type SortDir = "asc" | "desc";

interface ColumnSpec {
  key: SortKey;
  label: string;
  align: "left" | "right";
  /** Default sort direction the column flips to when first clicked.
   *  Numeric columns default desc (largest first), string columns asc. */
  defaultDir: SortDir;
}

const COLUMNS: ColumnSpec[] = [
  { key: "ticker", label: "Stock", align: "left", defaultDir: "asc" },
  { key: "country", label: "Paese", align: "left", defaultDir: "asc" },
  { key: "composite", label: "Score", align: "right", defaultDir: "desc" },
  { key: "pe", label: "P/E", align: "right", defaultDir: "asc" },
  { key: "pb", label: "P/B", align: "right", defaultDir: "asc" },
  { key: "roe", label: "ROE", align: "right", defaultDir: "desc" },
  { key: "revenue_growth", label: "Cresc. ric.", align: "right", defaultDir: "desc" },
  { key: "dividend_yield", label: "Div. Y", align: "right", defaultDir: "desc" },
  { key: "market_cap", label: "Mkt cap", align: "right", defaultDir: "desc" },
];

function compareRows(a: SectorStockRow, b: SectorStockRow, key: SortKey, dir: SortDir): number {
  const av = a[key];
  const bv = b[key];
  // Null-last regardless of direction: a row with no value (e.g. no P/E)
  // should never bubble to the top of either asc or desc sort.
  const aNull = av === null || av === undefined;
  const bNull = bv === null || bv === undefined;
  if (aNull && bNull) return 0;
  if (aNull) return 1;
  if (bNull) return -1;
  let cmp: number;
  if (typeof av === "number" && typeof bv === "number") {
    cmp = av - bv;
  } else {
    cmp = String(av).localeCompare(String(bv));
  }
  return dir === "asc" ? cmp : -cmp;
}

export function SortableStocksTable({ rows }: { rows: SectorStockRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("composite");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(() => {
    // Slice() so we don't mutate the prop array (React rules + downstream
    // memoisation guarantees in the parent hook).
    return [...rows].sort((a, b) => compareRows(a, b, sortKey, sortDir));
  }, [rows, sortKey, sortDir]);

  function onHeaderClick(col: ColumnSpec) {
    if (col.key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir(col.defaultDir);
    }
  }

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Building2}
          label={`Tutte le aziende (${rows.length})`}
          className="mb-3"
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-muted-foreground/80 border-b border-border/60">
                {COLUMNS.map((col) => {
                  const active = col.key === sortKey;
                  const Indicator = active
                    ? sortDir === "asc"
                      ? ArrowUp
                      : ArrowDown
                    : ArrowUpDown;
                  return (
                    <th
                      key={col.key}
                      // Clickable header: small hover affordance + cursor.
                      // The chevron flips between Up/Down for the active
                      // column and stays dim two-way for inactive ones —
                      // a discoverability hint per the "every clickable
                      // surface MUST look clickable" UX rule.
                      onClick={() => onHeaderClick(col)}
                      className={cn(
                        "px-2 py-2 font-mono select-none cursor-pointer",
                        "hover:text-foreground transition-colors",
                        col.align === "right" ? "text-right" : "text-left",
                        active && "text-foreground",
                      )}
                    >
                      <span
                        className={cn(
                          "inline-flex items-center gap-1",
                          col.align === "right" && "flex-row-reverse",
                        )}
                      >
                        <span>{col.label}</span>
                        <Indicator
                          className={cn(
                            "h-3 w-3 shrink-0",
                            active ? "opacity-100" : "opacity-40",
                          )}
                          aria-hidden
                        />
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => (
                <StockRow key={row.ticker} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
