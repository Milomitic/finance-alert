import { currencySymbol } from "@/lib/money";
import { GraficoSvg, type SerieGrafico } from "@/components/ui/grafico-svg";
import { STATO_VUOTO } from "@/lib/stati";

/* Il grafico trimestrale/annuale della scheda Fondamentali.
 *
 * Vive in un file suo, caricato pigramente: era l'unico consumatore di
 * Recharts sulla pagina di un titolo (374 kB, il 28% della rotta). Da FA-137
 * e' disegnato da `components/ui/grafico-svg`, e Recharts non c'e' piu'. */

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
}: {
  data: ChartPoint[];
  hasEstimate: boolean;
  /** La valuta dei RENDICONTI (`financial_currency`), per tutte le serie. */
  currency?: string | null;
}) {
  // ⚠️ Questo commento diceva che la valuta dei rendiconti «per una quotata e'
  // la sua valuta di quotazione». Non lo e': SHEL.L quota in pence e
  // rendiconta in dollari, TSM quota in dollari e rendiconta in dollari
  // taiwanesi. La scheda passa quella dei rendiconti; ignota = nessun simbolo.
  const unit = currencySymbol(currency) ?? "";
  if (data.length === 0) {
    return <div className={STATO_VUOTO}>Nessun dato per il grafico</div>;
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

  type Riga = (typeof scaled)[number];
  const serie: SerieGrafico<Riga>[] = [
    ...(hasEstimate ? [{ chiave: "revenue_est", nome: "Revenue est", valore: (p: Riga) => p.revenue_est,
      colore: C_REV_EST, tipo: "barre" as const, opacita: 0.45 }] : []),
    { chiave: "revenue", nome: "Revenue", valore: (p) => p.revenue, colore: C_REV, tipo: "barre" },
    ...(hasEstimate ? [{ chiave: "eps_est", nome: "EPS est", valore: (p: Riga) => p.eps_est, colore: C_EPS_EST,
      asse: "dx" as const, tratteggio: "4 3", punti: true }] : []),
    { chiave: "eps", nome: "EPS", valore: (p) => p.eps, colore: C_EPS, asse: "dx", spessore: 2.5, punti: true },
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
            className="inline-flex items-center gap-1 rounded bg-card/75 px-1 text-[0.6471rem] leading-tight text-muted-foreground"
          >
            <Segno voce={v} />
            {v.nome}
          </span>
        ))}
      </div>

      <GraficoSvg
        dati={scaled}
        x={(p) => p.label}
        formatoY={(v) => `${v.toFixed(0)}B`}
        formatoYDx={(v) => `${unit}${v.toFixed(1)}`}
        riferimenti={showZeroLine ? [{ y: 0, asse: "dx", tratteggio: "2 2", colore: "#64748b" }] : []}
        etichetta="Ricavi in miliardi e utile per azione, per periodo"
        serie={serie}
        tooltip={(p) => (
          <>
            <div className="font-medium">{p.label}</div>
            {serie.map((s) => {
              const v = s.valore(p);
              if (v == null) return null;
              const ricavi = s.asse !== "dx";
              return (
                <div key={s.chiave} className="tabular-nums">
                  {s.nome}: {unit}{ricavi ? `${v.toFixed(1)}B` : v.toFixed(2)}
                </div>
              );
            })}
          </>
        )}
      />
    </div>
  );
}
