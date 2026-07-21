import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Position } from "@/api/types";
import { PortfolioSummary } from "@/components/PortfolioSummary";

function pos(over: Partial<Position>): Position {
  return {
    id: 1,
    stock_id: 1,
    ticker: "AAPL",
    name: "Apple",
    alert_id: null,
    side: "long",
    entry_price: 100,
    stop_price: null,
    target_price: null,
    size: 10,
    opened_at: "2026-01-01T00:00:00Z",
    closed_at: null,
    exit_price: null,
    exit_reason: null,
    notes: null,
    last_price: 110,
    price_source: "live",
    unrealized_pct: 10,
    unrealized_abs: 100,
    realized_pct: null,
    realized_abs: null,
    currency: "USD",
    unrealized_usd: 100,
    realized_usd: null,
    cost_usd: 1000,
    ...over,
  };
}

describe("PortfolioSummary", () => {
  it("renders nothing when there are no positions", () => {
    const { container } = render(<PortfolioSummary open={[]} closed={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("sums P&L in USD across positions and shows the win rate", () => {
    const open = [pos({ unrealized_usd: 100, cost_usd: 1000 })];
    const closed = [
      pos({ closed_at: "2026-02-01", realized_usd: 50, realized_pct: 5, unrealized_usd: null }),
      pos({ closed_at: "2026-02-01", realized_usd: -20, realized_pct: -2, unrealized_usd: null }),
    ];
    render(<PortfolioSummary open={open} closed={closed} />);

    // Total P&L = 100 (open) + 50 - 20 (closed) = +130.
    expect(screen.getByText("+130")).toBeInTheDocument();
    // Win rate = 1 win / 2 closed = 50%.
    expect(screen.getByText(/win rate 50%/i)).toBeInTheDocument();
    // The FX caveat now says converted-to-USD, not "native currency".
    expect(screen.getByText(/convertite in USD/i)).toBeInTheDocument();
  });

  it("counts notional-only positions (no size) in the note", () => {
    const open = [pos({ size: null, unrealized_usd: null, cost_usd: null })];
    render(<PortfolioSummary open={open} closed={[]} />);
    expect(screen.getByText(/1 posizione notional/i)).toBeInTheDocument();
  });
});
