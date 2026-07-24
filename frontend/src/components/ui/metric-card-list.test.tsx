import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricCardList, type MetricColumn } from "./metric-card-list";

interface Row {
  ticker: string;
  pe: number;
  secret: string;
}

const rows: Row[] = [
  { ticker: "AAPL", pe: 28.4, secret: "desktop-only" },
  { ticker: "MSFT", pe: 31.2, secret: "desktop-only" },
];

const columns: MetricColumn<Row>[] = [
  { key: "pe", label: "P/E", cell: (r) => r.pe.toFixed(1) },
  { key: "secret", label: "Interno", cell: (r) => r.secret, desktopOnly: true },
];

describe("MetricCardList", () => {
  it("renders one card per row with its identity and headline", () => {
    render(
      <MetricCardList
        rows={rows}
        columns={columns}
        rowKey={(r) => r.ticker}
        identity={(r) => <span>{r.ticker}</span>}
        headline={(r) => <span>score {r.pe > 30 ? "alto" : "basso"}</span>}
      />,
    );
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("score alto")).toBeInTheDocument();
  });

  it("labels every metric — a card has no column position to infer it from", () => {
    render(
      <MetricCardList
        rows={[rows[0]]}
        columns={columns}
        rowKey={(r) => r.ticker}
        identity={(r) => <span>{r.ticker}</span>}
      />,
    );
    expect(screen.getByText("P/E")).toBeInTheDocument();
    expect(screen.getByText("28.4")).toBeInTheDocument();
  });

  it("omits desktopOnly columns so the card is not the wall of numbers again", () => {
    render(
      <MetricCardList
        rows={[rows[0]]}
        columns={columns}
        rowKey={(r) => r.ticker}
        identity={(r) => <span>{r.ticker}</span>}
      />,
    );
    expect(screen.queryByText("Interno")).not.toBeInTheDocument();
    expect(screen.queryByText("desktop-only")).not.toBeInTheDocument();
  });

  it("renders nothing but the container for an empty list", () => {
    const { container } = render(
      <MetricCardList
        rows={[]}
        columns={columns}
        rowKey={(r: Row) => r.ticker}
        identity={(r: Row) => <span>{r.ticker}</span>}
      />,
    );
    expect(container.querySelectorAll("dl")).toHaveLength(0);
  });
});
