import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PriceAlert } from "@/api/types";

import { PriceAlertsStrip } from "./PriceAlertsStrip";

/* You could create a price alert and then never touch it again.
 *
 * The create path shipped — click the chart, fill a dialog. The hooks for
 * update and delete shipped too, and nothing ever mounted them, so they were
 * removed as dead code while a plan document went on describing the UI as
 * delivered. The backend's PATCH and DELETE endpoints have been live and
 * uncalled the whole time.
 *
 * WHY A STRIP AND NOT A CARD. There WAS a `PriceAlertsCard` in the sidebar,
 * and it was removed on the owner's own feedback: "the price-alerts list isn't
 * worth a full sidebar card" (StockDetailPage.tsx). Rebuilding it would undo a
 * decision he made. So the alerts stay where they already are — annotations on
 * the chart — and gain a compact row of chips directly beneath it, which costs
 * nothing when there are none.
 */

function alert(over: Partial<PriceAlert> = {}): PriceAlert {
  return {
    id: 1,
    stock_id: 7,
    target_price: 189.5,
    direction: "above",
    enabled: true,
    note: null,
    triggered_at: null,
    created_at: "2026-09-01T10:00:00Z",
    ...over,
  };
}

describe("the strip stays out of the way when there is nothing to manage", () => {
  it("renders nothing at all with no alerts", () => {
    // Not an empty state: an empty box under the chart would cost layout to
    // say "you have no alerts", which the chart already shows by having no
    // lines on it.
    const { container } = render(
      <PriceAlertsStrip alerts={[]} onEdit={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("each alert is legible and editable from where it is drawn", () => {
  it("shows the price and the direction", () => {
    render(<PriceAlertsStrip alerts={[alert()]} onEdit={vi.fn()} />);
    expect(screen.getByRole("button", { name: /189[.,]50/ })).toBeInTheDocument();
  });

  it("opens the editor for the alert that was clicked", async () => {
    const onEdit = vi.fn();
    const a = alert({ id: 42, target_price: 210 });
    render(<PriceAlertsStrip alerts={[alert({ id: 1 }), a]} onEdit={onEdit} />);

    await userEvent.click(screen.getByRole("button", { name: /210/ }));

    expect(onEdit).toHaveBeenCalledWith(a);
  });

  it("says when an alert has already fired, rather than looking live", () => {
    render(
      <PriceAlertsStrip
        alerts={[alert({ triggered_at: "2026-09-05T14:00:00Z" })]}
        onEdit={vi.fn()}
      />,
    );
    expect(screen.getByText(/scattato/i)).toBeInTheDocument();
  });

  it("says when an alert is disabled, which is not the same as absent", () => {
    render(<PriceAlertsStrip alerts={[alert({ enabled: false })]} onEdit={vi.fn()} />);
    expect(screen.getByText(/disattivo/i)).toBeInTheDocument();
  });

  it("carries the note where there is one, since that is why it was written", () => {
    render(
      <PriceAlertsStrip alerts={[alert({ note: "resistenza" })]} onEdit={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /resistenza/ })).toBeInTheDocument();
  });
});
