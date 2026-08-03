import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InitialLoadBar } from "./initial-load-bar";
import { NoValue, hasValue } from "./no-value";

describe("hasValue", () => {
  it("rejects the values that render as literal NaN or Infinity", () => {
    /* 0/0 and x/0 come straight out of a percentage change computed on an
     * absent previous close. Unchecked they reach the DOM as "NaN%", which
     * looks like a bug report rather than a missing figure. */
    expect(hasValue(NaN)).toBe(false);
    expect(hasValue(Infinity)).toBe(false);
    expect(hasValue(null)).toBe(false);
    expect(hasValue(undefined)).toBe(false);
  });

  it("accepts zero, which is a real reading", () => {
    /* The opposite mistake: treating 0 as "missing" would hide a genuinely
     * unchanged price. Falsy is not the same as absent. */
    expect(hasValue(0)).toBe(true);
  });
});

describe("NoValue", () => {
  it("says it has no value instead of showing a number", () => {
    render(<NoValue />);
    expect(screen.getByText("n/d")).toBeInTheDocument();
  });

  it("carries the reason to both the tooltip and the screen reader", () => {
    render(<NoValue hint="Yahoo irraggiungibile" />);
    const el = screen.getByLabelText("Yahoo irraggiungibile");
    expect(el).toHaveAttribute("title", "Yahoo irraggiungibile");
  });
});

function withClient(ui: React.ReactNode, client: QueryClient) {
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("InitialLoadBar", () => {
  it("stays hidden when nothing is loading", () => {
    const { container } = withClient(<InitialLoadBar />, new QueryClient());
    expect(container).toBeEmptyDOMElement();
  });

  it("shows while a query has never held data", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.prefetchQuery({ queryKey: ["slow"], queryFn: () => new Promise(() => {}) });
    withClient(<InitialLoadBar />, qc);
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
  });
});
