import { useState } from "react";

import type { Stock } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useStockSearch } from "@/hooks/useStocks";

interface Props {
  onAdd: (stock: Stock) => void;
  excludeIds?: Set<number>;
}

export function StockSearchTab({ onAdd, excludeIds }: Props) {
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q, 300);
  const search = useStockSearch({ q: debouncedQ, limit: 30 }, debouncedQ.length >= 1);

  // Search response items now wrap each Stock in {stock, score}; this tab
  // doesn't surface scoring — unwrap to plain Stock[].
  const items = (search.data?.items ?? []).map((it) => it.stock);

  return (
    <div className="space-y-3">
      <Input
        placeholder="Cerca per ticker o nome (es. AAPL, Apple)…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        autoFocus
      />
      <div className="space-y-1.5 max-h-[420px] overflow-y-auto">
        {debouncedQ.length === 0 && (
          <p className="text-sm text-muted-foreground p-2">
            Inizia a digitare per cercare uno stock.
          </p>
        )}
        {debouncedQ.length > 0 && search.isLoading && (
          <p className="text-sm text-muted-foreground p-2">Caricamento…</p>
        )}
        {items.length === 0 && debouncedQ.length > 0 && !search.isLoading && (
          <p className="text-sm text-muted-foreground p-2">Nessun risultato.</p>
        )}
        {items.map((s) => {
          const already = excludeIds?.has(s.id) ?? false;
          return (
            <div
              key={s.id}
              className="flex items-center justify-between gap-2 rounded border bg-card p-2"
            >
              <div className="min-w-0">
                <div className="font-medium text-sm">
                  {s.ticker}
                  <span className="text-muted-foreground font-normal ml-2">
                    {s.exchange}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground truncate">{s.name}</div>
              </div>
              <Button
                size="sm"
                variant={already ? "secondary" : "default"}
                disabled={already}
                onClick={() => onAdd(s)}
              >
                {already ? "Già aggiunto" : "+ aggiungi"}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
