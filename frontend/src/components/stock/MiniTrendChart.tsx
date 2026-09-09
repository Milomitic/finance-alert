import { currencySymbol } from "@/lib/money";
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

/* Il grafico trimestrale/annuale della scheda Fondamentali.
 *
 * Vive in un file suo per una ragione misurata, non estetica: e' l'unico
 * consumatore di Recharts sulla pagina di un titolo, e importarlo a livello di
 * modulo trascinava 374 kB grezzi (112 kB gz) nel chunk statico della rotta —
 * il 28% del peso di /stocks/:ticker — per una scheda che sta SOTTO la piega.
 * Il grafico principale della pagina e' lightweight-charts, tutt'altra
 * libreria. Il caricamento pigro lo sposta fuori dal percorso critico senza
 * cambiare nulla di visibile: chi scorre fin la' vede lo scheletro per un
 * istante. */

export interface ChartPoint {
  label: string;
  revenue?: number | null;
  revenue_est?: number | null;
  eps?: number | null;
  eps_est?: number | null;
}

export default function MiniTrendChart({
  data, hasEstimate, currency = null,
}: { data: ChartPoint[]; hasEstimate: boolean; currency?: string | null }) {
  // Ricavi e utile per azione sono nella valuta di RENDICONTAZIONE, che per
  // una quotata e la sua valuta di quotazione. Gli assi dicevano dollari per
  // tutti, su un catalogo dove un titolo su tre non e in dollari.
  const unit = currencySymbol(currency) ?? "";
  if (data.length === 0) {
    return <div className="text-sm text-muted-foreground text-center py-6">Nessun dato per il grafico</div>;
  }
  // Revenue is huge ($B) — scale into billions for the bar values; Y-axis label
  // says "$B". EPS stays in dollars on the right axis.
  const scaled = data.map((p) => ({
    ...p,
    revenue: p.revenue != null ? p.revenue / 1e9 : null,
    revenue_est: p.revenue_est != null ? p.revenue_est / 1e9 : null,
  }));
  // Detect EPS sign range so we draw the zero reference line only when needed
  const epsValues = scaled.flatMap((p) => [p.eps, p.eps_est]).filter((v): v is number => v != null);
  const hasNegativeEps = epsValues.some((v) => v < 0);
  const hasPositiveEps = epsValues.some((v) => v > 0);
  const showZeroLine = hasNegativeEps && hasPositiveEps;
  // EPS line: indigo so it's distinct from Revenue blue and reads well over
  // both light and dark backgrounds. The estimate line is the same hue but
  // muted + dashed.
  const EPS_COLOR = "#6366f1";       // indigo-500
  const EPS_EST_COLOR = "#a5b4fc";   // indigo-300

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart
        data={scaled}
        margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        barCategoryGap="35%"
        barGap={2}
      >
        <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
        <XAxis dataKey="label" fontSize={10} tickLine={false} axisLine={false} />
        <YAxis
          yAxisId="rev" orientation="left" fontSize={10} tickLine={false} axisLine={false} width={36}
          tickFormatter={(v) => `${v.toFixed(0)}B`}
        />
        <YAxis
          yAxisId="eps" orientation="right" fontSize={10} tickLine={false} axisLine={false} width={36}
          tickFormatter={(v) => `${unit}${v.toFixed(1)}`}
        />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 6, padding: "4px 8px" }}
          formatter={(value: unknown, name: unknown) => {
            const n = typeof value === "number" ? value : Number(value);
            const nm = String(name ?? "");
            if (nm === "Revenue" || nm === "Revenue est") return [`${unit}${n.toFixed(1)}B`, nm];
            if (nm === "EPS" || nm === "EPS est") return [`${unit}${n.toFixed(2)}`, nm];
            return [String(value), nm];
          }}
        />
        <Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} iconSize={8} />
        {showZeroLine && (
          <ReferenceLine yAxisId="eps" y={0} stroke="#64748b" strokeOpacity={0.6}
            strokeDasharray="2 2" />
        )}
        {hasEstimate && (
          <Bar yAxisId="rev" dataKey="revenue_est" name="Revenue est"
            fill="#94a3b8" fillOpacity={0.45} radius={[2, 2, 0, 0]} maxBarSize={32} />
        )}
        <Bar yAxisId="rev" dataKey="revenue" name="Revenue"
          fill="#3b82f6" radius={[2, 2, 0, 0]} maxBarSize={32} />
        {hasEstimate && (
          <Line yAxisId="eps" type="monotone" dataKey="eps_est" name="EPS est"
            stroke={EPS_EST_COLOR} strokeDasharray="4 3" strokeWidth={1.5}
            dot={{ r: 2, fill: EPS_EST_COLOR, stroke: EPS_EST_COLOR }} />
        )}
        <Line yAxisId="eps" type="monotone" dataKey="eps" name="EPS"
          stroke={EPS_COLOR} strokeWidth={2.5}
          dot={{ r: 3, fill: EPS_COLOR, stroke: EPS_COLOR }}
          activeDot={{ r: 5, fill: EPS_COLOR, stroke: "#fff", strokeWidth: 2 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
