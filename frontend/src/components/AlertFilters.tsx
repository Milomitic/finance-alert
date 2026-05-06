import { Filter, Search, X } from "lucide-react";

import type { AlertListParams } from "@/api/alerts";
import type { RuleKind } from "@/api/types";
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
import { TONE_BG, getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

interface Props {
  value: AlertListParams;
  onChange: (next: AlertListParams) => void;
}

/* The full rule-kind catalog as Select options. Labels + icons come from
 * the shared alertMeta helper so adding a new rule kind there propagates
 * here automatically (no second list to keep in sync). */
const RULE_KINDS: RuleKind[] = [
  "rsi_oversold",
  "rsi_overbought",
  "golden_cross",
  "death_cross",
  "volume_spike",
  "breakout",
  "macd_bullish_cross",
  "macd_bearish_cross",
  "bollinger_breakout",
  // Desk/trader signals (replaced bollinger_squeeze)
  "adx_bullish_trend",
  "adx_bearish_trend",
  "gap_up",
  "gap_down",
  "mean_reversion_long",
  "mean_reversion_short",
];

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

  // Count active filters so the header can show a badge. "active" status
  // is the default and not counted; "archived" counts as 1.
  const activeCount =
    (value.ticker ? 1 : 0) +
    (value.q ? 1 : 0) +
    (value.rule_kind ? 1 : 0) +
    (status === "archived" ? 1 : 0);

  const ruleMeta = value.rule_kind ? getAlertKindMeta(value.rule_kind) : null;

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

        {/* Two-column responsive grid (was three before the Ticker
            input moved into the table header). `items-end` aligns the
            inputs (which have different label heights) along their
            bottom edge. */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
          <div>
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              Regola
            </Label>
            <Select
              value={value.rule_kind ?? "__all__"}
              onValueChange={(v) =>
                onChange({
                  ...value,
                  rule_kind: v === "__all__" ? undefined : (v as RuleKind),
                })
              }
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Tutte le regole" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Tutte le regole</SelectItem>
                {RULE_KINDS.map((kind) => {
                  const m = getAlertKindMeta(kind);
                  const Icon = m.icon;
                  return (
                    <SelectItem key={kind} value={kind}>
                      <span className="inline-flex items-center gap-2">
                        <Icon className="h-3.5 w-3.5" />
                        {m.label}
                      </span>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>

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
            {ruleMeta && (
              <FilterChip
                label={
                  <>
                    <ruleMeta.icon className="h-3 w-3" />
                    {ruleMeta.label}
                  </>
                }
                onClear={() => onChange({ ...value, rule_kind: undefined })}
                className={cn("border-transparent", TONE_BG[ruleMeta.tone])}
              />
            )}
            {status === "archived" && (
              <FilterChip
                label="Solo archiviati"
                onClear={() => onChange({ ...value, archived: false })}
                className="bg-muted text-foreground border-border"
              />
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
