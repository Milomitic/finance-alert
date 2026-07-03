import { useEffect, useState } from "react";

/**
 * `Date.now()` that re-renders every `ms` — but ONLY while the tab is visible.
 *
 * Replaces the bare `setInterval(() => setNow(Date.now()), 1000)` pattern that
 * several "elapsed time" widgets used: those timers kept firing 1Hz setState
 * in hidden tabs all day. On `visibilitychange → visible` the value refreshes
 * immediately, so a returning user never sees a stale elapsed label.
 */
export function useNowTick(ms: number = 1000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let id: number | null = null;

    const start = () => {
      if (id === null) id = window.setInterval(() => setNow(Date.now()), ms);
    };
    const stop = () => {
      if (id !== null) {
        window.clearInterval(id);
        id = null;
      }
    };
    const onVisibility = () => {
      if (document.hidden) {
        stop();
      } else {
        setNow(Date.now()); // catch up instantly on return
        start();
      }
    };

    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [ms]);

  return now;
}
