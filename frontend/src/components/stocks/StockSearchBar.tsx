import { Search, X } from "lucide-react";

import type { FilterOptions } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
export interface SearchState {
  q: string;
  indexCodes: string[];
  sectors: string[];
  exchanges: string[];
  countries: string[];
}

interface Props {
  state: SearchState;
  onChange: (next: SearchState) => void;
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
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 text-sm">
          {label} {selected.length > 0 && <Badge variant="secondary" className="ml-1.5 h-5">{selected.length}</Badge>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-2 max-h-72 overflow-y-auto">
        {options.length === 0 ? (
          <div className="text-xs text-muted-foreground p-2">Nessun valore</div>
        ) : (
          <ul className="space-y-1">
            {options.map((opt) => (
              <li key={opt.value}>
                <label className="flex items-center gap-2 px-2 py-1 text-sm rounded hover:bg-accent cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selected.includes(opt.value)}
                    onChange={() => toggle(opt.value)}
                    className="cursor-pointer"
                  />
                  <span className="truncate">{opt.label}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}

export function StockSearchBar({ state, onChange, filters }: Props) {
  const indexOptions = (filters?.indices ?? []).map((i) => ({ value: i.code, label: `${i.code} — ${i.name}` }));
  const sectorOptions = (filters?.sectors ?? []).map((s) => ({ value: s, label: s }));
  const exchangeOptions = (filters?.exchanges ?? []).map((e) => ({ value: e, label: e }));
  const countryOptions = (filters?.countries ?? []).map((c) => ({ value: c, label: c }));

  const totalActive =
    state.indexCodes.length + state.sectors.length + state.exchanges.length + state.countries.length;

  const clearAll = () => onChange({ q: "", indexCodes: [], sectors: [], exchanges: [], countries: [] });

  const removeChip = (kind: keyof Omit<SearchState, "q">, value: string) => {
    onChange({ ...state, [kind]: state[kind].filter((v) => v !== value) });
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[260px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={state.q}
            onChange={(e) => onChange({ ...state, q: e.target.value })}
            placeholder="Cerca per ticker o nome (es. AAPL, Apple, Nvidia...)"
            className="pl-9 h-9"
          />
          {state.q && (
            <button
              onClick={() => onChange({ ...state, q: "" })}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-accent"
              title="Pulisci"
            >
              <X className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          )}
        </div>
        <MultiSelect
          label="Indice" options={indexOptions} selected={state.indexCodes}
          onChange={(v) => onChange({ ...state, indexCodes: v })}
        />
        <MultiSelect
          label="Settore" options={sectorOptions} selected={state.sectors}
          onChange={(v) => onChange({ ...state, sectors: v })}
        />
        <MultiSelect
          label="Exchange" options={exchangeOptions} selected={state.exchanges}
          onChange={(v) => onChange({ ...state, exchanges: v })}
        />
        <MultiSelect
          label="Paese" options={countryOptions} selected={state.countries}
          onChange={(v) => onChange({ ...state, countries: v })}
        />
        {(totalActive > 0 || state.q) && (
          <Button variant="ghost" size="sm" onClick={clearAll} className="h-9 text-sm text-muted-foreground">
            <X className="h-3.5 w-3.5 mr-1" /> Pulisci
          </Button>
        )}
      </div>
      {totalActive > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Filtri attivi:</span>
          {state.indexCodes.map((v) => (
            <Badge key={`i-${v}`} variant="secondary" className="text-xs gap-1">
              {v}
              <button onClick={() => removeChip("indexCodes", v)} className="ml-0.5 hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {state.sectors.map((v) => (
            <Badge key={`s-${v}`} variant="secondary" className="text-xs gap-1">
              {v}
              <button onClick={() => removeChip("sectors", v)} className="ml-0.5 hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {state.exchanges.map((v) => (
            <Badge key={`e-${v}`} variant="secondary" className="text-xs gap-1">
              {v}
              <button onClick={() => removeChip("exchanges", v)} className="ml-0.5 hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {state.countries.map((v) => (
            <Badge key={`c-${v}`} variant="secondary" className="text-xs gap-1">
              {v}
              <button onClick={() => removeChip("countries", v)} className="ml-0.5 hover:text-destructive">
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
