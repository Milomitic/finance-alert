import { LineChart as LineChartIcon, Loader2 } from "lucide-react";
import { useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { GraficoSvg } from "@/components/ui/grafico-svg";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { type EquityFilters, useEquityCurve } from "@/hooks/useEquityCurve";
import { cn } from "@/lib/utils";

/* ─── EquityCurvePanel ────────────────────────────────────────────────────── *
 *
 * Reads the signal_outcomes warehouse and draws the hypothetical cumulative
 * equity of following every matured signal matching the filters. Two curves:
 *   - "Assoluta"  — compound the realised forward returns.
 *   - "Vs mercato" — compound the tone-signed excess vs the universe (the
 *     honest, beta-stripped read — flat here means "no edge over just being
 *     long the market").
 *
 * It's a growth-of-1 ILLUSTRATION, not a tradeable P&L: one unit per signal,
 * sequential, no overlap/sizing/costs. Labeled as such, in keeping with the
 * platform's "don't oversell the edge" stance. */

const COLORE_ASSOLUTA = "hsl(var(--primary))";
const COLORE_NEUTRA = "#0d9488";

const nf1 = new Intl.NumberFormat("it-IT", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function pct(v: number): string {
  return `${v >= 0 ? "+" : ""}${nf1.format(v)}%`;
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" | "muted" }) {
  return (
    <div className="rounded-md border bg-muted/20 px-3 py-2">
      <div className="text-[0.7059rem] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div
        className={cn(
          "text-lg font-semibold tabular-nums",
          tone === "up" && "text-emerald-800 dark:text-emerald-400",
          tone === "down" && "text-rose-600 dark:text-rose-400",
          tone === "muted" && "text-muted-foreground",
        )}
      >
        {value}
      </div>
    </div>
  );
}

const selectCls =
  "h-8 px-2 text-sm rounded-md border bg-muted/30 cursor-pointer hover:text-foreground";

export function EquityCurvePanel() {
  const [filters, setFilters] = useState<EquityFilters>({
    horizonDays: 21,
    detector: "",
    tone: "",
    regime: "",
    strengthMin: 0,
  });
  const set = <K extends keyof EquityFilters>(k: K, v: EquityFilters[K]) =>
    setFilters((f) => ({ ...f, [k]: v }));

  const q = useEquityCurve(filters);
  const data = q.data;

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle icon={LineChartIcon} label="Simulatore equity — segnali maturati" />

        {/* Filters */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <select
            className={selectCls}
            value={filters.detector}
            onChange={(e) => set("detector", e.target.value)}
            aria-label="Detector"
          >
            <option value="">Tutti i detector</option>
            {(data?.detectors ?? []).map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <select className={selectCls} value={filters.tone} onChange={(e) => set("tone", e.target.value)} aria-label="Tono">
            <option value="">Tono: tutti</option>
            <option value="bull">Bull</option>
            <option value="bear">Bear</option>
          </select>
          <select className={selectCls} value={filters.regime} onChange={(e) => set("regime", e.target.value)} aria-label="Regime">
            <option value="">Regime: tutti</option>
            <option value="bull">Regime bull</option>
            <option value="bear">Regime bear</option>
            <option value="flat">Regime flat</option>
          </select>
          <select
            className={selectCls}
            value={filters.horizonDays}
            onChange={(e) => set("horizonDays", Number(e.target.value))}
            aria-label="Orizzonte"
          >
            <option value={5}>Orizzonte 5g</option>
            <option value={21}>Orizzonte 21g</option>
          </select>
          <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            Forza ≥ {filters.strengthMin}
            <input
              type="range"
              min={0}
              max={95}
              step={5}
              value={filters.strengthMin}
              onChange={(e) => set("strengthMin", Number(e.target.value))}
              className="w-28"
              aria-label="Forza minima"
            />
          </label>
        </div>

        {/* Body */}
        {q.isLoading ? (
          <div className="mt-6 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Caricamento…
          </div>
        ) : q.isError ? (
          <div className="mt-6">
            <QueryError message="della curva equity" onRetry={q.refetch} isRetrying={q.isFetching} />
          </div>
        ) : !data || data.n_signals === 0 ? (
          <div className="mt-6 text-sm text-muted-foreground">
            Nessun segnale maturato con questi filtri.
          </div>
        ) : (
          <>
            {/* Summary tiles */}
            <div className="mt-4 grid grid-cols-2 sm:grid-cols-5 gap-2">
              <Stat label="Segnali" value={String(data.n_signals)} tone="muted" />
              <Stat label="Ritorno assoluto" value={pct(data.total_return_pct)} tone={data.total_return_pct >= 0 ? "up" : "down"} />
              <Stat label="Vs mercato" value={pct(data.mkt_neutral_return_pct)} tone={data.mkt_neutral_return_pct >= 0 ? "up" : "down"} />
              <Stat label="Win rate" value={`${nf1.format(data.win_rate_pct)}%`} tone="muted" />
              <Stat label="Max drawdown" value={`−${nf1.format(data.max_drawdown_pct)}%`} tone="down" />
            </div>

            {/* Curve */}
            {/* La legenda era quella di recharts: ora e' una riga sopra il grafico. */}
            <div className="mt-4 flex flex-wrap gap-x-4 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <span className="inline-block h-0.5 w-4 rounded" style={{ background: COLORE_ASSOLUTA }} aria-hidden />
                Assoluta
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="inline-block h-0.5 w-4 rounded" style={{ background: COLORE_NEUTRA }} aria-hidden />
                Vs mercato
              </span>
            </div>
            <div className="mt-1 h-[280px]">
              <GraficoSvg
                dati={data.points}
                x={(p) => p.date}
                formatoY={(v) => v.toFixed(2)}
                riferimenti={[{ y: 1, tratteggio: "4 4" }]}
                etichetta="Curva di equity ipotetica, assoluta e al netto del mercato"
                serie={[
                  { chiave: "equity", nome: "Assoluta", valore: (p) => p.equity, colore: COLORE_ASSOLUTA, spessore: 2 },
                  { chiave: "equity_mkt_neutral", nome: "Vs mercato", valore: (p) => p.equity_mkt_neutral,
                    colore: COLORE_NEUTRA, spessore: 2 },
                ]}
              />
            </div>

            <p className="mt-2 text-xs text-muted-foreground">
              Crescita ipotetica di 1 unità reinvestita su ogni segnale in sequenza
              (orizzonte {data.horizon_days}g) — <strong>senza</strong> gestione degli
              overlap, sizing o costi: è un'illustrazione, non un P&L replicabile. La
              curva <span className="text-teal-600 dark:text-teal-400">Vs mercato</span> è
              il segnale al netto del beta (piatta = nessun vantaggio sul mercato).
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
