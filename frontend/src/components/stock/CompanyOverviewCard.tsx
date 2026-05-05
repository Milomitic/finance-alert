import {
  Building2,
  CalendarDays,
  ExternalLink,
  Globe,
  MapPin,
  User,
  Users,
} from "lucide-react";
import { useState } from "react";

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
 *   ┌──────────────────────────────────────────────────────────┐
 *   │  [Description block]                  │  [Anagrafica]    │
 *   │  Long-form company summary — clamped  │  Sede   Milano   │
 *   │  to 4 lines + "Mostra tutto" button   │  CEO    G. Doe   │
 *   │  on overflow.                         │  Dipend. 15.2k    │
 *   │                                       │  Sito  example.it │
 *   └──────────────────────────────────────────────────────────┘
 *
 * On narrow viewports the columns stack vertically. The whole card hides
 * itself when neither a description nor any anagrafica field is available
 * — preserving vertical space for stocks where yfinance's info dict is
 * sparse (small caps, foreign listings).
 *
 * Why a separate card from FundamentalsCard:
 *   - Different shape of data: this is identity / textual; Fundamentals is
 *     numerical time series.
 *   - Different scroll behavior: the description should EXPAND on demand
 *     (clamp + click-to-expand), not be tucked into a horizontally-scrollable
 *     stat strip.
 *   - Persistent context: the user reading the chart benefits from "what
 *     does this company actually do" being visible without clicking
 *     anything.
 */

interface Props {
  ticker: string;
  /** Catalog stock row — used as the source of truth for fields the
   *  fundamentals payload doesn't have (exchange, currency) and to
   *  fall back when yfinance returns nothing for the profile fields. */
  stock: Stock;
}

const CLAMP_CLASS_4_LINES = "line-clamp-4";

export function CompanyOverviewCard({ ticker, stock }: Props) {
  const q = useStockFundamentals(ticker);
  const profile = q.data?.profile ?? null;
  const [expanded, setExpanded] = useState(false);

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
    <Card className="overflow-hidden">
      <CardContent className="p-4 sm:p-5">
        {/* Quick anagrafica chips on the right edge of the title row. Show
            the most-readable two facts inline at the top so even when the
            user doesn't read the description, they see "what country" and
            "how big" at a glance. */}
        <SectionTitle
          icon={Building2}
          label="Profilo società"
          right={
            <div className="flex items-center gap-1.5 flex-wrap justify-end">
              {stock.sector && (
                <Pill icon={Building2} label={stock.sector} />
              )}
              {headquarters && <Pill icon={MapPin} label={headquarters} />}
            </div>
          }
        />

        {/* Two-column body: description (left, wide) + anagrafica grid (right). */}
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-4 lg:gap-6">
          {/* ── Description ──────────────────────────────────────────── */}
          <div className="min-w-0">
            {description ? (
              <>
                <p
                  className={cn(
                    "text-[13px] leading-relaxed text-foreground/85",
                    !expanded && CLAMP_CLASS_4_LINES,
                  )}
                >
                  {description}
                </p>
                {/* Show toggle only when the description is long enough to
                    be clamped. We approximate with a character-count
                    threshold — exact line counts are fiddly without
                    measuring the DOM, and the cost of an unnecessary
                    "Mostra tutto" on a borderline-short string is tiny. */}
                {description.length > 280 && (
                  <button
                    type="button"
                    onClick={() => setExpanded((e) => !e)}
                    className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-primary hover:underline"
                  >
                    {expanded ? "Comprimi" : "Mostra tutto"}
                  </button>
                )}
              </>
            ) : (
              <p className="text-[13px] italic text-muted-foreground">
                Descrizione non disponibile per questo titolo.
              </p>
            )}
          </div>

          {/* ── Anagrafica grid ──────────────────────────────────────── */}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 self-start">
            <Field
              icon={MapPin}
              label="Sede"
              value={headquarters}
              span={2}
            />
            {/* CEO row: show the named officer + a small country flag.
                yfinance doesn't expose CEO nationality directly, so we use
                the company HQ country (catalog ISO code wins, profile full
                name is the fallback) as a sensible proxy — most CEOs are
                citizens of the company's primary domicile. */}
            {ceo && (
              <CeoField
                ceo={ceo}
                country={stock.country ?? country}
              />
            )}
            <Field
              icon={Users}
              label="Dipendenti"
              value={formatEmployees(employees)}
            />
            <Field
              icon={CalendarDays}
              label="Quotata dal"
              value={founded ? String(founded) : null}
            />
            <Field
              icon={Globe}
              label="Borsa"
              value={stock.exchange || null}
            />
            <Field
              icon={Building2}
              label="Industria"
              value={stock.industry}
            />
            {website && (
              <div className="col-span-2">
                <dt className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <ExternalLink className="h-3 w-3" />
                  Sito web
                </dt>
                <dd className="mt-0.5 truncate text-[13px]">
                  <a
                    href={normalizeUrl(website)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline tabular-nums"
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

/* ─── Pill (compact label with icon) ────────────────────────────────────── */

function Pill({
  icon: Icon,
  label,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-1.5 py-0.5 text-[10.5px] font-semibold tracking-wide text-muted-foreground">
      <Icon className="h-2.5 w-2.5" />
      <span className="truncate max-w-[14ch]">{label}</span>
    </span>
  );
}

/* ─── Anagrafica field — dt/dd row with icon ────────────────────────────── */

function Field({
  icon: Icon,
  label,
  value,
  span = 1,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | null;
  span?: 1 | 2;
}) {
  if (!value) return null;
  return (
    <div className={cn(span === 2 ? "col-span-2" : "col-span-1", "min-w-0")}>
      <dt className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <Icon className="h-3 w-3" />
        {label}
      </dt>
      <dd
        className="mt-0.5 truncate text-[13px] font-medium text-foreground/85 tabular-nums"
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}

/* ─── CEO field with nationality flag ───────────────────────────────────── */

function CeoField({
  ceo,
  country,
}: {
  ceo: string;
  country: string | null | undefined;
}) {
  const flag = getStockFlagCode(country);
  return (
    <div className="col-span-2 min-w-0">
      <dt className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <User className="h-3 w-3" />
        CEO
      </dt>
      <dd
        className="mt-0.5 flex items-center gap-1.5 text-[13px] font-medium text-foreground/85"
        title={ceo}
      >
        {flag && (
          <img
            src={`/flags/${flag}.svg`}
            alt={country ?? ""}
            width={18}
            height={12}
            // Tiny inline flag — same library used in the StockHeader hero.
            // The caller already gracefully degrades when the country isn't
            // known (no flag rendered).
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
