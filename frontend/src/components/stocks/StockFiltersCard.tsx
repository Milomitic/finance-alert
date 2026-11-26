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
import { conteggiFiltri, EMPTY_FILTERS } from "@/lib/screenerFilters";
import {
  parseAll,
  toStored,
  type ScreenerView,
  type SortDirection,
} from "@/lib/screenerViews";

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
  /** Solo i titoli con i fondamentali completi al 90% o piu' (FA-156). */
  datiCompleti: boolean;
  /** Solo i titoli in posizione o fra i preferiti (C-33). */
  soloMiei: boolean;
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
  /** Finestra "con segnali": null = filtro spento; altrimenti giorni entro
   *  cui il segnale deve essere scattato (1 = Oggi, 7, 30). Sostituisce il
   *  vecchio toggle senza limite temporale (che accendeva ~99% dei titoli). */
  signalsWithinDays: number | null;
  // --- Prezzo & Volume (EOD metrics) ---
  /** Price range in listing currency, or null = no bound. */
  priceMin: number | null;
  priceMax: number | null;
  /** Daily % change range (can be negative), or null = no bound. */
  changeMin: number | null;
  changeMax: number | null;
  /** Volume spike: vol_ratio > 2×. */
  volSpike: boolean;
  /** Soglia continua sul vol_ratio (≥, es. 1.5×), or null. Variante
   *  regolabile del preset fisso volSpike. */
  volRatioMin: number | null;
  /** Minimum today's volume (share count), or null. */
  volumeMin: number | null;
}

/** Le finestre offerte dal filtro "con segnali". 1 = solo l'ultima seduta. */
/* Non esportato: nessun altro file lo legge. */
const SIGNAL_WINDOW_OPTIONS: { days: number; label: string }[] = [
  { days: 1, label: "Oggi" },
  { days: 7, label: "7g" },
  { days: 30, label: "30g" },
];

function signalsWindowLabel(days: number): string {
  return SIGNAL_WINDOW_OPTIONS.find((o) => o.days === days)?.label ?? `${days}g`;
}

/** Merge a saved preset over EMPTY_FILTERS (fields added after the preset was
 *  saved get sane defaults) and migrate the legacy `hasSignals` boolean to the
 *  new `signalsWithinDays` window (7 giorni — the closest honest equivalent
 *  of the old unbounded toggle). */
function normalizePreset(saved: FiltersState): FiltersState {
  const legacy = (saved as unknown as { hasSignals?: boolean }).hasSignals;
  const next: FiltersState = { ...EMPTY_FILTERS, ...saved };
  if (legacy && next.signalsWithinDays == null) next.signalsWithinDays = 7;
  delete (next as unknown as { hasSignals?: boolean }).hasSignals;
  return next;
}

const PRESETS_KEY = "screenerFilterPresets";

/** What a saved view records BEYOND the filters. Optional so the card still
 *  works where no table sits under it: without this the menu quietly saves a
 *  sort of "ticker/asc" for a caller that has no sort at all, and applying it
 *  would look like a bug in the table rather than in the wiring. */
export interface ViewContext {
  sortBy: string;
  sortDir: SortDirection;
  hiddenColumns: string[];
  defaults: { sortBy: string; sortDir: SortDirection };
  onApply: (view: ScreenerView<FiltersState>) => void;
}

