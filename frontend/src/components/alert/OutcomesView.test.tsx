import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PlanOutcomeList } from "@/api/planOutcomes";

import { OutcomesView } from "./OutcomesView";

/* I controlli della scheda Esiti.
 *
 * ⚠️ Il perimetro vive nell'URL e il filtro si applica sul SERVER, quindi le
 * asserzioni guardano due cose: che cosa e' stato chiesto e che cosa e'
 * rimasto nell'indirizzo. Contare le righe rese misurerebbe il finto. */

const mockGet = vi.fn();
vi.mock("@/api/client", () => ({ api: (...args: unknown[]) => mockGet(...args) }));

/* La sottovista «Setup» monta la lista dei setup, che ha i suoi test e le sue
   chiamate: qui e' finta, cosi' una sua richiesta non si confonde con quelle
   di questa vista quando si legge l'ultima URL interrogata. */
vi.mock("@/components/setups/SetupsView", () => ({
  SetupsView: ({ vista }: { vista: string }) => <div>finta setups: {vista}</div>,
}));

const RISPOSTA: PlanOutcomeList = {
  items: [
    {
      alert_id: 1, ticker: "AAA", name: "AAA Inc.", detector: "sr_flip", tone: "bull",
      signal_date: "2026-03-01", entry_date: "2026-03-02", entry: 100, stop: 96,
      tp1: 108, tp2: null, r: 4, horizon_days: 21, esito: "tp1",
      resolved_date: "2026-03-10", bars_to_outcome: 6, r_multiple: 2.4, mae_r: 0.3,
      mfe_r: 2.1, tp2_reached: false, stop_hit_date: null, tp1_hit_date: "2026-03-10",
      tp2_hit_date: null, source: "emesso",
    },
  ],
  total: 1,
  has_more: false,
  counts_by_detector: { sr_flip: 1, gap_and_go: 4 },
  summary: {
    n: 1, effective_n: 1, horizon_days: 21, expectancy_r: 2.4, expectancy_ci: null,
    verdict: "inconclusive", win_rate: 100, esiti: { tp1: 1, stop: 0, ambigua: 0, scaduto: 0 },
    stop_too_tight: 0, mae_r_on_wins: 0.3, mfe_r_on_losses: null, median_bars: 6,
    low_confidence: true,
  },
};

function Posizione() {
  return <output data-testid="url">{useLocation().search}</output>;
}

function monta(url = "/alerts?vista=esiti") {
  mockGet.mockResolvedValue(RISPOSTA);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <OutcomesView />
        <Posizione />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** L'ultima URL chiesta al server. */
function ultimaUrl(): string {
  return String(mockGet.mock.calls.at(-1)?.[0] ?? "");
}

beforeEach(() => mockGet.mockReset());

describe("OutcomesView — i controlli", () => {
  it("i filtri sono gruppi con un'etichetta, non una fila di pastiglie uguali", async () => {
    // ⚠️ «Target» accanto a «Divergenza RSI» senza etichette sembra lo stesso
    // tipo di scelta. Tre dimensioni, tre gruppi nominati.
    monta();
    await screen.findByText("AAA");
    expect(screen.getByRole("group", { name: "Esito" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Verso" })).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("il verso va al SERVER e resta nell'indirizzo", async () => {
    monta();
    await screen.findByText("AAA");

    await userEvent.click(screen.getByRole("button", { name: "Ribassisti" }));

    await waitFor(() => expect(ultimaUrl()).toContain("tone=bear"));
    expect(screen.getByTestId("url")).toHaveTextContent("tono=ribassisti");
  });

  it("l'esito va al server col nome che il backend conosce", async () => {
    monta();
    await screen.findByText("AAA");

    await userEvent.click(screen.getByRole("button", { name: "Stessa barra" }));

    await waitFor(() => expect(ultimaUrl()).toContain("esito=ambigua"));
  });

  it("⚠️ il menu delle condizioni non si svuota scegliendone una", async () => {
    // I conteggi arrivano dal server misurati PRIMA del filtro per
    // condizione. Misurati dopo, il controllo si disabiliterebbe da solo al
    // primo uso: resterebbe la sola condizione scelta, e per tornare indietro
    // bisognerebbe sapere che esiste un «Tutte».
    monta("/alerts?vista=esiti&condizione=sr_flip");
    await screen.findByText("AAA");

    const opzioni = screen.getAllByRole("option").map((o) => o.textContent);
    expect(opzioni).toHaveLength(3);                       // Tutte + due condizioni
    expect(opzioni.join(" ")).toMatch(/Tutte \(5\)/);      // 1 + 4, non il totale filtrato
  });

  it("un perimetro nuovo riporta alla prima pagina", async () => {
    // Restare alla pagina 4 dopo aver cambiato filtro mostrerebbe una fetta di
    // mezzo di una popolazione diversa, senza che niente lo dica.
    monta("/alerts?vista=esiti&pagina=4");
    await screen.findByText("AAA");

    await userEvent.click(screen.getByRole("button", { name: "Rialzisti" }));

    expect(screen.getByTestId("url")).not.toHaveTextContent("pagina");
  });

  it("«Azzera i filtri» compare solo quando ce n'e' uno, e li toglie tutti", async () => {
    monta("/alerts?vista=esiti&gara=stop&tono=ribassisti&condizione=sr_flip&ticker=AAPL");
    await screen.findByText("AAA");

    await userEvent.click(screen.getByRole("button", { name: /azzera i filtri/i }));

    const url = screen.getByTestId("url");
    for (const chiave of ["gara", "tono", "condizione", "ticker"]) {
      expect(url).not.toHaveTextContent(chiave);
    }
    // La scheda resta quella: azzerare i filtri non e' uscire dalla vista.
    expect(url).toHaveTextContent("vista=esiti");
    // Controllo negativo: senza filtri il comando non ha niente da fare e non
    // deve occupare spazio.
    expect(screen.queryByRole("button", { name: /azzera i filtri/i })).not.toBeInTheDocument();
  });

  it("?ticker= si vede e si toglie", async () => {
    monta("/alerts?vista=esiti&ticker=aapl");
    await waitFor(() => expect(ultimaUrl()).toContain("ticker=AAPL"));

    await userEvent.click(await screen.findByRole("button", { name: /solo AAPL/i }));

    expect(screen.getByTestId("url")).not.toHaveTextContent("ticker");
  });

  it("la sottovista Setup non interroga i piani", async () => {
    // Una vista alla volta: `enabled` spento evita una richiesta per dati che
    // nessuno sta guardando.
    monta("/alerts?vista=esiti&esiti=setup");
    expect(await screen.findByText("finta setups: esiti")).toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
  });
});
