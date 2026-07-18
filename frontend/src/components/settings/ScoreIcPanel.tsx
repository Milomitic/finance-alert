import { ChevronDown, ChevronRight, LineChart, Loader2 } from "lucide-react";
import { useState } from "react";

import type { ScoreIcPillar } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useScoreIcReport } from "@/hooks/useScoreIcReport";
import { cn } from "@/lib/utils";

/* ─── ScoreIcPanel — the Qualità pillar-IC transparency study ───────────── *
 *
 * Surfaces app.scripts.score_ic_backtest, which until now lived only in a JSON
 * artifact, the docs, and a code comment. It is the honest backbone of a claim
 * the product makes: the Qualità composite is a company-QUALITY descriptor, not
 * a return predictor — no pillar shows a statistically significant Information
 * Coefficient on forward returns. Showing the numbers (and the caveats) beats
 * asking users to take that on faith.
 *
 * Collapsed by default; the fetch defers to first open (the artifact is static).
 */
const PILLAR_ORDER = ["profitability", "sustainability", "growth", "composite"] as const;
const PILLAR_LABEL: Record<string, string> = {
  profitability: "Redditività",
  sustainability: "Sostenibilità",
  growth: "Crescita",
  composite: "Composito",
};
const HORIZON_LABEL: Record<string, string> = { "21": "~1m", "63": "~3m", "126": "~6m" };

const nfIc = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
  signDisplay: "exceptZero",
});

/** |t| >= 2 is roughly significant at 5%. None of these clear it — which is the
 *  point — so cells stay muted; a hypothetical significant one would go
 *  green/red. */
function icClass(cell: ScoreIcPillar | undefined): string {
  if (!cell) return "text-muted-foreground/50";
  if (Math.abs(cell.t_stat) < 2) return "text-muted-foreground";
  return cell.ic_mean > 0
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-rose-600 dark:text-rose-400";
}

export function ScoreIcPanel() {
  const [open, setOpen] = useState(false);
  const q = useScoreIcReport(open);
  const report = q.data;
  const horizons = report?.results ? Object.keys(report.results) : [];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={LineChart}
          label="Qualità — studio Information Coefficient"
          right={
            <Button size="sm" variant="ghost" onClick={() => setOpen((v) => !v)}>
              {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
          }
        />

        {open && (
          <div className="mt-3 space-y-4">
            {q.isLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Caricamento…
              </div>
            )}
            {q.isError && (
              <p className="text-sm text-destructive" role="alert">
                Errore nel caricamento dello studio.
              </p>
            )}
            {report && report.available === false && (
              <p className="text-sm text-muted-foreground">
                Studio non ancora generato su questo deploy (
                <code>python -m app.scripts.score_ic_backtest</code>).
              </p>
            )}

            {report?.available && report.results && (
              <>
                {/* The verdict, stated plainly. */}
                <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3">
                  <p className="text-sm font-medium">
                    Il composito Qualità è un{" "}
                    <strong>descrittore di qualità aziendale</strong>, non un predittore di
                    rendimento.
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Nessun pilastro raggiunge un Information Coefficient statisticamente
                    significativo (|t| ≥ 2) sui rendimenti forward. IC = correlazione di rango
                    fra score e rendimento successivo: 0 = nessun potere predittivo.
                  </p>
                </div>

                {/* Pillar × horizon IC (t-stat below each). */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-[13px] uppercase tracking-wide text-muted-foreground">
                      <tr>
                        <th className="px-2 py-1.5 text-left">Pilastro</th>
                        {horizons.map((h) => (
                          <th key={h} className="px-2 py-1.5 text-right tabular-nums">
                            {HORIZON_LABEL[h] ?? `${h}g`}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {PILLAR_ORDER.map((pillar) => (
                        <tr
                          key={pillar}
                          className={cn(
                            "border-t",
                            pillar === "composite" && "border-t-2 font-semibold",
                          )}
                        >
                          <td className="px-2 py-2 text-left">{PILLAR_LABEL[pillar]}</td>
                          {horizons.map((h) => {
                            const cell = report.results?.[h]?.[pillar];
                            return (
                              <td
                                key={h}
                                className={cn("px-2 py-2 text-right tabular-nums", icClass(cell))}
                              >
                                {cell ? (
                                  <>
                                    {nfIc.format(cell.ic_mean)}
                                    <span className="block text-[11px] text-muted-foreground/70">
                                      t={cell.t_stat.toFixed(2)}
                                    </span>
                                  </>
                                ) : (
                                  "—"
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Coverage + honest caveats. */}
                {report.coverage && (
                  <div className="space-y-1 text-xs text-muted-foreground">
                    <p>
                      {report.coverage.n_observations.toLocaleString("it-IT")} osservazioni ·{" "}
                      {report.coverage.n_dates_observed} sezioni trimestrali ·{" "}
                      {report.coverage.with_pit_facts} titoli con fatti point-in-time
                      {report.params?.start && ` · dal ${report.params.start.slice(0, 4)}`}
                    </p>
                    {Object.keys(report.coverage.pillars_excluded ?? {}).length > 0 && (
                      <p>
                        Pilastri esclusi:{" "}
                        {Object.keys(report.coverage.pillars_excluded).join(", ")} (dati
                        point-in-time non ricostruibili).
                      </p>
                    )}
                    {report.coverage.caveats?.[0] && <p>⚠ {report.coverage.caveats[0]}</p>}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
