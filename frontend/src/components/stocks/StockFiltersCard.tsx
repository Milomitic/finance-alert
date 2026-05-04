import { ChevronDown, Filter, X } from "lucide-react";

import type { FilterOptions } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/** Filter state for the stock browser. The text-search field has been
 *  intentionally removed — the navbar's global ticker search covers that
 *  use case and a second input on the page was redundant. */
export interface FiltersState {
  indexCodes: string[];
  sectors: string[];
  exchanges: string[];
  countries: string[];
}

interface Props {
  state: FiltersState;
  onChange: (next: FiltersState) => void;
  filters: FilterOptions | undefined;
}

interface MultiSelectProps {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (next: string[]) => void;
}

function MultiSelect({ label, options, selected, onChange }: MultiSelectProps) {
  const toggle = (v: string) => {
    onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]);
  };
  const clear = () => onChange([]);
  const active = selected.length > 0;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant={active ? "secondary" : "outline"}
          size="sm"
          className={cn(
            "h-9 text-sm gap-1.5 min-w-[110px] justify-between",
            active && "border-primary/40",
          )}
        >
          <span className="flex items-center gap-1.5">
            <span>{label}</span>
            {active && (
              <Badge variant="default" className="h-5 px-1.5 text-[10px] font-semibold">
                {selected.length}
              </Badge>
            )}
          </span>
          <ChevronDown className="h-3.5 w-3.5 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-0">
        <div className="flex items-center justify-between px-3 py-2 border-b">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {label}
          </span>
          {active && (
            <button
              onClick={clear}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Pulisci
            </button>
          )}
        </div>
        <div className="max-h-72 overflow-y-auto p-1">
          {options.length === 0 ? (
            <div className="text-xs text-muted-foreground p-3">Nessun valore</div>
          ) : (
            <ul>
              {options.map((opt) => {
                const checked = selected.includes(opt.value);
                return (
                  <li key={opt.value}>
                    <label
                      className={cn(
                        "flex items-center gap-2 px-2 py-1.5 text-sm rounded cursor-pointer",
                        "hover:bg-accent",
                        checked && "bg-accent/50",
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(opt.value)}
                        className="cursor-pointer h-3.5 w-3.5"
                      />
                      <span className="truncate">{opt.label}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function StockFiltersCard({ state, onChange, filters }: Props) {
  const indexOptions = (filters?.indices ?? []).map((i) => ({
    value: i.code,
    label: `${i.code} — ${i.name}`,
  }));
  const sectorOptions = (filters?.sectors ?? []).map((s) => ({ value: s, label: s }));
  const exchangeOptions = (filters?.exchanges ?? []).map((e) => ({ value: e, label: e }));
  const countryOptions = (filters?.countries ?? []).map((c) => ({ value: c, label: c }));

  const totalActive =
    state.indexCodes.length + state.sectors.length + state.exchanges.length + state.countries.length;

  const clearAll = () =>
    onChange({ indexCodes: [], sectors: [], exchanges: [], countries: [] });

  const removeChip = (kind: keyof FiltersState, value: string) => {
    onChange({ ...state, [kind]: state[kind].filter((v) => v !== value) });
  };

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground mr-1">
            <Filter className="h-4 w-4" />
            <span>Filtri</span>
            {totalActive > 0 && (
              <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                {totalActive} attivi
              </Badge>
            )}
          </div>
          <MultiSelect
            label="Indice"
            options={indexOptions}
            selected={state.indexCodes}
            onChange={(v) => onChange({ ...state, indexCodes: v })}
          />
          <MultiSelect
            label="Settore"
            options={sectorOptions}
            selected={state.sectors}
            onChange={(v) => onChange({ ...state, sectors: v })}
          />
          <MultiSelect
            label="Exchange"
            options={exchangeOptions}
            selected={state.exchanges}
            onChange={(v) => onChange({ ...state, exchanges: v })}
          />
          <MultiSelect
            label="Paese"
            options={countryOptions}
            selected={state.countries}
            onChange={(v) => onChange({ ...state, countries: v })}
          />
          {totalActive > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearAll}
              className="h-9 text-sm text-muted-foreground ml-auto"
            >
              <X className="h-3.5 w-3.5 mr-1" /> Reset
            </Button>
          )}
        </div>
        {totalActive > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-border/50">
            <span className="text-xs text-muted-foreground mr-1">Attivi:</span>
            {state.indexCodes.map((v) => (
              <Badge key={`i-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Indice:</span> {v}
                <button
                  onClick={() => removeChip("indexCodes", v)}
                  className="ml-0.5 rounded hover:bg-background/60 p-0.5"
                  aria-label={`Rimuovi indice ${v}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
            {state.sectors.map((v) => (
              <Badge key={`s-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Settore:</span> {v}
                <button
                  onClick={() => removeChip("sectors", v)}
                  className="ml-0.5 rounded hover:bg-background/60 p-0.5"
                  aria-label={`Rimuovi settore ${v}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
            {state.exchanges.map((v) => (
              <Badge key={`e-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Exchange:</span> {v}
                <button
                  onClick={() => removeChip("exchanges", v)}
                  className="ml-0.5 rounded hover:bg-background/60 p-0.5"
                  aria-label={`Rimuovi exchange ${v}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
            {state.countries.map((v) => (
              <Badge key={`c-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Paese:</span> {v}
                <button
                  onClick={() => removeChip("countries", v)}
                  className="ml-0.5 rounded hover:bg-background/60 p-0.5"
                  aria-label={`Rimuovi paese ${v}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
