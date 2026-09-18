import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { schedaDa } from "@/lib/schedeSegnali";

import AlertsPage from "./AlertsPage";

/* ─── Le tre schede di Segnali ────────────────────────────────────────────
 *
 * Il ciclo di vita di un'idea in una destinazione sola: In formazione →
 * Segnali → Esiti. «In formazione» era `/setups`, una voce di menu a parte.
 *
 * ⚠️ Le tre viste sono FINTE qui, di proposito. Questo file prova cio' che
 * decide il contenitore — quale vista e' montata, che cosa finisce nell'URL —
 * e montare le vere costerebbe i finti di tre pagine per misurare la stessa
 * riga di logica. Che ciascuna vista renda il suo elenco lo provano i loro
 * file, che esistono gia'.
 */

vi.mock("@/components/setups/SetupsView", () => ({
  SetupsView: ({ vista }: { vista: string }) => <div>finta setups: {vista}</div>,
}));
vi.mock("@/components/alert/SignalsView", () => ({
  SignalsView: () => <div>finta lista segnali</div>,
}));
vi.mock("@/components/alert/OutcomesView", () => ({
  OutcomesView: () => <div>finti esiti</div>,
}));

function Posizione() {
  return <output data-testid="url">{useLocation().search}</output>;
}

function monta(url = "/alerts") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <AlertsPage />
      <Posizione />
    </MemoryRouter>,
  );
}

describe("AlertsPage — le schede", () => {
  it("senza scheda nell'URL si apre la lista dei segnali", () => {
    monta();
    expect(screen.getByText("finta lista segnali")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Segnali" })).toHaveAttribute(
      "aria-pressed", "true",
    );
  });

  it("?vista=formazione monta i setup ATTIVI, non la lista segnali", () => {
    monta("/alerts?vista=formazione");
    expect(screen.getByText("finta setups: formazione")).toBeInTheDocument();
    // Una vista alla volta: `hidden` terrebbe in piedi due alberi, due serie
    // di query, e quello nascosto verrebbe letto lo stesso dagli assistivi.
    expect(screen.queryByText("finta lista segnali")).not.toBeInTheDocument();
  });

  it("?vista=esiti monta gli esiti", () => {
    monta("/alerts?vista=esiti");
    expect(screen.getByText("finti esiti")).toBeInTheDocument();
  });

  it("cambiare scheda si scrive nell'URL, e il default non si scrive", async () => {
    monta();
    await userEvent.click(screen.getByRole("button", { name: "In formazione" }));
    expect(screen.getByTestId("url")).toHaveTextContent("vista=formazione");
    expect(screen.getByText("finta setups: formazione")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Segnali" }));
    expect(screen.getByTestId("url")).not.toHaveTextContent("vista");
  });

  it("⚠️ cambiare scheda azzera la PAGINA ma non i filtri", async () => {
    // La pagina 4 di una lista non significa niente in un'altra; `ticker`
    // invece descrive che cosa si sta guardando, ed e' il motivo per cui le
    // tre viste stanno insieme.
    monta("/alerts?vista=formazione&ticker=AAPL&pagina=4");
    await userEvent.click(screen.getByRole("button", { name: "Esiti" }));
    const url = screen.getByTestId("url");
    expect(url).toHaveTextContent("ticker=AAPL");
    expect(url).not.toHaveTextContent("pagina");
  });

  it("una scheda sconosciuta apre i segnali invece di una pagina vuota", () => {
    // Un segnalibro vecchio, un refuso: il ripiego e' una vista vera.
    monta("/alerts?vista=qualcosaltro");
    expect(screen.getByText("finta lista segnali")).toBeInTheDocument();
  });

  it("il titolo non cambia con la scheda", async () => {
    // Il nome della destinazione e' la sua IDENTITA'; cio' che appartiene
    // alla vista varia sotto. Il gate e2e localizza le pagine per il titolo,
    // e un titolo che si muove le fa sparire.
    monta("/alerts?vista=esiti");
    expect(screen.getByRole("heading", { name: "Segnali" })).toBeInTheDocument();
  });

  it("i bottoni NON promettono un tabpanel", () => {
    // `role="tab"` emette `aria-controls` verso un id che qui non esiste:
    // axe lo segnala e gli assistivi annunciano una relazione inventata. Due
    // bottoni con `aria-pressed` sono la forma corretta di un segmentato.
    monta();
    for (const nome of ["In formazione", "Segnali", "Esiti"]) {
      const b = screen.getByRole("button", { name: nome });
      expect(b).not.toHaveAttribute("aria-controls");
      expect(b).toHaveAttribute("aria-pressed");
    }
  });
});

describe("schedaDa", () => {
  it("riconosce le tre schede e ripiega sui segnali", () => {
    expect(schedaDa("formazione")).toBe("formazione");
    expect(schedaDa("esiti")).toBe("esiti");
    expect(schedaDa("segnali")).toBe("segnali");
    expect(schedaDa(null)).toBe("segnali");
    expect(schedaDa("misurazione")).toBe("segnali");
  });
});
