import { Clock, History, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";

import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { AlertKindChip, AlertToneChip } from "@/components/AlertChips";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { isDelayedDetection } from "@/lib/alertDates";
import {
  TONE_BORDER_LEFT,
  getAlertMeta,
  getSnapshotHeadline,
} from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

interface Props {
  alerts: Alert[];
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Format an ISO date "YYYY-MM-DD" as a Italian short date (day + month). */
function formatSignalDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "short",
    year: "2-digit",
  });
}

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime();
  const diffMin = (Date.now() - ts) / (1000 * 60);
  if (diffMin < 60) return `${Math.max(1, Math.round(diffMin))}m fa`;
  const diffH = diffMin / 60;
  if (diffH < 24) return `${Math.round(diffH)}h fa`;
  const diffD = diffH / 24;
  if (diffD < 30) return `${Math.round(diffD)}g fa`;
  const diffMo = diffD / 30;
  if (diffMo < 12) return `${Math.round(diffMo)}mes fa`;
  return `${Math.round(diffMo / 12)}a fa`;
}

/* ─── Aggregate stats (header strip) ────────────────────────────────────── */

interface AlertStats {
  total: number;
  bullish: number;
  bearish: number;
  last30d: number;
}

function computeStats(alerts: Alert[]): AlertStats {
  const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
  let bullish = 0;
  let bearish = 0;
  let last30d = 0;
  for (const a of alerts) {
    if (new Date(a.triggered_at).getTime() >= cutoff) last30d++;
    // Effective tone: handles both rule-based alerts (kind tone) and
    // price-target alerts (direction tone) so the aggregate counts
    // include price targets that fired.
    const tone = getAlertMeta(a).tone;
    if (tone === "bullish") bullish++;
    else if (tone === "bearish") bearish++;
  }
  return { total: alerts.length, bullish, bearish, last30d };
}

/* ─── Single-row visual ─────────────────────────────────────────────────── */
/* Layout mirrors a single AlertsTable row, just adapted to the narrower
 * card width: kind chip + tone chip + price + date column, all from the
 * shared `AlertChips` module so the visual exactly matches the alerts
 * page. */

function AlertRow({ alert, onClick }: { alert: Alert; onClick: () => void }) {
  const meta = getAlertMeta(alert);
  const delayed = isDelayedDetection(alert.triggered_at, alert.signal_date);
  const headline = getSnapshotHeadline(alert.rule_kind, alert.snapshot ?? null);

  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "w-full text-left rounded-md border-l-2 px-3 py-2 transition-colors",
          "hover:bg-accent/40 cursor-pointer",
          TONE_BORDER_LEFT[meta.tone],
        )}
      >
        <div className="flex items-start gap-3 flex-wrap">
          {/* LEFT: identity stack — same chips the alerts page uses
              (AlertKindChip + AlertToneChip) so the visual is identical
              across surfaces. Snapshot headline below as a subtle
              subtitle. */}
          <div className="flex flex-col gap-1 min-w-0 flex-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              <AlertKindChip alert={alert} />
              <AlertToneChip alert={alert} />
              <span className="text-sm tabular-nums font-semibold ml-1">
                ${alert.trigger_price.toFixed(2)}
              </span>
            </div>
            {headline && (
              <span
                className="text-[11px] text-muted-foreground tabular-nums truncate"
                title={headline}
              >
                {headline}
              </span>
            )}
          </div>

          {/* RIGHT: date column — signal_date primary, detection secondary.
              Orange clock chip when the system detected the signal ≥1 day
              late. Falls back to triggered_at as primary for legacy rows
              that lack signal_date. */}
          <span className="text-xs text-muted-foreground tabular-nums shrink-0 flex flex-col items-end pt-0.5">
            <span className="font-semibold text-foreground/85 inline-flex items-center gap-1">
              {delayed && (
                <Clock
                  className="h-3 w-3 text-amber-600 dark:text-amber-400"
                  aria-label="Rilevazione in ritardo"
                />
              )}
              {alert.signal_date
                ? formatSignalDate(alert.signal_date)
                : formatRelative(alert.triggered_at)}
            </span>
            <span className="opacity-70">
              {alert.signal_date
                ? `rilevato ${formatRelative(alert.triggered_at)}`
                : formatDate(alert.triggered_at)}
            </span>
          </span>
        </div>
      </button>
    </li>
  );
}

/* ─── Card root ─────────────────────────────────────────────────────────── */

export function StockAlertsHistoryCard({ alerts }: Props) {
  const [open, setOpen] = useState<Alert | null>(null);

  // Sort by triggered_at desc — backend should already order, but defensive.
  const sorted = useMemo(
    () =>
      [...alerts].sort(
        (a, b) =>
          new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime(),
      ),
    [alerts],
  );
  const stats = useMemo(() => computeStats(sorted), [sorted]);

  return (
    <>
      <Card>
        <CardContent className="p-4">
          {/* Header strip: title + aggregate stats (bull/bear/last30d/unread) */}
          <SectionTitle
            icon={History}
            label={`Alert storici per questo ticker (${stats.total})`}
            className="mb-3"
            right={
              stats.total > 0 ? (
                <div className="flex items-center gap-2 flex-wrap text-xs">
                  {stats.last30d > 0 && (
                    <span
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted/70"
                      title="Alert generati negli ultimi 30 giorni"
                    >
                      <span className="text-muted-foreground">30d:</span>
                      <span className="font-bold tabular-nums">{stats.last30d}</span>
                    </span>
                  )}
                  {stats.bullish > 0 && (
                    <span
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200"
                      title="Alert con tono bullish (RSI oversold, golden cross, breakout, ecc.)"
                    >
                      <TrendingUp className="h-3 w-3" />
                      <span className="font-bold tabular-nums">{stats.bullish}</span>
                    </span>
                  )}
                  {stats.bearish > 0 && (
                    <span
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-100 dark:bg-rose-900/40 text-rose-800 dark:text-rose-200"
                      title="Alert con tono bearish (RSI overbought, death cross, ecc.)"
                    >
                      <TrendingDown className="h-3 w-3" />
                      <span className="font-bold tabular-nums">{stats.bearish}</span>
                    </span>
                  )}
                </div>
              ) : undefined
            }
          />

          {sorted.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-8">
              Nessun alert mai generato per questo ticker.
              <div className="text-xs mt-1 opacity-75">
                Quando una regola si attiva sui dati di questo titolo, l'alert
                comparirà qui in cima.
              </div>
            </div>
          ) : (
            // Cap at ~14 rows visible (≈ 60px each); scroll for the rest.
            // Full list is preserved (no slice/+N truncation) since this
            // is the canonical history view for the ticker.
            <ul className="space-y-1 max-h-[420px] overflow-y-auto pr-1 -mr-1">
              {sorted.map((a) => (
                <AlertRow key={a.id} alert={a} onClick={() => setOpen(a)} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <AlertDetailDialog alert={open} onClose={() => setOpen(null)} />
    </>
  );
}
