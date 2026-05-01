import type { Mover, MoversBlock, VolumeSpike } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { IndexBadge } from "@/components/dashboard/IndexBadge";
import { StockLogo } from "@/components/dashboard/StockLogo";

interface Props {
  movers: MoversBlock;
}

function MoverRow({ m }: { m: Mover | VolumeSpike }) {
  const positive = m.change_pct >= 0;
  return (
    <tr className="border-b border-border/50 hover:bg-muted/40 transition-colors">
      <td className="px-3 py-1.5 font-semibold">
        <span className="inline-flex items-center gap-2">
          <StockLogo ticker={m.ticker} size="xs" />
          <span>{m.ticker}</span>
        </span>
      </td>
      <td className="px-2 py-1.5"><IndexBadge code={m.index} size="xs" /></td>
      <td className={`px-3 py-1.5 text-right ${positive ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
        {m.change_pct >= 0 ? "+" : ""}{m.change_pct.toFixed(2)}%
      </td>
      {"vol_ratio" in m && (
        <td className="px-3 py-1.5 text-right">{(m as VolumeSpike).vol_ratio.toFixed(1)}×</td>
      )}
    </tr>
  );
}

function MoversTable({ rows }: { rows: Mover[] | VolumeSpike[] }) {
  if (rows.length === 0) {
    return <div className="text-xs text-muted-foreground text-center py-6">Nessun dato</div>;
  }
  return (
    <table className="w-full text-xs tabular-nums">
      <tbody>
        {rows.map((m) => <MoverRow key={m.ticker} m={m} />)}
      </tbody>
    </table>
  );
}

export function MoversCard({ movers }: Props) {
  return (
    <Card>
      <CardContent className="p-0">
        <Tabs defaultValue="gainers">
          <TabsList className="h-9 px-1 rounded-none border-b w-full justify-start bg-muted/30">
            <TabsTrigger value="gainers" className="text-xs h-8 px-3">Gainers</TabsTrigger>
            <TabsTrigger value="losers" className="text-xs h-8 px-3">Losers</TabsTrigger>
            <TabsTrigger value="vol" className="text-xs h-8 px-3">Volume×</TabsTrigger>
            <TabsTrigger value="hilo" className="text-xs h-8 px-3">52w↑↓</TabsTrigger>
          </TabsList>
          <TabsContent value="gainers" className="m-0">
            <MoversTable rows={movers.gainers} />
          </TabsContent>
          <TabsContent value="losers" className="m-0">
            <MoversTable rows={movers.losers} />
          </TabsContent>
          <TabsContent value="vol" className="m-0">
            <MoversTable rows={movers.volume_spikes} />
          </TabsContent>
          <TabsContent value="hilo" className="m-0">
            <div className="px-3 py-2 text-xs text-muted-foreground">
              📈 {movers.new_52w_high.length} highs · 📉 {movers.new_52w_low.length} lows
            </div>
            <MoversTable rows={[...movers.new_52w_high, ...movers.new_52w_low]} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
