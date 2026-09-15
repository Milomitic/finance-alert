import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SignalBreadthRow } from "./SignalBreadthRow";

/* This row sits beside Forza and Probabilità, and a count of other stocks
 * placed there would read as a strength unless it says otherwise.
 *
 * It is not one. Two independent studies (CLAUDE.md) found concurrence NULL at
 * h=1/2/3/5: forty names doing the same thing does not make the signal better.
 * What it changes is the reader's conclusion — a market-wide move means the
 * stock is telling you nothing of its own.
 *
 * ⚠️ FA-064: the count is PER DIRECTION, and the opposite count is said.
 */

const api = vi.fn();
vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: (...a: unknown[]) => api(...a) };
});

beforeEach(() => {
  api.mockReset();
  api.mockImplementation(async (url: string) =>
    url === "/api/alerts/7/peers"
      ? [
          { alert_id: 11, stock_id: 2, ticker: "AMD", name: "Advanced Micro Devices", sector: "IT" },
          { alert_id: 12, stock_id: 3, ticker: "MU", name: "Micron", sector: "IT" },
        ]
      : [],
  );
});

type Props = ComponentProps<typeof SignalBreadthRow>;

function renderRow(p: Partial<Props>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SignalBreadthRow alertId={7} sameTone={null} sameToneSector={null} oppositeTone={null} {...p} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("it never reads as a confirmation", () => {
  it("says outright that it is not one", () => {
    renderRow({ sameTone: 38, sameToneSector: 12, oppositeTone: 0 });
    expect(screen.getByText(/non è una conferma/i)).toBeInTheDocument();
  });

  it("does not call the company a confluence, a confirm or a strength", () => {
    renderRow({ sameTone: 38, sameToneSector: 12, oppositeTone: 5 });
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/confluenz|rafforz|conferma il|più forte/i);
  });
});

describe("what it reports", () => {
  it("counts the same-direction stocks and splits out the sector", () => {
    renderRow({ sameTone: 38, sameToneSector: 12, oppositeTone: 0 });
    expect(screen.getByText("38")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/nella stessa direzione/);
    expect(screen.getByText(/nello stesso settore/)).toBeInTheDocument();
  });

  it("says the signal was alone rather than printing a zero", () => {
    renderRow({ sameTone: 0, sameToneSector: 0, oppositeTone: 0 });
    expect(screen.getByText(/solo questo titolo/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\b0 altri\b/);
  });

  it("reports what was OBSERVED, not a cause it cannot know", () => {
    /* ⚠️ FA-059: «movimento del titolo, non una condizione di mercato» era
     * un'affermazione di CAUSA dall'assenza di altri match, e il perimetro e'
     * il catalogo scansionato, non il mercato. Il controllo negativo e' la
     * meta' che conta. */
    renderRow({ sameTone: 0, sameToneSector: 0, oppositeTone: 0 });
    expect(screen.getByText(/catalogo scansionato/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/movimento del titolo/i);
    expect(document.body.textContent).not.toMatch(/non una condizione di mercato/i);
  });

  it("uses the singular for exactly one other stock", () => {
    renderRow({ sameTone: 1, sameToneSector: 0, oppositeTone: 0 });
    expect(screen.getByText(/altro titolo/)).toBeInTheDocument();
  });

  it("omits the sector clause when no peer shares the sector", () => {
    renderRow({ sameTone: 9, sameToneSector: 0, oppositeTone: 0 });
    expect(document.body.textContent).not.toMatch(/di cui/);
  });
});

describe("⚠️ the opposite direction is said, not folded in", () => {
  it("names the opposite count as its own sentence", () => {
    /* The defect: «Scattato anche su 20 altri titoli» for LAND.L, where 15 fired
     * the same way and 5 the opposite. The two numbers mean different things. */
    renderRow({ sameTone: 15, sameToneSector: 1, oppositeTone: 5 });
    const text = document.body.textContent ?? "";
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(text).toMatch(/direzione opposta/);
    expect(text).not.toMatch(/\b20\b/);
  });

  it("says it even when the signal was alone in its own direction", () => {
    // «Solo questo titolo» and silence about 3 stocks that fired the other way
    // would read as a lone stock on a quiet morning. It was not quiet.
    renderRow({ sameTone: 0, sameToneSector: 0, oppositeTone: 3 });
    expect(screen.getByText(/solo questo titolo/i)).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/direzione opposta è scattato su 3 titoli/);
  });

  it("stays silent about the opposite side when there is none", () => {
    renderRow({ sameTone: 4, sameToneSector: 0, oppositeTone: 0 });
    expect(document.body.textContent).not.toMatch(/direzione opposta/);
  });
});

describe("the components behind the number", () => {
  it("does NOT fetch the list until the reader asks for it", () => {
    renderRow({ sameTone: 2, sameToneSector: 2, oppositeTone: 0 });
    expect(api).not.toHaveBeenCalled();
  });

  it("lists the counted stocks, each linking to its page", async () => {
    renderRow({ sameTone: 2, sameToneSector: 2, oppositeTone: 0 });

    await userEvent.click(screen.getByRole("button", { name: /mostra i titoli/i }));

    await waitFor(() => expect(screen.getByRole("link", { name: "AMD" })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "AMD" })).toHaveAttribute("href", "/stocks/AMD");
    expect(screen.getByRole("link", { name: "MU" })).toBeInTheDocument();
    // Sull'URL e non sugli argomenti: da S-2 `api` riceve anche il segnale.
    expect(api.mock.calls.map((c) => c[0])).toContain("/api/alerts/7/peers");
  });

  it("offers no list when there is nothing to list", () => {
    renderRow({ sameTone: 0, sameToneSector: 0, oppositeTone: 4 });
    expect(screen.queryByRole("button", { name: /mostra i titoli/i })).not.toBeInTheDocument();
  });
});

describe("an alert with no day or no direction has nothing to compare against", () => {
  it("renders nothing rather than a zero that would read as 'it was alone'", () => {
    const { container } = renderRow({ sameTone: null, sameToneSector: null, oppositeTone: 3 });
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the field is absent from an older cached response", () => {
    const { container } = renderRow({ sameTone: undefined, sameToneSector: undefined, oppositeTone: undefined });
    expect(container).toBeEmptyDOMElement();
  });
});
