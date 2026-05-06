import { History, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";

import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { AlertsTable } from "@/components/AlertsTable";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { getAlertMeta } from "@/lib/alertMeta";

interface Props {
  alerts: Alert[];
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

/* ─── Card root ─────────────────────────────────────────────────────────── *
 *
 * Per user feedback, this card now renders the canonical AlertsTable
 * (in `embedded` mode) instead of a custom button-card-per-alert
 * layout. That gives the stock-detail page the same column structure,
 * date columns, kind/tone chips, archive flag, and price formatting
 * as the alerts page — identical info, identical visuals.
 *
 * Embedded-mode adjustments (see AlertsTable):
 *   - No checkbox column (no bulk archive on a per-stock view).
 *   - No search input in the Ticker column header (one stock = one
 *     possible value).
 *   - Ticker + Nome columns dropped — they'd just repeat the same
 *     value on every row.
 *
 * The aggregate stats strip (bull/bear/30d counts) stays at the top
 * since it's distinct context that the alerts page doesn't show.
 */
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

  // No-op handlers for the bulk-action props — embedded mode hides
  // the checkbox column, so these are never invoked in practice.
  const noopSelect = () => {};

  return (
    <>
      <Card>
        <CardContent className="p-4">
          {/* Header strip: title + aggregate stats (bull/bear/last30d) */}
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
            // Cap visible rows to a reasonable height; scroll for the rest.
            // Full list preserved (no slice) since this is the canonical
            // history view for the ticker.
            <div className="max-h-[460px] overflow-y-auto -mx-4 px-4">
              <AlertsTable
                embedded
                alerts={sorted}
                selectedIds={new Set()}
                onSelect={noopSelect}
                onSelectAll={noopSelect}
                onRowClick={setOpen}
                q=""
                onQueryChange={noopSelect}
              />
            </div>
          )}
        </CardContent>
      </Card>
      <AlertDetailDialog alert={open} onClose={() => setOpen(null)} />
    </>
  );
}
