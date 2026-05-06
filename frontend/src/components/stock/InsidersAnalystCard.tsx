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

/**
 * Compact one-line row for the sidebar slot. Was a 3-line stacked
 * layout (insider+position+date / transaction / shares+value); the
 * sidebar real-estate is too narrow for that, so all the info fits
 * on a single row with the date right-aligned. Hover-title preserves
 * the full strings for the truncated cells.
 */
function InsiderRow({ t }: { t: InsiderTransaction }) {
  const sub =
    t.value != null
      ? `${fmtShares(t.shares)} · ${fmtBig(t.value)}`
      : `${fmtShares(t.shares)}`;
  return (
    <li className="flex items-baseline gap-2 py-1 border-t border-border/40 first:border-t-0 leading-tight">
      <span
        className="text-[12.5px] font-semibold truncate"
        title={t.insider || ""}
      >
        {t.insider || "—"}
      </span>
      <span
        className={cn(
          "text-[11px] truncate shrink-0 max-w-[90px]",
          txnTone(t.transaction),
        )}
        title={t.transaction}
      >
        {t.transaction || "—"}
      </span>
      <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
        {sub}
      </span>
      <span className="ml-auto text-[11px] text-muted-foreground tabular-nums shrink-0">
        {shortDate(t.date)}
      </span>
    </li>
  );
}

/**
 * Insider transactions card. Lives in the stock-detail sidebar (slot
 * formerly held by PriceAlertsCard). Compact single-line rows so the
 * card fits 8-10 transactions in the same vertical real estate the
 * old StockScoreCard footer area had.
 */
export function InsidersAnalystCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-3">
          <SectionTitle
            icon={Briefcase}
            label="Insider transactions"
            className="mb-2"
          />
          <div className="h-24 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const insiders = q.data?.insiders ?? [];

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle
          icon={Briefcase}
          label="Insider transactions"
          className="mb-2"
          right={
            insiders.length > 0 ? (
              <span className="text-xs text-muted-foreground tabular-nums">
                ultime {Math.min(insiders.length, 10)}
              </span>
            ) : undefined
          }
        />
        {insiders.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-3">
            Nessuna transazione insider registrata.
          </div>
        ) : (
          <ul>
            {insiders.slice(0, 10).map((t, i) => (
              <InsiderRow key={`${t.insider}-${t.date}-${i}`} t={t} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
