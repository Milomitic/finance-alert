import {
  CalendarClock,
  CalendarRange,
  Check,
  ChevronDown,
  Clock,
  Code2,
  DollarSign,
  Pencil,
  ShieldAlert,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Alert, SignalChainStep, SignalSnapshot } from "@/api/types";
import { AlertKindChip, AlertToneChip } from "@/components/AlertChips";
import { HolderCountBadge } from "@/components/stocks/HolderCountBadge";
import { SignalChartSvg } from "@/components/SignalChartSvg";
import { SignalSnapshotView } from "@/components/SignalSnapshotView";
import { PlaybookView } from "@/components/PlaybookView";
import { TrackTradeForm } from "@/components/TrackTradeForm";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useHolderCounts } from "@/hooks/useInstitutionals";
import { useSignalOhlcv } from "@/hooks/useSignalOhlcv";
import { daysBetween, isDelayedDetection } from "@/lib/alertDates";
import {
  TONE_BORDER_LEFT,
  TONE_TEXT,
  NATURE_BG,
  NATURE_LABEL,
  getAlertMeta,
  isSignalKind,
  resolveSnapshot,
  signalNature,
  type AlertTone,
} from "@/lib/alertMeta";
import { cn } from "@/lib/utils";
import { buildPlaybook } from "@/lib/tradePlaybook";

interface Props {
  alert: Alert | null;
  onClose: () => void;
}

/* Format helpers */

function formatAbsolute(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "";
  const diffMin = (Date.now() - ts) / (1000 * 60);
  if (diffMin < 1) return "pochi secondi fa";
  if (diffMin < 60) return `${Math.round(diffMin)}m fa`;
  const diffH = diffMin / 60;
  if (diffH < 24) return `${Math.round(diffH)}h fa`;
  const diffD = diffH / 24;
  if (diffD < 30) return `${Math.round(diffD)}g fa`;
  const diffMo = diffD / 30;
  if (diffMo < 12) return `${Math.round(diffMo)} mesi fa`;
  return `${Math.round(diffMo / 12)} anni fa`;
}

/** Fallback horizon in trading days per snapshot.horizon bucket — mirrors the
 *  backend's `_H_BY_HORIZON` (signal_drift_service). Used only when the alert
 *  hasn't matured yet (no outcome_horizon_days); final fallback is 14. */
const HORIZON_FALLBACK_DAYS: Record<string, number> = { short: 5, medium: 21, long: 63 };

/** Days until the next earnings release IF it falls inside the signal's
 *  horizon window, else null (also null for past dates from a stale cache). */
function earningsProximityDays(a: {
  next_earnings_date?: string | null;
  outcome_horizon_days?: number | null;
  snapshot: Record<string, unknown>;
}): number | null {
  if (!a.next_earnings_date) return null;
  const ts = Date.parse(a.next_earnings_date.slice(0, 10));
  if (Number.isNaN(ts)) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((ts - today.getTime()) / 86_400_000);
  if (days < 0) return null; // già passati (cache non aggiornata) → niente badge
  const hzKey = (a.snapshot as { horizon?: unknown }).horizon;
  const horizon =
    a.outcome_horizon_days ??
    (typeof hzKey === "string" ? HORIZON_FALLBACK_DAYS[hzKey] : undefined) ??
    14;
  return days <= horizon ? days : null;
}

