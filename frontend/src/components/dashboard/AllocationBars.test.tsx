import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AllocationBars, type AllocItem } from "./AllocationBars";

/* The "positions per institution" panel.
 *
 * It used to render the same rows as the transactions table above it, for two
 * compounding reasons: exited funds were sorted in with live ones by weight
 * (so the `max` cut dropped them whenever the top holders were all current),
 * and every row was labelled with the 13F verb — ADD / REDUCE — even though
 * the bar and the numbers beside it are the fund's TOTAL position, not the
 * size of the change that produced it.
 */

function item(over: Partial<AllocItem> & { key: string }): AllocItem {
  return { label: over.key, valueUsd: 1e6, pct: 1, ...over };
}

describe("le posizioni chiuse non possono essere tagliate via", () => {
  it("keeps an exited fund even when live ones fill the limit", () => {
    const items: AllocItem[] = [
      ...Array.from({ length: 10 }, (_, i) =>
        item({ key: `live-${i}`, label: `Fondo ${i}`, pct: 10 - i })),
      // Tiny weight: a single weight-sorted list puts it dead last.
      item({ key: "gone", label: "Fondo Uscito", pct: 0.01, exited: true }),
    ];
    render(<AllocationBars title="t" items={items} max={10} />);
    expect(screen.getByText("Fondo Uscito")).toBeInTheDocument();
  });

  it("marks it as exited rather than showing a transaction verb", () => {
    render(<AllocationBars title="t" items={[
      item({ key: "gone", label: "Uscito SpA", exited: true }),
    ]} />);
    expect(screen.getByText("Uscito")).toBeInTheDocument();
    expect(screen.getByText("Uscito SpA").className).toContain("line-through");
  });

  it("puts live positions above closed ones", () => {
    render(<AllocationBars title="t" items={[
      item({ key: "gone", label: "Chiuso", pct: 99, exited: true }),
      item({ key: "live", label: "Vivo", pct: 1 }),
    ]} />);
    const rows = screen.getAllByRole("listitem");
    expect(rows[0].textContent).toContain("Vivo");
    expect(rows[1].textContent).toContain("Chiuso");
  });
});

describe("la colonna mostra il movimento, non il verbo della transazione", () => {
  it("renders a signed delta in percentage points", () => {
    render(<AllocationBars title="t" items={[
      item({ key: "a", label: "Su", deltaPct: 1.2 }),
      item({ key: "b", label: "Giu", deltaPct: -0.4 }),
    ]} />);
    expect(screen.getByText("+1.2pp")).toBeInTheDocument();
    expect(screen.getByText("−0.4pp")).toBeInTheDocument();
  });

  it("never prints ADD or REDUCE — the bar is a position, not a change", () => {
    render(<AllocationBars title="t" items={[
      item({ key: "a", label: "F", action: "add", deltaPct: 0.1 }),
      item({ key: "b", label: "G", action: "reduce", deltaPct: -2 }),
    ]} />);
    expect(screen.queryByText(/^Add$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Reduce$/i)).not.toBeInTheDocument();
  });

  it("shows an unchanged weight as = rather than a misleading +0.0pp", () => {
    render(<AllocationBars title="t" items={[
      item({ key: "a", label: "Fermo", deltaPct: 0.01 }),
    ]} />);
    expect(screen.getByText("=")).toBeInTheDocument();
  });
});
