import { Settings2 } from "lucide-react";

import type { IndicatorPeriods } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

/**
 * Indicator catalog + per-indicator state (visibility + style).
 * Style is user-editable: color and line width can be customized per series
 * via a small popover.
 */
export type IndicatorKey = "ema20" | "ema50" | "ema200" | "bb" | "rsi" | "macd";

export interface IndicatorStyle {
  visible: boolean;
  color: string;       // CSS color (#RRGGBB)
  width: number;       // 1..4
}

export type IndicatorState = Record<IndicatorKey, IndicatorStyle>;

export interface IndicatorMeta {
  key: IndicatorKey;
  label: string;
  group: "overlay" | "panel";
  defaultColor: string;
  description: string;
}

// May 2026: switched SMA → EMA across the chart overlays. The `key`
// strings (ema20/ema50/ema200) and the labels both reflect the new
// indicator type; the API field names switched in lockstep on the
// backend side.
export const INDICATOR_CATALOG: IndicatorMeta[] = [
  { key: "ema20",  label: "EMA 20",    group: "overlay", defaultColor: "#a855f7", description: "Media mobile esponenziale 20gg" },
  { key: "ema50",  label: "EMA 50",    group: "overlay", defaultColor: "#3b82f6", description: "Media mobile esponenziale 50gg" },
  { key: "ema200", label: "EMA 200",   group: "overlay", defaultColor: "#f59e0b", description: "Media mobile esponenziale 200gg (trend lungo)" },
  { key: "bb",     label: "Bollinger", group: "overlay", defaultColor: "#0ea5e9", description: "Bande di Bollinger (20, 2σ)" },
  { key: "rsi",    label: "RSI(14)",   group: "panel",   defaultColor: "#7c3aed", description: "Pannello separato — RSI 14gg" },
  { key: "macd",   label: "MACD",      group: "panel",   defaultColor: "#ef4444", description: "Pannello separato — MACD 12/26/9" },
];

// Default-on indicators: all three EMAs + Bollinger as overlays; RSI + MACD
// as separate panels. EMA20 enabled by default (was off): users want a
// short-term trend reference alongside the mid- and long-term ones, and
// the now-relocated indicator badges (right price scale instead of inline)
// mean an extra line doesn't visually crowd the candles.
export const DEFAULT_INDICATOR_STATE: IndicatorState = {
  ema20:  { visible: true,  color: "#a855f7", width: 1 },
  ema50:  { visible: true,  color: "#3b82f6", width: 1 },
  ema200: { visible: true,  color: "#f59e0b", width: 1 },
  bb:     { visible: true,  color: "#0ea5e9", width: 1 },
  rsi:    { visible: true,  color: "#7c3aed", width: 1 },
  macd:   { visible: true,  color: "#ef4444", width: 1 },
};

interface Props {
  state: IndicatorState;
  onChange: (key: IndicatorKey, next: IndicatorStyle) => void;
  /** Real periods used to compute the visible indicator series. When provided,
   *  toggle labels and tooltips reflect the actual numbers ("EMA 10" on a 1m
   *  range, "EMA 200" on 1y) instead of the static defaults. */
  periods?: IndicatorPeriods;
}

/** Compose the toggle label + descriptive tooltip from the live periods, with
 *  graceful fallback to the catalog defaults when periods aren't available. */
function describeIndicator(
  meta: IndicatorMeta,
  periods?: IndicatorPeriods,
): { label: string; description: string } {
  if (!periods) return { label: meta.label, description: meta.description };
  switch (meta.key) {
    case "ema20":
      return {
        label: `EMA ${periods.ema_fast}`,
        description: `Media mobile esponenziale ${periods.ema_fast} barre (rapida)`,
      };
    case "ema50":
      return {
        label: `EMA ${periods.ema_mid}`,
        description: `Media mobile esponenziale ${periods.ema_mid} barre (intermedia)`,
      };
    case "ema200":
      return {
        label: `EMA ${periods.ema_slow}`,
        description: `Media mobile esponenziale ${periods.ema_slow} barre (trend lungo)`,
      };
    case "rsi":
      return {
        label: `RSI(${periods.rsi})`,
        description: `Pannello separato — RSI ${periods.rsi} barre`,
      };
    case "macd":
      return {
        label: `MACD(${periods.macd_fast},${periods.macd_slow},${periods.macd_signal})`,
        description: `Pannello separato — MACD ${periods.macd_fast}/${periods.macd_slow}/${periods.macd_signal}`,
      };
    case "bb":
      return {
        label: `BB(${periods.bb_period},${periods.bb_k}σ)`,
        description: `Bande di Bollinger (${periods.bb_period} barre, ${periods.bb_k}σ)`,
      };
    default:
      return { label: meta.label, description: meta.description };
  }
}

