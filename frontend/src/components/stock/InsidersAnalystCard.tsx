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

/* Insider-transaction tone classifier.
 *
 * yfinance's `Transaction` text is unstructured and a few patterns
 * deserve different colors:
 *
 *  - "Sale" / "Sell"            → RED (open-market divestiture)
 *  - "Purchase" / "Buy"         → GREEN (open-market accumulation,
 *                                 the strongest signal in the dataset)
 *  - "Acquisition" / "Award" / "Conversion" / "Gift" → MUTED
 *    These represent NON-cash events: RSU vesting, option conversion,
 *    stock awards, gifts. Tagging them green misleads the reader into
 *    thinking the insider voluntarily put money in — they didn't.
 *
 * The user reasonably asked "why are green buys so rare?" — the answer
 * is structural: insider open-market PURCHASES are genuinely rare
 * compared to RSU-driven sales (every executive sells vested grants
 * to diversify and pay taxes; very few executives buy more of their
 * employer's stock with cash). When you DO see green, it's a
 * meaningful signal — the insider chose to put their own capital in.
 *
 * "Non Open Market" disclaimer in the text → automatically not green
 * (RSU vesting often shows up as "Acquisition (Non Open Market)").
 */
function txnTone(text: string): string {
  const lc = text.toLowerCase();
  // Hard-block: anything labeled "non open market" is by definition
  // a non-cash event, regardless of which verb the row uses.
  const isNonOpenMarket = lc.includes("non open market");

  if (lc.includes("sale") || lc.includes("sell")) {
    return "text-red-700 dark:text-red-300";
  }
  if (!isNonOpenMarket && (lc.includes("purchase") || lc.includes("buy"))) {
    return "text-green-700 dark:text-green-300";
  }
  // Acquisitions, gifts, conversions, awards, statements, dispositions,
  // and any other "neutral" disclosures stay muted — they don't reflect
  // the insider's directional conviction.
  return "text-muted-foreground";
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
function InsiderRow({ t }: { t: InsiderTransaction }) {
  const sub =
    t.value != null
      ? `${fmtShares(t.shares)} · ${fmtBig(t.value)}`
      : `${fmtShares(t.shares)}`;
  return (
    <li className="flex items-baseline gap-2 py-1 border-t border-border/40 first:border-t-0 leading-tight">
      {/* V3.5: insider name + position. The position (es. "CFO",
          "Director", "Chief Executive Officer") sits right after the
          name in muted/italic so the user identifies the role without
          mistaking it for the transaction text. */}
      <span
        className="text-[13.5px] font-semibold truncate"
        title={t.insider || ""}
      >
        {t.insider || "—"}
      </span>
      {t.position && (
        <span
          // Hover-title preserves the full verbose role for users who
          // need it; the visible label uses the canonical abbreviation
          // (CEO / CFO / EVP / etc.) so it doesn't truncate to "..."
          // in the cramped sidebar slot.
          className="text-[12px] italic text-muted-foreground/80 truncate max-w-[110px]"
          title={t.position}
        >
          {abbreviatePosition(t.position)}
        </span>
      )}
      <span
        className={cn(
          "text-[12px] truncate shrink-0 max-w-[90px]",
          txnTone(t.transaction),
        )}
        title={t.transaction}
      >
        {t.transaction || "—"}
      </span>
      <span className="text-[12px] text-muted-foreground tabular-nums shrink-0">
        {sub}
      </span>
      <span className="ml-auto text-[12px] text-muted-foreground tabular-nums shrink-0">
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
