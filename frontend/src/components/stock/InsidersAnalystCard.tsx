import { Briefcase } from "lucide-react";

import { stocks } from "@/api/stocks";
import type { InsiderTransaction } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { CardErrorOverlay } from "@/components/stock/CardErrorOverlay";
import { CardRefreshButton } from "@/components/stock/CardRefreshButton";
import { CardUpdatedAt } from "@/components/stock/CardUpdatedAt";
import { useCardRefresh } from "@/hooks/useCardRefresh";
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

/* Insider-transaction signal-vs-noise classification.
 *
 * Academic insider-trading literature (Lakonishok & Lee 2001;
 * Cohen-Malloy-Pomorski 2012) treats only a subset of Form 4 events
 * as informative:
 *
 *   STRONGEST signal  → open-market PURCHASES (insider puts cash in)
 *   WEAKER bearish    → open-market SALES / dispositions
 *                       (often noisy: 10b5-1 plans, taxes,
 *                        diversification — but in aggregate bearish)
 *   PURE NOISE        → option exercises, conversion of derivatives,
 *                       RSU vesting, awards, gifts, statements,
 *                       anything tagged "Non Open Market"
 *                       (these are mechanical compensation flows,
 *                        not directional bets)
 *
 * The list is filtered to drop the NOISE bucket entirely (see
 * `isInformativeTxn` below) so the user sees only directional rows.
 * `txnTone` then colours those rows green (bullish) or red (bearish).
 *
 * Why green buys still look rare: structural truth — executives
 * routinely sell RSUs to pay tax and diversify; very few EVER buy
 * more of their employer's stock with personal cash. So when you do
 * see a green row, it carries real signal weight. */
function txnTone(text: string): string {
  const lc = text.toLowerCase();
  // Belt-and-braces: even after the noise filter, never colour a
  // "non open market" event as directional — RSU edge cases can slip
  // through filters when phrasing is unusual.
  const isNonOpenMarket = lc.includes("non open market");

  // Bullish: open-market accumulation. Multiple yfinance phrasings.
  if (
    !isNonOpenMarket &&
    (lc.includes("purchase") || lc.includes("buy") || lc.includes("acquisition (open market)"))
  ) {
    return "text-green-700 dark:text-green-300";
  }
  // Bearish: open-market divestiture. Same row can be labelled
  // "Sale", "Sale (Multiple)", or "Disposition (Open Market)" /
  // "Disposition in the Public Market" depending on filer — match
  // all of them. The previous classifier left "Disposition" muted,
  // which under-reported bearish flow.
  if (
    !isNonOpenMarket &&
    (lc.includes("sale") || lc.includes("sell") || lc.includes("disposition"))
  ) {
    return "text-rose-700 dark:text-rose-300";
  }
  // Fallback for anything that somehow survives the filter — should
  // be rare. Stay muted so it never looks directional by accident.
  return "text-muted-foreground";
}

/* Filter: keep only directionally-informative transactions.
 *
 * Drops:
 *  - any "Exercise" / "Conversion of Derivative Security" — option
 *    exercises are mechanical vested-comp conversions, NOT a bet
 *  - anything "(Non Open Market)" — RSU vesting / tax withholding /
 *    deferred comp settlement: non-cash, non-directional
 *  - "Gift" / "Statement" / "Award" / "Grant" — non-cash compensation
 *    or disclosure events
 *
 * Keeps:
 *  - open-market Purchases (Buys) → bullish signal
 *  - open-market Sales / Dispositions → bearish signal
 *
 * The user's stock-detail card now reads as a directional ledger
 * instead of a mixed comp/trade feed.
 */
function isInformativeTxn(text: string | null | undefined): boolean {
  if (!text) return false;
  const lc = text.toLowerCase();

  // Hard noise filters (mechanical / non-cash / non-directional).
  if (lc.includes("non open market")) return false;
  if (lc.includes("exercise")) return false;            // option exercise
  if (lc.includes("conversion of derivative")) return false; // same idea, alt phrasing
  if (lc.includes("gift")) return false;                // gifted shares
  if (lc.includes("award") || lc.includes("grant")) return false; // RSU / stock award
  if (lc.includes("statement of ownership")) return false;
  // Ambiguous "Acquisition" alone without "Open Market" qualifier is
  // typically an RSU vest in yfinance feed → drop. Only the explicit
  // "Acquisition (Open Market)" variant survives (handled below as
  // bullish).
  if (lc.includes("acquisition") && !lc.includes("open market")) return false;

  // Allowlist on the informative side: be conservative — only let
  // through rows that match a known directional verb.
  return (
    lc.includes("purchase") ||
    lc.includes("buy") ||
    lc.includes("sale") ||
    lc.includes("sell") ||
    lc.includes("disposition") ||
    lc.includes("acquisition (open market)")
  );
}

