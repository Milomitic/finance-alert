import { ArrowDown, ArrowUp } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import { NoValue, hasValue } from "@/components/ui/no-value";
import { useIsPhone } from "@/hooks/useMediaQuery";
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
 * Motion: the rail is a real horizontal SCROLLER and the auto-advance
 * writes its `scrollLeft`. It used to be a CSS `transform: translateX`
 * inside `overflow: hidden`, which is cheaper — but that box has nothing
 * for a finger to drag, and adding one does not work: transform and
 * native scroll are two independent offsets that add up, so a drag
 * pulls the loop seam into view and letting go strands the tape where
 * the keyframes never accounted for. One axis, driven by both, composes;
 * two axes have to be arbitrated. The track still contains the row TWICE,
 * so wrapping at half the width lands on pixel-identical content.
 *
 * Pauses on hover and for a beat after any touch or wheel, so reading or
 * dragging is never fought. Honours prefers-reduced-motion by not
 * advancing — while staying scrollable by hand, which the CSS version
 * was not.
 *
 * Loading + error states fall back to a static placeholder strip
 * rather than disappearing — the dashboard's visual rhythm depends
 * on this band being there.
 */

/* A frame longer than this means the tab was backgrounded or the main thread
 * stalled — rAF simply stops delivering. Uncapped, the first frame back
 * carries the whole gap and teleports the tape. */
const MAX_FRAME_S = 0.5;

/** Next scroll offset, wrapping at `half` (one rail width). Pure, so the
 *  wrap and the dt cap are testable without a layout engine. */
export function advanceScroll(
  current: number,
  half: number,
  pxPerSecond: number,
  dtSeconds: number,
): number {
  // Before layout `scrollWidth` is 0. Wrapping on that would pin the tape at
  // the origin forever, which reads as "the ticker is broken".
  if (!(half > 0)) return current;
  const next = current + pxPerSecond * Math.min(dtSeconds, MAX_FRAME_S);
  return next >= half ? next - half : next;
}

/** Drive the rail's own scroll position, yielding to the user on contact. */
function useAutoScroll(durationSeconds: number) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    let raf = 0;
    let last = performance.now();
    let hovering = false;
    let resumeAt = 0;

    // A touch or a wheel wins outright for a beat. The generous window after
    // touchend is for iOS momentum, which fires no events while it coasts —
    // writing scrollLeft into it would stutter the flick.
    const hold = (ms: number) => {
      resumeAt = Math.max(resumeAt, performance.now() + ms);
    };
    const onDown = () => hold(3000);
    const onUp = () => hold(2000);
    const onWheel = () => hold(2000);
    const onEnter = () => { hovering = true; };
    const onLeave = () => { hovering = false; };

    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      if (!hovering && now >= resumeAt) {
        const half = el.scrollWidth / 2;
        el.scrollLeft = advanceScroll(
          el.scrollLeft, half, half / durationSeconds, dt,
        );
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);

    el.addEventListener("pointerdown", onDown);
    el.addEventListener("touchstart", onDown, { passive: true });
    el.addEventListener("pointerup", onUp);
    el.addEventListener("touchend", onUp, { passive: true });
    el.addEventListener("wheel", onWheel, { passive: true });
    el.addEventListener("pointerenter", onEnter);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("touchstart", onDown);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("touchend", onUp);
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("pointerenter", onEnter);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [durationSeconds]);

  return ref;
}

function fmtPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString("it-IT", { maximumFractionDigits: 0 });
  if (abs >= 100) return v.toFixed(2);
  if (abs >= 1) return v.toFixed(2);
  return v.toFixed(4);
}

/* Returns null when there is no number — the caller renders <NoValue/>.
 *
 * This used to return "0.00%", and that was the bug behind "the whole ticker
 * is empty": it was not empty, it was FABRICATED. Every index read
 * "Nasdaq 0.00%", which does not say "no data" — it says "the index did not
 * move", a specific and false claim, delivered with the same confidence as a
 * real quote. A missing value must look missing. */
