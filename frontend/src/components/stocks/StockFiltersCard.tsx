import { ChevronDown, Filter, X } from "lucide-react";

import type { FilterOptions } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import { CATEGORY_LABEL } from "@/lib/scoreMeta";
import { cn } from "@/lib/utils";

/** Filter state for the stock browser. The text-search field has been
 *  intentionally removed — the navbar's global ticker search covers that
 *  use case and a second input on the page was redundant. */
export interface FiltersState {
  indexCodes: string[];
  sectors: string[];
  industries: string[];
  exchanges: string[];
  countries: string[];
  /** Risk-tier filter from stock_scores. Empty = no filter. */
  riskTiers: ("conservative" | "moderate" | "aggressive")[];
  /** Min composite score 0–100, or null = no threshold. When set, unscored
   *  stocks are excluded by the backend. */
  minScore: number | null;
  /** Max composite score 0–100, or null = no ceiling. */
  scoreMax: number | null;
  /** Per-pillar minimum scores 0–100, or null = no threshold. */
  profitabilityMin: number | null;
  sustainabilityMin: number | null;
  growthMin: number | null;
  valueMin: number | null;
  sentimentMin: number | null;
  /** Technical composite minimum 0-100, or null. */
  techMin: number | null;
  /** Technical posture filter (Forte / Neutro / Debole). Empty = no filter. */
  postures: string[];
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

// Risk-tier static options — short list, hardcoded so we don't need to
// fetch enum values from the API. Kept as plain string-literal records
// (Tailwind purger contract from CLAUDE.md). Tone classes mirror the
// scoreMeta module's RISK_TONE map.
const RISK_OPTIONS: { value: "conservative" | "moderate" | "aggressive"; label: string; tone: string }[] = [
  { value: "conservative", label: "Conservative", tone: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300" },
  { value: "moderate",     label: "Moderate",     tone: "bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300" },
  { value: "aggressive",   label: "Aggressive",   tone: "bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300" },
];

/** Compact number input used for pillar min thresholds. */
function PillarInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-muted-foreground w-28 shrink-0">{label}</span>
      <div className="inline-flex items-center gap-1 h-7 px-1.5 rounded border border-input">
        <span className="text-xs text-muted-foreground">≥</span>
        <input
          type="number"
          min={0}
          max={100}
          step={5}
          placeholder="—"
          value={value ?? ""}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") { onChange(null); return; }
            const n = Number(raw);
            if (Number.isFinite(n) && n >= 0 && n <= 100) onChange(n);
          }}
          className="w-10 bg-transparent text-xs tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
      </div>
    </div>
  );
}

