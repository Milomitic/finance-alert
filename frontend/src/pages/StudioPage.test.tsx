import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { intervallo, parametriDaUrl } from "@/lib/studio";

import StudioPage from "./StudioPage";

/* FA-157: la pagina Studio. Lo stato e' nell'URL, e ogni numero ha il suo caso base. */

const risposte: Record<string, unknown> = {};
vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: async (url: string) => risposte[url.split("?")[0]] };
});

const misura = (media: number, finestre = 6) => ({
  casi: 12, finestre, media, mediana: media, quota_positivi: 0.5,
  intervallo: finestre >= 2 ? [media - 0.01, media + 0.01] : null,
});

function monta(url: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[url]}><StudioPage /></MemoryRouter></QueryClientProvider>);
}

describe("parametri dall'URL", () => {
  it("valori ammessi dal server anche da un link scritto a mano", () => {
    const p = parametriDaUrl(new URLSearchParams("simbolo=aapl&modello=boh&sedute=500&soglia=0&orizzonte=-3"));
    expect(p).toMatchObject({ simbolo: "AAPL", modello: "dopo_movimento", sedute: 63, soglia: -10, orizzonte: 1 });
  });

  it("l'intervallo dice perche' manca", () => {
    expect(intervallo(misura(0.02, 1) as never)).toMatch(/meno di due finestre/);
    expect(intervallo(misura(0.02) as never)).toBe("da +1,0% a +3,0%");
  });
});

