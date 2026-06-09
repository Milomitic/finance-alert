import { BadgeDollarSign, BookOpen, CalendarClock, ShieldAlert, Users } from "lucide-react";

import type { SignalSnapshot } from "@/api/types";
import {
  PROBABILITA_TOOLTIP,
  TONE_TEXT,
  snapshotForza,
  snapshotProbabilita,
  type AlertTone,
} from "@/lib/alertMeta";
import { cn } from "@/lib/utils";
import { glossForStep } from "@/lib/signalInterpretation";
import { useSignalCalibration } from "@/hooks/useSignalCalibration";

/* Source badge configuration for non-technical hybrid chain steps. */
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

/* Human labels for the per-detector strength sub-factors (the components that
   compose Forza). Keep in sync with the factors dicts in the backend signal
   detectors. */
const FACTOR_LABELS: Record<string, string> = {
  breakout_strength: "Forza breakout",
  volume_strength: "Forza volume",
  trend_alignment: "Allineamento trend",
  trend_strength: "Forza trend",
  resume: "Ripresa del trend",
  divergence_amplitude: "Ampiezza divergenza",
  extremity: "Estremita RSI",
  rsi_extremity: "Estremita RSI",
  trend_context: "Contesto trend",
  tightness: "Compressione",
  expansion_strength: "Forza espansione",
  proximity: "Vicinanza max 52w",
  trend: "Trend",
  momentum: "Momentum",
  trend_maturity: "Maturità trend",
  pattern_amplitude: "Ampiezza pattern",
  neckline_break: "Rottura neckline",
  candle_strength: "Forza candela",
  at_level: "A livello chiave",
  gap_size: "Dimensione gap",
  upgrade_present: "Upgrade analista",
  technical_strength: "Forza tecnica",
  adx_strength: "Forza ADX",
  di_spread: "Distanza +DI / -DI",
  breakout: "Breakout",
  confirmation: "Conferma",
  surprise_strength: "Sorpresa earnings",
  cluster_magnitude: "Entita cluster acquisti",
  rsi_confirmation: "Conferma RSI",
  support_proximity: "Vicinanza supporto",
  turn: "Inversione",
  structure: "Struttura",
  break_decisiveness: "Nettezza rottura",
  retest_proximity: "Vicinanza retest",
  break: "Rottura",
  hold: "Tenuta",
};

