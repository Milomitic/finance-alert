import {
  CalendarClock,
  CalendarRange,
  ChevronDown,
  Clock,
  Code2,
  DollarSign,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Alert, SignalChainStep, SignalSnapshot } from "@/api/types";
import { AlertKindChip, AlertToneChip } from "@/components/AlertChips";
import { SignalChartSvg } from "@/components/SignalChartSvg";
import { SignalSnapshotView } from "@/components/SignalSnapshotView";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { daysBetween, isDelayedDetection } from "@/lib/alertDates";
import {
  TONE_BORDER_LEFT,
  TONE_TEXT,
  getAlertMeta,
  isSignalKind,
  resolveSnapshot,
  type AlertTone,
} from "@/lib/alertMeta";
import { cn } from "@/lib/utils";
import { useSignalOhlcv } from "@/hooks/useSignalOhlcv";

interface Props {
  alert: Alert | null;
  onClose: () => void;
}

/* ─── Format helpers ────────────────────────────────────────────────────── */

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

/* ─── Snapshot row visual ───────────────────────────────────────────────── */

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

/* ─── Dialog ────────────────────────────────────────────────────────────── */

/**
 * Alert detail dialog.
 *
 * Layout (top → bottom):
 *   1. Header: rule-kind chip (icon + tone) + ticker as a clickable Link
 *      to the stock detail page.
 *   2. Hero strip: trigger price (large, prominent) + when-it-fired
 *      (relative + absolute).
 *   3. Snapshot section: the JSON dict from the rule's `snapshot()` call,
 *      translated into labeled human rows for the rules we know about.
 *      Unknown shapes (composite, future rules) fall back to a collapsible
 *      raw-JSON viewer so power users can still see everything.
 *   4. Footer: primary CTA "Apri dettaglio stock" (the most likely next
 *      action — go look at the chart) + a Close.
 */
