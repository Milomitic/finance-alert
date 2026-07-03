import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

interface Props {
  ticker: string | null | undefined;
  size?: "xs" | "sm" | "md";
}

const SIZE_PX: Record<NonNullable<Props["size"]>, number> = {
  xs: 28,
  sm: 36,
  md: 48,
};

// 8-color rotation for the fallback pill. Hash the ticker so a given
// stock always lands in the same color across renders — visually
// stable in scrolling lists. NB: the literals must be present in code
// for Tailwind's purger to keep them.
const FALLBACK_TONES = [
  "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200",
  "bg-sky-100 text-sky-800 dark:bg-sky-900/60 dark:text-sky-200",
  "bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200",
  "bg-violet-100 text-violet-800 dark:bg-violet-900/60 dark:text-violet-200",
  "bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-200",
  "bg-teal-100 text-teal-800 dark:bg-teal-900/60 dark:text-teal-200",
  "bg-orange-100 text-orange-800 dark:bg-orange-900/60 dark:text-orange-200",
  "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/60 dark:text-indigo-200",
];

function hashTicker(t: string): number {
  let h = 0;
  for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/**
 * CDN chain for stock logos. Tries each in order, falling through on 404.
 * Probed coverage:
 *   - parqet (full ticker, e.g. ENI.MI, 0688.HK): best EU/HK/CN coverage
 *   - parqet (ticker base, e.g. STLA): catches stocks listed on multiple exchanges
 *     where parqet only has the US listing
 *   - FMP (bare ticker, e.g. AAPL): good US coverage
 */
function logoSources(ticker: string): string[] {
  const base = ticker.split(".")[0];
  const enc = encodeURIComponent(ticker);
  const encBase = encodeURIComponent(base);
  return [
    `https://assets.parqet.com/logos/symbol/${enc}`,
    base !== ticker ? `https://assets.parqet.com/logos/symbol/${encBase}` : null,
    `https://financialmodelingprep.com/image-stock/${encBase}.png`,
  ].filter((u): u is string => u !== null);
}

// Per-ticker logo resolution memo, mirrored to sessionStorage so it survives
// client-side navigation. Value = index of the CDN source that loaded, or -1 =
// every source 404'd. Without it, scrolling/sorting/paginating a table remounts
// each row and re-probes the same known-404 URLs — up to 3 external requests per
// row, over and over. `EXHAUSTED = -1`.
const RESOLVED_KEY = "stockLogoResolved";
const EXHAUSTED = -1;

function loadResolved(): Record<string, number> {
  try {
    const raw = sessionStorage.getItem(RESOLVED_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

const _resolved: Record<string, number> = loadResolved();

function rememberResolved(ticker: string, idx: number): void {
  if (_resolved[ticker] === idx) return;
  _resolved[ticker] = idx;
  try {
    sessionStorage.setItem(RESOLVED_KEY, JSON.stringify(_resolved));
  } catch {
    /* private mode / quota — the in-memory map still helps for this session */
  }
}

export function StockLogo({ ticker, size = "sm" }: Props) {
  // Seed from the memo so a remount skips straight to the known-good source
  // (or the monogram) instead of re-walking the CDN chain from index 0.
  const cached = ticker ? _resolved[ticker] : undefined;
  const [srcIdx, setSrcIdx] = useState(cached != null && cached >= 0 ? cached : 0);
  const [exhausted, setExhausted] = useState(cached === EXHAUSTED);

  // Reset state when ticker changes (e.g. row in a list re-renders with new ticker)
  useEffect(() => {
    const c = ticker ? _resolved[ticker] : undefined;
    setSrcIdx(c != null && c >= 0 ? c : 0);
    setExhausted(c === EXHAUSTED);
  }, [ticker]);

  if (!ticker) return null;
  const px = SIZE_PX[size];
  const sources = logoSources(ticker);

  if (exhausted) {
    rememberResolved(ticker, EXHAUSTED);
    // CDN didn't have the logo (common for HK/JP/KR/EU exotic listings).
    // Render a colored monogram pill instead of a generic Building2 icon
    // — keeps the row visually distinguishable and confirms to the user
    // that a logo *would* be there if available. The first 1-2 chars of
    // the ticker (sans the exchange suffix) drive the monogram.
    const base = ticker.split(".")[0].toUpperCase();
    const monogram = base.slice(0, base.length >= 3 ? 2 : 1);
    const tone = FALLBACK_TONES[hashTicker(base) % FALLBACK_TONES.length];
    return (
      <span
        className={cn(
          "inline-flex items-center justify-center rounded-full font-bold shrink-0 select-none",
          tone,
        )}
        style={{ width: px, height: px, fontSize: Math.round(px * 0.42) }}
        title={ticker}
        aria-label={`${ticker} logo unavailable`}
      >
        {monogram}
      </span>
    );
  }

  return (
    <img
      src={sources[srcIdx]}
      alt={`${ticker} logo`}
      width={px}
      height={px}
      onError={() => {
        if (srcIdx < sources.length - 1) {
          setSrcIdx(srcIdx + 1);
        } else {
          setExhausted(true);
        }
      }}
      className={cn("rounded-full bg-white border border-border/50 shrink-0")}
      style={{ width: px, height: px, objectFit: "contain" }}
      loading="lazy"
    />
  );
}
