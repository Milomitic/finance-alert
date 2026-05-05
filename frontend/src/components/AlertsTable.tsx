import { Clock, Minus, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  daysBetween,
  formatDateTime,
  formatShortDate,
  isDelayedDetection,
} from "@/lib/alertDates";
import { TONE_LABEL, getAlertMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

interface Props {
  alerts: Alert[];
  selectedIds: Set<number>;
  onSelect: (id: number, selected: boolean) => void;
  onSelectAll: (selected: boolean) => void;
  onRowClick: (alert: Alert) => void;
}

export function AlertsTable({
  alerts,
  selectedIds,
  onSelect,
  onSelectAll,
  onRowClick,
}: Props) {
  const allSelected = alerts.length > 0 && alerts.every((a) => selectedIds.has(a.id));

  // Bumped one notch above the shared Table's default text-sm: the alert
  // listing is the page's primary content, not auxiliary metadata, so it
  // earns the larger reading size. Header stays text-sm to preserve the
  // visual hierarchy (label-vs-value); meta cells (timestamp, name,
  // status) move from text-xs to text-sm so they're still slightly
  // smaller than the primary cells but more comfortable to read.
  return (
    <Table className="text-base">
      <TableHeader>
        <TableRow>
          <TableHead className="w-8">
            <Checkbox
              checked={allSelected}
              onCheckedChange={(checked) => onSelectAll(!!checked)}
            />
          </TableHead>
          <TableHead className="text-sm" title="Data della barra di mercato in cui la regola è scattata">
            Data segnale
          </TableHead>
          <TableHead className="text-sm" title="Quando il sistema ha registrato l'alert">
            Rilevato
          </TableHead>
          <TableHead className="text-sm">Ticker</TableHead>
          <TableHead className="text-sm">Nome</TableHead>
          <TableHead className="text-sm">Regola</TableHead>
          <TableHead className="text-sm" title="Direzione semantica dell'alert (rialzista / ribassista / neutra)">
            Tono
          </TableHead>
          <TableHead className="text-sm text-right">Prezzo</TableHead>
          <TableHead className="text-sm">Archivio</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {alerts.map((a) => (
          <TableRow key={a.id} className="cursor-pointer" onClick={() => onRowClick(a)}>
            <TableCell onClick={(e) => e.stopPropagation()}>
              <Checkbox
                checked={selectedIds.has(a.id)}
                onCheckedChange={(c) => onSelect(a.id, !!c)}
              />
            </TableCell>
            {/* Signal date: when the market actually crossed the rule's
                threshold. Bold + tabular so it reads as the primary date —
                this is the one that matters for "when did the indicator
                fire". Backwards-compat: legacy rows have signal_date=null
                and we fall back to "—" with a tip explaining why. */}
            <TableCell className="text-sm font-semibold tabular-nums">
              {a.signal_date ? (
                formatShortDate(a.signal_date)
              ) : (
                <span
                  className="text-muted-foreground italic font-normal"
                  title="Alert legacy creato prima dell'introduzione della data segnale"
                >
                  —
                </span>
              )}
            </TableCell>
            {/* Detection timestamp: when the scan job created the row.
                Highlighted with an orange clock when noticeably later than
                the signal (≥1 calendar day) so the user sees at a glance
                that the system noticed a backfilled signal. */}
            <TableCell className="text-sm text-muted-foreground tabular-nums">
              {(() => {
                const delayed = isDelayedDetection(a.triggered_at, a.signal_date);
                const delta = daysBetween(a.triggered_at, a.signal_date);
                return (
                  <span
                    className="inline-flex items-center gap-1"
                    title={
                      delayed && delta != null
                        ? `Il sistema ha rilevato il segnale ${delta}g dopo la barra di mercato. Possibile backfill o scan saltato.`
                        : "Quando lo scan ha registrato l'alert"
                    }
                  >
                    {delayed && (
                      <Clock className="h-3 w-3 text-amber-600 dark:text-amber-400 shrink-0" />
                    )}
                    {formatDateTime(a.triggered_at)}
                  </span>
                );
              })()}
            </TableCell>
            {/* Ticker cell: stopPropagation so the click navigates to the
                stock detail page instead of bubbling up to the row's onClick
                (which opens the alert popup). The user's mental model is:
                "ticker is always a deep link to that stock, no matter where
                I see it." */}
            <TableCell className="font-semibold">
              {a.ticker ? (
                <Link
                  to={`/stocks/${encodeURIComponent(a.ticker)}`}
                  onClick={(e) => e.stopPropagation()}
                  className="hover:underline"
                  title={`Vai al dettaglio di ${a.ticker}`}
                >
                  {a.ticker}
                </Link>
              ) : (
                "—"
              )}
            </TableCell>
            <TableCell className="text-sm text-muted-foreground truncate max-w-[240px]" title={a.name ?? ""}>
              {a.name ?? "—"}
            </TableCell>
            <TableCell>
              <Badge variant="secondary" className="text-sm">
                {getAlertMeta(a).label}
              </Badge>
            </TableCell>
            <TableCell>
              <ToneChip alert={a} />
            </TableCell>
            <TableCell className="text-right tabular-nums font-semibold">
              ${a.trigger_price}
            </TableCell>
            <TableCell className="text-sm">
              {a.archived_at ? "🗄 Archiviato" : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/* ─── ToneChip — directional tone badge for the alerts table ────────────── */
/* Compact pill: arrow icon + word ("Bullish" / "Bearish" / "Allerta" /
 * "Neutro"). Skips rendering for `tone === "neutral"` so legacy rows
 * without direction (e.g. a Composite without a tone-bearing kind, or a
 * pre-direction price alert) don't get a misleading "Neutro" chip in
 * what's otherwise a directional column. */
function ToneChip({ alert }: { alert: Alert }) {
  const meta = getAlertMeta(alert);
  if (meta.tone === "neutral") {
    return <span className="text-xs text-muted-foreground/60">—</span>;
  }
  const Icon =
    meta.tone === "bullish"
      ? TrendingUp
      : meta.tone === "bearish"
        ? TrendingDown
        : Minus;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm border text-[11px] font-semibold uppercase tracking-wider whitespace-nowrap",
        meta.tone === "bullish" &&
          "border-emerald-300/70 dark:border-emerald-700/60 text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40",
        meta.tone === "bearish" &&
          "border-rose-300/70 dark:border-rose-700/60 text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/40",
        meta.tone === "warning" &&
          "border-amber-300/70 dark:border-amber-700/60 text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40",
      )}
      title={`Tono semantico: ${TONE_LABEL[meta.tone].toLowerCase()}`}
    >
      <Icon className="h-3 w-3" />
      {TONE_LABEL[meta.tone]}
    </span>
  );
}
