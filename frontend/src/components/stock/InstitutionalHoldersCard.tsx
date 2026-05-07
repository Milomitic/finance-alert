import { Building2 } from "lucide-react";
import { Link } from "react-router-dom";

import type { TickerHolder } from "@/api/types";
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

function HolderRow({ h }: { h: TickerHolder }) {
  const a = actionMeta(h.action);
  const displayName = h.institutional_manager
    ? `${h.institutional_manager} · ${h.institutional_name}`
    : h.institutional_name;

  return (
    <li className="flex items-baseline gap-2 py-1 border-t border-border/40 first:border-t-0 leading-tight">
      <Link
        to={`/institutionals/${h.institutional_slug}`}
        className="text-[13.5px] font-semibold truncate hover:underline"
        title={displayName}
      >
        {displayName}
      </Link>
      <span className={cn("text-[12px] truncate shrink-0", a.tone)} title={a.label}>
        {a.label}
      </span>
      <span className="text-[12px] text-muted-foreground tabular-nums shrink-0">
        {fmtPct(h.portfolio_pct)} · {fmtBig(h.value_usd)}
      </span>
      <span className="ml-auto text-[12px] text-muted-foreground tabular-nums shrink-0">
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
  const q = useTickerInstitutionalHolders(ticker);

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
  const visible = holders.slice(0, 10);

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
          <ul>
            {visible.map((h) => (
              <HolderRow key={`${h.institutional_id}-${h.period_end_date}`} h={h} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
