import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Layout, { NAV, NAV_GROUPS } from "./Layout";

/* ─── Il raggruppamento della navigazione ─────────────────────────────────
 *
 * Voce 5.2 del piano. Nove destinazioni in un elenco piatto non dicono che
 * Screener e Calendario rispondono a una domanda («che cosa c'e la fuori»)
 * e In formazione, Segnali e Posizioni a un'altra («che cosa sto seguendo»).
 *
 * ⚠️ Sono ETICHETTE DI NAVIGAZIONE, non nuove pagine: nessuna rotta cambia.
 * Rinominare gli indirizzi romperebbe i segnalibri senza risolvere niente che
 * si veda, e il piano lo esclude esplicitamente dalla stessa tranche.
 */

vi.mock("@/hooks/useAuth", () => ({
  useMe: () => ({ data: { username: "tester" } }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

function renderAt(path = "/") {
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

describe("i gruppi della navigazione", () => {
  it("⚠️ nessuna destinazione si perde o si duplica nel raggruppamento", () => {
    // Il controllo che conta: raggruppare e riordinare un elenco e
    // esattamente il momento in cui una voce sparisce senza che nessuno se ne
    // accorga, perche la barra continua a sembrare piena.
    const dai_gruppi = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.to));
    expect([...dai_gruppi].sort()).toEqual([...NAV.map((n) => n.to)].sort());
    expect(new Set(dai_gruppi).size).toBe(dai_gruppi.length);
  });

  it("le nove destinazioni di oggi ci sono tutte", () => {
    expect(NAV).toHaveLength(9);
    expect(NAV.map((n) => n.to)).toEqual(
      expect.arrayContaining([
        "/", "/sectors", "/stocks", "/calendar", "/institutionals",
        "/alerts", "/setups", "/positions", "/diagnostics",
      ]),
    );
  });

  it("rende le intestazioni Analisi e Monitoraggio", () => {
    renderAt();
    const barra = screen.getAllByRole("navigation")[0];
    expect(within(barra).getByText("Analisi")).toBeTruthy();
    expect(within(barra).getByText("Monitoraggio")).toBeTruthy();
  });

  it("⚠️ Dashboard e Diagnostica restano fuori da ogni gruppo", () => {
    // Un'intestazione sopra una voce sola e una riga di cornice con zero
    // informazione. Dopo FA-037, Stato e Metodo sono UNA destinazione, quindi
    // il gruppo «Strumenti» del piano avrebbe avuto un solo figlio.
    const senza = NAV_GROUPS.filter((g) => g.label === null);
    expect(senza.flatMap((g) => g.items.map((i) => i.to)).sort()).toEqual(
      ["/", "/diagnostics"],
    );
    for (const g of NAV_GROUPS) {
      if (g.label !== null) expect(g.items.length).toBeGreaterThan(1);
    }
  });

  it("⚠️ Monitoraggio segue la catena: In formazione, Segnali, Posizioni", () => {
    // L'ordine non e estetico: e la vita di un'idea, e da oggi e percorribile
    // davvero — setup -> segnale -> posizione sono collegati nei dati.
    const mon = NAV_GROUPS.find((g) => g.label === "Monitoraggio");
    expect(mon?.items.map((i) => i.to)).toEqual(["/setups", "/alerts", "/positions"]);
  });

  it("ogni gruppo e annunciato come tale, non solo disegnato", () => {
    renderAt();
    expect(screen.getAllByRole("group", { name: "Analisi" }).length).toBeGreaterThan(0);
  });

  it("⚠️ il titolo della scheda continua a derivare da NAV per ogni rotta", () => {
    // L'invariante che c'era prima: l'elenco che rende il menu e quello che
    // nomina la scheda, cosi i due non possono divergere. Raggruppare non deve
    // romperla.
    for (const voce of NAV) {
      renderAt(voce.to);
      expect(document.title).toBe(`${voce.label} · Finance-Alert`);
    }
  });
});
