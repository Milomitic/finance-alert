import { useEffect, useState } from "react";

/* Subscribe to a CSS media query from JS.
 *
 * Tailwind handles anything that is purely a matter of styling. This is for
 * the cases it structurally cannot reach: the CONTENT itself has to change,
 * not its presentation. A placeholder attribute, a label string, how many
 * items a list renders — CSS can hide those but cannot shorten them, and a
 * hidden-but-present string still gets measured, still gets read aloud, and
 * still truncates.
 *
 * Initialised from a real match rather than from `false`, so a small screen
 * never paints the desktop variant for one frame before correcting itself.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : false,
  );

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    setMatches(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** Below Tailwind's `sm` (640px) — i.e. phones. Kept as one constant so the
 *  JS breakpoint can never drift away from the CSS one. */
export const useIsPhone = () => useMediaQuery("(max-width: 639px)");
