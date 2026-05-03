import { Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

/**
 * Indicator catalog + per-indicator state (visibility + style).
 * Style is user-editable: color and line width can be customized per series
 * via a small popover.
 */
export type IndicatorKey = "sma20" | "sma50" | "sma200" | "bb" | "rsi" | "macd";

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

export const INDICATOR_CATALOG: IndicatorMeta[] = [
  { key: "sma20",  label: "SMA 20",    group: "overlay", defaultColor: "#a855f7", description: "Media mobile semplice 20gg" },
  { key: "sma50",  label: "SMA 50",    group: "overlay", defaultColor: "#3b82f6", description: "Media mobile semplice 50gg" },
  { key: "sma200", label: "SMA 200",   group: "overlay", defaultColor: "#f59e0b", description: "Media mobile semplice 200gg (trend lungo)" },
  { key: "bb",     label: "Bollinger", group: "overlay", defaultColor: "#0ea5e9", description: "Bande di Bollinger (20, 2σ)" },
  { key: "rsi",    label: "RSI(14)",   group: "panel",   defaultColor: "#7c3aed", description: "Pannello separato — RSI 14gg" },
  { key: "macd",   label: "MACD",      group: "panel",   defaultColor: "#ef4444", description: "Pannello separato — MACD 12/26/9" },
];

export const DEFAULT_INDICATOR_STATE: IndicatorState = {
  sma20:  { visible: false, color: "#a855f7", width: 1 },
  sma50:  { visible: true,  color: "#3b82f6", width: 1 },
  sma200: { visible: true,  color: "#f59e0b", width: 1 },
  bb:     { visible: false, color: "#0ea5e9", width: 1 },
  rsi:    { visible: true,  color: "#7c3aed", width: 1 },
  macd:   { visible: false, color: "#ef4444", width: 1 },
};

interface Props {
  state: IndicatorState;
  onChange: (key: IndicatorKey, next: IndicatorStyle) => void;
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

export function IndicatorToggles({ state, onChange }: Props) {
  return (
    <div className="inline-flex items-center gap-x-2 gap-y-1 flex-wrap">
      {INDICATOR_CATALOG.map((meta) => {
        const s = state[meta.key];
        const on = s.visible;
        // Active: fill the whole pill with a tinted version of the indicator
        // color (~18% alpha), border in the same color at full opacity.
        // Inactive: neutral card background, muted border.
        const activeBg = on ? withAlpha(s.color, 0.18) : undefined;
        const activeBorder = on ? s.color : undefined;
        return (
          <div
            key={meta.key}
            className="inline-flex items-center rounded-md overflow-hidden transition-colors"
            style={{
              backgroundColor: activeBg,
              border: `1px solid ${activeBorder ?? "hsl(var(--border))"}`,
            }}
          >
            <button
              type="button"
              onClick={() => onChange(meta.key, { ...s, visible: !on })}
              className="px-2.5 py-1 text-sm font-semibold transition-colors"
              title={`${on ? "Nascondi" : "Mostra"} ${meta.label}`}
              style={{ color: on ? s.color : "var(--muted-foreground, #64748b)" }}
            >
              {meta.label}
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
              <StyleEditor meta={meta} style={s} onChange={(next) => onChange(meta.key, next)} />
            </Popover>
          </div>
        );
      })}
    </div>
  );
}
