import { ArrowDown, ArrowUp, Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import type { SectorSummary } from "@/hooks/useSectorDetail";
import { GAP_NOTABLE, type SortKey, lensGap, sortSectors } from "@/lib/sectorLens";
import { cn } from "@/lib/utils";

/* ─── SectorLensTable — every sector on one screen, comparable ───────────── *
 *
 * Replaces the grid of eleven identical cards. Those cards presented every
 * sector the same way, in alphabetical order, with seven metrics each rendered
 * as plain text — so answering "which sector has the strongest technical
 * posture" meant reading and mentally comparing seventy-seven numbers.
 *
 * A table with sortable columns answers that in one click, and bars answer it
 * without any: where the reader only needs a comparison, a bar is a better
 * encoding than a digit. The digits stay for when the value itself matters.
 */

interface Props {
  sectors: SectorSummary[];
  activeSector?: string | null;
  onHover?: (name: string | null) => void;
}

/** Scale for the 0-100 lens bars. Clamped to 30-75 rather than 0-100 because
 *  real sector averages live in a ~43-66 band: on a full 0-100 axis every bar
 *  would sit near the middle and the comparison the bar exists for would be
 *  invisible. */
function lensPct(v: number): number {
  return Math.max(0, Math.min(100, ((v - 30) / 45) * 100));
}

function LensBar({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 w-12 shrink-0 rounded-full bg-muted overflow-hidden">
        <span
          className="block h-full rounded-full bg-primary"
          style={{ width: `${lensPct(value)}%` }}
        />
      </span>
      <span className="tabular-nums font-semibold">{value.toFixed(1)}</span>
    </span>
  );
}

/** Bull/bear as one split bar plus the total. The totals alone hide the
 *  reading: 121 signals and 22 signals say nothing about direction, while
 *  111/10 and 6/16 say everything. */
function SignalSplit({ s }: { s: SectorSummary }) {
  const tot = s.signals_7d_bull + s.signals_7d_bear;
  if (tot === 0) {
    return <span className="text-muted-foreground text-xs">nessuno</span>;
  }
  return (
    <span
      className="flex items-center gap-2"
      title={`${s.signals_7d_bull} rialzisti · ${s.signals_7d_bear} ribassisti (7 giorni)`}
    >
      <span className="flex h-1.5 w-14 shrink-0 rounded-full overflow-hidden bg-muted">
        <span className="bg-emerald-500" style={{ flex: s.signals_7d_bull }} />
        <span className="bg-red-500" style={{ flex: s.signals_7d_bear }} />
      </span>
      <span className="tabular-nums text-xs text-muted-foreground">{s.signals_7d}</span>
    </span>
  );
}

function Sparkline({ points }: { points: { date: string; avg: number }[] }) {
  if (points.length < 2) return <span className="text-muted-foreground text-xs">—</span>;
  const vals = points.map((p) => p.avg);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const rng = hi - lo || 1;
  const w = 68;
  const h = 20;
  const d = vals
    .map((v, i) => `${(i / (vals.length - 1)) * w},${h - ((v - lo) / rng) * h}`)
    .join(" ");
  const up = vals[vals.length - 1] >= vals[0];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-[68px] h-5" aria-hidden>
      <polyline
        points={d}
        fill="none"
        strokeWidth={1.5}
        className={up ? "stroke-emerald-500" : "stroke-red-500"}
      />
    </svg>
  );
}

function toneClass(v: number | null): string {
  if (v === null) return "text-muted-foreground";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-red-600 dark:text-red-400";
  return "text-muted-foreground";
}