function loadPresets(
  defaults: { sortBy: string; sortDir: SortDirection },
): Record<string, ScreenerView<FiltersState>> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(PRESETS_KEY) ?? "{}");
    // Reads BOTH shapes: the bare filter objects saved before views existed,
    // and the versioned envelope. The migration happens here so nobody has to
    // run anything and no saved work is lost.
    return parseAll<FiltersState>(parsed, defaults, (raw) => normalizePreset(raw as FiltersState));
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
  view,
}: {
  state: FiltersState;
  onChange: (next: FiltersState) => void;
  view?: ViewContext;
}) {
  const defaults = view?.defaults ?? { sortBy: "ticker", sortDir: "asc" as SortDirection };
  const [presets, setPresets] = useState<Record<string, ScreenerView<FiltersState>>>(() =>
    loadPresets(defaults),
  );
  const [name, setName] = useState("");
  // C-30: la vista applicata o salvata per ultima, detta sul bottone; e la
  // vista di cui si e' chiesta l'eliminazione, che si conferma col secondo tocco.
  const [attiva, setAttiva] = useState<string | null>(null);
  const [daEliminare, setDaEliminare] = useState<string | null>(null);
  const persist = (next: Record<string, ScreenerView<FiltersState>>) => {
    setPresets(next);
    try {
      localStorage.setItem(
        PRESETS_KEY,
        JSON.stringify(Object.fromEntries(Object.entries(next).map(([k, v]) => [k, toStored(v)]))),
      );
    } catch {
      /* storage full/unavailable — presets stay in-memory for the session */
    }
  };
  const save = () => {
    const n = name.trim();
    if (!n) return;
    // The whole configuration, not just the filters: a view that restored the
    // filters and left the sort and columns as they were is the gap this
    // replaces.
    persist({
      ...presets,
      [n]: {
        filters: state,
        sortBy: view?.sortBy ?? defaults.sortBy,
        sortDir: view?.sortDir ?? defaults.sortDir,
        hiddenColumns: view?.hiddenColumns ?? [],
      },
    });
    setAttiva(n);
    setName("");
  };
  // Un nome gia' usato si SOSTITUISCE solo dicendolo: prima sovrascriveva in
  // silenzio (C-30).
  const esiste = name.trim() !== "" && name.trim() in presets;
  const names = Object.keys(presets).sort((a, b) => a.localeCompare(b));
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5">
          <Bookmark className="h-3.5 w-3.5" />
          {/* Un nome solo, «Viste», sul bottone e nel pannello (C-30). */}
          {attiva && attiva in presets ? (
            <span className="max-w-[10rem] truncate">Vista: {attiva}</span>
          ) : (
            "Viste"
          )}
          {names.length > 0 && !(attiva && attiva in presets) && (
            <Badge variant="secondary" className="h-4 px-1 text-[0.6765rem]">
              {names.length}
            </Badge>
          )}
          <ChevronDown className="h-3 w-3 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-0">
        <div className="px-3 py-2 border-b">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Viste salvate
          </span>
        </div>
        <div className="max-h-60 overflow-y-auto p-1">
          {names.length === 0 ? (
            <div className="text-xs text-muted-foreground p-3">
              {view
                ? "Nessuna vista salvata. Imposta filtri, ordinamento e colonne, poi salvali qui sotto."
                : "Nessuna vista salvata. Imposta i filtri e salvali qui sotto."}
            </div>
          ) : (
            <ul>
              {names.map((n) => (
                <li key={n} className="flex items-center gap-1 rounded hover:bg-accent">
                  <button
                    type="button"
                    onClick={() => {
                      const saved = presets[n];
                      // Without a table under us only the filters can be
                      // restored, and saying so beats half-restoring silently.
                      if (view) view.onApply(saved);
                      else onChange(saved.filters);
                      setAttiva(n);
                    }}
                    className="flex-1 text-left px-2 py-1.5 text-sm truncate"
                    title={view ? `Applica la vista "${n}": filtri, ordinamento e colonne` : `Applica la vista "${n}"`}
                  >
                    {n}
                  </button>
                  {n === attiva && <span className="shrink-0 text-xs text-muted-foreground">attiva</span>}
                  {/* Eliminare chiede un secondo tocco (C-30): prima spariva
                      al primo, senza annullare. */}
                  <button
                    type="button"
                    onClick={() => {
                      if (daEliminare !== n) {
                        setDaEliminare(n);
                        return;
                      }
                      const next = { ...presets };
                      delete next[n];
                      persist(next);
                      setDaEliminare(null);
                      if (attiva === n) setAttiva(null);
                    }}
                    onBlur={() => setDaEliminare((d) => (d === n ? null : d))}
                    className={cn(
                      "mr-1 rounded p-1 text-xs hover:bg-background/60",
                      daEliminare === n ? "font-semibold text-red-700 dark:text-red-300" : "text-muted-foreground",
                    )}
                    aria-label={daEliminare === n ? `Conferma: elimina la vista ${n}` : `Elimina la vista ${n}`}
                  >
                    {daEliminare === n ? "Elimina?" : <X className="h-3.5 w-3.5" />}
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
            aria-label="Nome della vista da salvare"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
            }}
            placeholder="Nome della vista…"
            className="flex-1 h-8 px-2 text-sm rounded border border-input bg-transparent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          <Button size="sm" className="h-8 text-xs" onClick={save} disabled={!name.trim()}>
            {esiste ? "Sostituisci" : "Salva"}
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
  /** Sort and columns, so a saved view is the whole configuration. Optional:
   *  where the card renders without a table under it, the menu keeps its old
   *  filters-only behaviour rather than pretending to restore a sort. */
  view?: ViewContext;
  /** La ricerca testuale della tabella (C-29): conta fra i filtri attivi, ha
   *  il suo chip e «Reset» la cancella. Viveva fuori dal sistema dei filtri,
   *  e uno schermo con tre righe non diceva cosa le avesse ridotte. */
  ricerca?: { q: string; onClear: () => void };
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
              <Badge variant="default" className="h-5 px-1.5 text-[0.6765rem] font-semibold">
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
            <Button
              onClick={clear}
              variant="link" size="testo" className="text-xs text-muted-foreground hover:text-foreground"
            >
              Pulisci
            </Button>
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
  { value: "conservative", label: "Conservative", tone: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-300" },
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
      <div className="inline-flex items-center gap-1 h-7 px-1.5 rounded border border-input focus-within:ring-1 focus-within:ring-ring">
        <span className="text-xs text-muted-foreground">≥</span>
        <input
          type="number"
          min={0}
          max={100}
          step={5}
          aria-label={`${label} minimo`}
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
    <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input focus-within:ring-1 focus-within:ring-ring">
      <span className="text-xs text-muted-foreground">{label}</span>
      <input
        type="number"
        step={step}
        aria-label={`${label} minimo`}
        placeholder={minPlaceholder}
        value={min ?? ""}
        onChange={(e) => parse(e.target.value, onMinChange)}
        className={cn(inputCls, width)}
      />
      <span className="text-xs text-muted-foreground">–</span>
      <input
        type="number"
        step={step}
        aria-label={`${label} massimo`}
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
          <Badge variant="secondary" className="h-4 px-1 text-[0.6765rem]">
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



/** Il bottone che toglie un filtro dal suo chip. Era scritto a mano 33
 *  volte in questo file, identico (B-39): un componente solo, con l'anello
 *  di focus dei primitivi. */
function RimuoviChip({ onClick, etichetta }: { onClick: () => void; etichetta: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="ml-0.5 rounded p-0.5 hover:bg-background/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={etichetta}
    >
      <X className="h-3 w-3" aria-hidden />
    </button>
  );
}
export function StockFiltersCard({ state, onChange, filters, view, ricerca }: Props) {
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

  // Un proprietario solo per i conteggi (`lib/screenerFilters`): li legge
  // anche il pulsante «Filtri (N)» del telefono (C-31).
  const conteggi = conteggiFiltri(state);
  const mercatoActive = conteggi.mercato;
  const fondamentaliActive = conteggi.fondamentali;
  const tecniciActive = conteggi.tecnici;
  const prezzoVolumeActive = conteggi.prezzoVolume;
  const cercato = ricerca?.q.trim() ?? "";
  const totalActive = conteggi.totale + (cercato ? 1 : 0);
  const pillarActiveCount = conteggi.pilastri;

  const clearAll = () => {
    onChange({ ...EMPTY_FILTERS });
    ricerca?.onClear();
  };

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
      kind === "volSpike" || kind === "excludeEtf" || kind === "datiCompleti" || kind === "soloMiei";
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
              <Badge variant="secondary" className="h-5 px-1.5 text-[0.6765rem]">
                {totalActive} attivi
              </Badge>
            )}
          </div>
          <PresetsMenu state={state} onChange={onChange} view={view} />
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

        {/* Le quattro aree su DUE COLONNE dai monitor larghi in su.
         *
         * Impilate, ognuna occupava una riga intera per una manciata di
         * controlli che finivano entro i primi 700-1200px: su uno schermo da
         * 2000px il pannello era alto il doppio del necessario con meta
         * schermo vuoto a destra.
         *
         * `items-start` e load-bearing: senza, le aree si stirano all altezza
         * della riga e quella piu corta diventa una scatola mezza vuota, che e
         * peggio del problema di partenza.
         *
         * L ordine DOM decide l accoppiamento (row-major): Mercato con
         * Fondamentali, Tecnici con Prezzo. Non e casuale — accoppia la piu
         * alta (Fondamentali, che porta il blocco pillar) con la piu bassa
         * (Mercato), cosi le due righe si bilanciano invece di sommare due
         * massimi. */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 items-start">
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
              {/* C-33: la home rimanda «sui tuoi titoli», e lo screener non
                  sapeva restringersi a loro. Posizioni aperte o preferiti. */}
              <ToggleChip
                label="I miei titoli"
                active={state.soloMiei}
                onToggle={() => set({ soloMiei: !state.soloMiei })}
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
              {/* FA-156: i punteggi di un titolo con meta' bilancio mancante
                  sono stime su poco. Stessa soglia della scheda fondamentali. */}
              <ToggleChip
                label="Dati completi"
                active={state.datiCompleti}
                onToggle={() => set({ datiCompleti: !state.datiCompleti })}
              />
              {/* Composite score range: min + max inline. */}
              <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input focus-within:ring-1 focus-within:ring-ring">
                <span className="text-xs text-muted-foreground">Score</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  placeholder="min"
                  aria-label="Score minimo"
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
                  aria-label="Score massimo"
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
                  <Badge variant="secondary" className="h-4 px-1 text-[0.6765rem]">
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
              <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input focus-within:ring-1 focus-within:ring-ring">
                <span className="text-xs text-muted-foreground">Tecnico</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  placeholder="min"
                  aria-label="Punteggio tecnico minimo"
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
              <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input focus-within:ring-1 focus-within:ring-ring">
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
              {/* "Con segnali" con finestra di recenza — pill group come la
                  Postura. Cliccare la finestra attiva la spegne (toggle). */}
              <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input focus-within:ring-1 focus-within:ring-ring">
                <span className="text-xs text-muted-foreground">Segnali</span>
                {SIGNAL_WINDOW_OPTIONS.map((opt) => {
                  const on = state.signalsWithinDays === opt.days;
                  return (
                    <button
                      key={opt.days}
                      type="button"
                      onClick={() => set({ signalsWithinDays: on ? null : opt.days })}
                      title={`Solo titoli con segnali negli ultimi ${opt.days === 1 ? "1 giorno" : `${opt.days} giorni`}`}
                      className={cn("px-1.5 py-0.5 rounded text-xs font-medium", on ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
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
              {/* Soglia continua Vol× — la sorella regolabile del preset
                  vol spike (>2×): es. 1.5 = volume ≥ 1.5× la media 20g. */}
              <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input focus-within:ring-1 focus-within:ring-ring">
                <span className="text-xs text-muted-foreground">Vol× ≥</span>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  placeholder="—"
                  aria-label="Rapporto volume minimo"
                  value={state.volRatioMin ?? ""}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === "") { set({ volRatioMin: null }); return; }
                    const n = Number(raw);
                    if (Number.isFinite(n) && n >= 0) set({ volRatioMin: n });
                  }}
                  className="w-12 bg-transparent text-sm tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                />
              </div>
              {/* Volume min (share count). Wide-ish single input. */}
              <div className="inline-flex items-center gap-1 h-9 px-2 rounded border border-input focus-within:ring-1 focus-within:ring-ring">
                <span className="text-xs text-muted-foreground">Vol min</span>
                <input
                  type="number"
                  min={0}
                  step={100000}
                  placeholder="azioni"
                  aria-label="Volume minimo in azioni"
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
        </div>

        {totalActive > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-border/50">
            <span className="text-xs text-muted-foreground mr-1">Attivi:</span>
            {cercato && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Cerca:</span> {cercato}
                <RimuoviChip onClick={() => ricerca?.onClear()} etichetta={`Rimuovi la ricerca ${cercato}`} />
              </Badge>
            )}
            {state.indexCodes.map((v) => (
              <Badge key={`i-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Indice:</span> {v}
                <RimuoviChip onClick={() => removeChip("indexCodes", v)} etichetta={`Rimuovi indice ${v}`} />
              </Badge>
            ))}
            {state.sectors.map((v) => (
              <Badge key={`s-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Settore:</span> {v}
                <RimuoviChip onClick={() => removeChip("sectors", v)} etichetta={`Rimuovi settore ${v}`} />
              </Badge>
            ))}
            {state.industries.map((v) => (
              <Badge key={`ind-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Industry:</span> {v}
                <RimuoviChip onClick={() => removeChip("industries", v)} etichetta={`Rimuovi industry ${v}`} />
              </Badge>
            ))}
            {state.exchanges.map((v) => (
              <Badge key={`e-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Exchange:</span> {v}
                <RimuoviChip onClick={() => removeChip("exchanges", v)} etichetta={`Rimuovi exchange ${v}`} />
              </Badge>
            ))}
            {state.countries.map((v) => (
              <Badge key={`c-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Paese:</span> {v}
                <RimuoviChip onClick={() => removeChip("countries", v)} etichetta={`Rimuovi paese ${v}`} />
              </Badge>
            ))}
            {state.datiCompleti && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                Dati completi
                <RimuoviChip onClick={() => removeChip("datiCompleti", "")} etichetta="Rimuovi filtro dati completi" />
              </Badge>
            )}
            {state.soloMiei && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                I miei titoli
                <RimuoviChip onClick={() => removeChip("soloMiei", "")} etichetta="Rimuovi filtro i miei titoli" />
              </Badge>
            )}
            {state.excludeEtf && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                Escludi ETF
                <RimuoviChip onClick={() => removeChip("excludeEtf", "")} etichetta="Rimuovi filtro escludi ETF" />
              </Badge>
            )}
            {state.riskTiers.map((v) => (
              <Badge key={`r-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Rischio:</span> {v}
                <RimuoviChip onClick={() => removeChip("riskTiers", v)} etichetta={`Rimuovi rischio ${v}`} />
              </Badge>
            ))}
            {state.minScore != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Score ≥</span> {state.minScore}
                <RimuoviChip onClick={() => onChange({ ...state, minScore: null })} etichetta="Rimuovi soglia score minima" />
              </Badge>
            )}
            {state.scoreMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Score ≤</span> {state.scoreMax}
                <RimuoviChip onClick={() => onChange({ ...state, scoreMax: null })} etichetta="Rimuovi soglia score massima" />
              </Badge>
            )}
            {state.profitabilityMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Profitt. ≥</span> {state.profitabilityMin}
                <RimuoviChip onClick={() => onChange({ ...state, profitabilityMin: null })} etichetta="Rimuovi soglia profittabilità" />
              </Badge>
            )}
            {state.sustainabilityMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Sosten. ≥</span> {state.sustainabilityMin}
                <RimuoviChip onClick={() => onChange({ ...state, sustainabilityMin: null })} etichetta="Rimuovi soglia sostenibilità" />
              </Badge>
            )}
            {state.growthMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Crescita ≥</span> {state.growthMin}
                <RimuoviChip onClick={() => onChange({ ...state, growthMin: null })} etichetta="Rimuovi soglia crescita" />
              </Badge>
            )}
            {state.valueMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Valore ≥</span> {state.valueMin}
                <RimuoviChip onClick={() => onChange({ ...state, valueMin: null })} etichetta="Rimuovi soglia valore" />
              </Badge>
            )}
            {state.sentimentMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Sentiment ≥</span> {state.sentimentMin}
                <RimuoviChip onClick={() => onChange({ ...state, sentimentMin: null })} etichetta="Rimuovi soglia sentiment" />
              </Badge>
            )}
            {state.marketCapMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Mkt cap ≥</span> {(state.marketCapMin / 1e9).toFixed(0)}B$
                <RimuoviChip onClick={() => removeChip("marketCapMin", "")} etichetta="Rimuovi soglia market cap minima" />
              </Badge>
            )}
            {state.marketCapMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Mkt cap ≤</span> {(state.marketCapMax / 1e9).toFixed(0)}B$
                <RimuoviChip onClick={() => removeChip("marketCapMax", "")} etichetta="Rimuovi soglia market cap massima" />
              </Badge>
            )}
            {state.techMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Tecnico ≥</span> {state.techMin}
                <RimuoviChip onClick={() => removeChip("techMin", "")} etichetta="Rimuovi soglia tecnico" />
              </Badge>
            )}
            {state.postures.map((v) => (
              <Badge key={`p-${v}`} variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Postura:</span> {v}
                <RimuoviChip onClick={() => removeChip("postures", v)} etichetta={`Rimuovi postura ${v}`} />
              </Badge>
            ))}
            {state.rsiMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">RSI ≥</span> {state.rsiMin}
                <RimuoviChip onClick={() => removeChip("rsiMin", "")} etichetta="Rimuovi soglia RSI minima" />
              </Badge>
            )}
            {state.rsiMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">RSI ≤</span> {state.rsiMax}
                <RimuoviChip onClick={() => removeChip("rsiMax", "")} etichetta="Rimuovi soglia RSI massima" />
              </Badge>
            )}
            {state.aboveEma200 && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                sopra EMA200
                <RimuoviChip onClick={() => removeChip("aboveEma200", "")} etichetta="Rimuovi filtro sopra EMA200" />
              </Badge>
            )}
            {state.aboveEma50 && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                sopra EMA50
                <RimuoviChip onClick={() => removeChip("aboveEma50", "")} etichetta="Rimuovi filtro sopra EMA50" />
              </Badge>
            )}
            {state.near52wHigh && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                vicino max 52s
                <RimuoviChip onClick={() => removeChip("near52wHigh", "")} etichetta="Rimuovi filtro vicino massimo 52 settimane" />
              </Badge>
            )}
            {state.near52wLow && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                vicino min 52s
                <RimuoviChip onClick={() => removeChip("near52wLow", "")} etichetta="Rimuovi filtro vicino minimo 52 settimane" />
              </Badge>
            )}
            {state.signalsWithinDays != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Segnali:</span> {signalsWindowLabel(state.signalsWithinDays)}
                <RimuoviChip onClick={() => removeChip("signalsWithinDays", "")} etichetta="Rimuovi filtro con segnali" />
              </Badge>
            )}
            {state.priceMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Prezzo ≥</span> {state.priceMin}
                <RimuoviChip onClick={() => removeChip("priceMin", "")} etichetta="Rimuovi soglia prezzo minima" />
              </Badge>
            )}
            {state.priceMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Prezzo ≤</span> {state.priceMax}
                <RimuoviChip onClick={() => removeChip("priceMax", "")} etichetta="Rimuovi soglia prezzo massima" />
              </Badge>
            )}
            {state.changeMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Δ% ≥</span> {state.changeMin}
                <RimuoviChip onClick={() => removeChip("changeMin", "")} etichetta="Rimuovi soglia variazione minima" />
              </Badge>
            )}
            {state.changeMax != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Δ% ≤</span> {state.changeMax}
                <RimuoviChip onClick={() => removeChip("changeMax", "")} etichetta="Rimuovi soglia variazione massima" />
              </Badge>
            )}
            {state.volSpike && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                vol spike &gt;2×
                <RimuoviChip onClick={() => removeChip("volSpike", "")} etichetta="Rimuovi filtro volume spike" />
              </Badge>
            )}
            {state.volRatioMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Vol× ≥</span> {state.volRatioMin}
                <RimuoviChip onClick={() => removeChip("volRatioMin", "")} etichetta="Rimuovi soglia vol ratio minima" />
              </Badge>
            )}
            {state.volumeMin != null && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <span className="text-muted-foreground">Vol ≥</span> {state.volumeMin.toLocaleString()}
                <RimuoviChip onClick={() => removeChip("volumeMin", "")} etichetta="Rimuovi soglia volume minima" />
              </Badge>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
