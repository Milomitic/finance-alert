import { useIsFetching } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

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
 * THE DEADLINE IS THE REST OF THE DESIGN. A gate that waits for everything
 * hangs forever the first time a source is genuinely unavailable, which is not
 * hypothetical here: the dashboard's index panel had no data at all for
 * several hours the day this was written.
 */

/** Fraction of the wait the bar is allowed to cover on time alone, before any
 *  query has resolved. Time is a guess; resolved queries are a fact, so the
 *  guess is capped well short of the end and the facts carry the rest. */
const TIME_ONLY_CEILING = 0.35;

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
  const startedAt = useRef(Date.now());
  // Highest number of in-flight first-loads seen so far. This is the
  // denominator: it can only grow, so the ratio never walks backwards when a
  // late panel mounts and adds a query of its own.
  const [total, setTotal] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setTotal((t) => Math.max(t, pending));
  }, [pending]);

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
      {!open && (
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress * 100)}
          aria-busy="true"
          aria-label="Caricamento della dashboard"
          className="absolute inset-0 z-20 flex min-h-[55vh] flex-col items-center justify-center gap-5 px-6"
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
      <div
        aria-hidden={!open}
        inert={!open}
        className={
          open
            ? "transition-opacity duration-300 opacity-100"
            : "pointer-events-none select-none opacity-0"
        }
      >
        {children}
      </div>
    </div>
  );
}
