import { Briefcase } from "lucide-react";

import type { InsiderTransaction } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
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

function InsiderRow({ t }: { t: InsiderTransaction }) {
  return (
    <li className="flex items-start gap-2 py-1.5 border-t border-border/40 first:border-t-0">
      <Briefcase className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-sm font-semibold truncate">{t.insider || "—"}</span>
          <span className="text-sm text-muted-foreground truncate">{t.position || ""}</span>
          <span className="ml-auto text-sm text-muted-foreground tabular-nums shrink-0">{shortDate(t.date)}</span>
        </div>
        <div className={cn("text-[13px] truncate", txnTone(t.transaction))} title={t.transaction}>
          {t.transaction || "—"}
        </div>
        <div className="text-sm text-muted-foreground tabular-nums">
          {fmtShares(t.shares)} azioni
          {t.value != null && <> · {fmtBig(t.value)}</>}
        </div>
      </div>
    </li>
  );
}

/**
 * Insider transactions card. The previous "Analyst" half (price target +
 * recommendation bars) is now its own AnalystTargetCard placed next to the
 * StockHeader at the top of the page.
 */
export function InsidersAnalystCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <SectionTitle
            icon={Briefcase}
            label="Insider transactions"
            className="mb-2"
          />
          <div className="h-32 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const insiders = q.data?.insiders ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Briefcase}
          label="Insider transactions"
          className="mb-2"
          right={
            insiders.length > 0 ? (
              <span className="text-xs text-muted-foreground tabular-nums">
                ultime {Math.min(insiders.length, 12)}
              </span>
            ) : undefined
          }
        />
        {insiders.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-4">
            Nessuna transazione insider registrata.
          </div>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
            {insiders.slice(0, 12).map((t, i) => (
              <InsiderRow key={`${t.insider}-${t.date}-${i}`} t={t} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
