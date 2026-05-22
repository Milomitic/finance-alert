import { useQuery } from "@tanstack/react-query";
import { Gavel, Newspaper } from "lucide-react";
import { Link } from "react-router-dom";

import { dashboard, type AnalystAction } from "@/api/dashboard";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { cn } from "@/lib/utils";

/* Genuine rating CHANGES only — the card used to be dominated by
 * "Maintain"/"Reiterate" rows (a firm reaffirming, no change) which are
 * noise. We keep upgrades, downgrades and coverage initiations and drop
 * the maintains, matching the card's own description. */
const CHANGE_ACTIONS = new Set(["up", "down", "init"]);

/* A price target is only meaningful when strictly positive. yfinance /
 * the news extractor sometimes return 0 (or null) when a firm moved the
 * rating but didn't publish a number → treat non-positive as "no number". */
function posTarget(v: number | null | undefined): number | null {
  return v != null && v > 0 ? v : null;
}

/* Grade → buy/hold/sell tone bucket. Mirrors AnalystTargetCard.gradeTone
 * so the dashboard feed and the stock-detail "Analyst" card share the
 * exact same rating vocabulary + colors. */
function gradeTone(grade: string | null | undefined): "buy" | "hold" | "sell" | "neutral" {
  const g = (grade ?? "").toLowerCase();
  if (/buy|outperform|overweight|positive|accumulate/.test(g)) return "buy";
  if (/sell|underperform|underweight|negative|reduce/.test(g)) return "sell";
  if (/hold|neutral|equal|market perform|sector weight|in-line|peer perform/.test(g))
    return "hold";
  return "neutral";
}

/* Literal class strings (not composed) so Tailwind's purger keeps them.
 * Same palette as AnalystTargetCard's TONE_CLASSES. */
const TONE_CLASSES: Record<ReturnType<typeof gradeTone>, string> = {
  buy: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200",
  hold: "bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200",
  sell: "bg-rose-100 dark:bg-rose-900/40 text-rose-800 dark:text-rose-200",
  neutral: "bg-muted text-muted-foreground",
};

/* The rating itself, as a tone-classed chip (the new row "label" — the
 * Upgrade/Maintain action chip was removed). The full from→to transition
 * lives on hover for context. */
function GradeChip({
  from,
  to,
}: {
  from?: string | null;
  to?: string | null;
}) {
  const grade = to || from || "—";
  return (
    <span
      className={cn(
        "px-1.5 py-0.5 rounded text-[12px] font-semibold shrink-0",
        TONE_CLASSES[gradeTone(grade)],
      )}
      title={from && to && from !== to ? `${from} → ${to}` : grade}
    >
      {grade}
    </span>
  );
}

/* Price-target chip — arrow (direction of the target move) + the new
 * dollar figure, colored by `price_target_action`. Same inline style as
 * AnalystTargetCard.PriceTargetChip. Renders nothing when there's no
 * usable number (the date still anchors the row). */
function priceTargetTone(action: string | null | undefined): { cls: string; arrow: string } {
  switch (action) {
    case "Raises":
      return { cls: "text-emerald-700 dark:text-emerald-300", arrow: "↑" };
    case "Lowers":
      return { cls: "text-rose-700 dark:text-rose-300", arrow: "↓" };
    case "Initiates":
      return { cls: "text-blue-700 dark:text-blue-300", arrow: "✦" };
    case "Maintains":
    default:
      return { cls: "text-muted-foreground", arrow: "→" };
  }
}

function PriceTargetChip({ a }: { a: AnalystAction }) {
  const cur = posTarget(a.current_price_target);
  if (cur == null) return null;
  const prior = posTarget(a.prior_price_target);
  const tone = priceTargetTone(a.price_target_action);
  const fmt = Number.isInteger(cur) ? `$${cur}` : `$${cur.toFixed(2)}`;
  const title =
    prior != null && prior !== cur
      ? `Target: $${prior.toFixed(0)} → $${cur.toFixed(0)}`
      : `Target: $${cur.toFixed(0)}`;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 tabular-nums font-bold shrink-0 text-[13px]",
        tone.cls,
      )}
      title={title}
    >
      <span>{tone.arrow}</span>
      <span>{fmt}</span>
    </span>
  );
}

function fmtDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
}

function ActionRow({ a }: { a: AnalystAction }) {
  return (
    <li className="border-b border-border/40 last:border-b-0 min-w-0">
      <Link
        to={`/stocks/${encodeURIComponent(a.ticker)}`}
        className="flex items-center gap-2.5 px-3 py-2 hover:bg-accent/30 transition-colors min-w-0"
        title={a.name ?? a.ticker}
      >
        {/* Compact identity: logo + ticker (company name → row tooltip). */}
        <StockLogo ticker={a.ticker} size="xs" />
        <span className="shrink-0 w-[40px] text-[13px] font-bold tabular-nums leading-none truncate">
          {a.ticker}
        </span>

        {/* Firm — flexes + truncates first when the row gets tight. */}
        <span
          className="flex-1 min-w-0 text-[12px] text-muted-foreground truncate"
          title={a.firm}
        >
          {a.firm || "—"}
        </span>
        {a.from_news && (
          <span
            className="inline-flex items-center gap-0.5 text-[9.5px] text-muted-foreground/70 shrink-0"
            title="Estratto da una notizia (non dal feed strutturato)"
          >
            <Newspaper className="h-2.5 w-2.5" /> news
          </span>
        )}

        {/* The new "label": rating (valutazione) + price target, in the
            stock-detail Analyst card's style. */}
        <GradeChip from={a.from_grade} to={a.to_grade} />
        <PriceTargetChip a={a} />

        <span className="shrink-0 w-10 text-right text-[10px] text-muted-foreground tabular-nums whitespace-nowrap">
          {fmtDate(a.date)}
        </span>
      </Link>
    </li>
  );
}

function RowSkeleton() {
  return (
    <li className="border-b border-border/40 last:border-b-0 px-3 py-2">
      <div className="flex items-center gap-2.5">
        <div className="h-7 w-7 rounded-full bg-muted/60 animate-pulse" />
        <div className="h-3 w-10 rounded bg-muted/60 animate-pulse" />
        <div className="h-3 flex-1 rounded bg-muted/40 animate-pulse" />
        <div className="h-4 w-12 rounded bg-muted/40 animate-pulse" />
      </div>
    </li>
  );
}

export function AnalystActionsCard() {
  const q = useQuery({
    queryKey: ["analyst-actions"],
    queryFn: () => dashboard.analystActions(40),
    // Analyst actions only change when fundamentals are re-fetched
    // (weekly TTL). A 5-min client cache avoids re-pinging on every
    // dashboard revisit while staying fresh enough.
    staleTime: 5 * 60_000,
  });
  // Show only genuine rating changes — hide the Maintain/Reiterate rows.
  const items = (q.data ?? []).filter((a) => CHANGE_ACTIONS.has(a.action));
  const isEmpty = !q.isLoading && items.length === 0;

  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        <div className="shrink-0 px-3 py-2 border-b bg-muted/30">
          <SectionTitle
            icon={Gavel}
            label="Valutazioni analisti"
            right={
              <span className="text-xs text-muted-foreground">
                upgrade & downgrade
              </span>
            }
          />
        </div>
        {q.isLoading ? (
          <ul className="flex-1 min-h-0 overflow-y-auto">
            {Array.from({ length: 10 }).map((_, i) => (
              <RowSkeleton key={i} />
            ))}
          </ul>
        ) : isEmpty ? (
          <div className="flex-1 min-h-0 flex items-center justify-center px-4 text-center">
            <div className="text-xs text-muted-foreground">
              Nessun upgrade/downgrade recente.
              <br />
              <span className="text-muted-foreground/70">
                Compaiono qui i cambi di rating (upgrade / downgrade /
                initiation) degli ultimi 90 giorni man mano che i
                fondamentali vengono aggiornati.
              </span>
            </div>
          </div>
        ) : (
          <ul className="flex-1 min-h-0 overflow-y-auto">
            {items.map((a, i) => (
              <ActionRow key={`${a.ticker}-${a.date}-${a.firm}-${i}`} a={a} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
