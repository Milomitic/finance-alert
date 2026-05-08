import { ArrowDown, ArrowUp } from "lucide-react";

import { useLiveAssets, type LiveAsset } from "@/hooks/useLiveAssets";
import { cn } from "@/lib/utils";

/* ─── MarketTickerTape ──────────────────────────────────────────────────── *
 *
 * Horizontal scrolling tape at the very top of the dashboard. Mimics
 * the financial-news / trading-floor "stock ticker" — a continuous
 * left-bound stream of price updates with red/green Δ% beats giving
 * the page a live heartbeat. Reuses the same `useLiveAssets` query
 * the LiveAssetsPanel uses, so there's no extra network cost.
 *
 * Animation: pure CSS keyframes (no JS rAF). The track contains the
 * row TWICE so when the first copy fully translates off-screen, the
 * duplicate is already in place — the seamless restart is invisible.
 * Pauses on hover so the user can read a flying ticker.
 *
 * Loading + error states fall back to a static placeholder strip
 * rather than disappearing — the dashboard's visual rhythm depends
 * on this band being there.
 */

function fmtPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString("it-IT", { maximumFractionDigits: 0 });
  if (abs >= 100) return v.toFixed(2);
  if (abs >= 1) return v.toFixed(2);
  return v.toFixed(4);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "0.00%";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function TickerItem({ asset }: { asset: LiveAsset }) {
  const q = asset.quote;
  const price = q?.price ?? null;
  const changePct = q?.change_pct ?? null;
  const isLive = q?.market_state === "OPEN" && q?.error == null;
  const tone =
    changePct == null
      ? "text-muted-foreground"
      : changePct > 0
      ? "text-emerald-600 dark:text-emerald-400"
      : changePct < 0
      ? "text-rose-600 dark:text-rose-400"
      : "text-muted-foreground";
  const ArrowIcon = changePct == null
    ? null
    : changePct > 0
    ? ArrowUp
    : changePct < 0
    ? ArrowDown
    : null;

  return (
    <span className="inline-flex items-center gap-1.5 px-3.5 py-0.5 border-r border-border/40 whitespace-nowrap shrink-0">
      {/* Pulsing green dot for OPEN markets — the "live" tell.
          When cash is closed but futures price is being shown, an
          amber "FUT" badge replaces the dot so the user understands
          the source. The two are mutually exclusive. */}
      {isLive ? (
        <span className="relative inline-flex h-1.5 w-1.5 shrink-0">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
        </span>
      ) : asset.using_futures ? (
        <span
          className="shrink-0 px-0.5 py-0 rounded text-[8px] font-bold uppercase tracking-wider bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200"
          title="Cash market chiuso · prezzo dal contratto futures"
        >
          FUT
        </span>
      ) : null}
      <span className="font-mono font-semibold text-[12px] tracking-tight">
        {asset.name}
      </span>
      <span className="font-mono text-[12px] tabular-nums text-foreground/85">
        {fmtPrice(price)}
      </span>
      <span
        className={cn(
          "inline-flex items-center gap-0.5 font-mono font-semibold text-[12px] tabular-nums",
          tone,
        )}
      >
        {ArrowIcon && <ArrowIcon className="h-3 w-3" />}
        {fmtPct(changePct)}
      </span>
    </span>
  );
}

export function MarketTickerTape() {
  const q = useLiveAssets();
  const assets = q.data?.assets ?? [];

  // Loading / empty: thin animated bar to keep the layout stable.
  // Empty isn't really expected (the dashboard auth gate already
  // guarantees the user has the data) but defensive.
  if (q.isLoading || assets.length === 0) {
    return (
      <div className="relative w-full overflow-hidden rounded-md border bg-card/40 h-7">
        <div className="absolute inset-0 animate-pulse bg-muted/30" />
      </div>
    );
  }

  // Duplicate the rail so the loop seam is invisible. `aria-hidden`
  // on the duplicate prevents the screen reader from reading the
  // same tickers twice.
  const rail = (
    <div className="ticker-track inline-flex items-center">
      {assets.map((a) => (
        <TickerItem key={a.symbol} asset={a} />
      ))}
    </div>
  );

  // CRITICAL: every ancestor of the scrolling track must be width-
  // constrained, or the inline-flex content (which is wider than the
  // viewport) propagates upward and turns the WHOLE PAGE into a
  // horizontally scrollable box. Both `w-full` (responds to the parent
  // width) and `max-w-full` (clamp at the parent's width even if a
  // grandchild tries to grow) are needed; one without the other still
  // leaks. `min-w-0` on the inner flex row is the standard escape
  // hatch for letting overflow:hidden actually clip.
  return (
    <div
      className={cn(
        "relative w-full max-w-full overflow-hidden rounded-md border bg-card",
        // Hover-pause: applied via CSS (group hover) so the user can
        // read a flying ticker without aborting the animation.
        "group",
      )}
    >
      <div className="flex items-center h-7 ticker-rail min-w-0">
        {rail}
        <div aria-hidden>{rail}</div>
      </div>
    </div>
  );
}
