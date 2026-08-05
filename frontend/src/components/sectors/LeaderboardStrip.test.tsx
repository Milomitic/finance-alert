import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { LeaderboardStrip } from "./LeaderboardStrip";
import type { LeaderRow } from "@/hooks/useSectorDetail";

/* These boards rank stocks the user may act on, so two things have to hold
 * whatever else changes: the order on screen is the order the server sent
 * (the ranking logic lives in one place, not two), and the page never
 * presents them as predictions — six studies on this engine came back null. */

function row(over: Partial<LeaderRow> = {}): LeaderRow {
  return {
    ticker: "AAA",
    name: "AAA Inc",
    sector: "Technology",
    quality: 70,
    technical: 75,
    value: 80,
    detail: "consenso 1.4 · 25 analisti",
    signals_bull: 0,
    signals_bear: 0,
    detectors_bull: 0,
    analysts: null,
    recommendation: null,
    upside_pct: null,
    target: null,
    last_close: null,
    ...over,
  };
}

function renderStrip(over: Partial<Parameters<typeof LeaderboardStrip>[0]> = {}) {
  return render(
    <MemoryRouter>
      <LeaderboardStrip
        analysts={[]}
        combined={[]}
        signals={[]}
        signalWindowDays={30}
        {...over}
      />
    </MemoryRouter>,
  );
}

describe("LeaderboardStrip", () => {
  it("keeps the server's order instead of re-sorting on the displayed number", () => {
    /* The analyst board is ordered by a rank the server computes from upside,
     * conviction and coverage — deliberately NOT by upside alone, which
     * returns microcap biotech (see leaderboard_service). If this component
     * ever sorted by anything itself, that decision would silently move
     * client-side and the two could disagree. */
    renderStrip({
      analysts: [
        row({ ticker: "FIRST", value: 94 }),
        row({ ticker: "SECOND", value: 91 }),
        row({ ticker: "THIRD", value: 88 }),
      ],
    });

    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => within(li).getByText(/^(FIRST|SECOND|THIRD)$/).textContent))
      .toEqual(["FIRST", "SECOND", "THIRD"]);
  });

  it("links every row to its stock", () => {
    renderStrip({ combined: [row({ ticker: "NVDA" })] });
    expect(screen.getByRole("link", { name: /NVDA/ })).toHaveAttribute(
      "href",
      "/stocks/NVDA",
    );
  });

  it("encodes tickers that are not URL-safe", () => {
    // Real universe: 0700.HK, BRK-B, BT-A.L. A dot is safe, but the encoding
    // must survive anything the catalog holds.
    renderStrip({ combined: [row({ ticker: "0700.HK" })] });
    expect(screen.getByRole("link", { name: /0700\.HK/ })).toHaveAttribute(
      "href",
      "/stocks/0700.HK",
    );
  });

  it("states the signal window rather than hard-coding it", () => {
    // The window is a server constant; the copy has to follow it or the page
    // will one day claim 30 days while the query covers something else.
    renderStrip({ signalWindowDays: 45 });
    expect(screen.getByText(/45g/)).toBeInTheDocument();
  });

  it("says out loud that these are not return forecasts", () => {
    renderStrip({ combined: [row()] });
    expect(screen.getByText(/non sono previsioni di rendimento/i)).toBeInTheDocument();
  });

  it("explains an empty board instead of showing a blank card", () => {
    // A board can legitimately be empty — no name passes the analyst gate, or
    // the fundamentals cache is cold after a restart. Blank would read as a
    // broken page.
    renderStrip();
    expect(screen.getByText(/copertura sufficiente e consenso positivo/i))
      .toBeInTheDocument();
  });

  it("shows the signals board's net count with a sign", () => {
    renderStrip({
      signals: [row({ ticker: "ANET", value: 7, detail: "7 rialzisti · 0 ribassisti" })],
    });
    expect(screen.getByText("+7")).toBeInTheDocument();
  });

  it("renders skeletons while loading, and no stale board", () => {
    renderStrip({ isLoading: true, combined: [row({ ticker: "STALE" })] });
    expect(screen.queryByText("STALE")).not.toBeInTheDocument();
  });
});
