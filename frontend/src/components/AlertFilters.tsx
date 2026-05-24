import { Filter, Search, X } from "lucide-react";

import type { AlertListParams } from "@/api/alerts";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SectionTitle } from "@/components/ui/section-title";
import { cn } from "@/lib/utils";

interface Props {
  value: AlertListParams;
  onChange: (next: AlertListParams) => void;
}

// Archive axis only — read/unread was removed from the UI in a prior pass.
const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "active", label: "Tutti (esclusi archiviati)" },
  { value: "archived", label: "Solo archiviati" },
];

function statusToParams(status: string): Pick<AlertListParams, "archived"> {
  return status === "archived" ? { archived: true } : { archived: false };
}

function paramsToStatus(p: AlertListParams): string {
  return p.archived ? "archived" : "active";
}

// The 17 signal kinds the engine can emit.
const SIGNAL_KINDS: { value: string; label: string }[] = [
  { value: "signal:volume_breakout",    label: "Volume Breakout" },
  { value: "signal:trend_pullback",     label: "Trend + Pullback" },
  { value: "signal:rsi_divergence",     label: "Divergenza RSI" },
  { value: "signal:squeeze_expansion",  label: "Squeeze + Espansione" },
  { value: "signal:high52_momentum",    label: "Massimo 52 settimane" },
  { value: "signal:oversold_reversal",  label: "Reversal Oversold" },
  { value: "signal:sr_flip",            label: "S/R Flip" },
  { value: "signal:structure_break",    label: "Rottura Struttura" },
  { value: "signal:macd_divergence",    label: "Divergenza MACD" },
  { value: "signal:gap_and_go",         label: "Gap and Go" },
  { value: "signal:adx_confirmation",   label: "Conferma ADX" },
  { value: "signal:candle_reversal",    label: "Reversal Candele" },
  { value: "signal:pead",               label: "PEAD (Post-earnings drift)" },
  { value: "signal:analyst_momentum",   label: "Momentum Analisti" },
  { value: "signal:insider_buy",        label: "Insider Buy" },
  { value: "signal:chart_pattern",      label: "Chart Pattern" },
  { value: "signal:hidden_divergence",  label: "Divergenza Nascosta" },
];

const TONE_OPTIONS: { value: string; label: string }[] = [
  { value: "bull", label: "Rialzista" },
  { value: "bear", label: "Ribassista" },
];

/** Small "active filter" chip with an X to clear that single filter. Used
 *  to surface what's currently applied so the user can scan filters at
 *  a glance and dismiss them one at a time. */
function FilterChip({
  label,
  onClear,
  className,
}: {
  label: React.ReactNode;
  onClear: () => void;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-semibold",
        className,
      )}
    >
      {label}
      <button
        type="button"
        onClick={onClear}
        className="opacity-70 hover:opacity-100 transition-opacity"
        aria-label="Rimuovi filtro"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

