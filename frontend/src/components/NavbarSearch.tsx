import { Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { Stock } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Input } from "@/components/ui/input";
import { useMarketSummary } from "@/hooks/useMarketSummary";
import { useStockSearch } from "@/hooks/useStockSearch";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

export function NavbarSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const search = useStockSearch({ q: q || undefined, limit: 8 });
  const market = useMarketSummary();

  const changeByTicker = useMemo(() => {
    const m = new Map<string, number>();
    for (const leaf of market.data?.treemap ?? []) m.set(leaf.ticker, leaf.change_pct);
    return m;
  }, [market.data]);

  const items: Stock[] = q.trim().length > 0 ? search.data?.items ?? [] : [];

  // Reset highlight when items change
  useEffect(() => {
    setHighlight(0);
  }, [items.length, q]);

  // Close on outside click
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const navigateTo = (ticker: string) => {
    setOpen(false);
    setQ("");
    navigate(`/stocks/${encodeURIComponent(ticker)}`);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open && e.key !== "Escape") setOpen(true);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, Math.max(0, items.length - 1)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter" && items[highlight]) {
      e.preventDefault();
      navigateTo(items[highlight].ticker);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  return (
    <div ref={containerRef} className="relative w-full max-w-xl">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          ref={inputRef}
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Cerca stock per ticker o nome (es. AAPL, Apple, NVDA, Tencent...)"
          className="pl-9 pr-9 h-10 text-sm"
        />
        {q && (
          <button
            type="button"
            onClick={() => { setQ(""); setOpen(false); inputRef.current?.focus(); }}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-accent"
            title="Pulisci"
          >
            <X className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        )}
      </div>

      {open && q.trim().length > 0 && (
        <div className="absolute left-0 right-0 top-full mt-1 z-50 rounded-md border bg-popover shadow-lg overflow-hidden">
          {search.isLoading && (
            <div className="px-3 py-2.5 text-xs text-muted-foreground">Ricerca…</div>
          )}
          {!search.isLoading && items.length === 0 && (
            <div className="px-3 py-3 text-sm text-muted-foreground text-center">
              Nessun risultato per "<strong>{q}</strong>"
            </div>
          )}
          {items.length > 0 && (
            <>
              <ul className="max-h-[420px] overflow-y-auto">
                {items.map((s, i) => {
                  const flag = getStockFlagCode(s.country);
                  const change = changeByTicker.get(s.ticker);
                  const changeColor =
                    change == null ? "text-muted-foreground" :
                    change > 0 ? "text-green-600 dark:text-green-400" :
                    change < 0 ? "text-red-600 dark:text-red-400" : "";
                  return (
                    <li key={s.id}>
                      <button
                        type="button"
                        onClick={() => navigateTo(s.ticker)}
                        onMouseEnter={() => setHighlight(i)}
                        className={cn(
                          "w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors",
                          highlight === i ? "bg-accent" : "hover:bg-accent/50",
                        )}
                      >
                        <StockLogo ticker={s.ticker} size="sm" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className="font-bold text-sm tabular-nums">{s.ticker}</span>
                            {flag && (
                              <img
                                src={`/flags/${flag}.svg`}
                                alt={s.country ?? ""}
                                width={14} height={10}
                                style={{ width: "14px", height: "10px", objectFit: "cover" }}
                                className="rounded-[1px] shadow-sm"
                              />
                            )}
                            <span className="text-[10px] text-muted-foreground">{s.exchange}</span>
                          </div>
                          <div className="text-xs text-muted-foreground truncate">
                            {s.name}
                            {s.sector && <span className="opacity-60"> · {s.sector}</span>}
                          </div>
                        </div>
                        {change != null && (
                          <span className={cn("text-xs tabular-nums font-semibold shrink-0", changeColor)}>
                            {change >= 0 ? "+" : ""}{change.toFixed(2)}%
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
              <div className="border-t px-3 py-1.5 text-[10px] text-muted-foreground bg-muted/30 flex items-center justify-between">
                <span>{items.length} risultat{items.length === 1 ? "o" : "i"}</span>
                <span>↑↓ per navigare · ↵ per aprire · esc per chiudere</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
