import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

/* FA-187: il confronto in base 100, con lo stato nell'URL. */

vi.mock("@/hooks/useMercati", async () => {
  const vero = await vi.importActual<typeof import("@/hooks/useMercati")>("@/hooks/useMercati");
  return {
    ...vero,
    useConfronto: (simboli: string[]) => ({
      error: null,
      data: {
        date: ["2026-01-02", "2026-06-01", "2026-11-26"],
        serie: Object.fromEntries(simboli.map((s, i) => [s, [100, 105 + i, 110 + i * 10]])),
        riepilogo: Object.fromEntries(simboli.map((s, i) => [s, { rendimento: 0.1 + i * 0.1, peggior_calo: -0.08 }])),
        dal: "2026-01-02", al: "2026-11-26",
      },
    }),
  };
});

const { ConfrontoNormalizzato } = await import("./ConfrontoNormalizzato");

function Url() {
  return <span data-testid="url">{useLocation().search}</span>;
}

function monta(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/markets" element={<><ConfrontoNormalizzato nomi={{ "^GSPC": "S&P 500", "GC=F": "Oro", "^IXIC": "Nasdaq" }} /><Url /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ConfrontoNormalizzato", () => {
  it("una linea per simbolo, col rendimento e il peggior calo", () => {
    monta("/markets?confronta=^GSPC,GC=F&periodo=1a");
    expect(screen.getByRole("img", { name: /Confronto in base 100 dal 2\/1\/26: S&P 500, Oro/ })).toBeInTheDocument();
    expect(screen.getByText("+10,0%")).toBeInTheDocument();
    expect(screen.getByText("+20,0%")).toBeInTheDocument();
    expect(screen.getAllByText("calo −8,0%")).toHaveLength(2);
  });

  it("togliere e aggiungere cambia l'URL", () => {
    monta("/markets?confronta=^GSPC,GC=F&periodo=1a");
    fireEvent.click(screen.getByRole("button", { name: "Togli Oro dal confronto" }));
    expect(screen.getByTestId("url").textContent).toContain("confronta=%5EGSPC&");
    fireEvent.change(screen.getByLabelText("Aggiungi un titolo (es. AAPL)"), { target: { value: "aapl" } });
    fireEvent.click(screen.getByRole("button", { name: "Aggiungi" }));
    expect(decodeURIComponent(screen.getByTestId("url").textContent!)).toContain("confronta=^GSPC,AAPL");
  });
});
