import { useLayoutEffect, useRef } from "react";

/** FLIP-animate vertical reordering of a keyed list (the top-movers board:
 *  rows slide to their new rank instead of teleporting, matching the
 *  Wall-Street-tape feel of the per-cell FlashValue tints).
 *
 *  Usage: `const register = useFlipList();` then attach
 *  `ref={register(key)}` to each row's root element. On every commit the
 *  hook compares each key's `offsetTop` with the previous commit and plays
 *  a translateY slide for rows that moved. `offsetTop` (not
 *  getBoundingClientRect) so page scrolling between commits doesn't read
 *  as a phantom move. Web Animations API → no CSS-class lifecycle, and
 *  interrupted animations are simply replaced by the next one. */
export function useFlipList() {
  const els = useRef(new Map<string, HTMLElement>());
  const prevTops = useRef(new Map<string, number>());

  useLayoutEffect(() => {
    const next = new Map<string, number>();
    els.current.forEach((el, key) => {
      if (el.isConnected) next.set(key, el.offsetTop);
    });
    next.forEach((top, key) => {
      const was = prevTops.current.get(key);
      const el = els.current.get(key);
      if (el == null) return;
      if (was == null) {
        // Entering row (climbed into the visible top-N): gentle fade-in.
        // Skipped on the very first commit (prev map empty = initial mount).
        if (prevTops.current.size > 0) {
          el.animate([{ opacity: 0.2 }, { opacity: 1 }], {
            duration: 320,
            easing: "ease-out",
          });
        }
        return;
      }
      const dy = was - top;
      if (Math.abs(dy) > 4) {
        el.animate(
          [{ transform: `translateY(${dy}px)` }, { transform: "translateY(0)" }],
          { duration: 380, easing: "cubic-bezier(0.22, 0.9, 0.26, 1)" },
        );
      }
    });
    prevTops.current = next;
  });

  return (key: string) => (el: HTMLElement | null) => {
    if (el) els.current.set(key, el);
    else els.current.delete(key);
  };
}
