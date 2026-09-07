import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useIsBelowMd, useIsPhone } from "./useMediaQuery";

/* The JS breakpoints must equal the CSS ones they stand in for.
 *
 * `StockBrowserTable` used to render BOTH of its layouts — 200 `<tr>` and 200
 * `<li>` — and hide one with `md:hidden` / `hidden md:block`. Measured with a
 * React profiler at pageSize=200 that was 12,817 DOM nodes, 63 per logical
 * row, and half of every mount and every price tick was spent on the branch
 * the reader cannot see. It now mounts one, chosen by `useIsBelowMd`.
 *
 * That trade only holds while the JS threshold matches the CSS one it
 * replaced. If they drift, a range of widths renders the wrong layout or none
 * at all — and nothing throws, the page simply looks wrong on one size of
 * screen. Tailwind's `md` is 768px, so "below md" is 767 and under; `sm` is
 * 640px, so "phone" is 639 and under. These are off-by-one traps by nature,
 * which is why they are pinned rather than trusted to a comment.
 */

const queryOf = (hook: () => boolean) => {
  let captured = "";
  const original = window.matchMedia;
  // Stub deliberatamente minimo: serve solo rileggere la stringa che l'hook
  // passa a matchMedia.
  // @ts-expect-error — stub parziale
  window.matchMedia = (q: string) => {
    captured = q;
    return { matches: false, addEventListener() {}, removeEventListener() {} };
  };
  try {
    renderHook(() => hook());
  } finally {
    window.matchMedia = original;
  }
  return captured;
};

describe("the JS breakpoints match Tailwind's", () => {
  it("puts the md boundary at 767px, one below Tailwind's 768", () => {
    expect(queryOf(useIsBelowMd)).toBe("(max-width: 767px)");
  });

  it("puts the phone boundary at 639px, one below Tailwind's sm", () => {
    expect(queryOf(useIsPhone)).toBe("(max-width: 639px)");
  });

  it("keeps the two thresholds distinct", () => {
    // A single-layout table switches at md; content-shortening switches at sm.
    // Collapsing them would change which layout a tablet gets.
    expect(queryOf(useIsBelowMd)).not.toBe(queryOf(useIsPhone));
  });
});