export function AlertDetailDialog({ alert, onClose }: Props) {
  // Hooks must run unconditionally — keep state + queries above the
  // early-return guard. The OHLCV fetch is gated on `isSig` so it only fires
  // for signal alerts (the only kind that carries an annotated chart).
  const [showRaw, setShowRaw] = useState(false);
  const isSig = !!alert && isSignalKind(alert.rule_kind);
  const ohlcvQ = useSignalOhlcv(alert?.ticker, isSig);

  if (!alert) {
    return <Dialog open={false} onOpenChange={(open) => !open && onClose()} />;
  }

  // Effective meta drives the header band's left-border color. Chips
  // render via the shared AlertKindChip + AlertToneChip components so
  // the visual matches the alerts table and the stock-detail card.
  const meta = getAlertMeta(alert);
  const resolution = resolveSnapshot(alert.rule_kind, alert.snapshot ?? {});
  const hasResolvedRows = resolution.rows.length > 0;
  const hasRawData = Object.keys(alert.snapshot ?? {}).length > 0;
  const isArchived = alert.archived_at != null;

  return (
    <Dialog open={alert !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-4xl p-0 overflow-hidden">
        {/* HEADER — colored band carrying the rule-kind tone. The chip + ticker
            sit on a single baseline so the eye reads "this kind of alert / on
            this ticker" in one fixation. */}
        <DialogHeader
          className={cn(
            "p-5 pb-4 space-y-2 border-l-4",
            TONE_BORDER_LEFT[meta.tone],
          )}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <AlertKindChip alert={alert} />
            <AlertToneChip alert={alert} />
            {isArchived && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-muted text-muted-foreground">
                Archiviato
              </span>
            )}
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
              <span className="font-bold tracking-tight">—</span>
            )}
            {alert.name && (
              <span className="text-base font-medium text-muted-foreground truncate min-w-0">
                {alert.name}
              </span>
            )}
          </DialogTitle>
          {/* Visually-hidden description satisfies Radix a11y warnings for
              screen readers — the visible content above already conveys
              everything sighted users need. */}
          <DialogDescription className="sr-only">
            Dettagli dell'alert {meta.label} per {alert.ticker ?? "ticker sconosciuto"}.
          </DialogDescription>
        </DialogHeader>

        {/* HERO STRIP — three side-by-side tiles: trigger price + signal
            date (when the market did the thing) + detection timestamp
            (when the system noticed). Splitting "when" into two cells lets
            the user spot delayed-detection cases (orange clock badge). */}
        {(() => {
          const delayed = isDelayedDetection(alert.triggered_at, alert.signal_date);
          const delta = daysBetween(alert.triggered_at, alert.signal_date);
          return (
            <div className="px-5 grid grid-cols-3 gap-3">
              {/* Trigger price */}
              <div className="rounded-lg border border-border/60 bg-muted/30 dark:bg-muted/15 p-3">
                <div className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                  <DollarSign className="h-3 w-3" />
                  Prezzo trigger
                </div>
                <div className="text-2xl font-bold tabular-nums mt-1 leading-tight">
                  ${alert.trigger_price.toFixed(2)}
                </div>
              </div>

              {/* Signal date — when the rule's condition matched on the
                  underlying market data. The "primary" date conceptually:
                  it's the answer to "when did the indicator fire?". */}
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
                      title="Alert legacy creato prima dell'introduzione della data segnale"
                    >
                      legacy
                    </div>
                  </>
                )}
              </div>

              {/* Detection timestamp — when the scan job created the row.
                  Orange clock + tinted background appear when the gap from
                  signal_date is ≥ 1 calendar day, since that means the
                  alert "looks fresh" but the underlying bar is older. */}
              <div
                className={cn(
                  "rounded-lg border p-3",
                  delayed
                    ? "border-amber-300/70 bg-amber-50/60 dark:bg-amber-950/20"
                    : "border-border/60 bg-muted/30 dark:bg-muted/15",
                )}
                title={
                  delayed && delta != null
                    ? `Il sistema ha rilevato il segnale ${delta}g dopo la barra di mercato. Possibile backfill o scan saltato.`
                    : "Quando lo scan ha registrato l'alert"
                }
              >
                <div
                  className={cn(
                    "flex items-center gap-1 text-[11px] uppercase tracking-wider font-semibold",
                    delayed
                      ? "text-amber-700 dark:text-amber-300"
                      : "text-muted-foreground",
                  )}
                >
                  {delayed ? <Clock className="h-3 w-3" /> : <CalendarClock className="h-3 w-3" />}
                  {delayed ? "Rilevato (in ritardo)" : "Rilevato"}
                </div>
                <div className="text-base font-bold tabular-nums mt-1 leading-tight">
                  {formatRelative(alert.triggered_at)}
                </div>
                <div className="text-xs text-muted-foreground tabular-nums mt-0.5">
                  {formatAbsolute(alert.triggered_at)}
                </div>
                {delayed && delta != null && (
                  <div className="text-[11px] text-amber-700 dark:text-amber-300 italic mt-1.5">
                    +{delta}g vs segnale
                  </div>
                )}
              </div>
            </div>
          );
        })()}

        {/* ANNOTATED CHART — signal alerts only. A static SVG screenshot of the
            recent price (close line) with the detector's annotation levels +
            pattern shape + numbered chain markers, so the user can SEE the
            setup the chain describes. Fetched lazily by useSignalOhlcv. */}
        {isSignalKind(alert.rule_kind) && (
          <div className="px-5 pt-4">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
              Grafico del segnale
            </div>
            <SignalChartSvg
              bars={(ohlcvQ.data ?? []).map((b) => ({ date: b.date, close: b.close }))}
              annotations={(alert.snapshot as { annotations?: SignalSnapshot["annotations"] }).annotations}
              chain={(alert.snapshot as { chain?: SignalChainStep[] }).chain ?? []}
              tone={
                (alert.snapshot as { tone?: string }).tone === "bull"
                  ? "bull"
                  : (alert.snapshot as { tone?: string }).tone === "bear"
                    ? "bear"
                    : "neutral"
              }
            />
          </div>
        )}

        {/* SNAPSHOT — labeled rows when we know the kind, raw JSON otherwise. */}
        <div className="px-5 pt-4 pb-1">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            {isSignalKind(alert.rule_kind) ? "Dettaglio segnale" : "Snapshot del trigger"}
          </div>
          {isSignalKind(alert.rule_kind) ? (
            <SignalSnapshotView snapshot={alert.snapshot ?? {}} />
          ) : hasResolvedRows ? (
            <div className="rounded-lg border border-border/60 px-3 py-1">
              {resolution.rows.map((r) => (
                <SnapshotRow key={r.label} {...r} />
              ))}
            </div>
          ) : hasRawData ? (
            // Unknown rule kind (composite, future, legacy): keep the JSON
            // dump but make it presentable — still informative for power
            // users without dominating the dialog visually.
            <pre className="rounded-lg border border-border/60 bg-muted/40 dark:bg-muted/15 p-3 text-xs overflow-auto max-h-48 leading-relaxed">
              {JSON.stringify(alert.snapshot, null, 2)}
            </pre>
          ) : (
            <div className="rounded-lg border border-dashed border-border/60 p-3 text-xs text-muted-foreground italic text-center">
              Nessun dato di snapshot per questo alert.
            </div>
          )}

          {/* Power-user "raw JSON" toggle, available whenever we DO have a
              resolved view but raw data also exists. Lets a debugger inspect
              every field without forcing the JSON into the primary view. */}
          {(hasResolvedRows || isSignalKind(alert.rule_kind)) && hasRawData && (
            <button
              type="button"
              onClick={() => setShowRaw((v) => !v)}
              className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <Code2 className="h-3 w-3" />
              {showRaw ? "Nascondi" : "Mostra"} JSON grezzo
              <ChevronDown
                className={cn(
                  "h-3 w-3 transition-transform",
                  showRaw && "rotate-180",
                )}
              />
            </button>
          )}
          {(hasResolvedRows || isSignalKind(alert.rule_kind)) && hasRawData && showRaw && (
            <pre className="mt-2 rounded-lg border border-border/60 bg-muted/40 dark:bg-muted/15 p-3 text-xs overflow-auto max-h-48 leading-relaxed">
              {JSON.stringify(alert.snapshot, null, 2)}
            </pre>
          )}
        </div>

        {/* Footer ("Chiudi" + "Apri dettaglio stock") removed per user
            feedback: shadcn's Dialog already provides a top-right
            close button + Esc-to-close, and the user accesses stock
            detail via the ticker link inside the dialog body — the
            footer was redundant on both surfaces (alerts page +
            stock-detail). */}
      </DialogContent>
    </Dialog>
  );
}
