import { useQuery } from "@tanstack/react-query";
import {
  Gavel,
  ArrowUpRight,
  ArrowDownRight,
  ArrowRight,
  Sparkles,
  Minus,
  Newspaper,
  ChevronsUp,
  ChevronsDown,
  Target,
  Equal,
} from "lucide-react";
import { Link } from "react-router-dom";

import { dashboard, type AnalystAction } from "@/api/dashboard";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { cn } from "@/lib/utils";

/* Action → visual treatment. yfinance's `action` codes:
   up = upgrade, down = downgrade, init = new coverage,
   reit/main = reiterate/maintain (no grade change). */
const ACTION_META: Record<
  string,
  { label: string; tone: string; chipBg: string; Icon: React.ComponentType<{ className?: string }> }
> = {
  up:   { label: "Upgrade",    tone: "text-emerald-700 dark:text-emerald-300", chipBg: "bg-emerald-100/70 dark:bg-emerald-900/30 border-emerald-300/60 dark:border-emerald-700/50", Icon: ArrowUpRight },
  down: { label: "Downgrade",  tone: "text-rose-700 dark:text-rose-300",       chipBg: "bg-rose-100/70 dark:bg-rose-900/30 border-rose-300/60 dark:border-rose-700/50",          Icon: ArrowDownRight },
  init: { label: "Initiation", tone: "text-sky-700 dark:text-sky-300",         chipBg: "bg-sky-100/70 dark:bg-sky-900/30 border-sky-300/60 dark:border-sky-700/50",            Icon: Sparkles },
  reit: { label: "Reiterate",  tone: "text-muted-foreground",                  chipBg: "bg-muted/60 border-border/50",                                                          Icon: Minus },
  main: { label: "Maintain",   tone: "text-muted-foreground",                  chipBg: "bg-muted/60 border-border/50",                                                          Icon: Minus },
};

function actionMeta(action: string) {
  return ACTION_META[action] ?? ACTION_META.main;
}

/* Price-target chip palette — mirrors the rating action chip so the
 * row reads as a coherent pair: rating-action on the left, price-
 * target action on the right, same shape, same tone vocabulary.
 *
 * `price_target_action` is yfinance's *separate* axis from the
 * rating: e.g. a "Maintain" rating can pair with a "Raises" target.
 * That decoupling is informative ("they're standing pat on the
 * rating but bumping the target +5%") so we surface it explicitly
 * instead of folding the two into one chip. */
const PT_META: Record<
  string,
  { label: string; tone: string; chipBg: string; Icon: React.ComponentType<{ className?: string }> }
> = {
  Raises:    { label: "Alza target",    tone: "text-emerald-700 dark:text-emerald-300", chipBg: "bg-emerald-50/80 dark:bg-emerald-950/40 border-emerald-300/60 dark:border-emerald-700/50", Icon: ChevronsUp },
  Lowers:    { label: "Abbassa target", tone: "text-rose-700 dark:text-rose-300",       chipBg: "bg-rose-50/80 dark:bg-rose-950/40 border-rose-300/60 dark:border-rose-700/50",             Icon: ChevronsDown },
  Maintains: { label: "Conferma target", tone: "text-muted-foreground",                 chipBg: "bg-muted/40 border-border/40",                                                              Icon: Equal },
  Initiates: { label: "Apre target",    tone: "text-sky-700 dark:text-sky-300",         chipBg: "bg-sky-50/80 dark:bg-sky-950/40 border-sky-300/60 dark:border-sky-700/50",                Icon: Target },
};

function ptMeta(pt: string | null | undefined) {
  if (!pt) return null;
  return PT_META[pt] ?? null;
}

/* A price target is only meaningful when strictly positive. yfinance /
 * the news extractor sometimes hand back 0 (or null) when a firm moved
 * the rating but didn't publish a number — rendering that as "$0" was a
 * bug (see the Keybanc row in the screenshot). Coerce non-positive to
 * null so the chip logic treats it as "no number". */
function posTarget(v: number | null | undefined): number | null {
  return v != null && v > 0 ? v : null;
}

/* Grade → sentiment colour. Buy/Outperform/Overweight read bullish
 * (emerald), Sell/Underperform/Underweight bearish (rose), and
 * Hold/Neutral/Sector-Weight/Equal-Weight stay muted. Literal class
 * strings (not composed) so Tailwind's purger keeps them. */
function gradeTone(grade: string | null | undefined): string {
  if (!grade) return "text-muted-foreground";
  if (/sell|underperform|underweight|reduce|negative/i.test(grade))
    return "text-rose-600 dark:text-rose-400";
  if (/buy|outperform|overweight|accumulate|positive|^add$/i.test(grade))
    return "text-emerald-600 dark:text-emerald-400";
  return "text-muted-foreground"; // hold / neutral / sector weight / in-line
}

/* The resulting grade, sentiment-coloured. For a genuine change we show
 * "from → to" (the `to` carries the colour); the full pair also lives in
 * the title for when it truncates. The row's action chip (Upgrade/
 * Downgrade) already signals direction, so this stays compact. */
function GradeDisplay({
  from,
  to,
}: {
  from?: string | null;
  to?: string | null;
}) {
  const changed = !!(from && to && from !== to);
  if (changed) {
    return (
      <span
        className="inline-flex items-center gap-0.5 shrink-0 font-medium leading-none"
        title={`${from} → ${to}`}
      >
        <span className="text-muted-foreground/70">{from}</span>
        <ArrowRight className="h-2.5 w-2.5 shrink-0 text-muted-foreground/50" />
        <span className={gradeTone(to)}>{to}</span>
      </span>
    );
  }
  const g = to || from || null;
  return (
    <span
      className={cn("shrink-0 font-medium leading-none", gradeTone(g))}
      title={g ?? undefined}
    >
      {g || "—"}
    </span>
  );
}

