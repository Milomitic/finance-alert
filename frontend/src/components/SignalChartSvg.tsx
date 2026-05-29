import { useRef, useState } from "react";

import type { SignalChainStep, SignalSnapshot } from "@/api/types";

interface Bar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface Props {
  bars: Bar[];
  annotations: SignalSnapshot["annotations"];
  chain: SignalChainStep[];
}

const W = 680;
const H = 264;
const PAD_L = 46;
const PAD_R = 14;
const PAD_T = 16;
const PAD_B = 28;

const LEVEL_STYLE: Record<string, { stroke: string; dash?: string }> = {
  neckline: { stroke: "#6366f1" },
  breakout: { stroke: "#0ea5e9" },
  support: { stroke: "#17b551" },
  resistance: { stroke: "#dc2626" },
  stop: { stroke: "#d97706", dash: "4 3" },
};

const UP = "#17b551";
const DOWN = "#dc2626";
const GRID = "#94a3b8";

function dm(iso: string): string {
  const k = iso.slice(0, 10).split("-");
  return k.length === 3 ? `${k[2]}/${k[1]}` : iso.slice(0, 10);
}

function priceLabel(p: number): string {
  if (p >= 1000) return p.toFixed(0);
  if (p >= 100) return p.toFixed(1);
  if (p >= 1) return p.toFixed(2);
  return p.toFixed(3);
}

function emaArr(vals: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const out: number[] = [];
  let prev = vals.length ? vals[0] : NaN;
  for (let i = 0; i < vals.length; i++) {
    prev = i === 0 ? vals[0] : vals[i] * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}

const EMA_DEFS = [
  { p: 20, color: "#c084fc" },
  { p: 50, color: "#3b82f6" },
  { p: 200, color: "#f59e0b" },
];

function bbands(vals: number[], period = 20, k = 2): { up: number[]; lo: number[] } {
  const up: number[] = [];
  const lo: number[] = [];
  for (let i = 0; i < vals.length; i++) {
    if (i < period - 1) {
      up.push(NaN);
      lo.push(NaN);
      continue;
    }
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += vals[j];
    const mean = sum / period;
    let v = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const d = vals[j] - mean;
      v += d * d;
    }
    const sd = Math.sqrt(v / period);
    up.push(mean + k * sd);
    lo.push(mean - k * sd);
  }
  return { up, lo };
}

