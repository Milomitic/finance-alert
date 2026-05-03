import { Link } from "react-router-dom";

import type { Mover, MoversBlock, VolumeSpike } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { IndexBadge } from "@/components/dashboard/IndexBadge";
import { StockLogo } from "@/components/dashboard/StockLogo";

interface Props {
  movers: MoversBlock;
}

function MoverRow({ m }: { m: Mover | VolumeSpike }) {
  const change = m.change_pct ?? 0;
  const positive = change >= 0;
  return (
    <tr className="border-b border-border/50 hover:bg-muted/40 transition-colors">
      <td className="px-3 py-1.5 font-semibold">
        <Link to={`/stocks/${encodeURIComponent(m.ticker)}`} className="inline-flex items-center gap-2 hover:underline">
          <StockLogo ticker={m.ticker} size="xs" />
          <span>{m.ticker}</span>
        </Link>
      </td>
      <td className="px-2 py-1.5"><IndexBadge code={m.index} size="xs" /></td>
      <td className={`px-3 py-1.5 text-right ${positive ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
        {change >= 0 ? "+" : ""}{change.toFixed(2)}%
      </td>
      {"vol_ratio" in m && (
        <td className="px-3 py-1.5 text-right">{(m as VolumeSpike).vol_ratio.toFixed(1)}×</td>
      )}
    </tr>
  );
}

function MoversTable({ rows }: { rows: Mover[] | VolumeSpike[] }) {
  if (rows.length === 0) {
    return <div className="text-sm text-muted-foreground text-center py-6">Nessun dato</div>;
  }
  return (
    <table className="w-full text-sm tabular-nums">
      <tbody>
        {rows.map((m) => <MoverRow key={m.ticker} m={m} />)}
      </tbody>
    </table>
  );
}

export function MoversCard({ movers }: Props) {
  return (
    <Card>
      <CardContent className="p-0 h-full flex flex-col">
        <Tabs defaultValue="gainers" className="flex-1 flex flex-col">
          <TabsList className="h-10 px-1 rounded-none border-b w-full justify-start bg-muted/30">
            <TabsTrigger value="gainers" className="text-sm h-9 px-3">Gainers</TabsTrigger>
            <TabsTrigger value="losers" className="text-sm h-9 px-3">Losers</TabsTrigger>
            <TabsTrigger value="vol" className="text-sm h-9 px-3" title="Top stock con volume oggi maggiore di 2× la media a 20 giorni">Volume×</TabsTrigger>
            <TabsTrigger value="hilo" className="text-sm h-9 px-3" title="Stock che oggi raggiungono nuovi massimi/minimi a 52 settimane">52w↑↓</TabsTrigger>
          </TabsList>
          <TabsContent value="gainers" className="m-0 max-h-[280px] overflow-y-auto">
            <MoversTable rows={movers.gainers} />
          </TabsContent>
          <TabsContent value="losers" className="m-0 max-h-[280px] overflow-y-auto">
            <MoversTable rows={movers.losers} />
          </TabsContent>
          <TabsContent value="vol" className="m-0 max-h-[280px] overflow-y-auto">
            <MoversTable rows={movers.volume_spikes} />
          </TabsContent>
          <TabsContent value="hilo" className="m-0 max-h-[280px] overflow-y-auto">
            <div className="px-3 py-2 text-sm text-muted-foreground">
              📈 {movers.new_52w_high.length} highs · 📉 {movers.new_52w_low.length} lows
            </div>
            <MoversTable rows={[...movers.new_52w_high, ...movers.new_52w_low]} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
