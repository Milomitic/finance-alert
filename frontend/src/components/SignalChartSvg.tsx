import type { SignalChainStep, SignalSnapshot } from "@/api/types";

interface Bar {
  date: string;
  close: number;
}

interface Props {
  bars: Bar[];
  annotations: SignalSnapshot["annotations"];
  chain: SignalChainStep[];
  tone: "bull" | "bear" | "neutral";
}

const W = 640;
const H = 220;
const PAD_X = 8;
const PAD_T = 10;
const PAD_B = 18;

/** Per-kind line style for the annotation levels. `stop` is dashed amber to
 *  visually separate "where the setup invalidates" from the structural levels
 *  (neckline / breakout / support / resistance). */
const LEVEL_STYLE: Record<string, { stroke: string; dash?: string }> = {
  neckline: { stroke: "#6366f1" },
  breakout: { stroke: "#0ea5e9" },
  support: { stroke: "#16a34a" },
  resistance: { stroke: "#dc2626" },
  stop: { stroke: "#d97706", dash: "4 3" },
};

/**
 * Hand-drawn SVG of the detected signal: the recent close line (tone-colored),
 * the annotation levels as horizontal lines, the pattern shape as a dashed
 * polyline through its vertices, and numbered markers on the chain dates.
 *
 * Same hand-rolled approach as the existing MiniSpark — no charting library,
 * so it stays a cheap static screenshot suitable for the detail popup.
 */
export function SignalChartSvg({ bars, annotations, chain, tone }: Props) {
  if (!bars || bars.length < 2) {
    return (
      <div className="rounded-lg border border-dashed border-border/60 p-4 text-xs text-muted-foreground italic text-center">
        Grafico non disponibile per questo titolo.
      </div>
    );
  }

  const levels = annotations?.levels ?? [];
  const points = annotations?.points ?? [];
  const closes = bars.map((b) => b.close);
  const lvlPrices = levels.map((l) => l.price).filter((p) => Number.isFinite(p));
  const ptPrices = points.map((p) => p.price).filter((p) => Number.isFinite(p));
  const lo = Math.min(...closes, ...lvlPrices, ...ptPrices);
  const hi = Math.max(...closes, ...lvlPrices, ...ptPrices);
  const range = hi - lo || 1;
  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_T - PAD_B;
  const x = (i: number) => PAD_X + (i / (bars.length - 1)) * innerW;
  const y = (price: number) => PAD_T + (1 - (price - lo) / range) * innerH;

  // date -> bar index. Out-of-window dates clamp to the nearest edge so a
  // chain step whose date predates the loaded window still shows a marker.
  const idxByDate = new Map<string, number>();
  bars.forEach((b, i) => idxByDate.set(b.date.slice(0, 10), i));
  const firstDate = bars[0].date.slice(0, 10);
  const xForDate = (d: string): number => {
    const k = d.slice(0, 10);
    if (idxByDate.has(k)) return x(idxByDate.get(k)!);
    return k < firstDate ? x(0) : x(bars.length - 1);
  };
  const closeAtDate = (d: string): number | null => {
    const k = d.slice(0, 10);
    return idxByDate.has(k) ? bars[idxByDate.get(k)!].close : null;
  };

  const lineColor = tone === "bull" ? "#16a34a" : tone === "bear" ? "#dc2626" : "#64748b";
  const priceLine = closes.map((c, i) => `${x(i).toFixed(1)},${y(c).toFixed(1)}`).join(" ");
  const shape = points
    .map((p) => `${xForDate(p.date).toFixed(1)},${y(p.price).toFixed(1)}`)
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      className="overflow-visible"
      role="img"
      aria-label="Grafico annotato del segnale"
    >
      {/* level lines */}
      {levels.map((l, i) => {
        const st = LEVEL_STYLE[l.kind] ?? { stroke: "#94a3b8" };
        const yy = y(l.price);
        return (
          <g key={`lvl-${i}`}>
            <line
              x1={PAD_X}
              y1={yy}
              x2={W - PAD_X}
              y2={yy}
              stroke={st.stroke}
              strokeWidth={1}
              strokeDasharray={st.dash}
              opacity={0.8}
            />
            <text x={W - PAD_X} y={yy - 2} textAnchor="end" fontSize={9} fill={st.stroke}>
              {l.label}
            </text>
          </g>
        );
      })}
      {/* pattern shape */}
      {points.length >= 2 && (
        <polyline
          points={shape}
          fill="none"
          stroke="#a855f7"
          strokeWidth={1.4}
          strokeDasharray="3 2"
          opacity={0.9}
        />
      )}
      {/* price close line */}
      <polyline
        points={priceLine}
        fill="none"
        stroke={lineColor}
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
      {/* numbered chain markers */}
      {chain.map((step, i) => {
        const c = closeAtDate(step.date);
        if (c == null) return null;
        const cx = xForDate(step.date);
        const cy = y(c);
        return (
          <g key={`mk-${i}`}>
            <circle cx={cx} cy={cy} r={7} fill="#0f172a" opacity={0.85} />
            <text
              x={cx}
              y={cy + 3}
              textAnchor="middle"
              fontSize={9}
              fill="#fff"
              fontWeight="bold"
            >
              {i + 1}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
