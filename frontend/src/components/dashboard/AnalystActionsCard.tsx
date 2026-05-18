import { useQuery } from "@tanstack/react-query";
import { Gavel, ArrowUpRight, ArrowDownRight, Sparkles, Minus, Newspaper } from "lucide-react";
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
  { label: string; tone: string; Icon: React.ComponentType<{ className?: string }> }
> = {
  up: { label: "Upgrade", tone: "text-emerald-600 dark:text-emerald-400", Icon: ArrowUpRight },
  down: { label: "Downgrade", tone: "text-rose-600 dark:text-rose-400", Icon: ArrowDownRight },
  init: { label: "Initiation", tone: "text-sky-600 dark:text-sky-400", Icon: Sparkles },
  reit: { label: "Reiterate", tone: "text-muted-foreground", Icon: Minus },
  main: { label: "Maintain", tone: "text-muted-foreground", Icon: Minus },
};

function actionMeta(action: string) {
  return ACTION_META[action] ?? ACTION_META.main;
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
            <meta.Icon className={cn("h-3.5 w-3.5 shrink-0", meta.tone)} />
            <span className={cn("font-semibold shrink-0", meta.tone)}>
              {meta.label}
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
        {a.current_price_target != null && (
          <span
            className="shrink-0 w-[64px] text-right text-[12.5px] font-bold tabular-nums"
            title="Target price assegnato dall'analista"
          >
            ${a.current_price_target.toFixed(0)}
          </span>
        )}
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
