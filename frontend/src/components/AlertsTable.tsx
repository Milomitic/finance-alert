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

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8">
            <Checkbox
              checked={allSelected}
              onCheckedChange={(checked) => onSelectAll(!!checked)}
            />
          </TableHead>
          <TableHead>Timestamp</TableHead>
          <TableHead>Ticker</TableHead>
          <TableHead>Nome</TableHead>
          <TableHead>Regola</TableHead>
          <TableHead className="text-right">Prezzo</TableHead>
          <TableHead>Stato</TableHead>
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
            <TableCell className="text-muted-foreground text-xs">
              {new Date(a.triggered_at).toLocaleString("it-IT")}
            </TableCell>
            {/* Ticker cell: stopPropagation so the click navigates to the
                stock detail page instead of bubbling up to the row's onClick
                (which opens the alert popup). The user's mental model is:
                "ticker is always a deep link to that stock, no matter where
                I see it." */}
            <TableCell className="font-medium">
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
            <TableCell className="text-xs text-muted-foreground truncate max-w-[200px]" title={a.name ?? ""}>
              {a.name ?? "—"}
            </TableCell>
            <TableCell>
              <Badge variant="secondary">{getAlertKindMeta(a.rule_kind).label}</Badge>
            </TableCell>
            <TableCell className="text-right tabular-nums">${a.trigger_price}</TableCell>
            <TableCell className="text-xs">
              {a.archived_at
                ? "🗄 Archiviato"
                : a.read_at
                  ? "✅ Letto"
                  : "📩 Non letto"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
