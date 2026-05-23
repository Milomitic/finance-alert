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
  support: { stroke: "#16a34a" },
  resistance: { stroke: "#dc2626" },
  stop: { stroke: "#d97706", dash: "4 3" },
};

const UP = "#16a34a";
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
    startIdx = Math.max(0, minI - 24);
    endIdx = Math.min(bars.length - 1, maxI + 8);
    if (endIdx - startIdx < 14) {
      const mid = Math.round((minI + maxI) / 2);
      startIdx = Math.max(0, mid - 9);
      endIdx = Math.min(bars.length - 1, mid + 9);
    }
  }
  const win = bars.slice(startIdx, endIdx + 1);
  const wlen = win.length;

  const lvlP = levels.map((l) => l.price).filter((p) => Number.isFinite(p));
  const ptP = points.map((p) => p.price).filter((p) => Number.isFinite(p));
  const lo = Math.min(...win.map((b) => b.low), ...lvlP, ...ptP);
  const hi = Math.max(...win.map((b) => b.high), ...lvlP, ...ptP);
  const range = hi - lo || 1;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;
  const slot = innerW / wlen;
  const cx = (i: number) => PAD_L + slot * (i + 0.5);
  const y = (p: number) => PAD_T + (1 - (p - lo) / range) * innerH;
  const candleW = Math.max(1.5, Math.min(slot * 0.62, 11));

  const yTicks = Array.from({ length: 5 }, (_, k) => lo + (range * k) / 4);

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

      {/* pattern shape */}
      {points.length >= 2 && (
        <polyline points={shapePts} fill="none" stroke="#a855f7" strokeWidth={1.4} strokeDasharray="3 2" opacity={0.9} />
      )}

      {/* numbered markers (technical steps only), above the bar high */}
      {chain.map((step, i) => {
        const num = chainNum[i];
        if (num == null) return null;
        const idx = nearestIn(win, step.date);
        if (idx == null) return null;
        const x = cx(idx);
        const top = y(win[idx].high);
        let my = top - 13;
        if (my < PAD_T + 8) my = y(win[idx].low) + 15;
        return (
          <g key={`mk-${i}`}>
            <line x1={x} y1={my} x2={x} y2={top} stroke="#0f172a" strokeWidth={0.75} opacity={0.5} />
            <circle cx={x} cy={my} r={8} fill="#0f172a" stroke="#fff" strokeWidth={1} />
            <text x={x} y={my + 3} textAnchor="middle" fontSize={9} fill="#fff" fontWeight="bold">
              {num}
            </text>
          </g>
        );
      })}
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
