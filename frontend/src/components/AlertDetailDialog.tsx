import { ArrowRight, CalendarClock, ChevronDown, Code2, DollarSign } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  TONE_BG,
  TONE_BORDER_LEFT,
  TONE_TEXT,
  getAlertKindMeta,
  resolveSnapshot,
  type AlertTone,
} from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

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
  // Hooks must run unconditionally — keep state above the early-return guard.
  const [showRaw, setShowRaw] = useState(false);

  if (!alert) {
    return <Dialog open={false} onOpenChange={(open) => !open && onClose()} />;
  }

  const meta = getAlertKindMeta(alert.rule_kind);
  const Icon = meta.icon;
  const resolution = resolveSnapshot(alert.rule_kind, alert.snapshot ?? {});
  const hasResolvedRows = resolution.rows.length > 0;
  const hasRawData = Object.keys(alert.snapshot ?? {}).length > 0;
  const isUnread = alert.read_at == null;
  const isArchived = alert.archived_at != null;

  return (
    <Dialog open={alert !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg p-0 overflow-hidden">
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
            <span
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold",
                TONE_BG[meta.tone],
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {meta.label}
            </span>
            {isUnread && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-primary/10 text-primary">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                Non letto
              </span>
            )}
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

        {/* HERO STRIP — the two metrics the user most wants when reading
            an alert in isolation: how much was the price, and when did it
            fire. Side-by-side so they can be compared at a glance. */}
        <div className="px-5 grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-border/60 bg-muted/30 dark:bg-muted/15 p-3">
            <div className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
              <DollarSign className="h-3 w-3" />
              Prezzo trigger
            </div>
            <div className="text-2xl font-bold tabular-nums mt-1 leading-tight">
              ${alert.trigger_price.toFixed(2)}
            </div>
          </div>
          <div className="rounded-lg border border-border/60 bg-muted/30 dark:bg-muted/15 p-3">
            <div className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
              <CalendarClock className="h-3 w-3" />
              Triggerato
            </div>
            <div className="text-base font-bold tabular-nums mt-1 leading-tight">
              {formatRelative(alert.triggered_at)}
            </div>
            <div
              className="text-xs text-muted-foreground tabular-nums mt-0.5"
              title={alert.triggered_at}
            >
              {formatAbsolute(alert.triggered_at)}
            </div>
          </div>
        </div>

        {/* SNAPSHOT — labeled rows when we know the kind, raw JSON otherwise. */}
        <div className="px-5 pt-4 pb-1">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            Snapshot del trigger
          </div>
          {hasResolvedRows ? (
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
          {hasResolvedRows && hasRawData && (
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
          {hasResolvedRows && hasRawData && showRaw && (
            <pre className="mt-2 rounded-lg border border-border/60 bg-muted/40 dark:bg-muted/15 p-3 text-xs overflow-auto max-h-48 leading-relaxed">
              {JSON.stringify(alert.snapshot, null, 2)}
            </pre>
          )}
        </div>

        {/* FOOTER — primary CTA goes to the stock detail (the most likely
            next user action: "interesting alert, let me see the chart"). */}
        <DialogFooter className="px-5 py-4 bg-muted/30 dark:bg-muted/10 border-t border-border/60 sm:justify-between gap-2">
          <Button variant="ghost" onClick={onClose} className="sm:order-1">
            Chiudi
          </Button>
          {alert.ticker && (
            <Button asChild className="sm:order-2">
              <Link
                to={`/stocks/${encodeURIComponent(alert.ticker)}`}
                onClick={onClose}
              >
                Apri dettaglio stock
                <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
