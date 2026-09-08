import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { IndexMembershipChips } from "./IndexMembershipChips";

/* These chips sit beside the ETF ones and look identical, which is exactly why
 * they are a separate component: they make a DIFFERENT claim.
 *
 * Index membership is COMPLETE — the catalogue tracks every constituent it
 * ingests, all 813 stocks' worth — so "AAPL fa parte di S&P 500" is a fact and
 * the absence of an SP500 chip really does mean "not in the S&P 500". The ETF
 * chips can never say that: their cache stops at 25 holdings per fund, so
 * their absence only means "not one of its biggest weights".
 *
 * The two must not converge in wording. If someone hedges this one into "fra i
 * primi", the page starts understating what it knows; if someone strengthens
 * the ETF one into "in", it starts overstating. This test guards the first
 * direction, EtfMembershipChips.test.tsx the second.
 */

const show = (indices: { code: string; name: string }[] | undefined, ticker = "AAPL") =>
  render(
    <MemoryRouter>
      <IndexMembershipChips ticker={ticker} indices={indices} />
    </MemoryRouter>,
  );

describe("membership here is complete, so it is stated plainly", () => {
  it("says 'fa parte di', with no top-N hedge", () => {
    show([{ code: "SP500", name: "S&P 500" }]);
    const chip = screen.getByRole("link", { name: "SP500" });
    expect(chip).toHaveAttribute("title", expect.stringContaining("fa parte di S&P 500"));
    expect(chip.getAttribute("title")).not.toMatch(/fra i primi|posizioni più grandi/);
  });

  it("shows the code and keeps the full name in the tooltip", () => {
    // "Dow Jones Industrial Average" would blow out a chip row; the code is
    // what fits, the name is what explains it.
    show([{ code: "DJI", name: "Dow Jones Industrial Average" }]);
    expect(screen.getByRole("link", { name: "DJI" })).toHaveAttribute(
      "title",
      expect.stringContaining("Dow Jones Industrial Average"),
    );
  });
});

describe("each chip opens the index", () => {
  it("links to the screener filtered on that index", () => {
    show([{ code: "NDX", name: "Nasdaq-100" }]);
    expect(screen.getByRole("link", { name: "NDX" })).toHaveAttribute(
      "href",
      "/stocks?index=NDX",
    );
  });

  it("renders one chip per index, in the order given", () => {
    show([
      { code: "DJI", name: "Dow Jones Industrial Average" },
      { code: "NDX", name: "Nasdaq-100" },
      { code: "SP500", name: "S&P 500" },
    ]);
    expect(screen.getAllByRole("link").map((el) => el.textContent?.trim())).toEqual([
      "DJI",
      "NDX",
      "SP500",
    ]);
  });
});

describe("nothing to show, nothing rendered", () => {
  it("renders nothing for a stock in no tracked index", () => {
    // 173 of 986 are in none — a foreign listing or an eToro hand-pick.
    const { container } = show([]);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the field is absent from an older cached response", () => {
    const { container } = show(undefined);
    expect(container).toBeEmptyDOMElement();
  });
});
