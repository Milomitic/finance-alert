import {
  Building2,
  CalendarDays,
  ExternalLink,
  Factory,
  Globe,
  MapPin,
  User,
  Users,
} from "lucide-react";
import { useMemo } from "react";

import type { Stock } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

/* ─── CompanyOverviewCard — identity + short business summary ────────────── */
/* Sits between the top StockHeader (price/identity hero) and the 4-card data
 * row (fundamentals/valuation/news/analyst). The card has two halves on
 * desktop:
 *
 *   ┌────────────────────────────────────────────────────────────┐
 *   │  PROFILO SOCIETÀ                                            │
 *   │                                                             │
 *   │  Long-form summary in 2-3 paragraphs   │  SEDE  Seattle...  │
 *   │  (split on segment / topic transitions │  CEO   🇺🇸 B. Diller│
 *   │  for readability)                      │  IND.  Hotels, …   │
 *   │  [Mostra tutto] when clamped           │  BORSA NASDAQ      │
 *   │                                        │  DIP.  16k         │
 *   │                                        │  WEB   expedia.com │
 *   └────────────────────────────────────────────────────────────┘
 *
 * V2 changes:
 *   - Dropped the inline "sector + headquarters" pills from the title row —
 *     redundant with the right column which already shows them in full.
 *   - Right column is now a single-column ordered definition list (was a
 *     2-col grid that split awkwardly when fields were missing). Order
 *     follows a "where → who → what → year → link" reading sequence.
 *   - Description splits into paragraphs on yfinance's typical segment-
 *     transition phrases ("The company also...", "The B2B segment...",
 *     "In addition...") so 6-sentence walls of text become 2-3 readable
 *     groups.
 *   - Font sizes bumped: description 13→14px, anagrafica values 13→14px.
 */

interface Props {
  ticker: string;
  /** Catalog stock row — used as the source of truth for fields the
   *  fundamentals payload doesn't have (exchange, currency) and to
   *  fall back when yfinance returns nothing for the profile fields. */
  stock: Stock;
}

export function CompanyOverviewCard({ ticker, stock }: Props) {
  const q = useStockFundamentals(ticker);
  const profile = q.data?.profile ?? null;

  // Identity fallbacks: prefer profile data, fall back to the catalog row
  // (which is always present, populated at ingestion).
  const country = profile?.country ?? stock.country ?? null;
  const city = profile?.city ?? null;
  const headquarters = [city, country].filter(Boolean).join(", ") || null;
  const description = profile?.long_business_summary ?? null;
  const website = profile?.website ?? null;
  const employees = profile?.employees ?? null;
  const ceo = profile?.ceo ?? null;
  const founded = profile?.founded ?? null;

  // Condense the (often 6+ sentence) yfinance summary to a tight blurb, then
  // pre-split into paragraphs once. Memoized so the regex work doesn't run on
  // every render (description doesn't change).
  const paragraphs = useMemo(
    () => (description ? splitIntoParagraphs(condenseSummary(description)) : []),
    [description],
  );

  // Hide the card entirely when yfinance gave us nothing AND the catalog
  // doesn't add value. The 5-card row above already shows ticker/sector.
  const hasAnything =
    !!description ||
    !!headquarters ||
    !!website ||
    !!employees ||
    !!ceo ||
    !!founded;

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <div className="h-24 animate-pulse rounded bg-muted/40" />
        </CardContent>
      </Card>
    );
  }
  if (!hasAnything) {
    return null;
  }

  return (
    <Card className="overflow-hidden lg:h-full lg:flex lg:flex-col">
      <CardContent className="p-4 sm:p-5 lg:flex-1 lg:min-h-0 lg:flex lg:flex-col">
        <SectionTitle icon={Building2} label="Profilo società" />

        {/* Two-column body. The card's max height is driven by the right
            column (anagrafica) — the description on the left is wrapped
            in an absolute-positioned inner div on lg+ so its content
            doesn't contribute to the grid row's intrinsic height. The
            grid sizes itself to the tallest non-absolute item (the
            anagrafica `dl`), and the description scrolls internally
            when its content exceeds the row height.
            On mobile (<lg) the columns stack and the description flows
            naturally — no absolute trick needed. */}
        <div className="mt-4 lg:flex-1 lg:min-h-0 grid grid-cols-1 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] gap-5 lg:gap-8">
          {/* ── Description ──────────────────────────────────────────── */}
          <div className="min-w-0 lg:relative">
            <div
              className={cn(
                "space-y-3 text-sm leading-relaxed text-foreground/85",
                // Absolute container on lg+ → content doesn't push the
                // grid-row height; instead it scrolls inside the row.
                "lg:absolute lg:inset-0 lg:overflow-y-auto lg:pr-2",
              )}
            >
              {description ? (
                paragraphs.map((p, i) => <p key={i}>{p}</p>)
              ) : (
                <p className="italic text-muted-foreground">
                  Descrizione non disponibile per questo titolo.
                </p>
              )}
            </div>
          </div>

          {/* ── Anagrafica list ──────────────────────────────────────── */}
          {/* Single-column definition list. Each row is `[icon · LABEL] :
              value` aligned on a fixed-width label column so the values
              line up vertically into a clean column.
              Order: where → who → what (industria) → market → people →
              founded → website. This reads like a company card on a
              business news site.
              No `self-start` here (was on the previous version): the dl
              should drive the grid row's height, so let it stretch
              naturally. */}
          <dl className="divide-y divide-border/40">
            <Row icon={MapPin} label="Sede" value={headquarters} />
            {ceo && <CeoRow ceo={ceo} country={stock.country ?? country} />}
            <Row icon={Factory} label="Industria" value={stock.industry} />
            <Row icon={Globe} label="Borsa" value={stock.exchange || null} />
            <Row
              icon={Users}
              label="Dipendenti"
              value={formatEmployees(employees)}
            />
            <Row
              icon={CalendarDays}
              label="Quotata dal"
              value={founded ? String(founded) : null}
            />
            {website && (
              <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] items-baseline gap-3 py-2">
                <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <ExternalLink className="h-3 w-3 shrink-0" />
                  Sito web
                </dt>
                <dd className="text-sm truncate">
                  <a
                    href={normalizeUrl(website)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                    title={website}
                  >
                    {prettyHostname(website)}
                  </a>
                </dd>
              </div>
            )}
          </dl>
        </div>
      </CardContent>
    </Card>
  );
}

