import { Briefcase, Target, Users } from "lucide-react";

import type { AnalystRating, InsiderTransaction } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
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

function fmtShares(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toLocaleString();
}

function shortDate(s: string): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  if (!y || !m || !d) return s;
  return `${d}/${m}/${y.slice(2)}`;
}

function txnTone(text: string): string {
  const lc = text.toLowerCase();
  if (lc.includes("sale") || lc.includes("sell")) return "text-red-700 dark:text-red-300";
  if (lc.includes("buy") || lc.includes("purchase") || lc.includes("acquisition")) return "text-green-700 dark:text-green-300";
  return "text-muted-foreground";
}

function RatingBar({ r }: { r: AnalystRating }) {
  const total = r.strong_buy + r.buy + r.hold + r.sell + r.strong_sell;
  if (total === 0) return null;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className="text-xs">
      <div className="flex items-center justify-between text-muted-foreground mb-1">
        <span>{r.period === "0m" ? "Ora" : r.period}</span>
        <span className="tabular-nums">{total} analisti</span>
      </div>
      <div className="flex h-3 rounded-full overflow-hidden bg-muted">
        <div className="bg-emerald-600" style={{ width: pct(r.strong_buy) }} title={`Strong Buy: ${r.strong_buy}`} />
        <div className="bg-emerald-400" style={{ width: pct(r.buy) }} title={`Buy: ${r.buy}`} />
        <div className="bg-amber-400" style={{ width: pct(r.hold) }} title={`Hold: ${r.hold}`} />
        <div className="bg-rose-400" style={{ width: pct(r.sell) }} title={`Sell: ${r.sell}`} />
        <div className="bg-rose-600" style={{ width: pct(r.strong_sell) }} title={`Strong Sell: ${r.strong_sell}`} />
      </div>
      <div className="flex items-center justify-between mt-1 text-[10px] text-muted-foreground tabular-nums">
        <span className="text-emerald-700 dark:text-emerald-300">{r.strong_buy + r.buy} buy</span>
        <span className="text-amber-700 dark:text-amber-300">{r.hold} hold</span>
        <span className="text-rose-700 dark:text-rose-300">{r.sell + r.strong_sell} sell</span>
      </div>
    </div>
  );
}

function InsiderRow({ t }: { t: InsiderTransaction }) {
  return (
    <li className="flex items-start gap-2 py-1.5 border-t border-border/40 first:border-t-0">
      <Briefcase className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-xs font-semibold truncate">{t.insider || "—"}</span>
          <span className="text-[10px] text-muted-foreground truncate">{t.position || ""}</span>
          <span className="ml-auto text-[10px] text-muted-foreground tabular-nums shrink-0">{shortDate(t.date)}</span>
        </div>
        <div className={cn("text-[11px] truncate", txnTone(t.transaction))} title={t.transaction}>
          {t.transaction || "—"}
        </div>
        <div className="text-[10px] text-muted-foreground tabular-nums">
          {fmtShares(t.shares)} azioni
          {t.value != null && <> · {fmtBig(t.value)}</>}
        </div>
      </div>
    </li>
  );
}

export function InsidersAnalystCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Insiders & Analyst
          </div>
          <div className="h-32 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const f = q.data;
  if (!f) {
    return null;
  }

  const insiders = f.insiders ?? [];
  const ratings = f.analyst_ratings ?? [];
  const pt = f.price_target ?? null;
  const hasAny = insiders.length > 0 || ratings.length > 0 || (pt && pt.mean != null);

  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          Insiders & Analyst
        </div>

        {!hasAny && (
          <div className="text-xs text-muted-foreground">
            Nessun dato disponibile.
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Analyst recommendations + price target */}
          {(ratings.length > 0 || (pt && pt.mean != null)) && (
            <div className="space-y-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                <Target className="h-3.5 w-3.5" /> Analyst
              </div>
              {pt && pt.mean != null && (
                <div className="rounded-md bg-muted/40 p-2">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                    Price target (media analisti)
                  </div>
                  <div className="flex items-baseline gap-2 tabular-nums">
                    <span className="text-2xl font-bold">${pt.mean.toFixed(2)}</span>
                    {pt.current != null && (
                      <span className={cn(
                        "text-xs font-semibold",
                        pt.mean > pt.current ? "text-green-600" : "text-red-600",
                      )}>
                        {pt.mean > pt.current ? "+" : ""}{(((pt.mean - pt.current) / pt.current) * 100).toFixed(1)}% da current
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5 tabular-nums">
                    Range: ${pt.low?.toFixed(2) ?? "—"} – ${pt.high?.toFixed(2) ?? "—"} · mediana ${pt.median?.toFixed(2) ?? "—"}
                  </div>
                </div>
              )}
              {ratings.length > 0 && (
                <div className="space-y-2">
                  {ratings.slice(0, 3).map((r) => <RatingBar key={r.period} r={r} />)}
                </div>
              )}
            </div>
          )}

          {/* Insider transactions */}
          {insiders.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
                <Users className="h-3.5 w-3.5" /> Insider transactions (ultime {Math.min(insiders.length, 6)})
              </div>
              <ul className="max-h-60 overflow-y-auto pr-1">
                {insiders.slice(0, 6).map((t, i) => <InsiderRow key={`${t.insider}-${t.date}-${i}`} t={t} />)}
              </ul>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