function signed(v: number | null, digits = 1): string {
  if (v === null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;
}

const COLUMNS: { key: SortKey; label: string; help: string; num?: boolean }[] = [
  { key: "name", label: "Settore", help: "Nome GICS · clicca per il dettaglio" },
  { key: "stock_count", label: "N", help: "Stock nel settore", num: true },
  { key: "avg_score", label: "Qualità", help: "Media dei compositi fondamentali (0–100)" },
  { key: "avg_technical", label: "Tecnico", help: "Media dei compositi tecnici (0–100)" },
  { key: "gap", label: "Divario", help: "Tecnico − Qualità: dove le due lenti non concordano", num: true },
  { key: "change_pct", label: "Δ%", help: "Variazione media giornaliera del settore", num: true },
  { key: "signals", label: "Segnali 7g", help: "Rialzisti vs ribassisti negli ultimi 7 giorni" },
];

export function SectorLensTable({ sectors, activeSector, onHover }: Props) {
  // Quality descending is the page's existing mental model (the old cards led
  // with "score medio"), so the default order is familiar even though the
  // shape changed. Divario is one header-click away.
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({
    key: "avg_score",
    asc: false,
  });

  const rows = useMemo(
    () => sortSectors(sectors, sort.key, sort.asc),
    [sectors, sort],
  );

  const toggle = (key: SortKey) =>
    setSort((prev) =>
      prev.key === key ? { key, asc: !prev.asc } : { key, asc: key === "name" },
    );

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="px-3 py-2 border-b bg-muted/30 flex items-center justify-between gap-3">
          <SectionTitle icon={Table2} label={`Settori (${sectors.length})`} />
          <span className="text-[0.7059rem] text-muted-foreground truncate">
            clicca un'intestazione per riordinare
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[760px]">
            <thead>
              <tr className="border-b">
                {COLUMNS.map((c) => {
                  const active = sort.key === c.key;
                  return (
                    <th
                      key={c.key}
                      scope="col"
                      className={cn(
                        "px-3 py-1.5 font-medium text-[0.6765rem] uppercase tracking-[0.14em]",
                        c.num ? "text-right" : "text-left",
                        active ? "text-foreground" : "text-muted-foreground",
                      )}
                      aria-sort={active ? (sort.asc ? "ascending" : "descending") : "none"}
                    >
                      <button
                        type="button"
                        onClick={() => toggle(c.key)}
                        title={c.help}
                        className={cn(
                          "inline-flex items-center gap-1 hover:text-foreground transition-colors",
                          c.num && "flex-row-reverse",
                        )}
                      >
                        {c.label}
                        {active &&
                          (sort.asc ? (
                            <ArrowUp className="h-3 w-3" aria-hidden />
                          ) : (
                            <ArrowDown className="h-3 w-3" aria-hidden />
                          ))}
                      </button>
                    </th>
                  );
                })}
                <th scope="col" className="px-3 py-1.5 text-left font-medium text-[0.6765rem] uppercase tracking-[0.14em] text-muted-foreground">
                  Trend
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const gap = lensGap(s);
                const notable = gap !== null && Math.abs(gap) >= GAP_NOTABLE;
                return (
                  <tr
                    key={s.name}
                    onMouseEnter={() => onHover?.(s.name)}
                    onMouseLeave={() => onHover?.(null)}
                    className={cn(
                      "border-b last:border-b-0 transition-colors",
                      activeSector === s.name ? "bg-accent/50" : "hover:bg-accent/30",
                    )}
                  >
                    <td className="px-3 py-1.5">
                      <Link
                        to={`/sectors/${encodeURIComponent(s.name)}`}
                        className="font-medium hover:underline"
                      >
                        {s.name}
                      </Link>
                      {s.etf_proxy && (
                        <span className="ml-2 rounded border px-1 text-[0.6765rem] text-muted-foreground align-middle">
                          {s.etf_proxy}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                      {s.stock_count}
                    </td>
                    <td className="px-3 py-1.5"><LensBar value={s.avg_score} /></td>
                    <td className="px-3 py-1.5"><LensBar value={s.avg_technical} /></td>
                    <td
                      className={cn(
                        "px-3 py-1.5 text-right tabular-nums font-semibold",
                        toneClass(gap),
                      )}
                      title={
                        notable
                          ? "Le due lenti divergono di oltre 8 punti"
                          : "Tecnico meno Qualità"
                      }
                    >
                      {signed(gap)}
                      {/* Marked only past the threshold: highlighting every row
                          would make the highlight mean nothing. */}
                      {notable && <span className="ml-1" aria-hidden>•</span>}
                    </td>
                    <td className={cn("px-3 py-1.5 text-right tabular-nums", toneClass(s.change_pct))}>
                      {s.change_pct === null ? "—" : `${signed(s.change_pct, 2)}%`}
                    </td>
                    <td className="px-3 py-1.5"><SignalSplit s={s} /></td>
                    <td className="px-3 py-1.5">
                      <Sparkline points={s.score_trend} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* The sparkline and the Qualità column are NOT the same series — the
            trend comes from score_history captures, which cover only the
            stocks that had a score on each capture date. Saying so is cheaper
            than letting the reader wonder why a sector reading 47.7 draws a
            line around 59. */}
        <p className="px-3 py-2 border-t text-[0.7059rem] text-muted-foreground">
          Il trend proviene dalle catture storiche dello score e copre solo gli stock
          già valutati a ciascuna data: la sua scala può non coincidere con la colonna
          Qualità, che è calcolata su tutto il settore oggi.
        </p>
      </CardContent>
    </Card>
  );
}
