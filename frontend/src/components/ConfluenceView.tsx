import { ChevronDown, ChevronRight, Swords, TrendingDown, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Confluence } from "@/api/alerts";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { TONE_BG, getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* ─── ConfluenceView ─────────────────────────────────────────────────────
 * Renders confluence clusters (active signals grouped by ticker+direction).
 * One expandable row per ticker: identity + prevailing direction + strength
 * bar + signal count + "Conteso" badge when bull/bear disagree. Expanding
 * lists the component signals as tone-colored chips (friendly label +
 * confidence), each linking to the stock page. The individual alerts are
 * untouched — this is a read-only confluence lens. */
function dirClass(dir: string): string {
  return dir === "bull" ? TONE_BG.bullish : dir === "bear" ? TONE_BG.bearish : TONE_BG.neutral;
}

export function ConfluenceView({ clusters }: { clusters: Confluence[] }) {
  const [open, setOpen] = useState<Set<string>>(new Set());

  if (clusters.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-muted-foreground">
        Nessuna confluenza attiva: servono almeno 2 segnali concordi sullo stesso titolo.
      </div>
    );
  }

  const toggle = (t: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(t)) n.delete(t);
      else n.add(t);
      return n;
    });

  return (
    <ul className="divide-y">
      {clusters.map((c) => {
        const isOpen = open.has(c.ticker);
        const DirIcon = c.direction === "bull" ? TrendingUp : TrendingDown;
        const pct = Math.round(c.strength);
        return (
          <li key={c.ticker}>
            <div
              className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-accent/30 min-w-0"
              onClick={() => toggle(c.ticker)}
            >
              {isOpen ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
              <StockLogo ticker={c.ticker} size="xs" />
              <Link
                to={`/stocks/${encodeURIComponent(c.ticker)}`}
                onClick={(e) => e.stopPropagation()}
                className="min-w-0 hover:underline"
              >
                <div className="font-bold leading-tight">{c.ticker}</div>
                {c.name && (
                  <div className="text-[11px] text-muted-foreground truncate max-w-[220px] leading-tight">
                    {c.name}
                  </div>
                )}
              </Link>
              <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold shrink-0", dirClass(c.direction))}>
                <DirIcon className="h-3 w-3" />
                {c.direction === "bull" ? "Rialzista" : "Ribassista"}
              </span>
              {c.contested && (
                <span
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold shrink-0 bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                  title={`Segnali contrastanti: forza bull ${c.bull_strength} vs bear ${c.bear_strength}`}
                >
                  <Swords className="h-3 w-3" />
                  Conteso
                </span>
              )}
              <span className="text-xs text-muted-foreground shrink-0">{c.n_signals} segnali</span>
              <div className="ml-auto flex items-center gap-2 shrink-0">
                <div className="h-2 w-24 rounded-full bg-muted overflow-hidden">
                  <div
                    className={cn("h-full rounded-full", c.direction === "bull" ? "bg-emerald-500" : "bg-rose-500")}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-sm font-semibold tabular-nums w-9 text-right">{pct}</span>
              </div>
            </div>
            {isOpen && (
              <div className="px-10 pb-3 flex flex-wrap gap-2">
                {c.components.map((comp) => {
                  const meta = getAlertKindMeta(comp.rule_kind);
                  const Icon = meta.icon;
                  const ctone = comp.tone === "bull" ? TONE_BG.bullish : TONE_BG.bearish;
                  return (
                    <Link
                      key={comp.alert_id}
                      to={`/stocks/${encodeURIComponent(c.ticker)}`}
                      className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold hover:underline", ctone)}
                      title={`${meta.label} · confidenza ${comp.confidence}%`}
                    >
                      <Icon className="h-2.5 w-2.5" />
                      {meta.label}
                      <span className="opacity-70">{Math.round(comp.confidence)}%</span>
                    </Link>
                  );
                })}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
