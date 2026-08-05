import { Crosshair } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import type { SectorSummary } from "@/hooks/useSectorDetail";
import { bullShare, meanOf, shortSectorName } from "@/lib/sectorLens";
import { cn } from "@/lib/utils";

/* ─── SectorLensMatrix — the two lenses as two axes ─────────────────────── *
 *
 * Qualità and Tecnico are orthogonal by design (CLAUDE.md: three independent
 * lenses, kept decoupled on purpose). A table can show both numbers; only a
 * plane shows the RELATIONSHIP, and the relationship is the reading that
 * neither column carries: Financials sits far right of the diagonal (the
 * market prices it better than its fundamentals argue), Utilities far left
 * (sound on paper, dead on the tape). Side by side as two grey numbers those
 * two sectors look interchangeable.
 *
 * Four encodings, no text per point:
 *   x  Tecnico          y  Qualità
 *   r  stock count      colour  7-day signal balance
 *
 * Hand-drawn SVG rather than recharts. Eleven points do not justify a 331KB
 * chunk that the dashboard already lazy-loads to keep off its critical path.
 *
 * SIZE. The chart is capped at MAX_PX wide (see the wrapper below) rather than
 * filling its column. `w-full h-auto` on an SVG means the height follows the
 * page width, so on a 4K screen the old 680×400 box rendered well over 700px
 * tall and pushed everything else off the fold. A scatter of eleven points
 * gains nothing from that area — past a certain size the reader is just
 * moving their eyes further between the same eleven marks.
 *
 * Kept near-square on purpose. Both axes are 0-100 composites, so a point of
 * Qualità and a point of Tecnico should occupy the same number of pixels; a
 * wide, short band would quietly flatten the vertical spread and make the
 * lenses look more aligned than they are.
 */

interface Props {
  sectors: SectorSummary[];
  /** Highlighted from the table's hover, so the two views read as one. */
  activeSector?: string | null;
  onHover?: (name: string | null) => void;
}

const W = 440;
const H = 350;
const PAD_L = 32;
const PAD_R = 14;
const PAD_T = 14;
const PAD_B = 28;
/** Hard ceiling on the rendered width — the whole point of the resize. */
const MAX_PX = "max-w-[460px]";

/** Axis domain from the data, padded, then snapped outward to whole numbers.
 *  A fixed 0-100 domain would squeeze every sector into the middle third —
 *  the real spread is roughly 43-66 on both axes. */
function domain(values: number[]): [number, number] {
  if (values.length === 0) return [40, 70];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = Math.max(3, (hi - lo) * 0.18);
  return [Math.floor(lo - pad), Math.ceil(hi + pad)];
}

