/**
 * Compact toggle bar for chart overlays (SMA family + Bollinger) and
 * sub-panels (RSI, MACD). Each toggle is a checkbox + colored label so the
 * series color is discoverable at a glance.
 */
export type IndicatorKey = "sma20" | "sma50" | "sma200" | "bb" | "rsi" | "macd";

export interface IndicatorState {
  sma20: boolean;
  sma50: boolean;
  sma200: boolean;
  bb: boolean;
  rsi: boolean;
  macd: boolean;
}

interface Props {
  state: IndicatorState;
  onToggle: (key: IndicatorKey, value: boolean) => void;
}

const TOGGLES: { key: IndicatorKey; label: string; color: string; group: "overlay" | "panel" }[] = [
  { key: "sma20",  label: "SMA 20",  color: "#a855f7", group: "overlay" },
  { key: "sma50",  label: "SMA 50",  color: "#3b82f6", group: "overlay" },
  { key: "sma200", label: "SMA 200", color: "#f59e0b", group: "overlay" },
  { key: "bb",     label: "Bollinger", color: "#0ea5e9", group: "overlay" },
  { key: "rsi",    label: "RSI",     color: "#7c3aed", group: "panel" },
  { key: "macd",   label: "MACD",    color: "#ef4444", group: "panel" },
];

export function IndicatorToggles({ state, onToggle }: Props) {
  return (
    <div className="inline-flex items-center gap-x-3 gap-y-1 text-xs flex-wrap">
      {TOGGLES.map((t) => {
        const on = state[t.key];
        return (
          <label
            key={t.key}
            className="inline-flex items-center gap-1 cursor-pointer select-none"
            title={t.group === "panel" ? `Pannello ${t.label}` : `Overlay ${t.label} sul prezzo`}
          >
            <input
              type="checkbox"
              checked={on}
              onChange={(e) => onToggle(t.key, e.target.checked)}
              className="cursor-pointer accent-current"
              style={{ accentColor: t.color }}
            />
            <span style={{ color: on ? t.color : "var(--muted-foreground, #64748b)" }} className="font-medium">
              {t.label}
            </span>
          </label>
        );
      })}
    </div>
  );
}
