import { useQuery } from "@tanstack/react-query";
import {
  Gavel,
  ArrowUpRight,
  ArrowDownRight,
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
import { StockIdentity } from "@/components/dashboard/StockIdentity";
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
  const cur = a.current_price_target;
  const prior = a.prior_price_target;
  if (!meta && cur == null) return null;

  // Even without a meta entry (older API rows), a bare current target
  // still deserves the "Target" framing — gives it semantic context
  // instead of a stray dollar amount.
  const M = meta ?? PT_META.Maintains;
  const hasDelta = cur != null && prior != null && cur !== prior;
  const deltaPct =
    hasDelta && prior !== 0 ? ((cur! - prior!) / prior!) * 100 : null;

  return (
    <span
      className={cn(
        "shrink-0 inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 tabular-nums",
        M.chipBg,
        M.tone,
      )}
      title={
        deltaPct != null
          ? `${M.label}: $${prior!.toFixed(0)} → $${cur!.toFixed(0)} (${deltaPct >= 0 ? "+" : ""}${deltaPct.toFixed(1)}%)`
          : meta
          ? `${M.label}${cur != null ? `: $${cur.toFixed(0)}` : ""}`
          : "Target price"
      }
    >
      <M.Icon className="h-3 w-3 shrink-0" />
      {cur != null ? (
        <>
          {hasDelta && (
            <span className="text-[10.5px] line-through opacity-60">
              ${prior!.toFixed(0)}
            </span>
          )}
          <span className="text-[12.5px] font-bold leading-none">
            ${cur.toFixed(0)}
          </span>
        </>
      ) : (
        <span className="text-[11px] font-semibold">{M.label}</span>
      )}
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
  const gradeChange =
    a.from_grade && a.to_grade && a.from_grade !== a.to_grade
      ? `${a.from_grade} → ${a.to_grade}`
      : a.to_grade || a.from_grade || "—";
  return (
    <li className="border-b border-border/40 last:border-b-0 min-w-0">
      <Link
        to={`/stocks/${encodeURIComponent(a.ticker)}`}
        className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors min-w-0"
      >
        <StockIdentity ticker={a.ticker} name={a.name} />
        <div className="min-w-0 flex-1 hidden sm:block">
          <div className="flex items-center gap-1 text-[12px] truncate">
            {/* Rating chip — mirrors the price-target chip shape on the
                right so the row reads as a balanced "rating action /
                target action" pair. */}
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 shrink-0",
                meta.chipBg,
                meta.tone,
              )}
              title={`Rating: ${meta.label}`}
            >
              <meta.Icon className="h-3 w-3 shrink-0" />
              <span className="text-[11px] font-semibold leading-none">
                {meta.label}
              </span>
            </span>
            <span className="text-muted-foreground truncate" title={a.firm}>
              · {a.firm || "—"}
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
          <div className="text-[11px] text-muted-foreground truncate" title={gradeChange}>
            {gradeChange}
          </div>
        </div>
        <PriceTargetChip a={a} />
        <span className="shrink-0 w-[52px] text-right text-[11px] text-muted-foreground tabular-nums">
          {fmtDate(a.date)}
        </span>
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
