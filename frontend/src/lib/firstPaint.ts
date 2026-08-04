import { useSyncExternalStore } from "react";

/* Is a first-paint gate currently holding a page back?
 *
 * The gate lives inside the routed page; the global progress toasts live in
 * Layout, outside it. Without a shared signal a scan running at page load
 * paints its own bar in the corner at the same moment the gate paints its
 * bar in the middle — two loading indicators for one wait, which is what the
 * "one bar only" rule exists to prevent.
 *
 * Deliberately a module-level boolean rather than context: the toasts are not
 * descendants of the gate, so there is no provider that could sit above both
 * without wrapping the entire app for one flag.
 */

let active = false;
const listeners = new Set<() => void>();

export function setFirstPaintActive(next: boolean): void {
  if (active === next) return;
  active = next;
  for (const l of listeners) l();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

function getSnapshot(): boolean {
  return active;
}

/** True while a first-paint gate is covering the page. Anything that paints
 *  its own loading UI should render nothing while this holds. */
export function useFirstPaintActive(): boolean {
  // Server snapshot is always false — nothing is gated before hydration.
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