export function SignalSnapshotView({
  snapshot,
  showInvalidation = true,
  detector,
}: {
  snapshot: Record<string, unknown>;
  showInvalidation?: boolean;
  /** Detector name (from the alert's rule_kind) — used to look up the
   *  beta-stripped skill + honesty tag from the calibration table. */
  detector?: string;
}) {
  const s = snapshot as Partial<SignalSnapshot>;
  const { data: calTable } = useSignalCalibration();
  const cal = detector ? calTable?.detectors?.[detector] : undefined;
  const tone: AlertTone =
    s.tone === "bull" ? "bullish" : s.tone === "bear" ? "bearish" : "neutral";
  // Forza = pattern strength (snapshot.strength). Probabilità = historical
  // hit-rate (snapshot.probability). Both are first-class backend fields.
  const forza = snapshotForza(snapshot);
  const probPct = snapshotProbabilita(snapshot);
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

  // Number assigned only to TECHNICAL steps (no source); these are plotted on
  // the chart, so the number here matches the chart marker.
  let techCounter = 0;

  return (
    <div className="space-y-4">
      {isHybrid && (
        <div className="flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-full border border-indigo-300/60 bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700 dark:border-indigo-700/50 dark:bg-indigo-950/40 dark:text-indigo-300">
            Ibrido
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-[1.6fr_1fr] gap-x-6 gap-y-5">
        {/* Right column (desktop): Forza + Probabilità + the factors that
            compose the strength. Two distinct metrics: Forza = pattern
            strength in the signal's tone color; Probabilità = historical
            hit-rate in a neutral/info (slate/sky) treatment so they read as
            different things. */}
        <div className="space-y-4 md:order-2">
          {/* Forza — pattern strength, tone-colored. */}
          {forza != null && (
            <div className="flex items-center gap-3">
              <span className="w-[4.5rem] shrink-0 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                Forza
              </span>
              <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                <div className={cn("h-full rounded-full", barColor)} style={{ width: `${forza}%` }} />
              </div>
              <span className={cn("text-sm font-bold tabular-nums w-10 text-right", TONE_TEXT[tone])}>{forza}%</span>
            </div>
          )}

          {/* Probabilità — historical hit-rate, neutral/info (slate/sky).
              Shows the backend value, or "n/d" when truly absent. */}
          <div className="flex items-center gap-3" title={PROBABILITA_TOOLTIP}>
            <span className="w-[4.5rem] shrink-0 text-[11px] uppercase tracking-wider text-sky-700/80 dark:text-sky-300/80 font-semibold">
              Probabilità
            </span>
            <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
              {probPct != null && (
                <div className="h-full rounded-full bg-sky-500 dark:bg-sky-400" style={{ width: `${probPct}%` }} />
              )}
            </div>
            <span className="text-sm font-bold tabular-nums w-10 text-right text-sky-700 dark:text-sky-300">
              {probPct != null ? `${probPct}%` : "n/d"}
            </span>
          </div>

          {/* Honesty row: beta-stripped skill + a calibration tag. Most
              single-name technicals are historically ~coin-flips; this surfaces
              that truth instead of implying edge from the absolute hit-rate. */}
          {cal && (
            <div className="flex items-center gap-2 flex-wrap pl-[5.5rem] -mt-2">
              {cal.tag === "coinflip" && (
                <span className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60"
                  title="Storicamente ~50/50 al netto del mercato: nessun edge direzionale dimostrato">
                  ≈50/50 storico
                </span>
              )}
              {cal.tag === "negative" && (
                <span className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60"
                  title={`Edge storico NEGATIVO al netto del mercato (${cal.edge_pct?.toFixed(2)}%): segnale anti-predittivo`}>
                  edge storico negativo
                </span>
              )}
              {cal.tag === "edge" && (
                <span className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60"
                  title="Edge storico positivo al netto del mercato (beta-stripped)">
                  edge storico
                </span>
              )}
              {cal.skill != null && (
                <span className="text-[11px] text-muted-foreground tabular-nums"
                  title="Hit-rate storico al netto del movimento di mercato (skill, beta-stripped). La Probabilità sopra include invece il beta di mercato.">
                  skill {Math.round(cal.skill)}%{cal.n != null ? ` · n ${cal.n.toLocaleString("it-IT")}` : ""}
                </span>
              )}
            </div>
          )}

          {Object.keys(factors).length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
                Fattori di forza
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
        </div>

        {/* Left column (desktop): the event chain */}
        {chain.length > 0 && (
          <div className="md:order-1">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
              Catena di eventi
            </div>
            <ol className="relative border-l border-border/60 ml-2.5 space-y-3">
              {chain.map((step, i) => {
                const badge = step.source ? SOURCE_BADGE[step.source] : null;
                const num = step.source ? null : (techCounter += 1);
                const gloss = glossForStep(step.label, step.detail, s.tone, s.annotations?.levels ?? []);
                return (
                  <li key={`${step.date}-${i}`} className="ml-4 relative">
                    {num != null ? (
                      <span className="absolute -left-[1.72rem] top-0 h-5 w-5 rounded-full bg-slate-900 dark:bg-slate-700 text-white text-[10px] font-bold flex items-center justify-center border-2 border-background">
                        {num}
                      </span>
                    ) : (
                      <span className="absolute -left-[1.39rem] mt-1 h-3 w-3 rounded-full bg-muted-foreground/50 border-2 border-background" />
                    )}
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
                      {step.kind === "confirmation" && (
                        <span
                          className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60"
                          title="Evento co-temporale che rinforza il segnale"
                        >
                          conferma
                        </span>
                      )}
                    </div>
                    {step.detail && <div className="text-xs text-muted-foreground">{step.detail}</div>}
                    {gloss && (
                      <div className="text-[11px] text-sky-700/80 dark:text-sky-300/80 italic mt-0.5">{gloss}</div>
                    )}
                    <div className="text-[11px] text-muted-foreground/70 tabular-nums mt-0.5">{step.date}</div>
                  </li>
                );
              })}
            </ol>
          </div>
        )}
      </div>

      {showInvalidation && inv && (inv.level != null || inv.reason) && (
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