function SnapshotRow({
  label,
  value,
  hint,
  valueTone,
}: {
  label: string;
  value: string;
  hint?: string;
  valueTone?: AlertTone;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 border-b border-border/40 last:border-b-0">
      <div className="flex flex-col min-w-0 flex-1">
        <span className="text-sm font-medium text-foreground/80">{label}</span>
        {hint && (
          <span className="text-xs text-muted-foreground italic mt-0.5">
            {hint}
          </span>
        )}
      </div>
      <span
        className={cn(
          "text-base font-bold tabular-nums shrink-0",
          valueTone ? TONE_TEXT[valueTone] : "text-foreground",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function AlertDetailDialog({ alert, onClose }: Props) {
  // Hooks run unconditionally, above the early-return guard. The OHLCV fetch is
  // gated on isSig so it fires only for signal alerts.
  const [showRaw, setShowRaw] = useState(false);
  const isSig = !!alert && isSignalKind(alert.rule_kind);
  const ohlcvQ = useSignalOhlcv(alert?.ticker, isSig);
  // Smart-money badge: batch endpoint with a single-ticker "batch".
  // Empty array = disabled query (hooks must run unconditionally).
  const holderCounts = useHolderCounts(alert?.ticker ? [alert.ticker] : []);

  if (!alert) {
    return <Dialog open={false} onOpenChange={(open) => !open && onClose()} />;
  }

  const meta = getAlertMeta(alert);
  const resolution = resolveSnapshot(alert.rule_kind, alert.snapshot ?? {});
  const hasResolvedRows = resolution.rows.length > 0;
  const hasRawData = Object.keys(alert.snapshot ?? {}).length > 0;
  const isArchived = alert.archived_at != null;
  const delayed = isDelayedDetection(alert.triggered_at, alert.signal_date);
  const delta = daysBetween(alert.triggered_at, alert.signal_date);
  // Provenance: a snapshot revised after first emission (by a later scan or
  // an enrichment pass) carries `amended_at`. Surface it so the displayed
  // content — incl. confirmation steps appended later — is never mistaken for
  // analysis available at the original emission (`first_emitted_at`).
  const prov = alert.snapshot as { amended_at?: string; first_emitted_at?: string };
  const amendedAt = typeof prov.amended_at === "string" ? prov.amended_at : null;
  const firstEmittedAt = typeof prov.first_emitted_at === "string" ? prov.first_emitted_at : null;
  const inv =
    (alert.snapshot as { invalidation?: { level?: number; reason?: string } | null })
      .invalidation ?? null;
  const invLevel = inv && typeof inv.level === "number" ? inv.level : null;

  return (
    <Dialog open={alert !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-4xl p-0 max-h-[90vh] overflow-y-auto">
        <DialogHeader
          className={cn("p-5 pb-4 space-y-2 border-l-4", TONE_BORDER_LEFT[meta.tone])}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <AlertKindChip alert={alert} />
              <AlertToneChip alert={alert} />
              {(() => {
                const nat = signalNature(
                  alert.rule_kind,
                  (alert.snapshot as { chain?: { label?: string }[] }).chain,
                );
                return nat ? (
                  <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold", NATURE_BG[nat])}>
                    {NATURE_LABEL[nat]}
                  </span>
                ) : null;
              })()}
              {isArchived && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-muted text-muted-foreground">
                  Archiviato
                </span>
              )}
              {(() => {
                // Earnings-proximity risk flag: la trimestrale cade dentro
                // l'orizzonte del segnale → volatilità evento in arrivo.
                const gg = earningsProximityDays(alert);
                if (gg == null) return null;
                return (
                  <span
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60"
                    title={`Trimestrale il ${alert.next_earnings_date}: cade dentro l'orizzonte del segnale — attesa volatilità da evento.`}
                  >
                    <CalendarClock className="h-3 w-3" />
                    {gg === 0 ? "Earnings oggi" : `Earnings tra ${gg} gg`}
                  </span>
                );
              })()}
            </div>
            <div className="text-right shrink-0 pr-6">
              <div
                className={cn(
                  "flex items-center justify-end gap-1 text-[11px] font-semibold",
                  delayed ? "text-amber-700 dark:text-amber-300" : "text-muted-foreground",
                )}
              >
                {delayed ? <Clock className="h-3 w-3" /> : <CalendarClock className="h-3 w-3" />}
                {delayed ? "Rilevato in ritardo" : "Rilevato"}
              </div>
              <div className="text-[11px] text-muted-foreground tabular-nums mt-0.5">
                {formatRelative(alert.triggered_at)} - {formatAbsolute(alert.triggered_at)}
              </div>
              {delayed && delta != null && (
                <div className="text-[10px] text-amber-700 dark:text-amber-300 italic mt-0.5">
                  +{delta}g vs segnale
                </div>
              )}
              {amendedAt && (
                <div
                  className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60"
                  title={`Snapshot rivisto da uno scan successivo il ${formatAbsolute(amendedAt)}${
                    firstEmittedAt ? ` · emesso originariamente il ${formatAbsolute(firstEmittedAt)}` : ""
                  }. La catena riflette l'ultima revisione: eventi aggiunti dopo non risalgono alla data di emissione originale.`}
                >
                  <Pencil className="h-2.5 w-2.5" />
                  Rivisto {formatRelative(amendedAt)}
                </div>
              )}
            </div>
          </div>
          <DialogTitle className="text-2xl flex items-baseline gap-2 flex-wrap">
            {alert.ticker ? (
              <Link
                to={`/stocks/${encodeURIComponent(alert.ticker)}`}
                onClick={onClose}
                className="font-bold tracking-tight hover:underline decoration-2 underline-offset-4"
                title="Vai al dettaglio stock"
              >
                {alert.ticker}
              </Link>
            ) : (
              <span className="font-bold tracking-tight">-</span>
            )}
            {alert.name && (
              <span className="text-base font-medium text-muted-foreground truncate min-w-0">
                {alert.name}
              </span>
            )}
            {alert.ticker && (
              <HolderCountBadge count={holderCounts.data?.[alert.ticker]} />
            )}
          </DialogTitle>
          <DialogDescription className="sr-only">
            Dettagli segnale {meta.label} per {alert.ticker ?? "ticker sconosciuto"}.
          </DialogDescription>
        </DialogHeader>

        <div className="px-5 grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-border/60 bg-muted/30 dark:bg-muted/15 p-3">
            <div className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
              <DollarSign className="h-3 w-3" />
              Prezzo trigger
            </div>
            <div className="text-2xl font-bold tabular-nums mt-1 leading-tight">
              ${alert.trigger_price.toFixed(2)}
            </div>
          </div>

          <div
            className={cn(
              "rounded-lg border p-3",
              invLevel != null
                ? "border-amber-300/70 bg-amber-50/60 dark:bg-amber-950/20"
                : "border-border/60 bg-muted/30 dark:bg-muted/15",
            )}
          >
            <div
              className={cn(
                "flex items-center gap-1 text-[11px] uppercase tracking-wider font-semibold",
                invLevel != null ? "text-amber-700 dark:text-amber-300" : "text-muted-foreground",
              )}
            >
              <ShieldAlert className="h-3 w-3" />
              Invalidazione
            </div>
            {invLevel != null ? (
              <>
                <div className="text-2xl font-bold tabular-nums mt-1 leading-tight">
                  ${invLevel.toFixed(2)}
                </div>
                {inv?.reason && (
                  <div className="text-[11px] text-muted-foreground mt-0.5 leading-snug">
                    {inv.reason}
                  </div>
                )}
              </>
            ) : (
              <div className="text-base font-medium italic mt-1 leading-tight text-muted-foreground">
                n/d
              </div>
            )}
          </div>

          <div className="rounded-lg border border-border/60 bg-muted/30 dark:bg-muted/15 p-3">
            <div className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
              <CalendarRange className="h-3 w-3" />
              Data segnale
            </div>
            {alert.signal_date ? (
              <>
                <div className="text-base font-bold tabular-nums mt-1 leading-tight">
                  {new Date(alert.signal_date).toLocaleDateString("it-IT", {
                    weekday: "short",
                    day: "numeric",
                    month: "short",
                  })}
                </div>
                <div className="text-xs text-muted-foreground tabular-nums mt-0.5">
                  {alert.signal_date}
                </div>
              </>
            ) : (
              <>
                <div className="text-base font-medium italic mt-1 leading-tight text-muted-foreground">
                  n/d
                </div>
                <div
                  className="text-xs text-muted-foreground italic mt-0.5"
                  title="Segnale legacy creato prima della data segnale"
                >
                  legacy
                </div>
              </>
            )}
          </div>
        </div>

        {/* Esito realizzato — dal warehouse signal_outcomes. Presente solo per
            segnali con signal_date: maturato → valori reali; altrimenti hint
            "in maturazione". I legacy senza signal_date non maturano mai →
            nessuna sezione. */}
        {isSignalKind(alert.rule_kind) && alert.signal_date && (
          <div className="px-5 pt-4">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
              Esito realizzato
            </div>
            {alert.outcome_hit != null ? (
              (() => {
                const hit = alert.outcome_hit;
                const fwd = alert.outcome_fwd_return;
                const mkt = alert.outcome_mkt_excess;
                const hz = alert.outcome_horizon_days;
                const fmtPct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
                return (
                  <div
                    className={cn(
                      "rounded-lg border p-3 flex items-center gap-5 flex-wrap",
                      hit
                        ? "border-emerald-300/70 bg-emerald-50/60 dark:bg-emerald-950/20"
                        : "border-rose-300/70 bg-rose-50/60 dark:bg-rose-950/20",
                    )}
                  >
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold",
                        hit
                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
                          : "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
                      )}
                    >
                      {hit ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                      {hit ? "Direzione azzeccata" : "Direzione mancata"}
                    </span>
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                        Ritorno a {hz ?? "?"} gg
                      </div>
                      <div
                        className={cn(
                          "font-bold tabular-nums",
                          fwd != null && fwd >= 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-rose-600 dark:text-rose-400",
                        )}
                      >
                        {fwd != null ? fmtPct(fwd) : "n/d"}
                      </div>
                    </div>
                    {mkt != null && (
                      <div title="Excess market-neutral: quanto il segnale ha battuto la media dell'universo nella sua direzione, sullo stesso orizzonte.">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                          Excess vs mercato
                        </div>
                        <div
                          className={cn(
                            "font-bold tabular-nums",
                            mkt >= 0
                              ? "text-emerald-600 dark:text-emerald-400"
                              : "text-rose-600 dark:text-rose-400",
                          )}
                        >
                          {fmtPct(mkt)}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()
            ) : (
              <div className="rounded-lg border border-dashed border-border/60 p-3 text-xs text-muted-foreground italic">
                Esito in corso di maturazione: l'orizzonte del segnale non è ancora
                trascorso nei dati di mercato.
              </div>
            )}
          </div>
        )}

        {isSignalKind(alert.rule_kind) && (
          <div className="px-5 pt-4">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
              Grafico del segnale
            </div>
            <SignalChartSvg
              bars={ohlcvQ.data ?? []}
              annotations={(alert.snapshot as { annotations?: SignalSnapshot["annotations"] }).annotations}
              chain={(alert.snapshot as { chain?: SignalChainStep[] }).chain ?? []}
            />
          </div>
        )}

        <div className="px-5 pt-4 pb-1">
          {!isSignalKind(alert.rule_kind) && (
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
              Snapshot del trigger
            </div>
          )}
          {isSignalKind(alert.rule_kind) ? (
            <SignalSnapshotView
              snapshot={alert.snapshot ?? {}}
              showInvalidation={false}
              detector={(alert.rule_kind ?? "").replace(/^signal:/, "") || undefined}
            />
          ) : hasResolvedRows ? (
            <div className="rounded-lg border border-border/60 px-3 py-1">
              {resolution.rows.map((r) => (
                <SnapshotRow key={r.label} {...r} />
              ))}
            </div>
          ) : hasRawData ? (
            <pre className="rounded-lg border border-border/60 bg-muted/40 dark:bg-muted/15 p-3 text-xs overflow-auto max-h-48 leading-relaxed">
              {JSON.stringify(alert.snapshot, null, 2)}
            </pre>
          ) : (
            <div className="rounded-lg border border-dashed border-border/60 p-3 text-xs text-muted-foreground italic text-center">
              Nessun dato di snapshot per questo segnale.
            </div>
          )}

          {(hasResolvedRows || isSignalKind(alert.rule_kind)) && hasRawData && (
            <button
              type="button"
              onClick={() => setShowRaw((v) => !v)}
              className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <Code2 className="h-3 w-3" />
              {showRaw ? "Nascondi" : "Mostra"} JSON grezzo
              <ChevronDown
                className={cn("h-3 w-3 transition-transform", showRaw && "rotate-180")}
              />
            </button>
          )}
          {(hasResolvedRows || isSignalKind(alert.rule_kind)) && hasRawData && showRaw && (
            <pre className="mt-2 rounded-lg border border-border/60 bg-muted/40 dark:bg-muted/15 p-3 text-xs overflow-auto max-h-48 leading-relaxed">
              {JSON.stringify(alert.snapshot, null, 2)}
            </pre>
          )}
        </div>

        {isSignalKind(alert.rule_kind) && (() => {
          const pb = buildPlaybook(alert.snapshot ?? {}, alert.trigger_price, alert.rule_kind ?? null);
          return (
            <div className="px-5 pt-2 pb-4">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
                Piano operativo
              </div>
              {pb ? (
                <>
                  <PlaybookView playbook={pb} />
                  {/* B3-6: persiste entry/stop/target del piano come
                      posizione tracciata (P&L live + chiusura automatica
                      su stop/target). Prefill dal playbook + alert_id. */}
                  {alert.ticker && (
                    <TrackTradeForm
                      ticker={alert.ticker}
                      alertId={alert.id}
                      playbook={pb}
                    />
                  )}
                </>
              ) : (
                <div className="rounded-lg border border-dashed border-border/60 p-3 text-xs text-muted-foreground italic text-center">
                  Piano non disponibile: manca un livello di stop strutturale per questo segnale.
                </div>
              )}
            </div>
          );
        })()}
      </DialogContent>
    </Dialog>
  );
}