/* Position-name abbreviation map.
 *
 * yfinance returns the verbose SEC filing position string ("Chief
 * Executive Officer", "Senior Vice President of Finance"). The
 * sidebar slot has limited horizontal space so the long forms
 * truncate to "..." losing the actual role. Map the common forms to
 * conventional abbreviations BEFORE the truncate kicks in.
 *
 * Order matters: longer / more specific patterns first so
 * "Senior Vice President" wins over "Vice President".
 */
const POSITION_ABBREVIATIONS: Array<[RegExp, string]> = [
  // Compound titles first
  [/\bPresident\s+(?:and|&|,)\s+Chief\s+Executive\s+Officer\b/i, "President & CEO"],
  [/\bChief\s+Executive\s+Officer\s+(?:and|&|,)\s+Director\b/i, "CEO & Director"],
  [/\bChairman\s+(?:and|&|,)\s+Chief\s+Executive\s+Officer\b/i, "Chairman & CEO"],
  // C-suite singletons
  [/\bChief\s+Executive\s+Officer\b/i, "CEO"],
  [/\bChief\s+Financial\s+Officer\b/i, "CFO"],
  [/\bChief\s+Operating\s+Officer\b/i, "COO"],
  [/\bChief\s+Technology\s+Officer\b/i, "CTO"],
  [/\bChief\s+Marketing\s+Officer\b/i, "CMO"],
  [/\bChief\s+Investment\s+Officer\b/i, "CIO"],
  [/\bChief\s+Information\s+Officer\b/i, "CIO"],
  [/\bChief\s+Strategy\s+Officer\b/i, "CSO"],
  [/\bChief\s+Legal\s+Officer\b/i, "CLO"],
  [/\bChief\s+Compliance\s+Officer\b/i, "CCO"],
  [/\bChief\s+Accounting\s+Officer\b/i, "CAO"],
  [/\bChief\s+People\s+Officer\b/i, "CPO"],
  [/\bChief\s+Product\s+Officer\b/i, "CPO"],
  [/\bChief\s+Business\s+Officer\b/i, "CBO"],
  [/\bChief\s+Revenue\s+Officer\b/i, "CRO"],
  [/\bChief\s+Risk\s+Officer\b/i, "CRO"],
  [/\bChief\s+Security\s+Officer\b/i, "CSO"],
  [/\bChief\s+Human\s+Resources\s+Officer\b/i, "CHRO"],
  // VP tiers (more specific first)
  [/\bSenior\s+Executive\s+Vice\s+President\b/i, "SEVP"],
  [/\bExecutive\s+Vice\s+President\b/i, "EVP"],
  [/\bSenior\s+Vice\s+President\b/i, "SVP"],
  [/\bVice\s+President\b/i, "VP"],
  // Other long titles
  [/\bGeneral\s+Counsel\b/i, "Gen. Counsel"],
  [/\bChairman\s+of\s+the\s+Board\b/i, "Chairman"],
  [/\b10%\s+Owner\b/i, "10% Owner"],
];

function abbreviatePosition(raw: string | null | undefined): string {
  if (!raw) return "";
  let out = raw;
  for (const [re, abbr] of POSITION_ABBREVIATIONS) {
    out = out.replace(re, abbr);
  }
  return out;
}

/**
 * Compact one-line row for the sidebar slot. Was a 3-line stacked
 * layout (insider+position+date / transaction / shares+value); the
 * sidebar real-estate is too narrow for that, so all the info fits
 * on a single row with the date right-aligned. Hover-title preserves
 * the full strings for the truncated cells.
 */
/* Shared column grid — header + every row use the SAME template so
 * cells align by construction. Tracks:
 *   insider (flex, truncates) · role · transaction · shares·$ · date
 * `minmax(0,1fr)` injects the implicit min-width:0 the name needs to
 * truncate instead of overflowing its track. */