/* ─── Anagrafica row — label left (fixed col), value right ──────────────── */

function Row({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | null;
}) {
  if (!value) return null;
  return (
    <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] items-baseline gap-3 py-2">
      <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        <Icon className="h-3 w-3 shrink-0" />
        {label}
      </dt>
      <dd
        className="text-sm font-medium text-foreground/90 truncate"
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}

/* ─── CEO row — same row layout but with a flag glyph next to the name ──── */

function CeoRow({
  ceo,
  country,
}: {
  ceo: string;
  country: string | null | undefined;
}) {
  const flag = getStockFlagCode(country);
  return (
    <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] items-baseline gap-3 py-2">
      <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        <User className="h-3 w-3 shrink-0" />
        CEO
      </dt>
      <dd
        className="flex items-center gap-2 text-sm font-medium text-foreground/90 min-w-0"
        title={ceo}
      >
        {flag && (
          <img
            src={`/flags/${flag}.svg`}
            alt={country ?? ""}
            width={18}
            height={12}
            // Tiny inline flag matching the StockHeader hero. Hidden when
            // we don't recognize the country.
            style={{ width: "18px", height: "12px", objectFit: "cover" }}
            className="rounded-[2px] shadow-sm shrink-0"
            aria-hidden
          />
        )}
        <span className="truncate">{ceo}</span>
      </dd>
    </div>
  );
}

/* ─── Description paragraph splitter ────────────────────────────────────── */

/* yfinance's `longBusinessSummary` is one continuous paragraph (no `\n\n`)
 * but follows predictable narrative patterns: an opening "what they do",
 * then segment-by-segment breakdowns, often closing with a corporate
 * footer ("incorporated in 1995"). We split on those transitions to recover
 * the implicit paragraph structure.
 *
 * Strategy:
 *   1. Split into sentences on `. ` (preserving abbreviations is fuzzy but
 *      OK — the worst case is a slightly awkward break).
 *   2. Walk sentences and start a new paragraph when we hit a transition
 *      phrase ("The company also...", "The B2B segment...", "In addition...",
 *      "The company was founded..."). These are yfinance idioms.
 *   3. Cap each paragraph at ~3 sentences so dense ones still break.
 *   4. If after this pass we'd still output a single 6-sentence wall, force
 *      a break at the midpoint.
 */
const TRANSITION_HINTS = [
  /^the company also\b/i,
  /^the company offers\b/i,
  /^the company operates\b/i,
  /^the company provides\b/i,
  /^the company was founded\b/i,
  /^the b2b segment\b/i,
  /^the b2c segment\b/i,
  /^the [a-z]+ segment\b/i,
  /^in addition\b/i,
  /^additionally\b/i,
  /^founded in\b/i,
  /^it (was|is) (incorporated|founded|headquartered)\b/i,
  /^as of\b/i,
];

/* Trim the long yfinance summary to a concise lead (first N sentences) so the
 * fixed-height card shows a readable blurb instead of a scroll-heavy wall.
 * Appends an ellipsis when content was dropped. */
const _SUMMARY_MAX_SENTENCES = 3;

function condenseSummary(text: string): string {
  const sentences = text
    .split(/(?<=[.?!])\s+(?=[A-Z])/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (sentences.length <= _SUMMARY_MAX_SENTENCES) return text.trim();
  return `${sentences.slice(0, _SUMMARY_MAX_SENTENCES).join(" ")} …`;
}

function splitIntoParagraphs(text: string): string[] {
  // Sentence split — naive but adequate. We keep the period attached.
  const sentences = text
    .split(/(?<=[.?!])\s+(?=[A-Z])/)
    .map((s) => s.trim())
    .filter(Boolean);

  if (sentences.length <= 2) return [text.trim()];

  const paragraphs: string[] = [];
  let current: string[] = [];
  const flush = () => {
    if (current.length) {
      paragraphs.push(current.join(" "));
      current = [];
    }
  };

  for (const s of sentences) {
    const isTransition =
      current.length > 0 && TRANSITION_HINTS.some((rx) => rx.test(s));
    if (isTransition || current.length >= 3) {
      flush();
    }
    current.push(s);
  }
  flush();

  // Force a break if everything ended up in one paragraph (no transitions
  // matched + sentence count under 3 — uncommon since the cap above catches
  // most of these).
  if (paragraphs.length === 1 && sentences.length >= 4) {
    const half = Math.ceil(sentences.length / 2);
    return [
      sentences.slice(0, half).join(" "),
      sentences.slice(half).join(" "),
    ];
  }
  return paragraphs;
}

/* ─── Format helpers ────────────────────────────────────────────────────── */

function formatEmployees(v: number | null): string | null {
  if (v == null || !Number.isFinite(v) || v <= 0) return null;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return v.toLocaleString();
}

function normalizeUrl(raw: string): string {
  if (/^https?:\/\//i.test(raw)) return raw;
  return `https://${raw}`;
}

function prettyHostname(raw: string): string {
  try {
    const u = new URL(normalizeUrl(raw));
    return u.hostname.replace(/^www\./, "");
  } catch {
    return raw;
  }
}