export function AlertFilters({ value, onChange }: Props) {
  // The standalone Ticker text-input lived here previously; it has been
  // folded into the AlertsTable's Stock column header so the filter
  // sits where the user is already looking. The Ticker filter chip
  // logic is kept (counts toward activeCount, displays as a chip) so
  // the existing `value.ticker` URL param + CSV export still work.

  const status = paramsToStatus(value);

  const reset = () => {
    onChange({ archived: false });
  };

  // Friendly label for the currently-selected signal kind.
  const signalKindLabel = value.rule_kind
    ? (SIGNAL_KINDS.find((k) => k.value === value.rule_kind)?.label ?? value.rule_kind)
    : null;

  // Friendly label for the currently-selected tone.
  const toneLabel = value.tone
    ? (TONE_OPTIONS.find((t) => t.value === value.tone)?.label ?? value.tone)
    : null;

  // Count active filters so the header can show a badge. "active" status
  // is the default and not counted; "archived" counts as 1.
  const activeCount =
    (value.ticker ? 1 : 0) +
    (value.q ? 1 : 0) +
    (status === "archived" ? 1 : 0) +
    (value.rule_kind ? 1 : 0) +
    (value.tone ? 1 : 0) +
    (value.confidence_min != null ? 1 : 0) +
    (value.nature ? 1 : 0);

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <SectionTitle
          icon={Filter}
          label="Filtri"
          right={
            <div className="flex items-center gap-2">
              {activeCount > 0 && (
                <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full bg-primary text-primary-foreground text-[11px] font-bold tabular-nums">
                  {activeCount}
                </span>
              )}
              {activeCount > 0 && (
                <Button variant="ghost" size="sm" onClick={reset} className="h-7 text-xs">
                  <X className="h-3 w-3 mr-1" />
                  Reset
                </Button>
              )}
            </div>
          }
        />

        <div>
          <Label className="text-xs uppercase tracking-wider text-muted-foreground">
            Archivio
          </Label>
          <Select
            value={status}
            onValueChange={(v) => onChange({ ...value, ...statusToParams(v) })}
          >
            <SelectTrigger className="mt-1">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Tipo segnale — maps to rule_kind. "tutti" sentinel clears the filter. */}
        <div>
          <Label className="text-xs uppercase tracking-wider text-muted-foreground">
            Tipo segnale
          </Label>
          <Select
            value={value.rule_kind ?? "tutti"}
            onValueChange={(v) =>
              onChange({ ...value, rule_kind: v === "tutti" ? undefined : v })
            }
          >
            <SelectTrigger className="mt-1">
              <SelectValue placeholder="Tutti" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="tutti">Tutti</SelectItem>
              {SIGNAL_KINDS.map((k) => (
                <SelectItem key={k.value} value={k.value}>
                  {k.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Tono — bull / bear. "tutti" clears the filter. */}
        <div>
          <Label className="text-xs uppercase tracking-wider text-muted-foreground">
            Tono
          </Label>
          <Select
            value={value.tone ?? "tutti"}
            onValueChange={(v) =>
              onChange({ ...value, tone: v === "tutti" ? undefined : v })
            }
          >
            <SelectTrigger className="mt-1">
              <SelectValue placeholder="Tutti" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="tutti">Tutti</SelectItem>
              {TONE_OPTIONS.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Natura — continuazione / inversione. "tutti" clears. */}
        <div>
          <Label className="text-xs uppercase tracking-wider text-muted-foreground">
            Natura
          </Label>
          <Select
            value={value.nature ?? "tutti"}
            onValueChange={(v) => onChange({ ...value, nature: v === "tutti" ? undefined : v })}
          >
            <SelectTrigger className="mt-1">
              <SelectValue placeholder="Tutte" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="tutti">Tutte</SelectItem>
              <SelectItem value="continuazione">Continuazione</SelectItem>
              <SelectItem value="inversione">Inversione</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Confidenza minima — number input 0-100. */}
        <div>
          <Label className="text-xs uppercase tracking-wider text-muted-foreground">
            Confidenza minima
          </Label>
          <div className="mt-1 inline-flex items-center gap-1.5 h-9 px-2 rounded border border-input w-full">
            <input
              type="number"
              min={0}
              max={100}
              step={5}
              placeholder="—"
              value={value.confidence_min ?? ""}
              onChange={(e) => {
                const raw = e.target.value;
                if (raw === "") {
                  onChange({ ...value, confidence_min: undefined });
                  return;
                }
                const n = Number(raw);
                if (Number.isFinite(n) && n >= 0 && n <= 100) {
                  onChange({ ...value, confidence_min: n });
                }
              }}
              className="flex-1 bg-transparent text-sm tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <span className="text-xs text-muted-foreground">/ 100</span>
          </div>
        </div>

        {/* Active-filter chip row — shows what's applied so the user can
            scan filters at a glance and dismiss any one of them by clicking
            its X. Hidden when nothing is filtered. */}
        {activeCount > 0 && (
          <div className="flex items-center gap-2 flex-wrap pt-1 border-t border-border/40">
            <span className="text-xs text-muted-foreground italic">Attivi:</span>
            {value.ticker && (
              <FilterChip
                label={
                  <>
                    <Search className="h-3 w-3" />
                    {value.ticker}
                  </>
                }
                onClear={() => onChange({ ...value, ticker: undefined })}
                className="bg-muted text-foreground border-border"
              />
            )}
            {value.q && (
              <FilterChip
                label={
                  <>
                    <Search className="h-3 w-3" />
                    "{value.q}"
                  </>
                }
                onClear={() => onChange({ ...value, q: undefined })}
                className="bg-muted text-foreground border-border"
              />
            )}
            {status === "archived" && (
              <FilterChip
                label="Solo archiviati"
                onClear={() => onChange({ ...value, archived: false })}
                className="bg-muted text-foreground border-border"
              />
            )}
            {value.rule_kind && (
              <FilterChip
                label={
                  <>
                    <span className="text-muted-foreground/80">Segnale:</span>{" "}
                    {signalKindLabel}
                  </>
                }
                onClear={() => onChange({ ...value, rule_kind: undefined })}
                className="bg-muted text-foreground border-border"
              />
            )}
            {value.tone && (
              <FilterChip
                label={
                  <>
                    <span className="text-muted-foreground/80">Tono:</span>{" "}
                    {toneLabel}
                  </>
                }
                onClear={() => onChange({ ...value, tone: undefined })}
                className={
                  value.tone === "bull"
                    ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 border-emerald-200/70 dark:border-emerald-800/60"
                    : "bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300 border-rose-200/70 dark:border-rose-800/60"
                }
              />
            )}
            {value.confidence_min != null && (
              <FilterChip
                label={
                  <>
                    <span className="text-muted-foreground/80">Confidenza ≥</span>{" "}
                    {value.confidence_min}%
                  </>
                }
                onClear={() => onChange({ ...value, confidence_min: undefined })}
                className="bg-muted text-foreground border-border"
              />
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
