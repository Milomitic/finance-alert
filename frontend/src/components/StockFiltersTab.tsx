import { useMemo, useState } from "react";
import { ChevronDown, X } from "lucide-react";

import type { Stock } from "@/api/types";
import type { SearchParams } from "@/api/stocks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useStockFilters, useStockSearch } from "@/hooks/useStocks";

interface Props {
  onAddBulk: (stocks: Stock[]) => void;
  excludeIds?: Set<number>;
}

interface MultiSelectProps {
  label: string;
  values: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  display?: (value: string) => string;
}

function MultiSelect({ label, values, selected, onChange, display }: MultiSelectProps) {
  const toggle = (v: string) => {
    if (selected.includes(v)) onChange(selected.filter((x) => x !== v));
    else onChange([...selected, v]);
  };
  const labelFor = display ?? ((v: string) => v);

  return (
    <div className="space-y-1.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="w-full justify-between">
            <span className="truncate">
              {selected.length === 0
                ? `Tutti`
                : `${selected.length} selezionati`}
            </span>
            <ChevronDown className="h-4 w-4 opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="max-h-[240px] overflow-y-auto w-[240px]">
          <DropdownMenuLabel>{label}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {values.length === 0 && (
            <div className="px-2 py-1 text-xs text-muted-foreground">
              Nessuna opzione disponibile
            </div>
          )}
          {values.map((v) => (
            <DropdownMenuCheckboxItem
              key={v}
              checked={selected.includes(v)}
              onCheckedChange={() => toggle(v)}
              onSelect={(e) => e.preventDefault()}
            >
              {labelFor(v)}
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selected.map((v) => (
            <Badge key={v} variant="secondary" className="gap-1">
              {labelFor(v)}
              <button
                type="button"
                onClick={() => toggle(v)}
                className="opacity-60 hover:opacity-100"
                aria-label={`Rimuovi ${labelFor(v)}`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

export function StockFiltersTab({ onAddBulk, excludeIds }: Props) {
  const filters = useStockFilters();
  const [exchanges, setExchanges] = useState<string[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [indexCodes, setIndexCodes] = useState<string[]>([]);

  const params: SearchParams = useMemo(
    () => ({
      exchange: exchanges,
      sector: sectors,
      country: countries,
      index: indexCodes,
      limit: 500,
    }),
    [exchanges, sectors, countries, indexCodes]
  );

  const anyFilter =
    exchanges.length > 0 || sectors.length > 0 || countries.length > 0 || indexCodes.length > 0;
  const search = useStockSearch(params, anyFilter);

  const total = search.data?.total ?? 0;
  // Unwrap the new {stock, score} envelope — this tab is for selecting
  // stocks for a watchlist, the score data isn't relevant here.
  const items = (search.data?.items ?? []).map((it) => it.stock);

  const onAddAll = () => {
    if (items.length === 0) return;
    const fresh = excludeIds
      ? items.filter((s) => !excludeIds.has(s.id))
      : items;
    onAddBulk(fresh);
  };

  const indexLabel = (code: string) =>
    filters.data?.indices.find((i) => i.code === code)?.name ?? code;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <MultiSelect
          label="Exchange"
          values={filters.data?.exchanges ?? []}
          selected={exchanges}
          onChange={setExchanges}
        />
        <MultiSelect
          label="Settore"
          values={filters.data?.sectors ?? []}
          selected={sectors}
          onChange={setSectors}
        />
        <MultiSelect
          label="Paese"
          values={filters.data?.countries ?? []}
          selected={countries}
          onChange={setCountries}
        />
        <MultiSelect
          label="Indice"
          values={(filters.data?.indices ?? []).map((i) => i.code)}
          selected={indexCodes}
          onChange={setIndexCodes}
          display={indexLabel}
        />
      </div>

      <div className="rounded border bg-muted/30 p-3 flex items-center justify-between gap-3">
        <div className="text-sm">
          {anyFilter ? (
            <>
              <strong>{total}</strong>{" "}
              {total === 1 ? "stock selezionato" : "stock selezionati"}
              {total > items.length && (
                <span className="text-muted-foreground">
                  {" "}
                  (mostrati {items.length})
                </span>
              )}
            </>
          ) : (
            <span className="text-muted-foreground">
              Applica almeno un filtro per vedere i risultati.
            </span>
          )}
        </div>
        <Button
          size="sm"
          onClick={onAddAll}
          disabled={!anyFilter || items.length === 0}
        >
          Aggiungi tutti
        </Button>
      </div>
    </div>
  );
}
