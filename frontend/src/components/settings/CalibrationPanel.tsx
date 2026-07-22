import { Loader2, Target } from "lucide-react";
import { useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useCalibration } from "@/hooks/useRulePerformance";


/* ─── Calibration panel ─────────────────────────────────────────────────── */

export function CalibrationPanel() {
  const [horizon, setHorizon] = useState(20);
  const q = useCalibration(365, horizon);
  const c = q.data;
  const matured = c ? c.by_confidence.reduce((a, b) => a + b.count, 0) : 0;
  const pct = (v: number | null) => (v == null ? "-" : `${(v * 100).toFixed(0)}%`);
  const ret = (v: number | null) => (v == null ? "-" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`);

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Target}
          label="Calibrazione - confidenza vs esito reale"
          right={
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Orizzonte:</span>
              <select
                value={horizon}
                onChange={(e) => setHorizon(Number(e.target.value))}
                className="bg-background border rounded px-2 py-0.5 text-xs"
              >
                <option value={5}>5 giorni</option>
                <option value={10}>10 giorni</option>
                <option value={20}>20 giorni</option>
              </select>
            </div>
          }
          className="mb-3"
        />
        {q.isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground inline-flex items-center gap-2 justify-center w-full">
            <Loader2 className="h-4 w-4 animate-spin" />
            Calcolo calibrazione...
          </div>
        ) : (
          <div className="space-y-4">
            {matured > 0 ? (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
                  Live - esiti maturati: {matured} (orizzonte {horizon}g)
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <CalTable title="Per confidenza" rows={c!.by_confidence} pct={pct} ret={ret} />
                  <CalTable title="Per orizzonte" rows={c!.by_horizon} pct={pct} ret={ret} />
                  <CalTable title="Per natura" rows={c!.by_nature} pct={pct} ret={ret} />
                </div>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                Esiti live non ancora maturi (~{horizon}g di borsa dopo ogni segnale);
                si popolano col tempo. Sotto, il riferimento da backtest.
              </div>
            )}
            {c?.backtest_seed && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
                  Riferimento backtest - forward {c.backtest_seed.window}g, direction-adjusted
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <CalTable title="Per confidenza" rows={seedRows(c.backtest_seed.by_confidence, ["60-69", "70-79", "80-89", "90-100"])} pct={pct} ret={ret} />
                  <CalTable title="Per orizzonte" rows={seedRows(c.backtest_seed.by_horizon, ["short", "medium", "long"], HZ_IT)} pct={pct} ret={ret} />
                  <CalTable title="Per natura" rows={seedRows(c.backtest_seed.by_nature, ["continuazione", "inversione"])} pct={pct} ret={ret} />
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const HZ_IT: Record<string, string> = { short: "Breve", medium: "Medio", long: "Lungo" };

/** Adapt a backtest-seed Record<label, cell> into CalTable rows in a fixed
 *  order (mean_pct in the seed is already in %, so it's passed straight). */
function seedRows(
  rec: Record<string, { count: number; hit_rate: number | null; mean_pct: number | null }>,
  order: string[],
  labels?: Record<string, string>,
): { label: string; count: number; hit_rate: number | null; mean_pct: number | null }[] {
  return order.map((k) => {
    const cell = rec?.[k];
    return {
      label: labels?.[k] ?? k,
      count: cell?.count ?? 0,
      hit_rate: cell?.hit_rate ?? null,
      mean_pct: cell?.mean_pct ?? null,
    };
  });
}

function CalTable({
  title,
  rows,
  pct,
  ret,
}: {
  title: string;
  rows: { label: string; count: number; hit_rate: number | null; mean_pct: number | null }[];
  pct: (v: number | null) => string;
  ret: (v: number | null) => string;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
        {title}
      </div>
      <table className="w-full text-sm tabular-nums">
        <thead className="text-muted-foreground border-b">
          <tr>
            <th className="text-left px-2 py-1 font-semibold">Gruppo</th>
            <th className="text-right px-2 py-1 font-semibold">N</th>
            <th className="text-right px-2 py-1 font-semibold">Hit</th>
            <th className="text-right px-2 py-1 font-semibold">Media</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-border/40">
              <td className="px-2 py-1">{r.label}</td>
              <td className="px-2 py-1 text-right">{r.count || "-"}</td>
              <td className="px-2 py-1 text-right font-semibold">{r.count ? pct(r.hit_rate) : "-"}</td>
              <td className="px-2 py-1 text-right">{r.count ? ret(r.mean_pct) : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
