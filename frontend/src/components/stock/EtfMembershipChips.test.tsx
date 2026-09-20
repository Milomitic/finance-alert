import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { EtfMembershipChips, EtfMembershipStrip } from "./EtfMembershipChips";

/* The chips say which funds hold this stock. What they must never say is that
 * the stock is IN those funds.
 *
 * The cache behind them keeps 25 holdings per fund, so this answers "is among
 * the largest positions of". SPY has 503 constituents: its 200th correctly
 * gets no chip, which means the ABSENCE of a SPY chip reads "not one of its
 * biggest weights", never "not in the S&P 500". A chip worded "in SPY" would
 * make the app assertive about something it has not measured — the same defect
 * as a wrong number, per CLAUDE.md.
 *
 * That wording is the thing worth pinning, because it is one word away from
 * being false and nothing else would catch it.
 */

const show = (funds: string[] | undefined, ticker = "NVDA") =>
  render(
    <MemoryRouter>
      <EtfMembershipChips ticker={ticker} funds={funds} />
    </MemoryRouter>,
  );

describe("the chips claim only what the cache supports", () => {
  it("says 'among the 25 largest positions', not 'in'", () => {
    show(["SPY"]);
    const chip = screen.getByRole("link", { name: /SPY/ });
    expect(chip).toHaveAttribute(
      "title",
      expect.stringContaining("fra le 25 posizioni più grandi"),
    );
  });

  it("names the stock and the fund in the tooltip, so it reads on its own", () => {
    show(["XLK"], "AAPL");
    expect(screen.getByRole("link", { name: /XLK/ })).toHaveAttribute(
      "title",
      expect.stringContaining("AAPL"),
    );
  });
});

describe("the chips stay out of the way when there is nothing to say", () => {
  it("renders nothing for a stock in no fund's top holdings", () => {
    const { container } = show([]);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the field is absent from an older cached response", () => {
    // `in_etfs` is optional in the API type for exactly this case.
    const { container } = show(undefined);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("each chip opens the fund", () => {
  it("links to the fund's own detail page", () => {
    show(["SOXX"]);
    expect(screen.getByRole("link", { name: /SOXX/ })).toHaveAttribute(
      "href",
      "/stocks/SOXX",
    );
  });

  it("renders one chip per fund, in the order given", () => {
    // The backend sorts; the component must not re-order or dedupe silently.
    show(["QQQ", "SOXX", "SPY", "XLK"]);
    const names = screen.getAllByRole("link").map((el) => el.textContent?.trim());
    expect(names).toEqual(["QQQ", "SOXX", "SPY", "XLK"]);
  });

  it("escapes a fund symbol that is not URL-safe", () => {
    show(["BRK-B"]);
    expect(screen.getByRole("link", { name: /BRK-B/ })).toHaveAttribute(
      "href",
      "/stocks/BRK-B",
    );
  });
});

describe("EtfMembershipStrip — la stessa informazione in evidenza", () => {
  it("ha un titolo che dice la MISURA, e le chip dei fondi", () => {
    render(
      <MemoryRouter>
        <EtfMembershipStrip ticker="NVDA" funds={["SOXX", "QQQ", "XLK"]} />
      </MemoryRouter>,
    );
    // «Fra le prime 25 posizioni», non «componente di»: la cache tiene 25
    // posizioni per fondo, e la fascia afferma solo cio' che ha misurato.
    expect(screen.getByText(/Fra le prime 25 posizioni di 3 ETF/)).toBeInTheDocument();
    for (const f of ["SOXX", "QQQ", "XLK"]) {
      expect(screen.getByRole("link", { name: f })).toBeInTheDocument();
    }
  });

  it("senza fondi non occupa spazio", () => {
    // Controllo negativo: una fascia vuota con «0 ETF» si leggerebbe come
    // «non e' in nessun ETF», che e' un'affermazione che la cache non sa fare.
    const { container } = render(
      <MemoryRouter>
        <EtfMembershipStrip ticker="SOLO" funds={[]} />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
