import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DirectionPill } from "./ConfluenceCard";

/* The direction pill in the homepage confluence list.
 *
 * It wrapped. "Short 3" sat on two lines inside a 72px slot — the pill is an
 * inline-flex holding an icon and the text run "Short 3", and a text run
 * breaks at its space like any other. Two rows' worth of height, on every row
 * of a list whose whole job is to be scanned quickly.
 *
 * The slot width is in REM on purpose. The root font-size steps up at 1536px
 * and 1920px (see index.css), so the label grows on a large screen while a
 * `w-[72px]` slot would not — the wrap would come back exactly where there is
 * most room. This is the trap CLAUDE.md records: rem tokens scale, arbitrary
 * px values do not.
 *
 * These assert on CLASSES, which is normally the wrong thing to test. It is
 * the right thing here: jsdom performs no layout, so "did it wrap" is not
 * observable, and the two properties that prevent the wrap are exactly these.
 * Removing either one fails a test instead of silently returning the bug.
 */

describe("the direction pill never wraps", () => {
  it("forbids the line break between the word and the count", () => {
    render(<DirectionPill direction="bear" nSignals={3} />);
    const pill = screen.getByText(/Short/);
    expect(pill.className).toContain("whitespace-nowrap");
  });

  it("sizes its slot in rem so it grows with the root font", () => {
    const { container } = render(<DirectionPill direction="bull" nSignals={2} />);
    const slot = container.firstElementChild as HTMLElement;
    // A px width here is the regression: the label scales at 1536px/1920px
    // and the slot would not follow it.
    expect(slot.className).toMatch(/w-\[[\d.]+rem\]/);
    expect(slot.className).not.toMatch(/w-\[\d+px\]/);
  });

  it("keeps the word and the count together in one label", () => {
    render(<DirectionPill direction="bull" nSignals={2} />);
    // One text node, not two elements that could be split across lines.
    expect(screen.getByText("Long 2")).toBeInTheDocument();
  });

  it("says short for a bearish cluster", () => {
    render(<DirectionPill direction="bear" nSignals={5} />);
    expect(screen.getByText("Short 5")).toBeInTheDocument();
  });
});
