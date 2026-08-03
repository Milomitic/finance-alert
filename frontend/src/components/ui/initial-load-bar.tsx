import { useIsFetching } from "@tanstack/react-query";

/* A thin bar across the top while the page is still filling in for the FIRST
 * time.
 *
 * The counted set is deliberately narrow: queries that have never held data.
 * Two traps this avoids, and both are the difference between a useful
 * indicator and an irritating one.
 *
 * It must NOT follow background refetches. The dashboard re-polls quotes every
 * 15 seconds; a bar that reappears on every tick is a flicker the eye learns
 * to filter out, and then it no longer communicates anything when it matters.
 *
 * It must NOT wait for everything to succeed. "Show a loader until all fields
 * are populated" reads well until one source is genuinely unavailable — then
 * the loader never ends and the user is shown nothing instead of the 90% that
 * works. A query that fails RESOLVES; it stops being counted here and the
 * panel below states its own unavailability. The bar answers "is more still
 * arriving?", not "is everything perfect?".
 */
export function InitialLoadBar() {
  const pending = useIsFetching({
    predicate: (q) => q.state.data === undefined && q.state.status !== "error",
  });
  if (pending === 0) return null;

  return (
    <div
      role="progressbar"
      aria-busy="true"
      aria-label={`Caricamento dati: ${pending} in corso`}
      className="pointer-events-none fixed inset-x-0 top-0 z-50 h-0.5 overflow-hidden bg-primary/15"
    >
      {/* Indeterminate: we know how many queries are open, but not how long
          any of them will take, and a fake percentage is the same lie as a
          fabricated price. */}
      <div className="loadbar-sweep h-full w-1/3 bg-primary/70" />
    </div>
  );
}