export function StockFiltersCard({ state, onChange, filters }: Props) {
  const indexOptions = (filters?.indices ?? []).map((i) => ({
    value: i.code,
    label: `${i.code} — ${i.name}`,
  }));
  const sectorOptions = (filters?.sectors ?? []).map((s) => ({ value: s, label: s }));
  const industryOptions = (filters?.industries ?? []).map((i) => ({ value: i, label: i }));
  const exchangeOptions = (filters?.exchanges ?? []).map((e) => ({ value: e, label: e }));
  const countryOptions = (filters?.countries ?? []).map((c) => ({ value: c, label: c }));

  const pillarActiveCount =
    (state.profitabilityMin != null ? 1 : 0) +
    (state.sustainabilityMin != null ? 1 : 0) +
    (state.growthMin != null ? 1 : 0) +
    (state.valueMin != null ? 1 : 0) +
    (state.sentimentMin != null ? 1 : 0);

  const totalActive =
    state.indexCodes.length +
    state.sectors.length +
    state.industries.length +
    state.exchanges.length +
    state.countries.length +
    state.riskTiers.length +
    (state.minScore != null ? 1 : 0) +
    (state.scoreMax != null ? 1 : 0) +
    pillarActiveCount;

  const clearAll = () =>
    onChange({
      indexCodes: [], sectors: [], industries: [], exchanges: [], countries: [],
      riskTiers: [], minScore: null, scoreMax: null,
      profitabilityMin: null, sustainabilityMin: null, growthMin: null,
      valueMin: null, sentimentMin: null,
      techMin: null, postures: [],
    });

  const removeChip = (kind: keyof FiltersState, value: string) => {
    if (
      kind === "minScore" || kind === "scoreMax" ||
      kind === "profitabilityMin" || kind === "sustainabilityMin" ||
      kind === "growthMin" || kind === "valueMin" ||
      kind === "sentimentMin"
    ) {
      onChange({ ...state, [kind]: null });
      return;
    }
    if (kind === "riskTiers") {
      onChange({ ...state, riskTiers: state.riskTiers.filter((v) => v !== value) });
      return;
    }
    onChange({ ...state, [kind]: (state[kind] as string[]).filter((v) => v !== value) });
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
            label="Industry"
            options={industryOptions}
            selected={state.industries}
            onChange={(v) => onChange({ ...state, industries: v })}
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
          <MultiSelect
            label="Rischio"
            options={RISK_OPTIONS}
            selected={state.riskTiers}
            onChange={(v) => onChange({ ...state, riskTiers: v as FiltersState["riskTiers"] })}
          />
          {/* Composite score range: min + max inline. Kept without a popover
              since they're just two numbers and popover overhead is unwarranted. */}
          <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input">
            <span className="text-xs text-muted-foreground">Score</span>
            <input
              type="number"
              min={0}
              max={100}
              step={5}
              placeholder="min"
              value={state.minScore ?? ""}
              onChange={(e) => {
                const raw = e.target.value;
                if (raw === "") { onChange({ ...state, minScore: null }); return; }
                const n = Number(raw);
                if (Number.isFinite(n) && n >= 0 && n <= 100) onChange({ ...state, minScore: n });
              }}
              className="w-10 bg-transparent text-sm tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <span className="text-xs text-muted-foreground">–</span>
            <input
              type="number"
              min={0}
              max={100}
              step={5}
              placeholder="max"
              value={state.scoreMax ?? ""}
              onChange={(e) => {
                const raw = e.target.value;
                if (raw === "") { onChange({ ...state, scoreMax: null }); return; }
                const n = Number(raw);
                if (Number.isFinite(n) && n >= 0 && n <= 100) onChange({ ...state, scoreMax: n });
              }}
              className="w-10 bg-transparent text-sm tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
          </div>
          <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input">
            <span className="text-xs text-muted-foreground">Tecnico</span>
            <input
              type="number"
              min={0}
              max={100}
              step={5}
              placeholder="min"
              value={state.techMin ?? ""}
              onChange={(e) => {
                const raw = e.target.value;
                if (raw === "") { onChange({ ...state, techMin: null }); return; }
                const n = Number(raw);
                if (Number.isFinite(n) && n >= 0 && n <= 100) onChange({ ...state, techMin: n });
              }}
              className="w-10 bg-transparent text-sm tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
          </div>
          <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input">
            <span className="text-xs text-muted-foreground">Postura</span>
            {(["Forte", "Neutro", "Debole"] as const).map((pp) => {
              const on = state.postures.includes(pp);
              return (
                <button
                  key={pp}
                  type="button"
                  onClick={() => onChange({ ...state, postures: on ? state.postures.filter((x) => x !== pp) : [...state.postures, pp] })}
                  className={cn("px-1.5 py-0.5 rounded text-xs font-medium", on ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}
                >
                  {pp}
                </button>
              );
            })}
          </div>
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

        {/* Per-pillar minimum scores sub-section. Shown as a compact 2-col grid. */}
        <div className="pt-2 border-t border-border/40">
          <div className="flex items-center gap-1.5 mb-2">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Punteggi pillar
            </span>
            {pillarActiveCount > 0 && (
              <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                {pillarActiveCount}
              </Badge>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5">
            <PillarInput
              label={CATEGORY_LABEL.profitability}
              value={state.profitabilityMin}
              onChange={(v) => onChange({ ...state, profitabilityMin: v })}
            />
            <PillarInput
              label={CATEGORY_LABEL.sustainability}
              value={state.sustainabilityMin}
              onChange={(v) => onChange({ ...state, sustainabilityMin: v })}
            />
            <PillarInput
              label={CATEGORY_LABEL.growth}
              value={state.growthMin}
              onChange={(v) => onChange({ ...state, growthMin: v })}
            />
            <PillarInput
              label={CATEGORY_LABEL.value}
              value={state.valueMin}
              onChange={(v) => onChange({ ...state, valueMin: v })}
            />
            <PillarInput
              label={CATEGORY_LABEL.sentiment}
              value={state.sentimentMin}
              onChange={(v) => onChange({ ...state, sentimentMin: v })}
            />
          </div>
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
            {state.industries.map((v) => (
              <Badge key={`ind-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Industry:</span> {v}
                <button
                  onClick={() => removeChip("industries", v)}
                  className="ml-0.5 rounded hover:bg-background/60 p-0.5"
                  aria-label={`Rimuovi industry ${v}`}
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
            {state.riskTiers.map((v) => (
              <Badge key={`r-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Rischio:</span> {v}
                <button
                  onClick={() => removeChip("riskTiers", v)}
                  className="ml-0.5 rounded hover:bg-background/60 p-0.5"
                  aria-label={`Rimuovi rischio ${v}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
            {state.minScore != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Score ≥</span> {state.minScore}
                <button
                  onClick={() => onChange({ ...state, minScore: null })}
                  className="ml-0.5 rounded hover:bg-background/60 p-0.5"
                  aria-label="Rimuovi soglia score minima"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            )}
            {state.scoreMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Score ≤</span> {state.scoreMax}
                <button
                  onClick={() => onChange({ ...state, scoreMax: null })}
                  className="ml-0.5 rounded hover:bg-background/60 p-0.5"
                  aria-label="Rimuovi soglia score massima"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            )}
            {state.profitabilityMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Profitt. ≥</span> {state.profitabilityMin}
                <button onClick={() => onChange({ ...state, profitabilityMin: null })} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia profittabilità"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.sustainabilityMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Sosten. ≥</span> {state.sustainabilityMin}
                <button onClick={() => onChange({ ...state, sustainabilityMin: null })} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia sostenibilità"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.growthMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Crescita ≥</span> {state.growthMin}
                <button onClick={() => onChange({ ...state, growthMin: null })} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia crescita"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.valueMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Valore ≥</span> {state.valueMin}
                <button onClick={() => onChange({ ...state, valueMin: null })} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia valore"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.sentimentMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Sentiment ≥</span> {state.sentimentMin}
                <button onClick={() => onChange({ ...state, sentimentMin: null })} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia sentiment"><X className="h-3 w-3" /></button>
              </Badge>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
