import { Building2 } from "lucide-react";
import { Link } from "react-router-dom";

import type { TickerHolder } from "@/api/types";
import { AllocationBars } from "@/components/dashboard/AllocationBars";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useTickerInstitutionalHolders } from "@/hooks/useInstitutionals";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

function fmtBig(v: number | null | undefined): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toLocaleString()}`;
}

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null) return "—";
  return `${v.toFixed(digits)}%`;
}

function shortDate(s: string): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  if (!y || !m || !d) return s;
  return `${d}/${m}/${y.slice(2)}`;
}

/**
 * Action label + tone. Mirrors the Dataroma vocabulary:
 *   new      — first-time position
 *   add      — added shares (Q/Q)
 *   reduce   — trimmed
 *   sold_out — fully exited (still surfaced because the position was on
 *              the previous filing — the "sold out" signal is editorial value)
 *   hold     — unchanged
 */
function actionMeta(action: string | null): {
  label: string;
  tone: string;
} {
  switch (action) {
    case "new":
      return { label: "Nuovo", tone: "text-emerald-700 dark:text-emerald-300" };
    case "add":
      return { label: "Add", tone: "text-emerald-700 dark:text-emerald-300" };
    case "reduce":
      return { label: "Reduce", tone: "text-amber-700 dark:text-amber-300" };
    case "sold_out":
      return { label: "Sold out", tone: "text-red-700 dark:text-red-300" };
    case "hold":
      return { label: "Hold", tone: "text-muted-foreground" };
    default:
      return { label: action ?? "—", tone: "text-muted-foreground" };
  }
}

/* Shared column grid — header row and every data row use the SAME
 * template string so the cells align by construction. Tracks:
 *   name (flex, truncates) · action · % · value$ · date
 * `minmax(0,1fr)` (not plain `1fr`) is load-bearing: it injects the
 * implicit min-width:0 that lets the long fund name truncate instead
 * of overflowing its track. */
const HOLDER_GRID =
  "grid grid-cols-[minmax(0,1fr)_4rem_3rem_4.75rem_3.5rem] items-baseline gap-2 min-w-[340px] md:min-w-0";

function HolderHeader() {
  return (
    <li
      className={cn(
        HOLDER_GRID,
        "pb-1 text-[0.5882rem] uppercase tracking-wider text-muted-foreground/70 font-semibold",
      )}
    >
      <span className="truncate">Fondo</span>
      <span className="truncate">Azione</span>
      <span className="text-right">%</span>
      <span className="text-right">Valore</span>
      <span className="text-right">Data</span>
    </li>
  );
}

function HolderRow({ h }: { h: TickerHolder }) {
  const a = actionMeta(h.action);
  // Show ONLY the fund/firm — the individual manager/analyst name is
  // deliberately omitted (user spec: "lascia solo le società e i fondi
  // di appartenenza").
  const displayName = h.institutional_name;

  return (
    <li
      className={cn(
        HOLDER_GRID,
        "py-1 border-t border-border/40 leading-tight",
      )}
    >
      <Link
        to={`/institutionals/${h.institutional_slug}`}
        className="text-[13.5px] font-semibold truncate hover:underline min-w-0"
        title={displayName}
      >
        {displayName}
      </Link>
      <span className={cn("text-[0.7059rem] truncate", a.tone)} title={a.label}>
        {a.label}
      </span>
      <span className="text-[0.7059rem] text-muted-foreground tabular-nums text-right">
        {fmtPct(h.portfolio_pct)}
      </span>
      <span className="text-[0.7059rem] text-muted-foreground tabular-nums text-right">
        {fmtBig(h.value_usd)}
      </span>
      <span className="text-[0.7059rem] text-muted-foreground tabular-nums text-right">
        {shortDate(h.period_end_date)}
      </span>
    </li>
  );
}

/**
 * Lists the institutionals / superinvestors holding `ticker` in their
 * latest filing. Sits ABOVE the InsidersAnalystCard in the right
 * sidebar of the stock detail page (per user spec: "sopra insider").
 *
 * Empty data path: render a tiny "Nessun fondo tracciato detiene…"
 * line — the user explicitly opted to keep the card visible even when
 * empty so the info-architecture doesn't shift between stocks.
 */
export function InstitutionalHoldersCard({ ticker }: Props) {
  const q = useTickerInstitutionalHolders(ticker, 25, true);

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-3">
          <SectionTitle icon={Building2} label="Superinvestor / fondi" className="mb-2" />
          <div className="h-24 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const holders = q.data?.holders ?? [];
  const historical = q.data?.historical ?? [];
  const visible = holders.slice(0, 10);

  /* The positions panel, and why it is NOT the table above repeated.
   *
   * The table lists the latest TRANSACTIONS: one row per fund, labelled with
   * the 13F verb (Add / Reduce / Nuovo). This panel answers a different
   * question — who HOLDS this stock and how much of their book it is — so it
   * must not carry the same verbs. `value_usd` and `portfolio_pct` are the
   * fund's TOTAL position in its latest filing, not the size of the change:
   * an "Add" adds to whatever the fund already held, or equals the position
   * when it is the first. Labelling a total-position bar "ADD" answered a
   * question nobody asked of it. The movement now shows as a signed delta.
   *
   * One row per institution. A fund can appear in both lists (a stale current
   * row plus a newer historical one); the CURRENT row wins, because the panel
   * describes what is held now.
   *
   * Historical funds are `exited` → struck through with a dashed, hollow bar,
   * and AllocationBars keeps them in their own block so the `max` cut can
   * never drop them silently. Before this they were sorted in with live
   * positions by weight, so on any stock whose top ten holders were all
   * current the panel rendered exactly the ten rows above it — which is the
   * bug that made "incl. storiche" a promise the panel did not keep.
   */
  const seen = new Set<number>();
  const allocItems = [
    ...holders.map((h) => ({
      key: `cur-${h.institutional_id}-${h.period_end_date}`,
      label: h.institutional_name,
      href: `/institutionals/${h.institutional_slug}`,
      valueUsd: h.value_usd,
      pct: h.portfolio_pct,
      deltaPct: h.qoq_change_pct ?? null,
      exited: false,
      id: h.institutional_id,
    })),
    ...historical.map((h) => ({
      key: `hist-${h.institutional_id}-${h.period_end_date}`,
      label: h.institutional_name,
      href: `/institutionals/${h.institutional_slug}`,
      valueUsd: h.value_usd,
      pct: h.portfolio_pct,
      deltaPct: null,
      exited: true,
      id: h.institutional_id,
    })),
  ].filter((i) => (seen.has(i.id) ? false : (seen.add(i.id), true)));

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle
          icon={Building2}
          label="Superinvestor / fondi"
          className="mb-2"
          right={
            holders.length > 0 ? (
              <span className="text-xs text-muted-foreground tabular-nums">
                {visible.length} di {holders.length}
              </span>
            ) : undefined
          }
        />
        {holders.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-3">
            Nessun fondo tracciato detiene questo titolo.
          </div>
        ) : (
          <>
            {/* The fixed columns are wider than a phone; scroll the list
                rather than let the identity cell collapse to zero. */}
            <div className="overflow-x-auto md:overflow-visible">
            <ul>
              <HolderHeader />
              {visible.map((h) => (
                <HolderRow key={`${h.institutional_id}-${h.period_end_date}`} h={h} />
              ))}
            </ul>
            </div>
            {/* Besides the latest transactions above, the same data as
                an infographic: WHO holds this stock and in what
                measure — bar length = the holder's portfolio WEIGHT
                (the % shown next to it), so a tiny-weight mega-fund no
                longer fills the whole bar just because its dollar
                position is the largest. */}
            <div className="mt-3 border-t border-border/40 pt-3">
              <AllocationBars
                title="Posizioni per istituzione (incl. uscite)"
                max={14}
                metric="weight"
                items={allocItems}
              />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
