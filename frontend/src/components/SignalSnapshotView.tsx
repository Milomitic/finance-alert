import { BadgeDollarSign, BookOpen, CalendarClock, ShieldAlert, Users } from "lucide-react";

import type { SignalSnapshot } from "@/api/types";
import { TONE_TEXT, type AlertTone } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/** Source badge configuration for non-technical hybrid chain steps.
 *  Keeps label/icon in one place so adding a new source is a one-liner. */
const SOURCE_BADGE: Record<
  string,
  { label: string; Icon: React.FC<{ className?: string }>; cls: string }
> = {
  earnings: {
    label: "Earnings",
    Icon: CalendarClock,
    cls: "bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300",
  },
  analyst: {
    label: "Analista",
    Icon: Users,
    cls: "bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300",
  },
  insider: {
    label: "Insider",
    Icon: BadgeDollarSign,
    cls: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  },
};

/* Human labels for the per-detector confidence sub-factors. Unknown keys
 * fall back to the raw name (with underscores spaced) so a new detector's
 * factor still renders legibly before this map is updated. */
const FACTOR_LABELS: Record<string, string> = {
  breakout_strength: "Forza breakout",
  volume_strength: "Forza volume",
  trend_alignment: "Allineamento trend",
  trend_strength: "Forza trend",
  resume: "Ripresa",
  divergence_amplitude: "Ampiezza divergenza",
  extremity: "Estremita RSI",
  trend_context: "Contesto trend",
  tightness: "Compressione",
  expansion_strength: "Forza espansione",
  proximity: "Vicinanza max 52w",
  trend: "Trend",
  momentum: "Momentum",
};

/** Renders a signal-engine alert's snapshot: confidence bar, the dated event
 *  chain as a timeline, the [0,1] factor sub-scores, the invalidation level,
 *  and the cited sources. Reads the loosely-typed snapshot dict defensively
 *  (older/partial payloads must not crash the dialog). */
export function SignalSnapshotView({ snapshot }: { snapshot: Record<string, unknown> }) {
  const s = snapshot as Partial<SignalSnapshot>;
  const tone: AlertTone =
    s.tone === "bull" ? "bullish" : s.tone === "bear" ? "bearish" : "neutral";
  const confidence = typeof s.confidence === "number" ? Math.round(s.confidence) : null;
  const chain = Array.isArray(s.chain) ? s.chain : [];
  const isHybrid = chain.some(
    (step) => typeof step.source === "string" && step.source in SOURCE_BADGE,
  );
  const factors =
    s.factors && typeof s.factors === "object" ? (s.factors as Record<string, number>) : {};
  const sources = Array.isArray(s.sources) ? s.sources : [];
  const inv = s.invalidation ?? null;
  const barColor =
    tone === "bullish" ? "bg-emerald-500" : tone === "bearish" ? "bg-rose-500" : "bg-slate-400";

  return (
    <div className="space-y-4">
      {isHybrid && (
        <div className="flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-full border border-indigo-300/60 bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700 dark:border-indigo-700/50 dark:bg-indigo-950/40 dark:text-indigo-300">
            Ibrido
          </span>
        </div>
      )}

      {confidence != null && (
        <div className="flex items-center gap-3">
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
            Confidenza
          </span>
          <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
            <div className={cn("h-full rounded-full", barColor)} style={{ width: `${confidence}%` }} />
          </div>
          <span className={cn("text-sm font-bold tabular-nums", TONE_TEXT[tone])}>{confidence}%</span>
        </div>
      )}

      {chain.length > 0 && (
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            Catena di eventi
          </div>
          <ol className="relative border-l border-border/60 ml-2 space-y-3">
            {chain.map((step, i) => {
              const badge = step.source ? SOURCE_BADGE[step.source] : null;
              return (
                <li key={`${step.date}-${i}`} className="ml-4 relative">
                  <span className="absolute -left-[1.39rem] mt-1 h-3 w-3 rounded-full bg-primary/70 border-2 border-background" />
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-sm font-semibold">{step.label}</span>
                    {badge && (
                      <span
                        className={cn(
                          "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none",
                          badge.cls,
                        )}
                      >
                        <badge.Icon className="h-2.5 w-2.5" />
                        {badge.label}
                      </span>
                    )}
                  </div>
                  {step.detail && <div className="text-xs text-muted-foreground">{step.detail}</div>}
                  <div className="text-[11px] text-muted-foreground/70 tabular-nums">{step.date}</div>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {Object.keys(factors).length > 0 && (
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            Fattori di confidenza
          </div>
          <div className="space-y-1.5">
            {Object.entries(factors).map(([k, v]) => {
              const pct = Math.round(Math.max(0, Math.min(1, typeof v === "number" ? v : 0)) * 100);
              return (
                <div key={k} className="flex items-center gap-2">
                  <span className="w-36 text-xs text-foreground/70 shrink-0 truncate" title={FACTOR_LABELS[k] ?? k}>
                    {FACTOR_LABELS[k] ?? k}
                  </span>
                  <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-sky-500/70 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-9 text-right text-[11px] tabular-nums text-muted-foreground">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {inv && (inv.level != null || inv.reason) && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-300/60 bg-amber-50/50 dark:bg-amber-950/20 p-2.5">
          <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-amber-800 dark:text-amber-300">Invalidazione</span>
            {inv.level != null && (
              <span className="tabular-nums">
                {" "}a ${typeof inv.level === "number" ? inv.level.toFixed(2) : String(inv.level)}
              </span>
            )}
            {inv.reason && (
              <div className="text-amber-700/80 dark:text-amber-400/80">{inv.reason}</div>
            )}
          </div>
        </div>
      )}

      {sources.length > 0 && (
        <div className="flex items-start gap-2 text-[11px] text-muted-foreground">
          <BookOpen className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <div>{sources.join(" - ")}</div>
        </div>
      )}
    </div>
  );
}
