import { Building2, History, Search, TrendingUp, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { IndexBreadth, Stock } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Input } from "@/components/ui/input";
import { useMarketSummary } from "@/hooks/useMarketSummary";
import { useStockSearch } from "@/hooks/useStockSearch";
import { getIndexMeta } from "@/lib/indexMeta";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

// ── localStorage recent searches ──────────────────────────
const RECENT_KEY = "stock-search-recent";
const RECENT_MAX = 5;

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function pushRecent(ticker: string) {
  try {
    const list = loadRecent().filter((t) => t !== ticker);
    list.unshift(ticker);
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX)));
  } catch {
    // ignore quota errors
  }
}

// ── helpers ───────────────────────────────────────────────
function fmtMc(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

// ── flat result row for unified keyboard nav ──────────────
type RowKind = "index" | "stock" | "recent" | "mover";
interface FlatRow {
  kind: RowKind;
  // For index navigation
  indexCode?: string;
  // For stock/recent/mover navigation
  ticker?: string;
}

// ── component ─────────────────────────────────────────────
export function NavbarSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [recent, setRecent] = useState<string[]>(() => loadRecent());
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const search = useStockSearch({ q: q || undefined, limit: 8 });
  const market = useMarketSummary();

  // Map ticker → change_pct (and market_cap fallback) from market snapshot
  const enrichByTicker = useMemo(() => {
    const m = new Map<string, { change_pct: number; market_cap: number }>();
    for (const leaf of market.data?.treemap ?? []) {
      m.set(leaf.ticker, { change_pct: leaf.change_pct, market_cap: leaf.market_cap });
    }
    return m;
  }, [market.data]);

  const stockItems: Stock[] = q.trim().length > 0 ? search.data?.items ?? [] : [];

  // Index matches: filter by code or name match (case-insensitive)
  const indexMatches: IndexBreadth[] = useMemo(() => {
    if (q.trim().length === 0) return [];
    const needle = q.trim().toLowerCase();
    return (market.data?.by_index ?? []).filter(
      (i) => i.code.toLowerCase().includes(needle) || i.name.toLowerCase().includes(needle),
    );
  }, [market.data, q]);

  // Top movers (gainers) — empty state
  const topMovers = useMemo(() => {
    if (q.trim().length > 0) return [];
    return (market.data?.movers?.gainers ?? []).slice(0, 5);
  }, [market.data, q]);

  // Build flattened list for keyboard nav. Order matches visual order.
  const flatRows: FlatRow[] = useMemo(() => {
    const rows: FlatRow[] = [];
    if (q.trim().length > 0) {
      for (const i of indexMatches) rows.push({ kind: "index", indexCode: i.code });
      for (const s of stockItems) rows.push({ kind: "stock", ticker: s.ticker });
    } else {
      for (const t of recent) rows.push({ kind: "recent", ticker: t });
      for (const m of topMovers) rows.push({ kind: "mover", ticker: m.ticker });
    }
    return rows;
  }, [q, indexMatches, stockItems, recent, topMovers]);

  // Reset highlight when results change
  useEffect(() => {
    setHighlight(0);
  }, [flatRows.length, q]);

  // Close on outside click (mousedown to beat focus loss)
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  // Keyboard `/` shortcut to focus
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const goToTicker = (ticker: string) => {
    pushRecent(ticker);
    setRecent(loadRecent());
    setOpen(false);
    setQ("");
    navigate(`/stocks/${encodeURIComponent(ticker)}`);
  };

  const goToIndex = (code: string) => {
    setOpen(false);
    setQ("");
    navigate(`/stocks?index=${encodeURIComponent(code)}`);
  };

  const navigateRow = (row: FlatRow) => {
    if (row.kind === "index" && row.indexCode) goToIndex(row.indexCode);
    else if (row.ticker) goToTicker(row.ticker);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open && e.key !== "Escape") setOpen(true);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, Math.max(0, flatRows.length - 1)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter" && flatRows[highlight]) {
      e.preventDefault();
      navigateRow(flatRows[highlight]);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  // Index of the current row in the flat list, for highlight matching
  const highlightedIdx = highlight;
  let cursor = 0;
  const isHighlighted = (n: number) => n === highlightedIdx;

  // ── render helpers ──────────────────────────────────────
  function IndexRow({ i, idx }: { i: IndexBreadth; idx: number }) {
    const meta = getIndexMeta(i.code);
    const change = i.avg_change_pct;
    const changeColor =
      change == null ? "text-muted-foreground" :
      change > 0 ? "text-green-600 dark:text-green-400" :
      change < 0 ? "text-red-600 dark:text-red-400" : "";
    return (
      <button
        type="button"
        onClick={() => goToIndex(i.code)}
        onMouseEnter={() => setHighlight(idx)}
        className={cn(
          "w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors",
          isHighlighted(idx) ? "bg-accent" : "hover:bg-accent/50",
        )}
      >
        {meta.countryCode && (
          <img
            src={`/flags/${meta.countryCode}.svg`}
            alt={meta.country}
            width={24} height={16}
            style={{ width: "24px", height: "16px", objectFit: "cover" }}
            className="rounded shadow-sm shrink-0"
          />
        )}
        <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-1.5">
            <span className="text-sm font-bold tabular-nums">{i.code}</span>
            <span className="text-xs text-muted-foreground truncate">{meta.fullName}</span>
          </div>
          <div className="text-[11px] text-muted-foreground">
            {i.n} stock · {i.pct_above_sma200 != null ? `${i.pct_above_sma200.toFixed(0)}% > SMA200` : "—"}
          </div>
        </div>
        {change != null && (
          <span className={cn("text-sm tabular-nums font-semibold shrink-0", changeColor)}>
            {change >= 0 ? "+" : ""}{change.toFixed(2)}%
          </span>
        )}
      </button>
    );
  }

  function StockRow({ s, idx }: { s: Stock; idx: number }) {
    const flag = getStockFlagCode(s.country);
    const enriched = enrichByTicker.get(s.ticker);
    const change = enriched?.change_pct;
    const mc = s.market_cap ?? enriched?.market_cap ?? null;
    const changeColor =
      change == null ? "text-muted-foreground" :
      change > 0 ? "text-green-600 dark:text-green-400" :
      change < 0 ? "text-red-600 dark:text-red-400" : "";
    return (
      <button
        type="button"
        onClick={() => goToTicker(s.ticker)}
        onMouseEnter={() => setHighlight(idx)}
        className={cn(
          "w-full flex items-center gap-3 px-3 py-3 text-left transition-colors",
          isHighlighted(idx) ? "bg-accent" : "hover:bg-accent/50",
        )}
      >
        <StockLogo ticker={s.ticker} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-bold text-sm tabular-nums">{s.ticker}</span>
            {flag && (
              <img
                src={`/flags/${flag}.svg`}
                alt={s.country ?? ""}
                width={16} height={11}
                style={{ width: "16px", height: "11px", objectFit: "cover" }}
                className="rounded-[1px] shadow-sm shrink-0"
              />
            )}
            <span className="text-[10px] text-muted-foreground bg-muted/60 dark:bg-muted/40 px-1.5 py-0.5 rounded">
              {s.exchange}
            </span>
            {s.sector && (
              <span className="text-[10px] text-muted-foreground bg-muted/60 dark:bg-muted/40 px-1.5 py-0.5 rounded truncate max-w-[140px]">
                {s.sector}
              </span>
            )}
          </div>
          <div className="text-xs text-muted-foreground truncate mt-0.5">{s.name}</div>
          {mc != null && (
            <div className="text-[10px] text-muted-foreground/80 mt-0.5">
              Mkt cap <strong className="text-muted-foreground tabular-nums">{fmtMc(mc)}</strong>
            </div>
          )}
        </div>
        {change != null && (
          <div className="text-right shrink-0">
            <div className={cn("text-base font-bold tabular-nums", changeColor)}>
              {change >= 0 ? "+" : ""}{change.toFixed(2)}%
            </div>
            <div className="text-[10px] text-muted-foreground">oggi</div>
          </div>
        )}
      </button>
    );
  }

  function CompactRow({ ticker, idx, kind }: { ticker: string; idx: number; kind: RowKind }) {
    const enriched = enrichByTicker.get(ticker);
    const change = enriched?.change_pct;
    const changeColor =
      change == null ? "text-muted-foreground" :
      change > 0 ? "text-green-600 dark:text-green-400" :
      change < 0 ? "text-red-600 dark:text-red-400" : "";
    const Icon = kind === "recent" ? History : TrendingUp;
    return (
      <button
        type="button"
        onClick={() => goToTicker(ticker)}
        onMouseEnter={() => setHighlight(idx)}
        className={cn(
          "w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors",
          isHighlighted(idx) ? "bg-accent" : "hover:bg-accent/50",
        )}
      >
        <Icon className="h-3.5 w-3.5 text-muted-foreground/60 shrink-0" />
        <StockLogo ticker={ticker} size="sm" />
        <span className="font-bold text-sm tabular-nums">{ticker}</span>
        {change != null && (
          <span className={cn("ml-auto text-sm tabular-nums font-semibold", changeColor)}>
            {change >= 0 ? "+" : ""}{change.toFixed(2)}%
          </span>
        )}
      </button>
    );
  }

  // ── render ──────────────────────────────────────────────
  const totalResults = stockItems.length + indexMatches.length;
  const totalEmpty = recent.length + topMovers.length;

  return (
    <div ref={containerRef} className="relative w-full max-w-2xl">
      <div className="relative">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground pointer-events-none" />
        <Input
          ref={inputRef}
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Cerca stock, indici, settori… (premi / per focus)"
          className="pl-11 pr-10 h-12 text-base"
        />
        {q && (
          <button
            type="button"
            onClick={() => { setQ(""); setOpen(false); inputRef.current?.focus(); }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-accent"
            title="Pulisci"
          >
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        )}
      </div>

      {open && (
        <div className="absolute left-0 right-0 top-full mt-2 z-50 rounded-lg border bg-popover shadow-2xl overflow-hidden">
          {/* Loading state */}
          {q.trim().length > 0 && search.isLoading && (
            <div className="px-4 py-3 text-sm text-muted-foreground">Ricerca in corso…</div>
          )}

          {/* Search-with-results state */}
          {q.trim().length > 0 && !search.isLoading && (
            <div className="max-h-[600px] overflow-y-auto">
              {totalResults === 0 ? (
                <div className="px-4 py-6 text-sm text-muted-foreground text-center">
                  Nessun risultato per "<strong className="text-foreground">{q}</strong>"
                </div>
              ) : (
                <>
                  {/* Indices section */}
                  {indexMatches.length > 0 && (
                    <div>
                      <div className="px-4 py-1.5 bg-muted/40 text-[10px] uppercase tracking-wider font-bold text-muted-foreground border-b">
                        🏛️ Indici ({indexMatches.length})
                      </div>
                      {indexMatches.map((i) => {
                        const idx = cursor++;
                        return <IndexRow key={i.code} i={i} idx={idx} />;
                      })}
                    </div>
                  )}

                  {/* Stocks section */}
                  {stockItems.length > 0 && (
                    <div>
                      <div className="px-4 py-1.5 bg-muted/40 text-[10px] uppercase tracking-wider font-bold text-muted-foreground border-b">
                        🔍 Stocks ({stockItems.length})
                      </div>
                      {stockItems.map((s) => {
                        const idx = cursor++;
                        return <StockRow key={s.id} s={s} idx={idx} />;
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Empty input state: Recent + Top movers */}
          {q.trim().length === 0 && (
            <div className="max-h-[600px] overflow-y-auto">
              {totalEmpty === 0 ? (
                <div className="px-4 py-6 text-sm text-muted-foreground text-center">
                  Inizia a digitare per cercare stock, indici o settori
                </div>
              ) : (
                <>
                  {recent.length > 0 && (
                    <div>
                      <div className="px-4 py-1.5 bg-muted/40 text-[10px] uppercase tracking-wider font-bold text-muted-foreground border-b">
                        🕓 Visti di recente ({recent.length})
                      </div>
                      {recent.map((t) => {
                        const idx = cursor++;
                        return <CompactRow key={`r-${t}`} ticker={t} idx={idx} kind="recent" />;
                      })}
                    </div>
                  )}
                  {topMovers.length > 0 && (
                    <div>
                      <div className="px-4 py-1.5 bg-muted/40 text-[10px] uppercase tracking-wider font-bold text-muted-foreground border-b">
                        🚀 Top movers oggi ({topMovers.length})
                      </div>
                      {topMovers.map((m) => {
                        const idx = cursor++;
                        return <CompactRow key={`m-${m.ticker}`} ticker={m.ticker} idx={idx} kind="mover" />;
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Footer */}
          <div className="border-t px-4 py-1.5 text-[10px] text-muted-foreground bg-muted/30 flex items-center justify-between">
            <span>
              {q.trim().length > 0
                ? `${stockItems.length} stock${stockItems.length === 1 ? "" : "s"} + ${indexMatches.length} indic${indexMatches.length === 1 ? "e" : "i"}`
                : "Suggerimenti"}
            </span>
            <span>
              <kbd className="px-1 py-0.5 bg-background rounded border text-[9px]">↑↓</kbd>
              <kbd className="ml-1 px-1 py-0.5 bg-background rounded border text-[9px]">↵</kbd>
              <kbd className="ml-1 px-1 py-0.5 bg-background rounded border text-[9px]">esc</kbd>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
