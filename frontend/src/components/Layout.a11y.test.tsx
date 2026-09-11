import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Layout from "./Layout";

/* Three defects the UI/UX audit found, all in the shared shell, all invisible
 * to anyone using a mouse on a desktop.
 *
 * ⚠️ One of them CANNOT be caught here, and pretending otherwise would be
 * worse than not testing it. The logout button hid its label with Tailwind's
 * `hidden` class, which sets `display:none` and therefore removes the word
 * from the accessibility tree — leaving an icon-only button with no name on a
 * phone. jsdom loads no stylesheet, so `hidden` is an inert class name here
 * and `getByRole('button', {name: 'Esci'})` passes identically before and
 * after the fix. That is exactly the "a test can be true of nothing" trap in
 * CLAUDE.md. So the assertion below is on the CLASS, which is the thing that
 * actually decides, and it is written knowing it is a proxy.
 */

vi.mock("@/hooks/useAuth", () => ({
  useMe: () => ({ data: { username: "tester" } }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/*" element={<Layout />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("un utente da tastiera può saltare la navigazione", () => {
  it("offre un link di salto che punta al landmark principale", () => {
    renderAt("/");

    const skip = screen.getByRole("link", { name: /salta al contenuto/i });

    // The link is useless if its target does not exist: every page would send
    // the reader to a fragment that resolves to nothing.
    expect(skip).toHaveAttribute("href", "#contenuto");
    expect(document.querySelector("main#contenuto")).not.toBeNull();
  });

  it("il link è il primo elemento focalizzabile, non l'ultimo", () => {
    // Placing it after the sidebar would defeat the purpose: the point is to
    // arrive before the ~12 navigation links, not after them.
    renderAt("/");

    const skip = screen.getByRole("link", { name: /salta al contenuto/i });
    const focusable = document.querySelectorAll("a[href], button, input, [tabindex]");

    expect(focusable[0]).toBe(skip);
  });
});

describe("il pulsante di uscita conserva un nome", () => {
  it("non nasconde la propria etichetta con display:none", () => {
    renderAt("/");

    const label = screen.getByText("Esci");

    // `hidden` would remove it from the accessibility tree; `sr-only` keeps it
    // there and merely takes it out of the visual flow.
    expect(label.className).not.toMatch(/\bhidden\b/);
    expect(label.className).toMatch(/\bsr-only\b/);
  });

  it("il nome accessibile è lo stesso testo che si legge su desktop", () => {
    // One source for the label, so a rename cannot leave the two out of step.
    renderAt("/");
    expect(screen.getByRole("button", { name: /esci/i })).toBeInTheDocument();
  });
});

describe("la scheda del browser dice quale pagina è aperta", () => {
  it("nomina la rotta corrente", () => {
    renderAt("/positions");
    expect(document.title).toBe("Posizioni · Finance-Alert");
  });

  it("usa l'etichetta del menu, così le due non possono divergere", () => {
    renderAt("/alerts");
    expect(document.title).toBe("Segnali · Finance-Alert");
  });

  it("su una rotta di dettaglio resta generico invece di indovinare", () => {
    // /stocks/NVDA is a stock, not "Screener". A confidently wrong title is
    // worse than a plain one, so prefix matching is deliberately not used.
    renderAt("/stocks/NVDA");
    expect(document.title).toBe("Finance-Alert");
  });
});

describe("il drawer mobile si comporta da modale: deve anche dirlo", () => {
  /* ⚠️ Trovato collaudando FA-011 su un browser vero. Il comportamento c'e
   * tutto — focus che entra, trap in avanti e all'indietro, ESC che chiude,
   * focus restituito al bottone che l'ha aperto, scorrimento bloccato — ma il
   * contenitore non portava ne `role` ne `aria-modal`.
   *
   * La differenza non e teorica: senza quelle due parole un lettore di schermo
   * non annuncia un confine e non sa che il resto della pagina e fuori gioco,
   * quindi l'utente sente il trap come «il fuoco non si muove piu» invece che
   * come «sono dentro un pannello». Il comportamento senza la semantica e la
   * forma peggiore, perche funziona per chi guarda e confonde chi ascolta.
   *
   * ⚠️ axe non lo prende: un `div` senza ruolo non viola nessuna regola: e
   * l'ASSENZA di una dichiarazione, non una dichiarazione sbagliata. Serve
   * un'asserzione che sappia cosa quel contenitore sta facendo. */
  it("dichiara ruolo e modalita quando e aperto", async () => {
    renderAt("/");
    const apri = screen.getByRole("button", { name: /apri menu/i });
    await userEvent.click(apri);
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-label")).toBeTruthy();
  });

  it("e quando e chiuso non c'e affatto, non e solo nascosto", () => {
    // Il drawer si monta solo da aperto, quindi resta fuori dall'albero di
    // accessibilita invece di restarci come contenuto invisibile.
    renderAt("/");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