describe("StudioPage", () => {
  it("senza simbolo propone domande d'esempio (D-81)", () => {
    monta("/studio");
    expect(screen.getByText(/Scegli un simbolo, oppure parti da una di queste domande/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /AAPL nelle 21 sedute dopo un calo del 10%/ })).toBeInTheDocument();
  });

  it("dopo un movimento: condizione contro base", async () => {
    risposte["/api/studio/dopo_movimento"] = {
      simbolo: "AAPL", condizione: misura(0.03), base: misura(0.01), differenza: 0.02,
      intervallo_differenza: [-0.01, 0.05], verdetto: "non_concludente",
      parametri: { sedute: 5, soglia_pct: -10, orizzonte: 21 },
    };
    monta("/studio?simbolo=AAPL&modello=dopo_movimento&soglia=-10&sedute=5&orizzonte=21");
    expect(await screen.findByText("Dopo il movimento")).toBeInTheDocument();
    expect(screen.getByText("Base: tutte le finestre")).toBeInTheDocument();
    expect(screen.getByText("+2,00%")).toBeInTheDocument();
    // D-84: il verdetto sta sopra i numeri, con l'intervallo della differenza.
    expect(screen.getByText("Non concludente")).toBeInTheDocument();
    expect(screen.getByText(/da −1,00% a \+5,00%, 95%/)).toBeInTheDocument();
  });

  it("attorno a un evento: il percorso e la misura", async () => {
    risposte["/api/studio/evento"] = {
      simbolo: "AAPL", tipo: "trimestrali", serie_macro: null, eventi: 0, percorso: [],
      a_orizzonte: misura(0, 0), base: misura(0.001), orizzonte: 5,
      differenza: null, intervallo_differenza: null, verdetto: "non_concludente",
    };
    monta("/studio?simbolo=AAPL&modello=evento");
    // FA-192: un messaggio solo, senza verdetto «0 finestre» ne' tabella di trattini.
    expect(await screen.findByText(/Nessuna trimestrale nota per AAPL/)).toBeInTheDocument();
    expect(screen.queryByText("Non concludente")).toBeNull();
    expect(screen.queryByText("Base: tutte le finestre")).toBeNull();
  });

  it("un effetto che cambia segno fra le due meta' non e' «diverso», e la distribuzione si vede (ondata 1)", async () => {
    risposte["/api/studio/dopo_movimento"] = {
      simbolo: "AAPL",
      condizione: { ...misura(0.03, 40), mediana: -0.01, p10: -0.08, p90: 0.12, peggiore: -0.2, migliore: 0.3 },
      base: misura(0.01, 120), differenza: 0.02, intervallo_differenza: [0.005, 0.035], verdetto: "instabile",
      stabilita: { prima: 0.05, seconda: -0.01, concordi: false },
      istogramma: [{ da: -0.1, a: 0, condizione: 0.4, base: 0.5 }, { da: 0, a: 0.1, condizione: 0.6, base: 0.5 }],
      parametri: { sedute: 5, soglia_pct: -10, orizzonte: 21 },
    };
    monta("/studio?simbolo=AAPL&modello=dopo_movimento&soglia=-10&sedute=5&orizzonte=21");
    expect(await screen.findByText("Non regge nelle due metà")).toBeInTheDocument();
    expect(screen.getByText(/Prima metà \+5,00% · seconda metà −1,00%/)).toBeInTheDocument();
    expect(screen.getByText("Distribuzione")).toBeInTheDocument();
    expect(screen.getByText("−20,0%")).toBeInTheDocument();
    // D-87: il risultato ripete la domanda.
    expect(screen.getByRole("heading", { name: /AAPL · Dopo un movimento/ })).toBeInTheDocument();
    // FA-192: la frase col meno tipografico, e l'istogramma dice le mediane e lo zero.
    expect(screen.getByText(/si era mosso di −10% o peggio in 5 sedute/)).toBeInTheDocument();
    expect(screen.getByText(/linea: mediana −1,0%/)).toBeInTheDocument();
    expect(screen.getByText("tratteggio: zero")).toBeInTheDocument();
  });

  it("su telefono, a studio calcolato, il modulo e' una riga che si riapre (FA-192)", async () => {
    const mm = window.matchMedia;
    window.matchMedia = ((q: string) => ({
      matches: q.includes("max-width"), media: q, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    try {
      risposte["/api/studio/dopo_movimento"] = {
        simbolo: "AAPL", condizione: misura(0.03), base: misura(0.01), differenza: 0.02,
        intervallo_differenza: [-0.01, 0.05], verdetto: "non_concludente",
        parametri: { sedute: 5, soglia_pct: -10, orizzonte: 21 },
      };
      monta("/studio?simbolo=AAPL&modello=dopo_movimento&soglia=-10&sedute=5&orizzonte=21");
      expect(await screen.findByText("AAPL · −10% in 5 · 21 sedute")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Calcola" })).toBeNull();
      screen.getByRole("button", { name: "Modifica" }).click();
      expect(await screen.findByRole("button", { name: "Calcola" })).toBeInTheDocument();
      // I tre modelli in un menu: a 375 px il gruppo usciva dal bordo.
      expect(screen.getByRole("combobox", { name: "Domanda" })).toBeInTheDocument();
    } finally {
      window.matchMedia = mm;
    }
  });

  it("il percorso con la discesa massima, e i casi uno per uno (FA-193, FA-194)", async () => {
    risposte["/api/studio/dopo_movimento"] = {
      simbolo: "AAPL", condizione: misura(0.03), base: misura(0.01), differenza: 0.02,
      intervallo_differenza: [-0.01, 0.05], verdetto: "non_concludente",
      parametri: { sedute: 5, soglia_pct: -10, orizzonte: 21 },
      percorso: [0, 1, 2].map((k) => ({ seduta: k, media: 0.01 * k, mediana: 0.008 * k, p10: -0.02 * k, p90: 0.03 * k, base: 0.002 * k })),
      escursioni: { mae_mediana: -0.041, mae_p10: -0.112, mfe_mediana: 0.065, mfe_p90: 0.2, casi: 12 },
      elenco_casi: [
        { data: "2025-04-07", esito: 0.05, episodio: 6, primo: false, mossa: -0.12 },
        { data: "2025-04-04", esito: 0.08, episodio: 6, primo: true, mossa: -0.14 },
        { data: "2020-03-12", esito: -0.03, episodio: 5, primo: true, mossa: -0.2 },
      ],
    };
    monta("/studio?simbolo=AAPL&modello=dopo_movimento&soglia=-10&sedute=5&orizzonte=21");
    expect(await screen.findByText(/nel caso tipico la discesa massima è stata/)).toBeInTheDocument();
    expect(screen.getByText("−4,1%")).toBeInTheDocument();
    expect(screen.getByText("−11,2%")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Rendimento cumulato di AAPL nelle 21 sedute/ })).toBeInTheDocument();
    expect(screen.getByText("I 12 casi (6 episodi)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Esporta CSV/ })).toBeInTheDocument();
    expect(screen.getByText("2020-03-12")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Solo il primo giorno di ogni episodio/));
    expect(screen.queryByText("2025-04-07")).toBeNull();
    expect(screen.getByText("2025-04-04")).toBeInTheDocument();
  });

  it("la stagionalita' e' un forest plot con il calendario anno per anno (FA-195)", async () => {
    const mese = (n: string, media: number, sig: boolean) => ({ mese: n, ...misura(media, 30), significativo: sig });
    risposte["/api/studio/stagionalita"] = {
      simbolo: "^GSPC",
      mesi: [mese("gen", 0.012, false), mese("apr", 0.0136, true)],
      base_mesi: misura(0.006, 360), giorni: [{ giorno: "lun", ...misura(0.0002, 900) }], base_giorni: misura(0.0003, 4500),
      confronti: 17, sopravvissuti: 4,
      calendario: { anni: [{ anno: 2025, mesi: Array(12).fill(0.01), anno_totale: 0.12, parziale: false }],
        media_mesi: Array(12).fill(0.01), positivi_mesi: Array(12).fill(0.6), casi_mesi: Array(12).fill(1), ultimo_mese: "2025-12" },
    };
    monta("/studio?simbolo=%5EGSPC&modello=stagionalita");
    expect(await screen.findByRole("img", { name: /Rendimento medio per mese di \^GSPC, con l'intervallo al 95%/ })).toBeInTheDocument();
    expect(screen.getByText(/Punto: media del mese; barra: intervallo al 95%/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Anno per anno" })).toBeInTheDocument();
  });

  it("toccare prima: la barra divisa con gli intervalli (FA-196)", async () => {
    risposte["/api/studio/primo_passaggio"] = {
      simbolo: "AAPL", disponibile: true, finestre: 120, target: 48, stop: 42, nessuno: 30,
      intervallo_target: [0.31, 0.49], intervallo_stop: [0.27, 0.44], intervallo_nessuno: [0.18, 0.33],
      dal: "2016-05-05", al: "2026-11-26", verdetto: "descritto",
    };
    monta("/studio?simbolo=AAPL&modello=primo_passaggio&target=8&stop=5&orizzonte=21");
    expect(await screen.findByText("prima l'obiettivo")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText(/48 su 120 · da 31% a 49%/)).toBeInTheDocument();
    expect(screen.getByText(/non una probabilità per domani/)).toBeInTheDocument();
  });

  it("cali e recuperi: il calo di oggi fra quelli della storia (FA-198)", async () => {
    risposte["/api/studio/cali"] = {
      simbolo: "^GSPC", soglia_pct: 10, dal: "1927-12-30",
      episodi: [{ picco: "2020-02-19", minimo: "2020-03-23", recupero: "2020-08-18", profondita: -0.339, sedute_discesa: 23, sedute_recupero: 103 }],
      numero: 30, recuperati: 29, profondita_mediana: -0.19, sedute_recupero_mediane: 250, sedute_discesa_mediane: 60,
      corrente: { profondita: -0.063, picco: "2026-10-06", sedute_dal_picco: 36 }, episodi_piu_profondi_del_corrente: 0,
      sott_acqua: [{ data: "2020-01-02", valore: 0 }, { data: "2020-03-23", valore: -0.339 }, { data: "2026-11-26", valore: -0.063 }],
    };
    monta("/studio?simbolo=%5EGSPC&modello=cali&soglia_cali=10");
    expect(await screen.findByText(/sotto il massimo del 6\/10\/2026/)).toBeInTheDocument();
    expect(screen.getByText("−33,9%")).toBeInTheDocument();
    expect(screen.getByText("103 sedute")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Distanza di \^GSPC dal massimo precedente/ })).toBeInTheDocument();
  });

  it("al netto di un riferimento lo dice nel titolo e nella frase (FA-197)", async () => {
    risposte["/api/studio/dopo_movimento"] = {
      simbolo: "AAPL", netto: "^GSPC", condizione: misura(0.01), base: misura(0.002), differenza: 0.008,
      intervallo_differenza: [-0.01, 0.02], verdetto: "compatibile_con_zero",
      parametri: { sedute: 5, soglia_pct: -10, orizzonte: 21 },
    };
    monta("/studio?simbolo=AAPL&modello=dopo_movimento&soglia=-10&sedute=5&orizzonte=21&netto=%5EGSPC");
    expect(await screen.findByRole("heading", { name: /AAPL · Dopo un movimento · al netto di S&P 500/ })).toBeInTheDocument();
    // Il titolo c'e' subito, la frase arriva con i dati.
    expect(await screen.findByText(/misurate in eccesso su S&P 500/)).toBeInTheDocument();
  });
});