export function SignalChartSvg({ bars, annotations, chain }: Props) {
  // Hover crosshair state (hooks run before any early return).
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null);

  if (!bars || bars.length < 2) {
    return (
      <div className="rounded-lg border border-dashed border-border/60 p-4 text-xs text-muted-foreground italic text-center">
        Grafico non disponibile per questo titolo.
      </div>
    );
  }

  const levels = annotations?.levels ?? [];
  const points = annotations?.points ?? [];

  // Number only the technical chain steps (no source). Collect their dates so
  // the window can zoom around them. Non-technical steps have no chart point.
  const techDates: string[] = [];
  const chainNum: (number | null)[] = [];
  let tc = 0;
  for (const step of chain) {
    if (step.source) {
      chainNum.push(null);
    } else {
      tc += 1;
      chainNum.push(tc);
      techDates.push(step.date.slice(0, 10));
    }
  }

  const nearestIn = (list: Bar[], iso: string): number | null => {
    const t = Date.parse(iso.slice(0, 10));
    if (Number.isNaN(t)) return null;
    let best = -1;
    let bestD = Infinity;
    for (let i = 0; i < list.length; i++) {
      const d = Math.abs(Date.parse(list[i].date.slice(0, 10)) - t);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    return best >= 0 ? best : null;
  };

  // Focus window: indices of the technical chain dates + the shape points,
  // padded on both sides, to zoom into the relevant area.
  const focusDates = [...techDates, ...points.map((p) => p.date.slice(0, 10))];
  const focusIdx = focusDates
    .map((d) => nearestIn(bars, d))
    .filter((v): v is number => v != null);
  let startIdx = 0;
  let endIdx = bars.length - 1;
  if (focusIdx.length > 0) {
    const minI = Math.min(...focusIdx);
    const maxI = Math.max(...focusIdx);
    startIdx = Math.max(0, minI - 55);
    endIdx = Math.min(bars.length - 1, maxI + 18);
    if (endIdx - startIdx < 50) {
      const mid = Math.round((minI + maxI) / 2);
      startIdx = Math.max(0, mid - 30);
      endIdx = Math.min(bars.length - 1, mid + 20);
    }
  }
  const win = bars.slice(startIdx, endIdx + 1);
  const wlen = win.length;

  const closesFull = bars.map((b) => b.close);
  const emaWin = EMA_DEFS.map((d) => ({
    color: d.color,
    label: `EMA${d.p}`,
    vals: emaArr(closesFull, d.p).slice(startIdx, endIdx + 1),
  }));
  const emaAll = emaWin.flatMap((e) => e.vals).filter((v) => Number.isFinite(v));
  const bb = bbands(closesFull, 20, 2);
  const bbUp = bb.up.slice(startIdx, endIdx + 1);
  const bbLo = bb.lo.slice(startIdx, endIdx + 1);
  const bbAll = [...bbUp, ...bbLo].filter((v) => Number.isFinite(v));

  const lvlP = levels.map((l) => l.price).filter((p) => Number.isFinite(p));
  const ptP = points.map((p) => p.price).filter((p) => Number.isFinite(p));
  const lo = Math.min(...win.map((b) => b.low), ...lvlP, ...ptP, ...emaAll, ...bbAll);
  const hi = Math.max(...win.map((b) => b.high), ...lvlP, ...ptP, ...emaAll, ...bbAll);
  const range = hi - lo || 1;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;
  const slot = innerW / wlen;
  const cx = (i: number) => PAD_L + slot * (i + 0.5);
  const y = (p: number) => PAD_T + (1 - (p - lo) / range) * innerH;
  const candleW = Math.max(1.5, Math.min(slot * 0.62, 11));

  const yTicks = Array.from({ length: 5 }, (_, k) => lo + (range * k) / 4);

  const bbUpLine = bbUp
    .map((v, i) => (Number.isFinite(v) ? `${cx(i).toFixed(1)},${y(v).toFixed(1)}` : null))
    .filter((q): q is string => q != null)
    .join(" ");
  const bbLoLine = bbLo
    .map((v, i) => (Number.isFinite(v) ? `${cx(i).toFixed(1)},${y(v).toFixed(1)}` : null))
    .filter((q): q is string => q != null)
    .join(" ");
  const bbIdx = bbUp.map((_, i) => i).filter((i) => Number.isFinite(bbUp[i]) && Number.isFinite(bbLo[i]));
  const bbFill =
    bbIdx.length >= 2
      ? [
          ...bbIdx.map((i) => `${cx(i).toFixed(1)},${y(bbUp[i]).toFixed(1)}`),
          ...bbIdx.slice().reverse().map((i) => `${cx(i).toFixed(1)},${y(bbLo[i]).toFixed(1)}`),
        ].join(" ")
      : "";

  const shapePts = points
    .map((p) => {
      const idx = nearestIn(win, p.date);
      return idx == null ? null : `${cx(idx).toFixed(1)},${y(p.price).toFixed(1)}`;
    })
    .filter((v): v is string => v != null)
    .join(" ");

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      role="img"
      aria-label="Grafico annotato del segnale"
      style={{ cursor: "crosshair" }}
      onMouseMove={(e) => {
        const el = svgRef.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        setHover({
          x: ((e.clientX - r.left) / r.width) * W,
          y: ((e.clientY - r.top) / r.height) * H,
        });
      }}
      onMouseLeave={() => setHover(null)}
    >
      <rect x={0} y={0} width={W} height={H} fill="transparent" />
      {/* price axis: gridlines + labels (left) */}
      {yTicks.map((p, i) => {
        const yy = y(p);
        return (
          <g key={`y-${i}`}>
            <line x1={PAD_L} y1={yy} x2={W - PAD_R} y2={yy} stroke={GRID} strokeWidth={0.5} opacity={0.25} />
            <text x={PAD_L - 5} y={yy + 3} textAnchor="end" fontSize={9} fill={GRID}>
              {priceLabel(p)}
            </text>
          </g>
        );
      })}

      {/* date axis: vertical guides + labels at the numbered markers */}
      {chain.map((step, i) => {
        if (chainNum[i] == null) return null;
        const idx = nearestIn(win, step.date);
        if (idx == null) return null;
        const x = cx(idx);
        return (
          <g key={`x-${i}`}>
            <line x1={x} y1={PAD_T} x2={x} y2={H - PAD_B} stroke={GRID} strokeWidth={0.5} strokeDasharray="2 3" opacity={0.45} />
            <text x={x} y={H - PAD_B + 13} textAnchor="middle" fontSize={9} fill="#64748b">
              {dm(step.date)}
            </text>
          </g>
        );
      })}

      {/* annotation levels + labels (right) */}
      {levels.map((l, i) => {
        const st = LEVEL_STYLE[l.kind] ?? { stroke: GRID };
        const yy = y(l.price);
        return (
          <g key={`lvl-${i}`}>
            <line x1={PAD_L} y1={yy} x2={W - PAD_R} y2={yy} stroke={st.stroke} strokeWidth={1} strokeDasharray={st.dash} opacity={0.85} />
            <text x={W - PAD_R} y={yy - 2} textAnchor="end" fontSize={9} fill={st.stroke}>
              {l.label}
            </text>
          </g>
        );
      })}

      {/* Bollinger Bands (20, 2 sigma) */}
      {bbFill && <polygon points={bbFill} fill="#94a3b8" opacity={0.08} />}
      {bbUpLine && (
        <polyline points={bbUpLine} fill="none" stroke="#94a3b8" strokeWidth={0.75} strokeDasharray="2 2" opacity={0.55} />
      )}
      {bbLoLine && (
        <polyline points={bbLoLine} fill="none" stroke="#94a3b8" strokeWidth={0.75} strokeDasharray="2 2" opacity={0.55} />
      )}

      {/* candlesticks */}
      {win.map((b, i) => {
        const up = b.close >= b.open;
        const col = up ? UP : DOWN;
        const x = cx(i);
        const bodyTop = Math.min(y(b.open), y(b.close));
        const bodyH = Math.max(1, Math.abs(y(b.close) - y(b.open)));
        return (
          <g key={`c-${i}`}>
            <line x1={x} y1={y(b.high)} x2={x} y2={y(b.low)} stroke={col} strokeWidth={1} />
            <rect x={x - candleW / 2} y={bodyTop} width={candleW} height={bodyH} fill={col} />
          </g>
        );
      })}

      {/* moving averages */}
      {emaWin.map((e) => {
        const pl = e.vals
          .map((v, i) => (Number.isFinite(v) ? `${cx(i).toFixed(1)},${y(v).toFixed(1)}` : null))
          .filter((q): q is string => q != null)
          .join(" ");
        return <polyline key={e.label} points={pl} fill="none" stroke={e.color} strokeWidth={1} opacity={0.75} />;
      })}
      {emaWin.map((e, i) => (
        <text key={`leg-${e.label}`} x={PAD_L + 2 + i * 52} y={PAD_T + 8} fontSize={9} fill={e.color} fontWeight="bold">
          {e.label}
        </text>
      ))}

      {/* pattern shape */}
      {points.length >= 2 && (
        <polyline points={shapePts} fill="none" stroke="#a855f7" strokeWidth={1.4} strokeDasharray="3 2" opacity={0.9} />
      )}

      {/* numbered markers (technical steps only). Markers that resolve to
          the SAME candle (e.g. a break + same-bar confirmation) are fanned
          upward by a fixed step so they never hide one another. */}
      {(() => {
        type Mk = { num: number; idx: number; x: number; hi: number; lo: number };
        const desc: Mk[] = [];
        chain.forEach((step, i) => {
          const num = chainNum[i];
          if (num == null) return;
          const idx = nearestIn(win, step.date);
          if (idx == null) return;
          desc.push({ num, idx, x: cx(idx), hi: y(win[idx].high), lo: y(win[idx].low) });
        });
        const usedByIdx: Record<number, number> = {};
        const STEP = 19; // vertical gap between stacked markers (circle r=8)
        return desc.map((d, k) => {
          const order = usedByIdx[d.idx] ?? 0;
          usedByIdx[d.idx] = order + 1;
          let my = d.hi - 13 - order * STEP; // stack upward on collision
          let anchorY = d.hi;
          if (my < PAD_T + 8) {              // no headroom -> stack below the low
            my = d.lo + 15 + order * STEP;
            anchorY = d.lo;
          }
          return (
            <g key={`mk-${k}`}>
              <line x1={d.x} y1={my} x2={d.x} y2={anchorY} stroke="#0f172a" strokeWidth={0.75} opacity={0.5} />
              <circle cx={d.x} cy={my} r={8} fill="#0f172a" stroke="#fff" strokeWidth={1} />
              <text x={d.x} y={my + 3} textAnchor="middle" fontSize={9} fill="#fff" fontWeight="bold">
                {d.num}
              </text>
            </g>
          );
        });
      })()}
      {hover &&
        (() => {
          const hx = Math.max(PAD_L, Math.min(W - PAD_R, hover.x));
          const hy = Math.max(PAD_T, Math.min(H - PAD_B, hover.y));
          const bi = Math.max(0, Math.min(wlen - 1, Math.round((hx - PAD_L) / slot - 0.5)));
          const bx = cx(bi);
          const price = lo + (1 - (hy - PAD_T) / innerH) * range;
          return (
            <g>
              <line x1={bx} y1={PAD_T} x2={bx} y2={H - PAD_B} stroke="#475569" strokeWidth={0.6} strokeDasharray="3 2" opacity={0.75} />
              <line x1={PAD_L} y1={hy} x2={W - PAD_R} y2={hy} stroke="#475569" strokeWidth={0.6} strokeDasharray="3 2" opacity={0.75} />
              <circle cx={bx} cy={y(win[bi].close)} r={2.5} fill="#0f172a" stroke="#fff" strokeWidth={1} />
              <rect x={0} y={hy - 7} width={PAD_L - 3} height={14} rx={2} fill="#0f172a" />
              <text x={PAD_L - 5} y={hy + 3} textAnchor="end" fontSize={9} fill="#fff">{priceLabel(price)}</text>
              <rect x={bx - 19} y={H - PAD_B + 2} width={38} height={13} rx={2} fill="#0f172a" />
              <text x={bx} y={H - PAD_B + 11} textAnchor="middle" fontSize={9} fill="#fff">{dm(win[bi].date)}</text>
            </g>
          );
        })()}
    </svg>
  );
}
