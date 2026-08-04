import { useIsFetching } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { setFirstPaintActive } from "@/lib/firstPaint";
import { cn } from "@/lib/utils";

/* Holds a page back until its data has arrived, then reveals it in one go.
 *
 * The problem it solves is the staggered reveal: on a cold cache each panel
 * appears the instant its own query resolves, so the page assembles itself in
 * front of the reader, reflowing as it goes.
 *
 * CHILDREN ARE MOUNTED THE WHOLE TIME, only made invisible. Two reasons, and
 * the first is fatal to the obvious implementation:
 *
 *  - The queries live INSIDE the children. Render a placeholder instead and
 *    nothing has been requested yet, so the pending count is 0, so the gate
 *    opens immediately and gates nothing.
 *  - `opacity`, not `display:none`. A hidden element has no box, and
 *    lightweight-charts sizes itself from its container — it would measure
 *    zero and come back wrong.
 *
 * THE OVERLAY IS `fixed`, NOT `absolute` — that one word is why the bar used
 * to sit in the wrong place. The children are the whole dashboard (3644px,
 * measured), and an `absolute inset-0` overlay stretches to its parent, so
 * `justify-center` centred the bar 1822px down: two and a half screens below
 * the fold. Fixed centres it on the VIEWPORT, which is the box the reader is
 * actually looking at.
 *
 * It also covers everything, sidebar included, over an opaque background.
 * While the page loads the bar is the only thing on screen — anything else is
 * a second thing to look at during a wait that is meant to end quickly.
 *
 * THE DEADLINE IS THE REST OF THE DESIGN. A gate that waits for everything
 * hangs forever the first time a source is genuinely unavailable, which is not
 * hypothetical here: the dashboard's index panel had no data at all for
 * several hours the day this was written.
 */

/** Fraction of the wait the bar is allowed to cover on time alone, before any
 *  query has resolved. Time is a guess; resolved queries are a fact, so the
 *  guess is capped well short of the end and the facts carry the rest. */
const TIME_ONLY_CEILING = 0.35;

/** Cross-fade length. Short on purpose: the gate exists to hide the assembly,
 *  and a slow fade only trades a staggered reveal for a sluggish one. */
const FADE_MS = 160;

export function FirstPaintGate({
  children,
  timeoutMs = 6000,
  minShowMs = 200,
}: {
  children: React.ReactNode;
  timeoutMs?: number;
  minShowMs?: number;
}) {
  const pending = useIsFetching({
    predicate: (q) => q.state.data === undefined && q.state.status !== "error",
  });

  const [open, setOpen] = useState(false);
  // Stays mounted for one fade after `open` flips, so the overlay can fade OUT
  // rather than vanish between two frames.
  const [overlayMounted, setOverlayMounted] = useState(true);
  const startedAt = useRef(Date.now());
  // Highest number of in-flight first-loads seen so far. This is the
  // denominator: it can only grow, so the ratio never walks backwards when a
  // late panel mounts and adds a query of its own.
  const [total, setTotal] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setTotal((t) => Math.max(t, pending));
  }, [pending]);

  // Tell the rest of the app it is covered, so the global progress toasts do
  // not paint a second bar over this one. Cleared on unmount as well —
  // navigating away mid-load must not leave them muted forever.
  useEffect(() => {
    setFirstPaintActive(!open);
    return () => setFirstPaintActive(false);
  }, [open]);

  // Drives the time component of the estimate. Stops the moment the gate
  // opens, so nothing keeps ticking behind a page the reader is using.
  useEffect(() => {
    if (open) return;
    const id = setInterval(() => setElapsed(Date.now() - startedAt.current), 80);
    return () => clearInterval(id);
  }, [open]);

  useEffect(() => {
    if (open) return;
    const bail = setTimeout(() => setOpen(true), timeoutMs);
    return () => clearTimeout(bail);
  }, [open, timeoutMs]);

  useEffect(() => {
    if (open || pending !== 0) return;
    const wait = Math.max(0, minShowMs - (Date.now() - startedAt.current));
    const t = setTimeout(() => setOpen(true), wait);
    return () => clearTimeout(t);
  }, [open, pending, minShowMs]);

  // Unmount the overlay only once its fade-out has finished.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => setOverlayMounted(false), FADE_MS);
    return () => clearTimeout(t);
  }, [open]);

  const resolved = Math.max(0, total - pending);
  // What actually happened: the share of first-loads that have landed. This is
  // a measurement, not an animation.
  const byQueries = total > 0 ? resolved / total : 0;
  // What is merely plausible: elapsed against the deadline, deliberately
  // capped. Without it the bar sits frozen at 0 while a single slow query
  // runs, which reads as a hang; with it uncapped it would promise progress
  // nobody has made.
  const byTime = Math.min(elapsed / timeoutMs, 1) * TIME_ONLY_CEILING;
  // 0.97 rather than 1: the bar must not sit at "done" while the page is
  // still hidden. It completes when the content appears, not before.
  const progress = Math.min(0.97, Math.max(byQueries, byTime));

  return (
    <div className="relative">
      {overlayMounted && (
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress * 100)}
          aria-busy={!open}
          aria-label="Caricamento della dashboard"
          className={cn(
            "fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 px-6",
            "bg-background transition-opacity ease-out",
            open ? "pointer-events-none opacity-0" : "opacity-100",
          )}
          style={{ transitionDuration: `${FADE_MS}ms` }}
        >
          <div className="w-full max-w-lg space-y-3">
            <div className="flex items-baseline justify-between text-sm">
              <span className="font-medium">Caricamento dati…</span>
              <span className="tabular-nums text-muted-foreground">
                {Math.round(progress * 100)}%
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary/70 to-primary transition-[width] duration-300 ease-out"
                style={{ width: `${progress * 100}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {total > 0
                ? `${resolved} di ${total} sezioni pronte`
                : "Preparazione…"}
            </p>
          </div>
        </div>
      )}
      {/* NO transition on the children — deliberately, and this cost a second
          blank screen before it was measured.
       *
       * Putting `transition-opacity` on both states makes the VISIBLE state
       * the end of an animation, so the content is only readable once that
       * animation completes. A paused compositor (background tab, throttling,
       * a devtools pane that isn't painting) leaves the transition stuck at
       * its start value and the page stays blank permanently — observed:
       * computed opacity 0 with a never-finishing opacity transition, three
       * seconds after the gate had opened.
       *
       * The reveal doesn't need it. The overlay above is opaque and fades out
       * over FADE_MS; the children are already at full opacity underneath by
       * then, so the dissolve IS the reveal. Here the resting state is plain
       * `opacity-100` with nothing to wait for: if no animation ever runs, the
       * page is visible, which is the correct failure direction. */}
      <div
        aria-hidden={!open}
        inert={!open}
        className={open ? "opacity-100" : "pointer-events-none select-none opacity-0"}
      >
        {children}
      </div>
    </div>
  );
}