export function SectorLensMatrix({ sectors, activeSector, onHover }: Props) {
  const navigate = useNavigate();

  const model = useMemo(() => {
    // A point needs BOTH lenses. Sectors missing one are not plotted at 0 —
    // they are counted and named under the chart, because a sector silently
    // absent from an overview is worse than one listed as unmeasured.
    const plottable = sectors.filter(
      (s) => s.avg_score !== null && s.avg_technical !== null,
    );
    const missing = sectors.filter(
      (s) => s.avg_score === null || s.avg_technical === null,
    );
    const xDom = domain(plottable.map((s) => s.avg_technical as number));
    const yDom = domain(plottable.map((s) => s.avg_score as number));
    const maxCount = Math.max(1, ...plottable.map((s) => s.stock_count));
    const mx = meanOf(plottable, (s) => s.avg_technical);
    const my = meanOf(plottable, (s) => s.avg_score);
    return { plottable, missing, xDom, yDom, maxCount, mx, my };
  }, [sectors]);

  const { plottable, missing, xDom, yDom, maxCount, mx, my } = model;

  const X = (v: number) =>
    PAD_L + ((v - xDom[0]) / (xDom[1] - xDom[0])) * (W - PAD_L - PAD_R);
  const Y = (v: number) =>
    H - PAD_B - ((v - yDom[0]) / (yDom[1] - yDom[0])) * (H - PAD_T - PAD_B);
  // Area-proportional, not radius-proportional: doubling the radius quadruples
  // the ink, which would read as four times the stocks. Range narrowed with
  // the box (was 8-24): at the smaller scale the old bubbles overlapped into
  // one another and the labels had nowhere to sit.
  const R = (n: number) => 4 + Math.sqrt(n / maxCount) * 9;

  const ticks = (d: [number, number]) => {
    const step = d[1] - d[0] > 24 ? 10 : 5;
    const out: number[] = [];
    for (let v = Math.ceil(d[0] / step) * step; v <= d[1]; v += step) out.push(v);
    return out;
  };

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 h-full flex flex-col min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0 flex items-center justify-between gap-3">
          <SectionTitle icon={Crosshair} label="Qualità × Tecnico" />
          <span className="text-[11px] text-muted-foreground truncate">
            bolla = n° stock · colore = saldo segnali 7g
          </span>
        </div>

        <div className={cn("flex-1 min-h-0 p-2 w-full mx-auto", MAX_PX)}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full h-auto"
            role="img"
            aria-label="Dispersione dei settori per punteggio Qualità e Tecnico"
          >
            {/* Grid + ticks first, so points always paint over them. */}
            {ticks(xDom).map((v) => (
              <g key={`x${v}`}>
                <line
                  x1={X(v)} y1={PAD_T} x2={X(v)} y2={H - PAD_B}
                  className="stroke-border" strokeWidth={1} strokeOpacity={0.35}
                />
                <text
                  x={X(v)} y={H - PAD_B + 15} textAnchor="middle"
                  className="fill-muted-foreground text-[10px]"
                >
                  {v}
                </text>
              </g>
            ))}
            {ticks(yDom).map((v) => (
              <g key={`y${v}`}>
                <line
                  x1={PAD_L} y1={Y(v)} x2={W - PAD_R} y2={Y(v)}
                  className="stroke-border" strokeWidth={1} strokeOpacity={0.35}
                />
                <text
                  x={PAD_L - 8} y={Y(v) + 3} textAnchor="end"
                  className="fill-muted-foreground text-[10px]"
                >
                  {v}
                </text>
              </g>
            ))}

            {/* Quadrant split at the MEANS of what is on screen, not at a
                hard-coded 50: the labels below only mean something relative to
                the other sectors in the same picture. */}
            {mx !== null && (
              <line
                x1={X(mx)} y1={PAD_T} x2={X(mx)} y2={H - PAD_B}
                className="stroke-foreground/40" strokeWidth={1} strokeDasharray="4 4"
              />
            )}
            {my !== null && (
              <line
                x1={PAD_L} y1={Y(my)} x2={W - PAD_R} y2={Y(my)}
                className="stroke-foreground/40" strokeWidth={1} strokeDasharray="4 4"
              />
            )}
            {/* The four quadrant captions used to be drawn in the corners.
                They were the longest text in the picture, and at this size
                they landed on top of the points they were describing. The
                same key now sits under the chart as one line, where it can be
                read in full without competing with the data. */}

            <text x={W - PAD_R} y={H - 4} textAnchor="end"
                  className="fill-muted-foreground text-[10px] font-medium">
              Tecnico →
            </text>
            <text x={0} y={0} transform={`rotate(-90) translate(${-(H - PAD_B)} 10)`}
                  className="fill-muted-foreground text-[10px] font-medium">
              Qualità →
            </text>

            {plottable.map((s) => {
              const cx = X(s.avg_technical as number);
              const cy = Y(s.avg_score as number);
              const r = R(s.stock_count);
              const share = bullShare(s);
              const tone =
                share === null ? "muted" : share >= 0.66 ? "pos" : share <= 0.45 ? "neg" : "mid";
              const active = activeSector === s.name;
              return (
                <g
                  key={s.name}
                  className="cursor-pointer"
                  onMouseEnter={() => onHover?.(s.name)}
                  onMouseLeave={() => onHover?.(null)}
                  onClick={() => navigate(`/sectors/${encodeURIComponent(s.name)}`)}
                >
                  <title>
                    {`${s.name} — Qualità ${(s.avg_score as number).toFixed(1)} · `
                      + `Tecnico ${(s.avg_technical as number).toFixed(1)} · `
                      + `${s.stock_count} stock · `
                      + `${s.signals_7d_bull} rialzisti / ${s.signals_7d_bear} ribassisti`}
                  </title>
                  <circle
                    cx={cx} cy={cy} r={r}
                    className={cn(
                      "transition-[stroke-width,fill-opacity]",
                      tone === "pos" && "fill-emerald-500 stroke-emerald-500",
                      tone === "neg" && "fill-red-500 stroke-red-500",
                      tone === "mid" && "fill-amber-500 stroke-amber-500",
                      tone === "muted" && "fill-muted-foreground stroke-muted-foreground",
                    )}
                    fillOpacity={active ? 0.42 : 0.22}
                    strokeWidth={active ? 2.5 : 1.5}
                  />
                  <text
                    x={cx} y={cy - r - 4} textAnchor="middle"
                    className={cn(
                      "text-[9px] pointer-events-none",
                      active ? "fill-foreground font-semibold" : "fill-foreground/70",
                    )}
                  >
                    {shortSectorName(s.name)}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Reading key, displaced from the plot corners. The two off-diagonal
            quadrants are the interesting ones — they are where the lenses
            disagree, which is the reading no column of the table carries. */}
        <p className="px-3 pb-1.5 text-[11px] text-muted-foreground shrink-0 leading-snug">
          Le linee tratteggiate sono le medie. In alto a sinistra la{" "}
          <span className="text-foreground/80">qualità non ancora prezzata</span>, in
          basso a destra il <span className="text-foreground/80">momentum senza
          qualità</span>: è lì che le due lenti si contraddicono.
        </p>

        {missing.length > 0 && (
          <p className="px-3 pb-2 text-[11px] text-muted-foreground shrink-0">
            Non rappresentati ({missing.length}): {missing.map((s) => s.name).join(", ")} —
            manca uno dei due punteggi.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
