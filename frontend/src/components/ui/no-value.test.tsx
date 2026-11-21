import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InitialLoadBar } from "./initial-load-bar";
import { NoValue } from "./no-value";
import { hasValue } from "@/lib/hasValue";

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
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Dato non disponibile")).toHaveClass("sr-only");
  });

  it("porta il motivo al lettore di schermo e a un aiuto che si apre al tocco, non in title", () => {
    const { container } = render(<NoValue hint="Yahoo irraggiungibile" />);
    expect(screen.getByText("Yahoo irraggiungibile")).toHaveClass("sr-only");
    expect(screen.getByRole("button", { name: /Spiegazione/ })).toBeInTheDocument();
    expect(container.querySelector("[title]")).toBeNull();
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