const COLOR_PALETTE = [
  "#3b82f6", "#06b6d4", "#0ea5e9", "#7c3aed", "#a855f7", "#ec4899",
  "#ef4444", "#f59e0b", "#eab308", "#16a34a", "#10b981", "#64748b",
];

function StyleEditor({
  meta, style, onChange,
}: { meta: IndicatorMeta; style: IndicatorStyle; onChange: (s: IndicatorStyle) => void }) {
  return (
    <PopoverContent className="w-60 p-3 text-sm">
      <div className="font-semibold mb-1">{meta.label}</div>
      <div className="text-sm text-muted-foreground mb-3">{meta.description}</div>

      <div className="text-sm font-medium mb-1">Colore</div>
      <div className="grid grid-cols-6 gap-1.5 mb-3">
        {COLOR_PALETTE.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => onChange({ ...style, color: c })}
            className="h-6 w-6 rounded-full border-2 transition-transform hover:scale-110"
            style={{ background: c, borderColor: c === style.color ? "hsl(var(--foreground))" : "transparent" }}
            aria-label={`Colore ${c}`}
            title={c}
          />
        ))}
      </div>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm">Custom:</span>
        <input
          type="color"
          value={style.color}
          onChange={(e) => onChange({ ...style, color: e.target.value })}
          className="h-7 w-12 cursor-pointer rounded border"
        />
        <span className="text-sm font-mono text-muted-foreground">{style.color}</span>
      </div>

      <div className="text-sm font-medium mb-1">Spessore linea</div>
      <div className="flex items-center gap-2 mb-1">
        <input
          type="range"
          min={1} max={4} step={1}
          value={style.width}
          onChange={(e) => onChange({ ...style, width: Number(e.target.value) })}
          className="flex-1 cursor-pointer"
        />
        <span className="text-sm font-mono w-6 text-right">{style.width}px</span>
      </div>
    </PopoverContent>
  );
}

/** Append an alpha hex pair to a 6-digit hex color. e.g. "#3b82f6" + 0.18 → "#3b82f62E" */
function withAlpha(hex: string, a: number): string {
  const clamped = Math.max(0, Math.min(1, a));
  const ah = Math.round(clamped * 255).toString(16).padStart(2, "0");
  return `${hex}${ah}`;
}

export function IndicatorToggles({ state, onChange, periods }: Props) {
  return (
    <div className="inline-flex items-center gap-2 flex-wrap">
      {INDICATOR_CATALOG.map((meta) => {
        const s = state[meta.key];
        const on = s.visible;
        // Resolve the live label/description per indicator, then fall back to
        // the catalog default when periods aren't available (e.g. older API
        // response, initial render before /detail returns).
        const live = describeIndicator(meta, periods);
        // Active: fill the whole pill with a tinted version of the indicator
        // color (~18% alpha), border in the same color at full opacity.
        // Inactive: neutral card background, muted border.
        const activeBg = on ? withAlpha(s.color, 0.18) : undefined;
        const activeBorder = on ? s.color : undefined;
        return (
          <div
            key={meta.key}
            className="inline-flex h-8 items-center rounded-md overflow-hidden transition-colors"
            style={{
              backgroundColor: activeBg,
              border: `1px solid ${activeBorder ?? "hsl(var(--border))"}`,
            }}
          >
            <button
              type="button"
              onClick={() => onChange(meta.key, { ...s, visible: !on })}
              className="h-full px-2.5 text-sm font-semibold transition-colors flex items-center"
              title={`${on ? "Nascondi" : "Mostra"} ${live.label} — ${live.description}`}
              style={{ color: on ? s.color : "var(--muted-foreground, #64748b)" }}
            >
              {live.label}
            </button>
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-full px-1.5 rounded-none"
                  style={{ borderLeft: `1px solid ${on ? withAlpha(s.color, 0.5) : "hsl(var(--border))"}` }}
                  title="Personalizza colore e spessore"
                >
                  <Settings2 className="h-3 w-3" />
                </Button>
              </PopoverTrigger>
              <StyleEditor
                meta={{ ...meta, label: live.label, description: live.description }}
                style={s}
                onChange={(next) => onChange(meta.key, next)}
              />
            </Popover>
          </div>
        );
      })}
    </div>
  );
}
