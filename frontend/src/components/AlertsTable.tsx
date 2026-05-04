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
import { getAlertKindMeta } from "@/lib/alertMeta";

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
          <TableHead className="text-sm">Timestamp</TableHead>
          <TableHead className="text-sm">Ticker</TableHead>
          <TableHead className="text-sm">Nome</TableHead>
          <TableHead className="text-sm">Regola</TableHead>
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
            <TableCell className="text-muted-foreground text-sm">
              {new Date(a.triggered_at).toLocaleString("it-IT")}
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
                {getAlertKindMeta(a.rule_kind).label}
              </Badge>
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
