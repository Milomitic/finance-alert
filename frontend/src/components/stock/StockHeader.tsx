import { ListChecks, Radio } from "lucide-react";
import { Link } from "react-router-dom";

import type { EffectiveRule, Stock, StockKpis } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { ACRONYM_HELP } from "@/lib/acronymHelp";
import { useLiveQuote } from "@/hooks/useLiveQuote";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

interface Props {
  stock: Stock;
  kpis: StockKpis;
  /** When the stock is in one or more watchlists with a Tier-2 rule override,
   *  surface those watchlist names inline so the user knows the alert behavior
   *  for this ticker isn't pure-global. */
  effectiveRules?: EffectiveRule[];
}

function fmtMc(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

function fmtVolume(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toLocaleString();
}

export function StockHeader({ stock, kpis, effectiveRules = [] }: Props) {
  // Distinct watchlist names that override this stock's rules (Tier 2).
  const tier2 = Array.from(
    new Set(
      effectiveRules
        .filter((r) => r.source === "tier2" && !!r.watchlist_name)
        .map((r) => r.watchlist_name as string),
    ),
  );
  const flag = getStockFlagCode(stock.country);

  // Live quote — polls every 15s. Falls back to the kpis snapshot (last
  // close from the daily scan) when the live fetch hasn't returned yet,
  // when it errored (e.g. yfinance breaker open), or when the live price
  // isn't available (e.g. delisted ticker).
  const live = useLiveQuote(stock.ticker);
  const liveOk = live.data && live.data.price != null && live.data.error == null;
  const isMarketOpen = liveOk && live.data!.market_state === "OPEN";
  // The yfinance fast_info endpoint always returns yesterday's close when the
  // market is shut, so we still want the live data when available — but the
  // UI labels it differently (LIVE only when actually trading).
  const displayPrice = liveOk ? live.data!.price! : kpis.last_close;
  const change = liveOk ? (live.data!.change_pct ?? null) : kpis.change_pct;
  const changeAbs = liveOk ? live.data!.change_abs : null;
  const liveAge = liveOk ? Date.now() / 1000 - live.data!.fetched_at : null;

  // Tone: subtle tinted card + accent stripe on left, no aggressive gradient
  const tone =
    change == null
      ? { bg: "bg-card", stripe: "bg-slate-300 dark:bg-slate-600", text: "text-muted-foreground", arrow: "" }
      : change > 0
        ? { bg: "bg-emerald-50/50 dark:bg-emerald-950/15", stripe: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-300", arrow: "▲" }
        : change < 0
          ? { bg: "bg-rose-50/50 dark:bg-rose-950/15", stripe: "bg-rose-500", text: "text-rose-700 dark:text-rose-300", arrow: "▼" }
          : { bg: "bg-card", stripe: "bg-slate-300 dark:bg-slate-600", text: "text-muted-foreground", arrow: "" };

  return (
    <Card className={cn("relative overflow-hidden border-border/60", tone.bg)}>
      <div className={cn("absolute left-0 top-0 bottom-0 w-1.5", tone.stripe)} aria-hidden />
      <CardContent className="p-6 pl-7">
        <div className="flex items-start gap-6 flex-wrap">
          {/* Logo + flag */}
          <div className="flex flex-col items-center gap-2 shrink-0">
            <div className="rounded-2xl bg-white dark:bg-zinc-900 border border-border/60 p-2 shadow-sm">
              <StockLogo ticker={stock.ticker} size="md" />
            </div>
            {flag && (
              <img
                src={`/flags/${flag}.svg`}
                alt={stock.country ?? ""}
                width={36} height={24}
                style={{ width: "36px", height: "24px", objectFit: "cover" }}
                className="rounded shadow-sm"
              />
            )}
          </div>

          {/* Identity */}
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="text-4xl sm:text-5xl font-bold tracking-tight tabular-nums leading-none">
                {stock.ticker}
              </span>
              <span className="text-xl text-foreground/80 font-medium truncate" title={stock.name}>
                {stock.name}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              <span className="inline-flex items-center rounded-md bg-muted/70 dark:bg-muted/40 px-2.5 py-1 text-sm font-medium">
                {stock.exchange}
              </span>
              {stock.sector && (
                <span className="inline-flex items-center rounded-md bg-muted/70 dark:bg-muted/40 px-2.5 py-1 text-sm font-medium">
                  {stock.sector}
                </span>
              )}
              {stock.industry && (
                <span className="text-sm text-muted-foreground truncate max-w-[420px]">
                  {stock.industry}
                </span>
              )}
            </div>
          </div>

          {/* Price block */}
          <div className="text-right tabular-nums shrink-0 flex flex-col gap-1 items-end">
            {displayPrice != null && (
              <>
                <div className="flex items-center gap-1.5 text-sm uppercase tracking-wide">
                  {isMarketOpen ? (
                    <span
                      className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-300 font-semibold"
                      title={
                        liveAge != null
                          ? `Mercato aperto · prezzo aggiornato ${Math.round(liveAge)}s fa (cache 10s + polling 15s)`
                          : "Prezzo live"
                      }
                    >
                      <span className="relative inline-flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                      </span>
                      <Radio className="h-3 w-3" />
                      LIVE
                    </span>
                  ) : (
                    <span
                      className="inline-flex items-center gap-1 text-muted-foreground font-semibold"
                      title={
                        liveOk
                          ? "Mercato chiuso — il prezzo mostrato è l'ultima chiusura"
                          : "Live quote non disponibile — mostra l'ultima chiusura giornaliera"
                      }
                    >
                      Ultima chiusura
                    </span>
                  )}
                </div>
                <div className="text-5xl font-bold leading-none">${displayPrice.toFixed(2)}</div>
              </>
            )}
            {change != null && (
              <div className={cn("inline-flex items-baseline gap-1.5 text-2xl font-bold mt-1", tone.text)}>
                <span className="text-lg">{tone.arrow}</span>
                {changeAbs != null && (
                  <span className="text-base font-semibold opacity-80">
                    {changeAbs >= 0 ? "+" : ""}{changeAbs.toFixed(2)}
                  </span>
                )}
                <span>{change >= 0 ? "+" : ""}{change.toFixed(2)}%</span>
              </div>
            )}
          </div>
        </div>

        {/* Tier-2 watchlist banner: shown only when at least one watchlist
            applies a custom rule override to this stock. Tells the user the
            alert behavior here is not pure-global. */}
        {tier2.length > 0 && (
          <div className="mt-4 px-3 py-2 rounded-md border border-amber-300/60 dark:border-amber-700/40 bg-amber-50/70 dark:bg-amber-950/20 flex items-center gap-2 flex-wrap">
            <ListChecks className="h-4 w-4 text-amber-700 dark:text-amber-300 shrink-0" />
            <span className="text-sm text-amber-900 dark:text-amber-100">
              <strong>Regole custom attive</strong> dalla watchlist{tier2.length > 1 ? "s" : ""}:
            </span>
            <span className="flex items-center gap-1.5 flex-wrap">
              {tier2.map((wl) => (
                <Link
                  key={wl}
                  to="/watchlists"
                  className="inline-flex items-center rounded-md px-2 py-0.5 text-sm font-semibold bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-100 hover:bg-amber-200 dark:hover:bg-amber-900/60 transition-colors"
                  title={`Apri /watchlists per modificare gli override di "${wl}"`}
                >
                  {wl}
                </Link>
              ))}
            </span>
          </div>
        )}

        {/* KPI strip */}
        <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
          {kpis.high_52w != null && kpis.low_52w != null && (
            <KpiTile
              label="52w range"
              tooltip="Range a 52 settimane"
              value={
                <span className="tabular-nums">
                  ${kpis.low_52w.toFixed(2)} <span className="text-muted-foreground mx-1">→</span> ${kpis.high_52w.toFixed(2)}
                </span>
              }
              valueClass="text-base font-semibold"
            />
          )}
          <KpiTile
            label="Mkt cap"
            tooltip={ACRONYM_HELP.UNIVERSE}
            value={fmtMc(stock.market_cap)}
            valueClass="text-xl font-bold"
          />
          {kpis.vol_today != null && (
            <KpiTile
              label="Volume oggi"
              tooltip="Volume scambiato oggi"
              value={fmtVolume(kpis.vol_today)}
              valueClass="text-xl font-bold"
            />
          )}
          {kpis.vol_ratio != null && (
            <KpiTile
              label="Vol × avg20"
              tooltip={ACRONYM_HELP.VOL_SPIKE}
              value={`${kpis.vol_ratio.toFixed(2)}×`}
              valueClass={cn(
                "text-xl font-bold",
                kpis.vol_ratio > 2 ? "text-amber-700 dark:text-amber-300" : "",
              )}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function KpiTile({
  label, tooltip, value, valueClass,
}: {
  label: string;
  tooltip?: string;
  value: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div
      className="rounded-lg bg-card/80 dark:bg-black/20 border border-border/50 p-3 text-center"
      title={tooltip}
    >
      <div className="text-[13px] uppercase tracking-wider text-muted-foreground font-medium">{label}</div>
      <div className={cn("mt-1 tabular-nums", valueClass)}>{value}</div>
    </div>
  );
}
