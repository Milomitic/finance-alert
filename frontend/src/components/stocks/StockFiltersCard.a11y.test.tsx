import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EMPTY_FILTERS, StockFiltersCard } from "./StockFiltersCard";

/* Every numeric filter in this card is a borderless <input> inside a bordered
 * box that also holds a caption <span>: "Score [ min ]–[ max ]". The span is
 * not a label — it is text next to a field — so a screen reader announced
 * "spin button, blank" for all nine of them, and in a min/max box a single
 * caption could not have described both ends anyway.
 *
 * The matching visual defect: those inputs carry `focus:outline-none`, which
 * is correct (an outline INSIDE the box looks broken) and was never replaced,
 * so nothing at all marked the focused field. The ring now sits on the box via
 * `focus-within:ring`. That part is pure CSS and jsdom does not compute it, so
 * asserting it here would only re-check a string; it was verified instead by
 * grepping the built stylesheet for the generated rule, since Tailwind emits
 * only classes it can see as literals.
 *
 * What IS worth asserting here is the accessible name, which testing-library
 * computes for real.
 *
 * THE TRAP THIS TEST HAD TO AVOID: three of the four filter areas are closed
 * by default (AREA_DEFAULT_OPEN), so a bare mount renders almost none of these
 * inputs and "they all have names" would be true of a nearly empty set. The
 * areas are opened first, and the count is asserted from below — a change that
 * stops rendering them fails here instead of passing quietly.
 */

/* `useFilterAreas` persists which areas are open. This environment's
 * localStorage has no usable `clear()`, and the state would otherwise carry
 * from one test into the next, so the file supplies its own in-memory Storage
 * and resets it. The component wraps its reads in try/catch and falls back to
 * AREA_DEFAULT_OPEN, so this only buys determinism — never the pass itself. */
beforeEach(() => {
  const mem = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => mem.get(k) ?? null,
    setItem: (k: string, v: string) => void mem.set(k, v),
    removeItem: (k: string) => void mem.delete(k),
    clear: () => mem.clear(),
    key: (i: number) => [...mem.keys()][i] ?? null,
    get length() {
      return mem.size;
    },
  });
});

async function renderAllAreasOpen() {
  const user = userEvent.setup();
  render(
    <StockFiltersCard state={EMPTY_FILTERS} onChange={vi.fn()} filters={undefined} />,
  );
  for (const header of screen.getAllByRole("button", { expanded: false })) {
    await user.click(header);
  }
  return user;
}

describe("every filter field says what it is", () => {
  it("gives each numeric filter an accessible name", async () => {
    await renderAllAreasOpen();

    const numeric = screen.getAllByRole("spinbutton");

    // Below this the assertion below would be vacuous.
    expect(numeric.length).toBeGreaterThanOrEqual(9);

    const unnamed = numeric.filter(
      (el) => !(el.getAttribute("aria-label") || el.getAttribute("id")),
    );
    expect(unnamed).toEqual([]);
  });

  it("names the two ends of a range apart, not both after the caption", async () => {
    await renderAllAreasOpen();

    // "Score" alone cannot tell a reader which end they are filling.
    expect(screen.getByRole("spinbutton", { name: /score minimo/i })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: /score massimo/i })).toBeInTheDocument();
  });

  it("names the preset field, whose only description was a placeholder", async () => {
    const user = await renderAllAreasOpen();

    // The field lives inside the Preset popover, so it does not exist until
    // the popover is opened. Asserting without this passes through
    // getByRole's "not found" error, not through a missing label.
    await user.click(screen.getByRole("button", { name: /preset/i }));

    // A placeholder disappears the moment you type into it, so it is not a label.
    expect(
      screen.getByRole("textbox", { name: /nome del preset/i }),
    ).toBeInTheDocument();
  });
});
