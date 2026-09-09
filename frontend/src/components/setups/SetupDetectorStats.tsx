import { Card, CardContent } from "@/components/ui/card";
import type { SetupDetectorStat } from "@/hooks/useSetups";
import { cn } from "@/lib/utils";

/* Which setup families actually work.
 *
 * The strip above answers "does this feature convert". It cannot answer "which
 * setup should I trust", and averaging a family that converts nine times in ten
 * with one that never converts describes neither.
 *
 * ⚠️ The visualization is a rate WITH ITS INTERVAL against a 50% reference,
 * not a bar of the rate alone. A bare bar at 78% reads as a strong setup; the
 * same number over three independent windows spans roughly 28 to 97, which is
 * a coin flip with a wide error. CLAUDE.md records exactly that shape for
 * `macd_divergence`, and it is the reason every efficacy number in this repo
 * carries a Wilson band sized on non-overlapping windows rather than on rows.
 *
 * So the bar's WIDTH is the uncertainty and its POSITION is the estimate. A
 * band that straddles the 50 line has said nothing, and it looks like it.
 */

/** Where 0..100 sits inside the track. */
const pos = (pct: number) => `${Math.max(0, Math.min(100, pct))}%`;

function RateBand({ row }: { row: SetupDetectorStat }) {
  if (row.hit_rate === null) {
    return (
      <span className="text-xs text-muted-foreground italic">
        nessun esito maturo
      </span>
    );
  }
  const lo = row.ci_low ?? row.hit_rate;
  const hi = row.ci_high ?? row.hit_rate;
  // Straddling 50 means the sample cannot tell this apart from a coin flip.
  // Colouring it as a win would be the "number that claims more than the
  // measurement supports" this codebase keeps removing.
  const inconclusive = lo <= 50 && hi >= 50;

  return (
    <div className="min-w-[7rem]">
      <div className="relative h-4 rounded bg-muted/60">
        {/* The coin-flip reference. Everything is read against this line. */}
        <div className="absolute inset-y-0 left-1/2 w-px bg-foreground/30" />
        <div
          className={cn(
            "absolute inset-y-[3px] rounded-sm",
            inconclusive
              ? "bg-slate-400/70 dark:bg-slate-500/70"
              : row.hit_rate > 50
                ? "bg-emerald-500/70"
                : "bg-rose-500/70",
          )}
          style={{ left: pos(lo), width: pos(Math.max(hi - lo, 1.5)) }}
        />
        <div
          className="absolute inset-y-0 w-0.5 bg-foreground/80"
          style={{ left: pos(row.hit_rate) }}
        />
      </div>
      <div className="mt-0.5 flex items-baseline gap-1.5 text-xs">
        <span className="tabular-nums font-medium">{row.hit_rate.toFixed(0)}%</span>
        <span className="text-muted-foreground tabular-nums">
          {lo.toFixed(0)}–{hi.toFixed(0)}
        </span>
        {inconclusive && (
          <span className="text-muted-foreground italic">non concludente</span>
        )}
      </div>
    </div>
  );
}

function Num({ value, suffix = "" }: { value: number | null; suffix?: string }) {
  // "—" and "0" are different statements and must not share a glyph.
  if (value === null) return <span className="text-muted-foreground">—</span>;
  const tone =
    suffix === "%" && value !== 0
      ? value > 0
        ? "text-emerald-800 dark:text-emerald-400"
        : "text-rose-700 dark:text-rose-400"
      : "";
  return (
    <span className={cn("tabular-nums", tone)}>
      {value > 0 && suffix === "%" ? "+" : ""}
      {value.toFixed(suffix === "%" ? 2 : 0)}
      {suffix}
    </span>
  );
}

export default function SetupDetectorStats({ rows }: { rows: SetupDetectorStat[] }) {
  if (rows.length === 0) return null;

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-baseline justify-between gap-3 px-4 pt-3 pb-2 border-b">
          <h3 className="text-sm font-semibold tracking-tight">
            Per tipo di setup
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {rows.length} famigli{rows.length === 1 ? "a" : "e"}
            </span>
          </h3>
          <span className="text-xs text-muted-foreground">
            efficacia contro il 50% · banda = incertezza
          </span>
        </div>

        {/* Horizontal scroll on its own container so the page body never
            scrolls sideways on a phone. */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[0.6765rem] uppercase tracking-wider text-muted-foreground font-mono">
                <th className="text-left font-normal px-4 py-2">Setup</th>
                <th className="text-right font-normal px-2 py-2">Conv. / Scad.</th>
                <th className="text-right font-normal px-2 py-2">Tasso conv.</th>
                <th className="text-right font-normal px-2 py-2">Giudicati</th>
                <th className="text-left font-normal px-2 py-2">Efficacia</th>
                <th className="text-right font-normal px-4 py-2">Ecc. mediano</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.detector} className="border-t hover:bg-accent/40">
                  <td className="px-4 py-2 font-medium truncate max-w-[12rem]">
                    {r.detector}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums whitespace-nowrap">
                    {r.converted} / {r.expired}
                  </td>
                  <td className="px-2 py-2 text-right">
                    <Num value={r.conversion_rate} suffix="" />
                    {r.conversion_rate !== null && <span>%</span>}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {/* The count that produced the band beside it, plus the
                        independent-window count when they differ — which is
                        the whole reason a wide band can sit under many rows. */}
                    {r.judged}
                    {r.judged > 0 && r.effective_n !== r.judged && (
                      <span className="text-muted-foreground">
                        {" "}
                        · {r.effective_n} fin.
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <RateBand row={r} />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Num value={r.median_excess_pct} suffix="%" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="px-4 py-2 text-xs text-muted-foreground border-t">
          L'efficacia è market-neutral: il setup ha battuto la mediana
          dell'universo nella propria direzione. Il conteggio delle finestre
          indipendenti, non delle righe, dimensiona la banda — setup che
          scattano a pochi giorni di distanza condividono quasi tutta la
          finestra futura e non sono osservazioni separate.
        </p>
      </CardContent>
    </Card>
  );
}
