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

interface Props {
  alerts: Alert[];
  selectedIds: Set<number>;
  onSelect: (id: number, selected: boolean) => void;
  onSelectAll: (selected: boolean) => void;
  onRowClick: (alert: Alert) => void;
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

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
            <TableCell className="font-medium">{a.ticker ?? "—"}</TableCell>
            <TableCell>
              <Badge variant="secondary">{KIND_LABEL[a.rule_kind ?? ""] ?? a.rule_kind}</Badge>
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