/* Renders the right-hand price-target chip. Inside one tag we pack:
 *  - colour/tone signalling the direction (Raises/Lowers/etc.)
 *  - the new target as the dominant figure
 *  - the prior target as a smaller strikethrough → "291 → $314"
 *
 * If we have an action but no numeric target (Yahoo doesn't always
 * expose them), we fall back to just the action label so the user
 * still sees that the firm touched the target. If we have neither,
 * we render nothing (the date column still anchors the row). */
function PriceTargetChip({ a }: { a: AnalystAction }) {
  const meta = ptMeta(a.price_target_action);
  const cur = posTarget(a.current_price_target);
  const prior = posTarget(a.prior_price_target);

  // No usable number. A chip is only worth showing if the firm
  // DIRECTIONALLY moved the target (Raises / Lowers) — that conveys
  // signal even without a figure. A bare "Maintains"/"Initiates" with
  // no number is noise (this is exactly what produced the meaningless
  // "= $0" chip), so we render nothing and let the date anchor the row.
  if (cur == null) {
    const directional =
      a.price_target_action === "Raises" || a.price_target_action === "Lowers";
    if (meta && directional) {
      return (
        <span
          className={cn(
            "shrink-0 inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5",
            meta.chipBg,
            meta.tone,
          )}
          title={meta.label}
        >
          <meta.Icon className="h-3 w-3 shrink-0" />
          <span className="text-[10.5px] font-semibold leading-none">
            {meta.label}
          </span>
        </span>
      );
    }
    return null;
  }

  // We have a positive target. Frame it with the PT action when known,
  // else fall back to a neutral "Target" treatment.
  const M = meta ?? PT_META.Maintains;
  const hasDelta = prior != null && cur !== prior;
  const deltaPct = hasDelta && prior !== 0 ? ((cur - prior!) / prior!) * 100 : null;

  return (
    <span
      className={cn(
        "shrink-0 inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 tabular-nums",
        M.chipBg,
        M.tone,
      )}
      title={
        deltaPct != null
          ? `${M.label}: $${prior!.toFixed(0)} → $${cur.toFixed(0)} (${deltaPct >= 0 ? "+" : ""}${deltaPct.toFixed(1)}%)`
          : `${M.label}: $${cur.toFixed(0)}`
      }
    >
      <M.Icon className="h-3 w-3 shrink-0" />
      {hasDelta && (
        <span className="text-[10px] line-through opacity-60">
          ${prior!.toFixed(0)}
        </span>
      )}
      <span className="text-[12.5px] font-bold leading-none">
        ${cur.toFixed(0)}
      </span>
    </span>
  );
}

function fmtDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
}

function ActionRow({ a }: { a: AnalystAction }) {
  const meta = actionMeta(a.action);
  return (
    <li className="border-b border-border/40 last:border-b-0 min-w-0">
      <Link
        to={`/stocks/${encodeURIComponent(a.ticker)}`}
        className="flex items-center gap-2.5 px-3 py-2 hover:bg-accent/30 transition-colors min-w-0"
        title={a.name ?? a.ticker}
      >
        {/* Compact identity: logo + ticker only (company name → row
            tooltip). In this narrow 1fr dashboard column the repeated
            full name was clutter AND a second flex-1 block that starved
            the firm/grade of width. Fixing identity to a small width
            hands all the free space to the content block below. */}
        <StockLogo ticker={a.ticker} size="xs" />
        <span className="shrink-0 w-[40px] text-[13px] font-bold tabular-nums leading-none truncate">
          {a.ticker}
        </span>

        {/* Content — the sole flex-1 block, so it claims the full
            remaining width. Line 1: rating action + firm. Line 2:
            resulting grade (sentiment-coloured). */}
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 shrink-0",
                meta.chipBg,
                meta.tone,
              )}
              title={`Rating: ${meta.label}`}
            >
              <meta.Icon className="h-3 w-3 shrink-0" />
              <span className="text-[10.5px] font-semibold leading-none">
                {meta.label}
              </span>
            </span>
            <span
              className="text-[11.5px] text-muted-foreground truncate"
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
          </div>
          <div className="flex items-center gap-1 text-[11px] min-w-0 leading-none">
            <GradeDisplay from={a.from_grade} to={a.to_grade} />
          </div>
        </div>

        {/* Right cluster — price-target chip stacked over the date,
            right-aligned. Stacking reclaims the horizontal room the old
            inline date column took, giving the firm/grade more space. */}
        <div className="shrink-0 flex flex-col items-end gap-1">
          <PriceTargetChip a={a} />
          <span className="text-[10px] text-muted-foreground tabular-nums leading-none">
            {fmtDate(a.date)}
          </span>
        </div>
      </Link>
    </li>
  );
}

function RowSkeleton() {
  return (
    <li className="border-b border-border/40 last:border-b-0 px-3 py-1.5">
      <div className="flex items-center gap-2">
        <div className="h-7 w-7 rounded-full bg-muted/60 animate-pulse" />
        <div className="flex-1 space-y-1">
          <div className="h-3 w-20 rounded bg-muted/60 animate-pulse" />
          <div className="h-2.5 w-28 rounded bg-muted/40 animate-pulse" />
        </div>
        <div className="h-3.5 w-10 rounded bg-muted/40 animate-pulse" />
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
  const items = q.data ?? [];
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
                ultime uscite sul pool
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
              Nessuna valutazione analista recente.
              <br />
              <span className="text-muted-foreground/70">
                Compaiono qui upgrade/downgrade/initiation degli ultimi 90
                giorni man mano che i fondamentali vengono aggiornati.
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
