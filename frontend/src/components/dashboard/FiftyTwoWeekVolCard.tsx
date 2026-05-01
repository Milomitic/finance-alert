import type { Mover, MoversBlock, VolumeSpike } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface Props {
  movers: MoversBlock;
}

function ListRow({ m, kind }: { m: Mover; kind: "high" | "low" }) {
  const arrow = kind === "high" ? "📈" : "📉";
  const color = kind === "high" ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400";
  return (
    <tr className="border-b border-border/50">
      <td className="px-2 py-1.5">{arrow}</td>
      <td className="px-3 py-1.5 font-semibold">{m.ticker}</td>
      <td className="px-2 py-1.5 text-[10px] text-muted-foreground">{m.index ?? "—"}</td>
      <td className={`px-3 py-1.5 text-right tabular-nums ${color}`}>${m.last_close.toFixed(2)}</td>
    </tr>
  );
}

function VolRow({ m }: { m: VolumeSpike }) {
  const positive = m.change_pct >= 0;
  return (
    <tr className="border-b border-border/50">
      <td className="px-3 py-1.5 font-semibold">{m.ticker}</td>
      <td className="px-2 py-1.5 text-[10px] text-muted-foreground">{m.index ?? "—"}</td>
      <td className="px-3 py-1.5 text-right tabular-nums">{m.vol_ratio.toFixed(1)}×</td>
      <td className={`px-3 py-1.5 text-right tabular-nums ${positive ? "text-green-600" : "text-red-600"}`}>
        {m.change_pct >= 0 ? "+" : ""}{m.change_pct.toFixed(2)}%
      </td>
    </tr>
  );
}

export function FiftyTwoWeekVolCard({ movers }: Props) {
  return (
    <Card>
      <CardContent className="p-0">
        <Tabs defaultValue="hilo">
          <TabsList className="h-9 px-1 rounded-none border-b w-full justify-start bg-muted/30">
            <TabsTrigger value="hilo" className="text-xs h-8 px-3">52w events</TabsTrigger>
            <TabsTrigger value="vol" className="text-xs h-8 px-3">Volume spikes</TabsTrigger>
          </TabsList>
          <TabsContent value="hilo" className="m-0">
            <div className="px-3 py-2 text-xs text-muted-foreground">
              📈 {movers.new_52w_high.length} highs · 📉 {movers.new_52w_low.length} lows
            </div>
            <table className="w-full text-xs">
              <tbody>
                {movers.new_52w_high.map((m) => <ListRow key={`h-${m.ticker}`} m={m} kind="high" />)}
                {movers.new_52w_low.map((m) => <ListRow key={`l-${m.ticker}`} m={m} kind="low" />)}
                {movers.new_52w_high.length === 0 && movers.new_52w_low.length === 0 && (
                  <tr><td colSpan={4} className="text-xs text-muted-foreground text-center py-6">Nessun evento</td></tr>
                )}
              </tbody>
            </table>
          </TabsContent>
          <TabsContent value="vol" className="m-0">
            <table className="w-full text-xs">
              <tbody>
                {movers.volume_spikes.map((m) => <VolRow key={m.ticker} m={m} />)}
                {movers.volume_spikes.length === 0 && (
                  <tr><td colSpan={4} className="text-xs text-muted-foreground text-center py-6">Nessuno spike</td></tr>
                )}
              </tbody>
            </table>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
