import { describe, expect, it } from "vitest";

import { advanceScroll } from "./MarketTickerTape";

/* The ticker tape advanced itself with a CSS `transform: translateX` inside an
 * `overflow: hidden` box. That is the cheapest possible marquee and it was the
 * right call — until the tape had to be draggable on a phone.
 *
 * Transform and native scrolling do not compose: the finger moves `scrollLeft`
 * while the keyframes move `translateX`, so the two offsets add up, the loop
 * seam drifts into view, and letting go leaves the tape somewhere the
 * animation never accounted for. Driving the SAME `scrollLeft` the finger
 * drives removes the conflict instead of arbitrating it — the rail is one
 * scroller, and auto-advance is just a slow finger.
 */

describe("advanceScroll", () => {
  it("moves by the speed times the elapsed time", () => {
    expect(advanceScroll(0, 1000, 60, 0.5)).toBeCloseTo(30);
  });

  it("wraps at the halfway point, where the duplicate rail begins", () => {
    // The track renders the rail twice, so scrolling past one rail width shows
    // pixel-identical content — subtracting it is invisible.
    expect(advanceScroll(995, 1000, 60, 0.5)).toBeCloseTo(25);
  });

  it("stays put before layout, when the width is still zero", () => {
    // First frame after mount: scrollWidth is 0 and half is 0. Wrapping on
    // that would divide the tape by nothing and pin it at the origin forever.
    expect(advanceScroll(0, 0, 60, 0.5)).toBe(0);
    expect(advanceScroll(42, 0, 60, 0.5)).toBe(42);
  });

  it("does not lurch after the tab was in the background", () => {
    // rAF stops while hidden, so the first frame back reports a dt of many
    // seconds. Left uncapped the tape teleports; the cap makes it resume.
    const jump = advanceScroll(0, 100000, 60, 120);
    expect(jump).toBeLessThan(60 * 1); // at most a second's worth of travel
  });

  it("keeps a manual scroll position instead of resetting it", () => {
    // The finger put the tape at 400; the next auto frame continues from
    // there rather than from wherever the animation thought it was.
    expect(advanceScroll(400, 1000, 60, 0.1)).toBeCloseTo(406);
  });
});
