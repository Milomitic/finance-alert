import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { DataSourceMetric } from "@/api/platformHealth";

type Props = {
  metrics: DataSourceMetric[];
  yfinanceBreaker: Record<string, unknown>;
};

const HEALTH_TONE: Record<string, string> = {
  ok: "bg-emerald-500/10 text-emerald-700 px-1.5 rounded",
  warn: "bg-amber-500/10 text-amber-700 px-1.5 rounded",
  fail: "bg-red-500/10 text-red-700 px-1.5 rounded",
};

export default function DataSourcesCard({ metrics, yfinanceBreaker }: Props) {
  const breakerState = String(yfinanceBreaker.state ?? "ok").toLowerCase();
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">Sorgenti dati</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span>yfinance breaker</span>
          <span className={HEALTH_TONE[breakerState] ?? HEALTH_TONE.ok}>
            {String(yfinanceBreaker.state ?? "—")}
          </span>
        </div>
        <div className="border-t pt-2 space-y-1">
          {metrics.length === 0 && (
            <div className="text-muted-foreground italic">
              Nessuna metrica raccolta ancora
            </div>
          )}
          {metrics.map((m) => (
            <div
              key={`${m.source}.${m.op}`}
              className="flex items-center justify-between"
            >
              <span className="font-mono truncate" title={`${m.source}.${m.op}`}>
                {m.source}.{m.op}
              </span>
              <span className={HEALTH_TONE[m.health] ?? HEALTH_TONE.ok}>
                {(m.success_rate * 100).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
