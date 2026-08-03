import { useIsFetching } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

/* Holds a page back until its data has arrived, then reveals it in one go.
 *
 * The problem it solves is the staggered reveal: on a cold cache each panel
 * appears the instant its own query resolves, so the page assembles itself in
 * front of the reader, reflowing as it goes. Waiting for the set and painting
 * once is calmer.
 *
 * CHILDREN ARE MOUNTED THE WHOLE TIME, only made invisible. Two reasons, and
 * the first is fatal to the obvious implementation:
 *
 *  - The queries live INSIDE the children. Render a placeholder instead and
 *    nothing has been requested yet, so `pending` is 0, so the gate opens
 *    immediately and gates nothing. The children must mount for there to be
 *    anything to wait for.
 *  - `opacity`, not `display:none`. A hidden element has no box, and
 *    lightweight-charts sizes itself from its container — it would measure
 *    zero and come back wrong. Opacity keeps layout and measurement intact,
 *    so the reveal is instant instead of triggering a resize storm.
 *
 * THE DEADLINE IS THE REST OF THE DESIGN. A gate that waits for everything
 * hangs forever the first time a source is genuinely unavailable, and that is
 * not hypothetical here: the dashboard's index panel had no data at all for
 * several hours the day this was written. Unbounded, the whole home page would
 * have been a spinner instead of the ninety percent that worked. Panels that
 * are still empty at reveal say so themselves — NoValue exists for that.
 *
 * Only FIRST loads count, and the gate latches open. A background refetch must
 * never re-hide a page the reader is already using.
 */
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

  useEffect(() => {
    if (open) return;
    const bail = setTimeout(() => setOpen(true), timeoutMs);
    return () => clearTimeout(bail);
  }, [open, timeoutMs]);

  useEffect(() => {
    if (open || pending !== 0) return;
    // minShowMs keeps a warm cache from flashing the placeholder for a single
    // frame, which reads as a glitch rather than as loading.
    const wait = Math.max(0, minShowMs - (Date.now() - startedAt.current));
    const t = setTimeout(() => setOpen(true), wait);
    return () => clearTimeout(t);
  }, [open, pending, minShowMs]);

  return (
    <div className="relative">
      {!open && (
        <div
          role="status"
          aria-live="polite"
          aria-busy="true"
          className="absolute inset-x-0 top-0 z-20 flex min-h-[60vh] flex-col items-center justify-center gap-4"
        >
          <div className="h-1 w-56 overflow-hidden rounded-full bg-primary/15">
            <div className="loadbar-sweep h-full w-1/3 bg-primary/70" />
          </div>
          <p className="text-sm text-muted-foreground">Caricamento dati…</p>
        </div>
      )}
      <div
        // aria-hidden while gated: the content is present for layout and for
        // its queries, but a screen reader should not read a page the sighted
        // reader cannot see yet.
        aria-hidden={!open}
        // `inert` takes a boolean in React 19's typings. It also keeps the
        // hidden content out of the tab order, which aria-hidden alone does
        // not — without it the reader can Tab into panels they cannot see.
        inert={!open}
        className={
          open
            ? "transition-opacity duration-200 opacity-100"
            : "pointer-events-none select-none opacity-0"
        }
      >
        {children}
      </div>
    </div>
  );
}