const INSIDER_GRID =
  "grid grid-cols-[minmax(0,1fr)_4.25rem_5.5rem_5.25rem_3.5rem] items-baseline gap-2 min-w-[380px] md:min-w-0";

function InsiderHeader() {
  return (
    <li
      className={cn(
        INSIDER_GRID,
        "pb-1 text-[10px] uppercase tracking-wider text-muted-foreground/70 font-semibold",
      )}
    >
      <span className="truncate">Insider</span>
      <span className="truncate">Ruolo</span>
      <span className="truncate">Operazione</span>
      <span className="text-right">Quote · $</span>
      <span className="text-right">Data</span>
    </li>
  );
}

function InsiderRow({ t }: { t: InsiderTransaction }) {
  const sub =
    t.value != null
      ? `${fmtShares(t.shares)} · ${fmtBig(t.value)}`
      : `${fmtShares(t.shares)}`;
  return (
    <li
      className={cn(
        INSIDER_GRID,
        "py-1 border-t border-border/40 leading-tight",
      )}
    >
      {/* V3.5: insider name + position. The position (es. "CFO",
          "Director", "Chief Executive Officer") sits right after the
          name in muted/italic so the user identifies the role without
          mistaking it for the transaction text. */}
      <span
        className="text-[13.5px] font-semibold truncate min-w-0"
        title={t.insider || ""}
      >
        {t.insider || "—"}
      </span>
      <span
        // Hover-title preserves the full verbose role; the visible
        // label uses the canonical abbreviation (CEO / CFO / EVP / …)
        // so it doesn't truncate to "..." in the cramped slot.
        className="text-[12px] italic text-muted-foreground/80 truncate"
        title={t.position || ""}
      >
        {t.position ? abbreviatePosition(t.position) : "—"}
      </span>
      <span
        className={cn("text-[12px] truncate", txnTone(t.transaction))}
        title={t.transaction}
      >
        {t.transaction || "—"}
      </span>
      <span className="text-[12px] text-muted-foreground tabular-nums text-right">
        {sub}
      </span>
      <span className="text-[12px] text-muted-foreground tabular-nums text-right">
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
  const { refresh, isRefreshing, refreshError } = useCardRefresh({
    queryKey: ["stocks", ticker, "fundamentals"],
    mutationFn: () => stocks.fundamentals(ticker, { force: true }),
  });

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

  // Two-stage filter:
  //   1. monetary value > 0 — drops zero-value disclosures (statements,
  //      ownership filings, dollar-less amends).
  //   2. `isInformativeTxn` — drops mechanical / non-directional events
  //      (option exercises, RSU vesting, gifts, awards, non-open-market
  //      acquisitions). See the function's docstring for the rationale
  //      grounded in insider-trading literature.
  // Result: the list reads as a directional buy/sell ledger only, which
  // is what the user actually scans this card for.
  const insiders = (q.data?.insiders ?? [])
    .filter((t) => t.value != null && t.value > 0)
    .filter((t) => isInformativeTxn(t.transaction))
    .sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  const latest = insiders.slice(0, 10);

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle
          icon={Briefcase}
          label="Insider transactions"
          className="mb-2"
          right={
            <div className="flex items-center gap-2">
              {latest.length > 0 && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  ultime {latest.length}
                </span>
              )}
              <CardUpdatedAt updatedAt={q.data?.fetched_at} />
              <CardRefreshButton
                onClick={refresh}
                busy={isRefreshing}
                title="Aggiorna transazioni insider"
              />
            </div>
          }
        />
        {refreshError ? (
          <CardErrorOverlay
            error={refreshError}
            onRetry={refresh}
            retrying={isRefreshing}
          />
        ) : latest.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-3">
            Nessuna transazione insider direzionale recente
            <span className="block text-[10.5px] text-muted-foreground/70 mt-1">
              (acquisti/vendite open-market — vest, exercise e award sono filtrati)
            </span>
          </div>
        ) : (
          // The fixed columns are wider than a phone; scroll the list rather
          // than let the identity cell collapse to zero.
          <div className="overflow-x-auto md:overflow-visible">
          <ul>
            <InsiderHeader />
            {latest.map((t, i) => (
              <InsiderRow key={`${t.insider}-${t.date}-${i}`} t={t} />
            ))}
          </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
