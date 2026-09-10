import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import DiagnosticsPage from "./DiagnosticsPage";

/* Una destinazione diagnostica, due schede.
 *
 * L'app ne aveva DUE, con nomi diversi e posti diversi nel menu, e una si
 * chiamava «Impostazioni» pur non contenendo una sola impostazione: otto
 * pannelli diagnostici sotto un ingranaggio, cioe nel posto dove ogni
 * applicazione mette le preferenze.
 *
 * ⚠️ La separazione fra le due schede non e organizzativa. **Disponibilita del
 * sistema** e **capacita predittiva del motore** sono due domande diverse: una
 * sorgente che non risponde e un guasto, un detector che legge «non
 * concludente» non lo e — e la misura che dice la verita. Nella stessa pagina
 * senza separarle, la seconda si leggerebbe come un allarme.
 */

// Le due viste montano SSE, react-query e una decina di pannelli: qui interessa
// il contenitore, cioe quale delle due viene montata e quando.
vi.mock("./PlatformHealthPage", () => ({
  default: () => <div data-testid="vista">piattaforma</div>,
}));
vi.mock("./SettingsPage", () => ({
  default: () => <div data-testid="vista">motore</div>,
}));

function at(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/diagnostics" element={<DiagnosticsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("la scheda vive nell'URL", () => {
  it("un link a una singola vista resta condivisibile", async () => {
    at("/diagnostics?vista=motore");

    expect(await screen.findByTestId("vista")).toHaveTextContent("motore");
  });

  it("senza parametro si apre la piattaforma", async () => {
    // Risponde alla piu urgente delle due domande: «qualcosa e rotto?».
    at("/diagnostics");

    expect(await screen.findByTestId("vista")).toHaveTextContent("piattaforma");
  });

  it("un valore che non conosciamo non rompe la pagina", async () => {
    // Un segnalibro vecchio o un refuso non devono lasciare una pagina vuota.
    at("/diagnostics?vista=qualcosaltro");

    expect(await screen.findByTestId("vista")).toHaveTextContent("piattaforma");
  });
});

describe("solo la scheda attiva viene montata", () => {
  it("la vista non attiva non e nel documento", async () => {
    // ⚠️ Non e solo peso: la vista Piattaforma tiene aperta una connessione
    // SSE per tutta la propria vita, e montarla dietro una scheda chiusa la
    // lascerebbe aperta mentre si guarda l'altra.
    at("/diagnostics?vista=motore");
    await screen.findByTestId("vista");

    expect(screen.getAllByTestId("vista")).toHaveLength(1);
    expect(screen.queryByText("piattaforma")).not.toBeInTheDocument();
  });

  it("cliccare una scheda cambia la vista montata", async () => {
    at("/diagnostics");
    await screen.findByTestId("vista");

    await userEvent.click(screen.getByRole("tab", { name: /motore/i }));

    expect(await screen.findByTestId("vista")).toHaveTextContent("motore");
  });
});

describe("le schede sono annunciate come tali", () => {
  it("hanno il ruolo e lo stato di selezione", async () => {
    at("/diagnostics?vista=motore");

    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(2);
    expect(screen.getByRole("tab", { name: /motore/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // Il controllo negativo: se entrambe risultassero selezionate, uno screen
    // reader non saprebbe dire dove si e.
    expect(screen.getByRole("tab", { name: /piattaforma/i })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });
});
