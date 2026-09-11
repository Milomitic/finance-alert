import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { NAV, NAV_GROUPS } from "@/lib/nav";

import Layout from "./Layout";

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

describe("un'ancora in fondo non deve sembrare dentro il gruppo sopra", () => {
  /* ⚠️ Trovato dalla verifica A SCHERMO, e jsdom non poteva dirlo: nel DOM
   * `Diagnostica` e fuori da ogni gruppo — il test sopra lo asserisce e passa —
   * ma resa senza stacco, subito sotto `Posizioni`, si LEGGE come l'ultima
   * voce di Monitoraggio. Struttura giusta, lettura sbagliata.
   *
   * E la ragione per cui il quinto criterio di chiusura del piano esiste e
   * spetta a chi guarda: «il contrasto e il target touch non sono misurabili
   * dai test». Questo non e contrasto, ma e la stessa classe — una proprieta
   * dell'aspetto che nessuna asserzione sul DOM stava misurando.
   *
   * La verifica possibile qui e sul CONFINE: un gruppo senza etichetta che
   * segue un gruppo etichettato deve portare un separatore. */
  it("il gruppo senza etichetta che segue uno etichettato porta un separatore", () => {
    renderAt();
    const barra = screen.getAllByRole("navigation")[0];
    const gruppi = Array.from(barra.children);
    const i = gruppi.findIndex((g) => g.textContent?.includes("Diagnostica"));
    expect(i).toBeGreaterThan(0);
    expect(gruppi[i].querySelector('[data-nav-separator="true"]')).not.toBeNull();
  });

  it("⚠️ il PRIMO gruppo non ne porta uno: non c'e niente da separare", () => {
    // Un separatore in cima sarebbe una riga di cornice sopra il nulla, cioe
    // lo stesso difetto dell'intestazione su una voce sola.
    renderAt();
    const barra = screen.getAllByRole("navigation")[0];
    const primo = barra.children[0];
    expect(primo.textContent).toContain("Dashboard");
    expect(primo.querySelector('[data-nav-separator="true"]')).toBeNull();
  });
});

describe("la shell esporta solo componenti", () => {
  /* ⚠️ Un file che esporta componenti E costanti rompe il Fast Refresh —
   * `react-refresh/only-export-components`. Questo repo non gated quella
   * regola per scelta (la barra scritta e che una violazione rompa qualcosa
   * che si sente, e un refresh lento non lo e), e la regola sta a 24 finding,
   * quindi non si puo accendere senza una campagna.
   *
   * Ma `Layout.tsx` e il file che TUTTE le pagine attraversano, ed e proprio
   * quello in cui la separazione mancava: i dati della navigazione ci vivevano
   * dentro. Un pin mirato protegge il file che conta senza pretendere di
   * ripulire gli altri ventiquattro — che e' il modo in cui FA-008 e scritta:
   * «da fare quando si tocca il file, non come campagna».
   */
  it("Layout non esporta costanti accanto al componente", async () => {
    const src = (await import("./Layout.tsx?raw")).default as string;
    const esportazioni = [...src.matchAll(/^export\s+(const|let|function|interface|type|\{)/gm)]
      .map((m) => m[0].trim());
    // L'unico export ammesso e il default, cioe il componente.
    expect(esportazioni).toEqual([]);
    expect(src).toMatch(/export default function Layout/);
  });

  it("e i dati della navigazione vivono in un modulo che non rende nulla", async () => {
    /* ⚠️ L'asserzione e sul CONTENUTO, non sulla sintassi. Il primo tentativo
     * cercava un `<` per escludere il JSX e falliva sui generici TypeScript
     * (`ComponentType<...>`): un controllo che grida sul codice giusto viene
     * cancellato dal primo che lo incontra. Qui la proprieta che conta e che il
     * modulo non definisca componenti — nessun default, nessuna funzione con
     * l'iniziale maiuscola. */
    const src = (await import("@/lib/nav.ts?raw")).default as string;
    expect(src).toContain("export const NAV_GROUPS");
    expect(src).not.toMatch(/export default/);
    expect(src).not.toMatch(/function\s+[A-Z]/);
  });
});
