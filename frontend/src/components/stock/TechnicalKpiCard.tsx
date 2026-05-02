import type { IndicatorSeries, StockKpis } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { ACRONYM_HELP } from "@/lib/acronymHelp";

interface Props {
  kpis: StockKpis;
  indicators: IndicatorSeries;
}

function lastValue(series: { value: number | null }[]): number | null {
  for (let i = series.length - 1; i >= 0; i--) {
    if (series[i].value !== null) return series[i].value;
  }
  return null;
}

function fmtNum(v: number | null, digits = 2): string {
  return v == null ? "—" : v.toFixed(digits);
}

export function TechnicalKpiCard({ kpis, indicators }: Props) {
  const sma50 = lastValue(indicators.sma50);
  const sma200 = lastValue(indicators.sma200);
  const rsi = lastValue(indicators.rsi14);

  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          KPI tecnici
        </div>
        <table className="w-full text-sm tabular-nums">
          <tbody>
            <tr><td className="py-1 text-muted-foreground">SMA 50</td><td className="py-1 text-right font-semibold">${fmtNum(sma50)}</td></tr>
            <tr><td className="py-1 text-muted-foreground">SMA 200</td><td className="py-1 text-right font-semibold">${fmtNum(sma200)}</td></tr>
            <tr><td className="py-1 text-muted-foreground" title={ACRONYM_HELP.RSI_OVERSOLD}>RSI(14)</td><td className="py-1 text-right font-semibold">{fmtNum(rsi, 1)}</td></tr>
            <tr><td className="py-1 text-muted-foreground">52w high</td><td className="py-1 text-right">${fmtNum(kpis.high_52w)}</td></tr>
            <tr><td className="py-1 text-muted-foreground">52w low</td><td className="py-1 text-right">${fmtNum(kpis.low_52w)}</td></tr>
            <tr><td className="py-1 text-muted-foreground">Vol oggi</td><td className="py-1 text-right">{kpis.vol_today?.toLocaleString() ?? "—"}</td></tr>
            <tr><td className="py-1 text-muted-foreground" title={ACRONYM_HELP.VOL_SPIKE}>Vol×avg20</td><td className="py-1 text-right font-semibold">{fmtNum(kpis.vol_ratio, 2)}×</td></tr>
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
