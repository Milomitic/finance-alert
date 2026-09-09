import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations, describeViolations } from "@/test/axe";

import { EMPTY_FILTERS, StockFiltersCard } from "./StockFiltersCard";

/* The densest form in the app: nine numeric fields, several of them min/max
 * pairs, plus selects and a preset popover. It is exactly the shape where a
 * label goes missing without anything looking wrong, which is what happened
 * here once already — every one of those spin buttons announced "blank".
 *
 * The hand-written assertions in StockFiltersCard.a11y.test.tsx pin the
 * specific names, and they stay: axe cannot tell you that "Score" fails to
 * distinguish the two ends of a range, only that a name exists at all. This
 * file is the broad net beside them.
 *
 * ⚠️ THE SAME TRAP APPLIES. Three of the four filter areas are closed by
 * default, so running axe on a bare mount would scan a nearly empty card and
 * report zero violations about almost nothing. Every area is opened first, and
 * the field count is asserted from below so the scan cannot silently shrink.
 */

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
  const view = render(
    <StockFiltersCard state={EMPTY_FILTERS} onChange={vi.fn()} filters={undefined} />,
  );
  for (const header of screen.getAllByRole("button", { expanded: false })) {
    await user.click(header);
  }
  return { user, ...view };
}

describe("il pannello filtri non ha violazioni strutturali", () => {
  it("con ogni area aperta", async () => {
    const { container } = await renderAllAreasOpen();

    // Guard against scanning almost nothing: below this the result would be
    // green because the card is closed, not because it is sound.
    expect(screen.getAllByRole("spinbutton").length).toBeGreaterThanOrEqual(9);

    const violations = await axeViolations(container);

    expect(violations, describeViolations(violations)).toHaveLength(0);
  }, 30_000);

  it("ogni campo del modulo resta associato a un'etichetta", async () => {
    const { container } = await renderAllAreasOpen();

    const violations = await axeViolations(container, {
      runOnly: {
        type: "rule",
        values: ["label", "form-field-multiple-labels", "select-name", "aria-input-field-name"],
      },
    });

    expect(violations, describeViolations(violations)).toHaveLength(0);
  }, 30_000);

  it("anche il popover dei preset, che non esiste finché non lo apri", async () => {
    // Scanning without opening it would pass over a control that is simply
    // not in the DOM yet — a green result about an absence.
    const { user, container } = await renderAllAreasOpen();
    await user.click(screen.getByRole("button", { name: /preset/i }));

    expect(screen.getByRole("textbox", { name: /nome del preset/i })).toBeInTheDocument();

    const violations = await axeViolations(container);

    expect(violations, describeViolations(violations)).toHaveLength(0);
  }, 30_000);
});
