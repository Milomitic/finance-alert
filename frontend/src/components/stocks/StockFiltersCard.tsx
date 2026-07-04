import { Bookmark, ChevronDown, Filter, X } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";

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
  /** Tipo strumento: true = escludi le righe ETF/ETN (instrument_type='etf'). */
  excludeEtf: boolean;
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
  // --- Fondamentali: market cap range (absolute dollars, null = no bound) ---
  marketCapMin: number | null;
  marketCapMax: number | null;
  // --- Tecnici (EOD metrics) ---
  /** RSI-14 range 0-100, or null = no bound. */
  rsiMin: number | null;
  rsiMax: number | null;
  /** Bool toggles. False = inactive (no predicate sent). */
  aboveEma50: boolean;
  aboveEma200: boolean;
  near52wHigh: boolean;
  near52wLow: boolean;
  hasSignals: boolean;
  // --- Prezzo & Volume (EOD metrics) ---
  /** Price range in listing currency, or null = no bound. */
  priceMin: number | null;
  priceMax: number | null;
  /** Daily % change range (can be negative), or null = no bound. */
  changeMin: number | null;
  changeMax: number | null;
  /** Volume spike: vol_ratio > 2×. */
  volSpike: boolean;
  /** Minimum today's volume (share count), or null. */
  volumeMin: number | null;
}

/** The all-clear filter state. Single source of truth for "no filters":
 *  used by the Reset button AND as the base when applying a saved preset,
 *  so presets saved before new filter fields were added stay valid. */
export const EMPTY_FILTERS: FiltersState = {
  indexCodes: [], sectors: [], industries: [], exchanges: [], countries: [],
  riskTiers: [], excludeEtf: false, minScore: null, scoreMax: null,
  profitabilityMin: null, sustainabilityMin: null, growthMin: null,
  valueMin: null, sentimentMin: null,
  techMin: null, postures: [],
  marketCapMin: null, marketCapMax: null,
  rsiMin: null, rsiMax: null,
  aboveEma50: false, aboveEma200: false, near52wHigh: false, near52wLow: false,
  hasSignals: false,
  priceMin: null, priceMax: null, changeMin: null, changeMax: null,
  volSpike: false, volumeMin: null,
};

const PRESETS_KEY = "screenerFilterPresets";

