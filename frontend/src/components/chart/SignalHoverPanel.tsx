import { cn } from "@/lib/utils";
import type { SignalHoverItem } from "@/lib/signalMarkers";

/** Floating detail panel for the signal(s) fired on the hovered candle.
 *  Renders under the OHLC legend (top-left), only while the crosshair is on a
 *  marked bar. `pointer-events-none` so it never steals the crosshair. Each
 *  row: tone dot + detector label + Forza + realized outcome. */
const toneDot: Record<SignalHoverItem["tone"], string> = {
  bullish: "bg-emerald-500",
  bearish: "bg-red-500",
  warning: "bg-amber-500",
  neutral: "bg-muted-foreground",
};

function outcomeGlyph(outcome: boolean | null | undefined): { text: string; cls: string } {
  if (outcome === true) return { text: "✓", cls: "text-emerald-600 dark:text-emerald-400" };
  if (outcome === false) return { text: "✗", cls: "text-red-600 dark:text-red-400" };
  return { text: "· in maturazione", cls: "text-muted-foreground" };
}

export function SignalHoverPanel({ signals }: { signals: SignalHoverItem[] | null }) {
  if (!signals || signals.length === 0) return null;
  return (
    <div className="absolute top-[52px] left-2 z-10 pointer-events-none max-w-[280px] rounded-md border bg-card/90 backdrop-blur-sm px-3 py-1.5 shadow-sm text-xs leading-snug space-y-0.5">
      {signals.map((s, i) => {
        const oc = outcomeGlyph(s.outcome);
        return (
          <div key={i} className="flex items-center gap-1.5">
            <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", toneDot[s.tone])} />
            <span className="font-medium truncate">{s.label}</span>
            {s.forza != null && (
              <span className="text-muted-foreground tabular-nums shrink-0">
                Forza {s.forza}
              </span>
            )}
            <span className={cn("tabular-nums shrink-0", oc.cls)}>{oc.text}</span>
          </div>
        );
      })}
    </div>
  );
}
