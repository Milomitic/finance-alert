import { Link } from "react-router-dom";

import type { TopStock } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface Props {
  data: TopStock[];
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

export function TopStocksTable({ data }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Top 10 stock (30gg)</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {data.length === 0 ? (
          <div className="p-6 text-center text-sm text-muted-foreground">
            Nessun alert nei 30 giorni.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ticker</TableHead>
                <TableHead>Regola top</TableHead>
                <TableHead className="text-right">Alert</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((s) => (
                <TableRow key={s.stock_id}>
                  <TableCell className="font-medium">
                    <Link
                      to={`/stocks/${encodeURIComponent(s.ticker)}`}
                      className="hover:underline"
                    >
                      {s.ticker}
                    </Link>
                  </TableCell>
                  <TableCell>
                    {s.top_kind ? (
                      <Badge variant="secondary">
                        {KIND_LABEL[s.top_kind] ?? s.top_kind}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {s.alert_count}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