function loadPresets(): Record<string, FiltersState> {
  try {
    const parsed = JSON.parse(localStorage.getItem(PRESETS_KEY) ?? "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

/** Saved filter presets (localStorage): save the current FiltersState under a
 *  name, re-apply with one click, delete. Applying merges the preset over
 *  EMPTY_FILTERS so fields added after the preset was saved get sane defaults. */
function PresetsMenu({
  state,
  onChange,
}: {
  state: FiltersState;
  onChange: (next: FiltersState) => void;
}) {
  const [presets, setPresets] = useState<Record<string, FiltersState>>(loadPresets);
  const [name, setName] = useState("");
  const persist = (next: Record<string, FiltersState>) => {
    setPresets(next);
    try {
      localStorage.setItem(PRESETS_KEY, JSON.stringify(next));
    } catch {
      /* storage full/unavailable — presets stay in-memory for the session */
    }
  };
  const save = () => {
    const n = name.trim();
    if (!n) return;
    persist({ ...presets, [n]: state });
    setName("");
  };
  const names = Object.keys(presets).sort((a, b) => a.localeCompare(b));
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5">
          <Bookmark className="h-3.5 w-3.5" />
          Preset
          {names.length > 0 && (
            <Badge variant="secondary" className="h-4 px-1 text-[10px]">
              {names.length}
            </Badge>
          )}
          <ChevronDown className="h-3 w-3 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-0">
        <div className="px-3 py-2 border-b">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Preset filtri
          </span>
        </div>
        <div className="max-h-60 overflow-y-auto p-1">
          {names.length === 0 ? (
            <div className="text-xs text-muted-foreground p-3">
              Nessun preset salvato. Imposta i filtri e salvali qui sotto.
            </div>
          ) : (
            <ul>
              {names.map((n) => (
                <li key={n} className="flex items-center gap-1 rounded hover:bg-accent">
                  <button
                    type="button"
                    onClick={() => onChange({ ...EMPTY_FILTERS, ...presets[n] })}
                    className="flex-1 text-left px-2 py-1.5 text-sm truncate"
                    title={`Applica il preset "${n}"`}
                  >
                    {n}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const next = { ...presets };
                      delete next[n];
                      persist(next);
                    }}
                    className="p-1 mr-1 rounded hover:bg-background/60 text-muted-foreground"
                    aria-label={`Elimina preset ${n}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="flex items-center gap-1.5 p-2 border-t">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
            }}
            placeholder="Nome preset…"
            className="flex-1 h-8 px-2 text-sm rounded border border-input bg-transparent focus:outline-none"
          />
          <Button size="sm" className="h-8 text-xs" onClick={save} disabled={!name.trim()}>
            Salva
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
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

/** Generic min–max number range with a label. Used for ranges that aren't
 *  the bounded 0-100 score inputs (price, Δ%, market cap, RSI, volume).
 *  `allowNegative` lets the Δ% range accept negatives; otherwise values are
 *  clamped to ≥ 0. Each bound is independent (either can be null). */
function NumberRange({
  label,
  min,
  max,
  onMinChange,
  onMaxChange,
  step = 1,
  allowNegative = false,
  minPlaceholder = "min",
  maxPlaceholder = "max",
  suffix,
  width = "w-14",
}: {
  label: string;
  min: number | null;
  max: number | null;
  onMinChange: (v: number | null) => void;
  onMaxChange: (v: number | null) => void;
  step?: number;
  allowNegative?: boolean;
  minPlaceholder?: string;
  maxPlaceholder?: string;
  suffix?: string;
  width?: string;
}) {
  const parse = (raw: string, set: (v: number | null) => void) => {
    if (raw === "") { set(null); return; }
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    if (!allowNegative && n < 0) return;
    set(n);
  };
  const inputCls =
    "bg-transparent text-sm tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none";
  return (
    <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input">
      <span className="text-xs text-muted-foreground">{label}</span>
      <input
        type="number"
        step={step}
        placeholder={minPlaceholder}
        value={min ?? ""}
        onChange={(e) => parse(e.target.value, onMinChange)}
        className={cn(inputCls, width)}
      />
      <span className="text-xs text-muted-foreground">–</span>
      <input
        type="number"
        step={step}
        placeholder={maxPlaceholder}
        value={max ?? ""}
        onChange={(e) => parse(e.target.value, onMaxChange)}
        className={cn(inputCls, width)}
      />
      {suffix && <span className="text-xs text-muted-foreground">{suffix}</span>}
    </div>
  );
}

/** Single bool toggle rendered as a pill button. Active = primary fill. */
function ToggleChip({
  label,
  active,
  onToggle,
}: {
  label: string;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "h-9 px-3 rounded border text-sm font-medium transition-colors",
        active
          ? "bg-primary text-primary-foreground border-primary"
          : "border-input text-muted-foreground hover:bg-muted",
      )}
    >
      {label}
    </button>
  );
}

/** Keys for the 4 collapsible filter areas. Open/closed state persists in
 *  localStorage under `screenerFilterAreas`. */
type AreaKey = "mercato" | "fondamentali" | "tecnici" | "prezzoVolume";

const AREA_DEFAULT_OPEN: Record<AreaKey, boolean> = {
  mercato: true,
  fondamentali: false,
  tecnici: false,
  prezzoVolume: false,
};

const AREAS_STORAGE_KEY = "screenerFilterAreas";

function useFilterAreas() {
  const [open, setOpen] = useState<Record<AreaKey, boolean>>(() => {
    try {
      const raw = localStorage.getItem(AREAS_STORAGE_KEY);
      if (raw) return { ...AREA_DEFAULT_OPEN, ...JSON.parse(raw) };
    } catch { /* ignore */ }
    return AREA_DEFAULT_OPEN;
  });
  useEffect(() => {
    try { localStorage.setItem(AREAS_STORAGE_KEY, JSON.stringify(open)); } catch { /* ignore */ }
  }, [open]);
  const toggle = useCallback((k: AreaKey) => {
    setOpen((prev) => ({ ...prev, [k]: !prev[k] }));
  }, []);
  return { open, toggle };
}

/** A labeled, collapsible filter section. The header shows a count badge of
 *  active filters inside it and a chevron; the body holds the controls. */
function CollapsibleArea({
  title,
  activeCount,
  isOpen,
  onToggle,
  children,
}: {
  title: string;
  activeCount: number;
  isOpen: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border border-border/60">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        aria-expanded={isOpen}
      >
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          {title}
        </span>
        {activeCount > 0 && (
          <Badge variant="secondary" className="h-4 px-1 text-[10px]">
            {activeCount}
          </Badge>
        )}
        <ChevronDown
          className={cn(
            "ml-auto h-4 w-4 text-muted-foreground transition-transform",
            isOpen && "rotate-180",
          )}
        />
      </button>
      {isOpen && (
        <div className="px-3 pb-3 pt-1">
          {children}
        </div>
      )}
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

  const { open: areaOpen, toggle: toggleArea } = useFilterAreas();

  const set = (patch: Partial<FiltersState>) => onChange({ ...state, ...patch });

  const pillarActiveCount =
    (state.profitabilityMin != null ? 1 : 0) +
    (state.sustainabilityMin != null ? 1 : 0) +
    (state.growthMin != null ? 1 : 0) +
    (state.valueMin != null ? 1 : 0) +
    (state.sentimentMin != null ? 1 : 0);

  // Per-area active counts (drive the badge on each collapsible header).
  const mercatoActive =
    state.indexCodes.length + state.sectors.length + state.industries.length +
    state.exchanges.length + state.countries.length +
    (state.excludeEtf ? 1 : 0);

  const fondamentaliActive =
    (state.minScore != null ? 1 : 0) +
    (state.scoreMax != null ? 1 : 0) +
    state.riskTiers.length +
    pillarActiveCount +
    (state.marketCapMin != null ? 1 : 0) +
    (state.marketCapMax != null ? 1 : 0);

  const tecniciActive =
    (state.techMin != null ? 1 : 0) +
    state.postures.length +
    (state.rsiMin != null ? 1 : 0) +
    (state.rsiMax != null ? 1 : 0) +
    (state.aboveEma50 ? 1 : 0) +
    (state.aboveEma200 ? 1 : 0) +
    (state.near52wHigh ? 1 : 0) +
    (state.near52wLow ? 1 : 0) +
    (state.hasSignals ? 1 : 0);

  const prezzoVolumeActive =
    (state.priceMin != null ? 1 : 0) +
    (state.priceMax != null ? 1 : 0) +
    (state.changeMin != null ? 1 : 0) +
    (state.changeMax != null ? 1 : 0) +
    (state.volSpike ? 1 : 0) +
    (state.volumeMin != null ? 1 : 0);

  const totalActive = mercatoActive + fondamentaliActive + tecniciActive + prezzoVolumeActive;

  const clearAll = () => onChange({ ...EMPTY_FILTERS });

  const removeChip = (kind: keyof FiltersState, value: string) => {
    if (kind === "riskTiers") {
      onChange({ ...state, riskTiers: state.riskTiers.filter((v) => v !== value) });
      return;
    }
    if (
      kind === "indexCodes" || kind === "sectors" || kind === "industries" ||
      kind === "exchanges" || kind === "countries" || kind === "postures"
    ) {
      onChange({ ...state, [kind]: (state[kind] as string[]).filter((v) => v !== value) });
      return;
    }
    // Everything else is a scalar/bool filter → reset to its empty value.
    const isBool =
      kind === "aboveEma50" || kind === "aboveEma200" ||
      kind === "near52wHigh" || kind === "near52wLow" ||
      kind === "hasSignals" || kind === "volSpike" ||
      kind === "excludeEtf";
    onChange({ ...state, [kind]: isBool ? false : null });
  };

  // Market cap is stored in absolute dollars but entered/displayed in
  // billions. These helpers convert at the input boundary only.
  const mcToBillions = (v: number | null) => (v == null ? null : v / 1e9);
  const mcFromBillions = (v: number | null) => (v == null ? null : v * 1e9);

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        {/* Header row: label + total badge + global reset. */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
            <Filter className="h-4 w-4" />
            <span>Filtri</span>
            {totalActive > 0 && (
              <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                {totalActive} attivi
              </Badge>
            )}
          </div>
          <PresetsMenu state={state} onChange={onChange} />
          {totalActive > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearAll}
              className="h-8 text-sm text-muted-foreground ml-auto"
            >
              <X className="h-3.5 w-3.5 mr-1" /> Reset
            </Button>
          )}
        </div>

        {/* ─── Area 1: Mercato (classification) ─── */}
        <CollapsibleArea
          title="Mercato"
          activeCount={mercatoActive}
          isOpen={areaOpen.mercato}
          onToggle={() => toggleArea("mercato")}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <MultiSelect
              label="Indice"
              options={indexOptions}
              selected={state.indexCodes}
              onChange={(v) => set({ indexCodes: v })}
            />
            <MultiSelect
              label="Settore"
              options={sectorOptions}
              selected={state.sectors}
              onChange={(v) => set({ sectors: v })}
            />
            <MultiSelect
              label="Industry"
              options={industryOptions}
              selected={state.industries}
              onChange={(v) => set({ industries: v })}
            />
            <MultiSelect
              label="Exchange"
              options={exchangeOptions}
              selected={state.exchanges}
              onChange={(v) => set({ exchanges: v })}
            />
            <MultiSelect
              label="Paese"
              options={countryOptions}
              selected={state.countries}
              onChange={(v) => set({ countries: v })}
            />
            {/* Tipo strumento: gli ETF/ETN (24 prodotti NYSE Arca) non hanno
                score Qualità per design — questo toggle li nasconde. */}
            <ToggleChip
              label="Escludi ETF"
              active={state.excludeEtf}
              onToggle={() => set({ excludeEtf: !state.excludeEtf })}
            />
          </div>
        </CollapsibleArea>

        {/* ─── Area 2: Fondamentali ─── */}
        <CollapsibleArea
          title="Fondamentali"
          activeCount={fondamentaliActive}
          isOpen={areaOpen.fondamentali}
          onToggle={() => toggleArea("fondamentali")}
        >
          <div className="flex items-center gap-2 flex-wrap">
            {/* Composite score range: min + max inline. */}
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
                  if (raw === "") { set({ minScore: null }); return; }
                  const n = Number(raw);
                  if (Number.isFinite(n) && n >= 0 && n <= 100) set({ minScore: n });
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
                  if (raw === "") { set({ scoreMax: null }); return; }
                  const n = Number(raw);
                  if (Number.isFinite(n) && n >= 0 && n <= 100) set({ scoreMax: n });
                }}
                className="w-10 bg-transparent text-sm tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              />
            </div>
            <MultiSelect
              label="Rischio"
              options={RISK_OPTIONS}
              selected={state.riskTiers}
              onChange={(v) => set({ riskTiers: v as FiltersState["riskTiers"] })}
            />
            {/* Market cap range — entered in billions, stored in absolute $. */}
            <NumberRange
              label="Mkt cap"
              suffix="B$"
              step={1}
              min={mcToBillions(state.marketCapMin)}
              max={mcToBillions(state.marketCapMax)}
              onMinChange={(v) => set({ marketCapMin: mcFromBillions(v) })}
              onMaxChange={(v) => set({ marketCapMax: mcFromBillions(v) })}
            />
          </div>
          {/* Per-pillar minimum scores grid. */}
          <div className="mt-3 pt-3 border-t border-border/40">
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
                onChange={(v) => set({ profitabilityMin: v })}
              />
              <PillarInput
                label={CATEGORY_LABEL.sustainability}
                value={state.sustainabilityMin}
                onChange={(v) => set({ sustainabilityMin: v })}
              />
              <PillarInput
                label={CATEGORY_LABEL.growth}
                value={state.growthMin}
                onChange={(v) => set({ growthMin: v })}
              />
              <PillarInput
                label={CATEGORY_LABEL.value}
                value={state.valueMin}
                onChange={(v) => set({ valueMin: v })}
              />
              <PillarInput
                label={CATEGORY_LABEL.sentiment}
                value={state.sentimentMin}
                onChange={(v) => set({ sentimentMin: v })}
              />
            </div>
          </div>
        </CollapsibleArea>

        {/* ─── Area 3: Tecnici ─── */}
        <CollapsibleArea
          title="Tecnici"
          activeCount={tecniciActive}
          isOpen={areaOpen.tecnici}
          onToggle={() => toggleArea("tecnici")}
        >
          <div className="flex items-center gap-2 flex-wrap">
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
                  if (raw === "") { set({ techMin: null }); return; }
                  const n = Number(raw);
                  if (Number.isFinite(n) && n >= 0 && n <= 100) set({ techMin: n });
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
                    onClick={() => set({ postures: on ? state.postures.filter((x) => x !== pp) : [...state.postures, pp] })}
                    className={cn("px-1.5 py-0.5 rounded text-xs font-medium", on ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}
                  >
                    {pp}
                  </button>
                );
              })}
            </div>
            {/* RSI 0-100 range. */}
            <NumberRange
              label="RSI"
              step={1}
              min={state.rsiMin}
              max={state.rsiMax}
              onMinChange={(v) => set({ rsiMin: v == null ? null : Math.min(100, Math.max(0, v)) })}
              onMaxChange={(v) => set({ rsiMax: v == null ? null : Math.min(100, Math.max(0, v)) })}
              width="w-12"
            />
            <ToggleChip label="sopra EMA200" active={state.aboveEma200} onToggle={() => set({ aboveEma200: !state.aboveEma200 })} />
            <ToggleChip label="sopra EMA50" active={state.aboveEma50} onToggle={() => set({ aboveEma50: !state.aboveEma50 })} />
            <ToggleChip label="vicino max 52s" active={state.near52wHigh} onToggle={() => set({ near52wHigh: !state.near52wHigh })} />
            <ToggleChip label="vicino min 52s" active={state.near52wLow} onToggle={() => set({ near52wLow: !state.near52wLow })} />
            <ToggleChip label="con segnali" active={state.hasSignals} onToggle={() => set({ hasSignals: !state.hasSignals })} />
          </div>
        </CollapsibleArea>

        {/* ─── Area 4: Prezzo & Volume ─── */}
        <CollapsibleArea
          title="Prezzo & Volume"
          activeCount={prezzoVolumeActive}
          isOpen={areaOpen.prezzoVolume}
          onToggle={() => toggleArea("prezzoVolume")}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <NumberRange
              label="Prezzo"
              step={1}
              min={state.priceMin}
              max={state.priceMax}
              onMinChange={(v) => set({ priceMin: v })}
              onMaxChange={(v) => set({ priceMax: v })}
            />
            <NumberRange
              label="Δ%"
              step={0.5}
              allowNegative
              min={state.changeMin}
              max={state.changeMax}
              onMinChange={(v) => set({ changeMin: v })}
              onMaxChange={(v) => set({ changeMax: v })}
              width="w-12"
            />
            <ToggleChip label="vol spike >2×" active={state.volSpike} onToggle={() => set({ volSpike: !state.volSpike })} />
            {/* Volume min (share count). Wide-ish single input. */}
            <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input">
              <span className="text-xs text-muted-foreground">Vol min</span>
              <input
                type="number"
                min={0}
                step={100000}
                placeholder="azioni"
                value={state.volumeMin ?? ""}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === "") { set({ volumeMin: null }); return; }
                  const n = Number(raw);
                  if (Number.isFinite(n) && n >= 0) set({ volumeMin: n });
                }}
                className="w-20 bg-transparent text-sm tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              />
            </div>
          </div>
        </CollapsibleArea>

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
            {state.excludeEtf && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                Escludi ETF
                <button
                  onClick={() => removeChip("excludeEtf", "")}
                  className="ml-0.5 rounded hover:bg-background/60 p-0.5"
                  aria-label="Rimuovi filtro escludi ETF"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            )}
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
            {state.marketCapMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Mkt cap ≥</span> {(state.marketCapMin / 1e9).toFixed(0)}B$
                <button onClick={() => removeChip("marketCapMin", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia market cap minima"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.marketCapMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Mkt cap ≤</span> {(state.marketCapMax / 1e9).toFixed(0)}B$
                <button onClick={() => removeChip("marketCapMax", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia market cap massima"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.techMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Tecnico ≥</span> {state.techMin}
                <button onClick={() => removeChip("techMin", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia tecnico"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.postures.map((v) => (
              <Badge key={`p-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Postura:</span> {v}
                <button onClick={() => removeChip("postures", v)} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label={`Rimuovi postura ${v}`}><X className="h-3 w-3" /></button>
              </Badge>
            ))}
            {state.rsiMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">RSI ≥</span> {state.rsiMin}
                <button onClick={() => removeChip("rsiMin", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia RSI minima"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.rsiMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">RSI ≤</span> {state.rsiMax}
                <button onClick={() => removeChip("rsiMax", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia RSI massima"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.aboveEma200 && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                sopra EMA200
                <button onClick={() => removeChip("aboveEma200", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi filtro sopra EMA200"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.aboveEma50 && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                sopra EMA50
                <button onClick={() => removeChip("aboveEma50", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi filtro sopra EMA50"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.near52wHigh && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                vicino max 52s
                <button onClick={() => removeChip("near52wHigh", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi filtro vicino massimo 52 settimane"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.near52wLow && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                vicino min 52s
                <button onClick={() => removeChip("near52wLow", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi filtro vicino minimo 52 settimane"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.hasSignals && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                con segnali
                <button onClick={() => removeChip("hasSignals", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi filtro con segnali"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.priceMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Prezzo ≥</span> {state.priceMin}
                <button onClick={() => removeChip("priceMin", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia prezzo minima"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.priceMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Prezzo ≤</span> {state.priceMax}
                <button onClick={() => removeChip("priceMax", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia prezzo massima"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.changeMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Δ% ≥</span> {state.changeMin}
                <button onClick={() => removeChip("changeMin", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia variazione minima"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.changeMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Δ% ≤</span> {state.changeMax}
                <button onClick={() => removeChip("changeMax", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia variazione massima"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.volSpike && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                vol spike &gt;2×
                <button onClick={() => removeChip("volSpike", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi filtro volume spike"><X className="h-3 w-3" /></button>
              </Badge>
            )}
            {state.volumeMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground/80">Vol ≥</span> {state.volumeMin.toLocaleString()}
                <button onClick={() => removeChip("volumeMin", "")} className="ml-0.5 rounded hover:bg-background/60 p-0.5" aria-label="Rimuovi soglia volume minima"><X className="h-3 w-3" /></button>
              </Badge>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
