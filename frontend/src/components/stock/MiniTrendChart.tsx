import { currencySymbol } from "@/lib/money";
import {
  Bar, CartesianGrid, ComposedChart, Line, ReferenceLine,
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

/* ─── I colori delle serie, in un posto solo ───────────────────────────────
 *
 * ⚠️ La legenda non e' piu' quella di Recharts (vedi sotto), quindi il colore
 * di ogni serie viene letto DUE volte: dalla barra o dalla linea che lo
 * disegna, e dal segno che la nomina. Due copie della stessa costante sono la
 * forma che diverge appena qualcuno ne tocca una — in questo progetto e' gia'
 * costata un 500 in produzione, quando `finalize` e `recompute_one`
 * costruivano la stessa riga in due copie e solo una fu aggiornata.
 *
 * EPS in indaco per restare distinto dal blu dei ricavi e leggersi su fondo
 * chiaro e scuro; le stime sono la stessa tinta smorzata. */
const C_EPS = "#6366f1";       // indigo-500
const C_EPS_EST = "#a5b4fc";   // indigo-300
const C_REV = "#3b82f6";       // blue-500
const C_REV_EST = "#94a3b8";   // slate-400

type Voce = { nome: string; colore: string; forma: "linea" | "tratteggio" | "barra" };

/** Il segno accanto al nome. Un quadrato per una barra, un tratto per una
 *  linea: la legenda deve dire anche COME la serie e' disegnata, altrimenti
 *  su quattro voci in due assi diversi non si sa a cosa guardare. */
function Segno({ voce }: { voce: Voce }) {
  if (voce.forma === "barra") {
    return (
      <span
        className="inline-block h-2 w-2 shrink-0 rounded-[1px]"
        style={{ backgroundColor: voce.colore }}
        aria-hidden
      />
    );
  }
  return (
    <svg width="12" height="8" viewBox="0 0 12 8" aria-hidden className="shrink-0">
      <line
        x1="0" y1="4" x2="12" y2="4"
        stroke={voce.colore}
        strokeWidth={voce.forma === "tratteggio" ? 1.5 : 2.5}
        strokeDasharray={voce.forma === "tratteggio" ? "4 3" : undefined}
      />
    </svg>
  );
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

  /* ⚠️ Le voci si costruiscono dalle STESSE costanti che disegnano le serie,
   * e le due stime compaiono solo quando esistono: una legenda che nomina una
   * serie assente dal grafico manda a cercare qualcosa che non c'e'. */
  const voci: Voce[] = [
    { nome: "EPS", colore: C_EPS, forma: "linea" },
    ...(hasEstimate
      ? [{ nome: "EPS est", colore: C_EPS_EST, forma: "tratteggio" } as Voce]
      : []),
    { nome: "Revenue", colore: C_REV, forma: "barra" },
    ...(hasEstimate
      ? [{ nome: "Revenue est", colore: C_REV_EST, forma: "barra" } as Voce]
      : []),
  ];

  return (
    /* ⚠️ La legenda NON e' piu' `<Legend>` di Recharts, ed e' una scelta di
     * layout, non di stile: Recharts RISERVA al grafico un'altezza pari al
     * riquadro misurato della legenda, quindi finche' sta li' dentro non puo'
     * sovrapporsi — toglie spazio al tracciato per definizione. Sfilata dal
     * grafico, la legenda si posa sopra la parte bassa dell'area e quei ~20px
     * tornano al disegno.
     *
     * `pointer-events-none` e' indispensabile: sovrapposta al tracciato,
     * intercetterebbe il passaggio del mouse e spegnerebbe il tooltip proprio
     * sulle barre piu' basse. */
    <div className="relative h-full w-full">
      <div className="pointer-events-none absolute inset-x-0 bottom-[22px] z-10 flex flex-wrap items-center justify-center gap-x-3 gap-y-0.5 px-2">
        {voci.map((v) => (
          <span
            key={v.nome}
            className="inline-flex items-center gap-1 rounded bg-card/75 px-1 text-[0.625rem] leading-tight text-muted-foreground"
          >
            <Segno voce={v} />
            {v.nome}
          </span>
        ))}
      </div>

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
        {showZeroLine && (
          <ReferenceLine yAxisId="eps" y={0} stroke="#64748b" strokeOpacity={0.6}
            strokeDasharray="2 2" />
        )}
        {hasEstimate && (
          <Bar yAxisId="rev" dataKey="revenue_est" name="Revenue est"
            fill={C_REV_EST} fillOpacity={0.45} radius={[2, 2, 0, 0]} maxBarSize={32} />
        )}
        <Bar yAxisId="rev" dataKey="revenue" name="Revenue"
          fill={C_REV} radius={[2, 2, 0, 0]} maxBarSize={32} />
        {hasEstimate && (
          <Line yAxisId="eps" type="monotone" dataKey="eps_est" name="EPS est"
            stroke={C_EPS_EST} strokeDasharray="4 3" strokeWidth={1.5}
            dot={{ r: 2, fill: C_EPS_EST, stroke: C_EPS_EST }} />
        )}
        <Line yAxisId="eps" type="monotone" dataKey="eps" name="EPS"
          stroke={C_EPS} strokeWidth={2.5}
          dot={{ r: 3, fill: C_EPS, stroke: C_EPS }}
          activeDot={{ r: 5, fill: C_EPS, stroke: "#fff", strokeWidth: 2 }} />
      </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