function fmtPct(v: number | null | undefined): string | null {
  if (!hasValue(v)) return null;
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

  const pct = fmtPct(changePct);
  // Say WHY it is missing. The upstream error is the most useful answer when
  // there is one; otherwise the honest statement is that the quote has not
  // arrived, not a guess at the cause.
  const unavailableHint = q?.error
    ? `${asset.name}: quotazione non disponibile (${q.error})`
    : `${asset.name}: quotazione non ancora ricevuta`;

  // Each tile is a Link to the MarketDetailPage for that symbol —
  // same routing convention as LiveAssetsPanel uses. The hover-pause
  // on the parent rail keeps working because the animation is on the
  // outer .ticker-rail, not on the Link itself; the Link inherits the
  // pointer-events normally so click flows through.
  return (
    <Link
      to={`/markets/${encodeURIComponent(asset.symbol)}`}
      className="inline-flex items-center gap-2 px-4 py-0.5 border-r border-border/40 whitespace-nowrap shrink-0 hover:bg-accent/40 transition-colors"
      title={`${asset.name} — apri la pagina di dettaglio`}
    >
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
          className="shrink-0 px-1 py-0 rounded text-[0.6471rem] font-bold uppercase tracking-wider bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200"
          title="Cash market chiuso · prezzo dal contratto futures"
        >
          FUT
        </span>
      ) : null}
      {/* Font bumped from text-[0.7059rem] → text-sm (~14px). The ticker
          tape used to feel cramped; the readability gain at this
          size is worth the slight extra horizontal footprint. */}
      <span className="font-mono font-semibold text-sm tracking-tight">
        {asset.name}
      </span>
      <span className="font-mono text-sm tabular-nums text-foreground/85">
        {hasValue(price) ? fmtPrice(price) : <NoValue hint={unavailableHint} />}
      </span>
      <span
        className={cn(
          "inline-flex items-center gap-0.5 font-mono font-semibold text-sm tabular-nums",
          tone,
        )}
      >
        {ArrowIcon && <ArrowIcon className="h-3.5 w-3.5" />}
        {pct ?? <NoValue hint={unavailableHint} />}
      </span>
    </Link>
  );
}

export function MarketTickerTape() {
  const q = useLiveAssets();
  // One rail width per N seconds — the same "duration" semantics the CSS had,
  // so the tuned desktop pace is unchanged. The phone window is ~5x narrower,
  // so the same pixel speed shows two tickers and a long wait; it read as
  // stalled rather than live. 28s already conceded that; 18s finishes the job.
  const isPhone = useIsPhone();
  const railRef = useAutoScroll(isPhone ? 18 : 60);
  const assets = q.data?.assets ?? [];

  // Loading / empty: thin animated bar to keep the layout stable.
  // Empty isn't really expected (the dashboard auth gate already
  // guarantees the user has the data) but defensive.
  // Height bumped 7→9 (28→36px) to match the live rail's new
  // text-sm font (was text-[0.7059rem]).
  if (q.isLoading || assets.length === 0) {
    return (
      <div className="relative w-full overflow-hidden border bg-card/40 h-9 -mx-3 rounded-none border-x-0 sm:mx-0 sm:rounded-md sm:border-x">
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
        // overflow-hidden stays on the OUTER box: the inner scroller clips
        // its own content, but without this the inline-flex track's width
        // still propagates up and turns the whole page into a horizontal
        // scroller. Both guards are needed; neither alone is enough.
        "relative w-full max-w-full overflow-hidden border bg-card",
        // Full-bleed on phones: cancel the main's p-3 with -mx-3 so the tape
        // runs edge to edge, and drop the rounding/side borders that only
        // make sense for an inset card. Back to an inset rounded card at sm+.
        "-mx-3 rounded-none border-x-0 sm:mx-0 sm:rounded-md sm:border-x",
      )}
    >
      {/* THIS is the scroller — the element the finger drags and the element
          the auto-advance writes. `ticker-scroller` hides the scrollbar (a
          36px strip has no room for one) and contains horizontal overscroll
          so a flick cannot trigger the browser's back gesture. Vertical
          touch is left to the page: overflow-y is hidden, so an upward swipe
          that starts on the tape scrolls the dashboard as expected. */}
      <div ref={railRef} className="flex items-center h-9 min-w-0 overflow-x-auto overflow-y-hidden ticker-scroller">
        {rail}
        <div aria-hidden>{rail}</div>
      </div>
    </div>
  );
}
