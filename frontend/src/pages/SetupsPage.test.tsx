import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SetupsPage from "./SetupsPage";
import { conditionKey } from "@/lib/setupGrouping";
import {
  LAST_SEEN_STALE_DAYS,
  type SetupDetectorStat,
  type SetupStats,
  type SetupsResponse,
} from "@/hooks/useSetups";

/* The backend went to some length to keep setups from masquerading as
 * predictions — no probability, a conversion rate that is null rather than 0
 * before anything resolves. All of that leaks away if the UI renders it
 * carelessly, so these tests guard the last step. */

const mockGet = vi.fn();
vi.mock("@/api/client", () => ({ api: (...args: unknown[]) => mockGet(...args) }));

/** ⚠️ `total`, `has_more` e `counts_by_detector` sono riempiti da qui quando il
 *  caso non li nomina, cosi' i casi che NON riguardano il perimetro restano
 *  leggibili. I test che lo riguardano li passano espliciti. */
type RispostaParziale = Pick<SetupsResponse, "setups" | "stats"> &
  Partial<SetupsResponse>;

/** La query string corrente, a schermo: la vista e il filtro vivono nell'URL. */
function Posizione() {
  return <output data-testid="url">{useLocation().search}</output>;
}

function renderWith(parziale: RispostaParziale, url = "/setups") {
  const data: SetupsResponse = {
    total: parziale.setups.length,
    has_more: false,
    counts_by_detector: parziale.setups.reduce<Record<string, number>>(
      (acc, s) => ({ ...acc, [s.detector]: (acc[s.detector] ?? 0) + 1 }), {}),
    ...parziale,
  };
  mockGet.mockResolvedValue(data);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <SetupsPage />
        <Posizione />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Le misure stanno in una vista loro (FA-066). */
/** Dal 2026-09-16 le misure stanno sopra la lista: nessuna vista dedicata. */
const MISURAZIONE = "/setups";

const setup = {
  id: 1,
  ticker: "AAPL",
  name: "Apple Inc.",
  detector: "oversold_reversal",
  tone: "bull",
  proximity: 0.85,
  distance_atr: 0.42,
  convenience: 72.4,
  missing: "la barra deve girare al livello 180.00",
  first_seen_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
  last_seen_at: new Date().toISOString(),
  annotations: { levels: [{ label: "Supporto", price: 180, kind: "support" }] },
};

const stats: SetupStats = {
  active: 1,
  converted: 0,
  expired: 0,
  closed: 0,
  total: 1,
  active_bull: 1,
  active_bear: 0,
  converted_positive: 0,
  converted_negative: 0,
  converted_pending: 0,
  median_lead_days: null,
  lead_days_min: null,
  lead_days_max: null,
  conversion_rate: null,
  avg_lead_days: null,
  converted_judged: 0,
  converted_hit_rate: null,
  converted_effective_n: 0,
  converted_horizon_days: null,
  converted_ci_low: null,
  converted_ci_high: null,
  converted_low_confidence: true,
  median_excess_pct: null,
  mean_excess_pct: null,
  median_return_pct: null,
  mean_return_pct: null,
  by_detector: [],
};

beforeEach(() => {
  mockGet.mockReset();
});

/* ─── FA-056: il perimetro della lista ─────────────────────────────────────
 *
 * Misurato in produzione: 1.415 setup attivi, 59 in shortlist, e la lista ne
 * rendeva 50. Filtro per detector e ordinamento lavoravano sul sottoinsieme
 * GIA' RICEVUTO, quindi un detector i cui setup cadevano oltre la
 * cinquantesima riga era irraggiungibile e i chip contavano la pagina.
 */
describe("SetupsPage — perimetro", () => {
  /** L'ultima query string che la pagina ha chiesto. */
  const ultimaUrl = () => String(mockGet.mock.calls.at(-1)?.[0] ?? "");

  it("i conteggi dei chip vengono dal SERVER, non dalle righe ricevute", async () => {
    renderWith({
      setups: [setup],                       // UNA riga in pagina...
      stats,
      total: 70,
      has_more: true,
      counts_by_detector: { [setup.detector]: 67, squeeze_expansion: 3 },
    });
    // ...ma il chip dice 67, perche' descrive la popolazione.
    expect(await screen.findByText("67")).toBeInTheDocument();
    // ⚠️ E il detector raro ha il suo chip anche se NESSUNA sua riga e' in
    // pagina: col conteggio lato client non sarebbe esistito, quindi non si
    // sarebbe potuto selezionare.
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("selezionare un detector lo chiede al server e torna alla prima pagina", async () => {
    renderWith({
      setups: [setup], stats, total: 70, has_more: true,
      counts_by_detector: { [setup.detector]: 67, squeeze_expansion: 3 },
    });
    await screen.findByText("67");

    await userEvent.click(screen.getByRole("button", { name: /Successivi/ }));
    await waitFor(() => expect(ultimaUrl()).toContain("offset=50"));

    await userEvent.click(screen.getByText("3").closest("button")!);
    await waitFor(() => expect(ultimaUrl()).toContain("detector=squeeze_expansion"));
    // ⚠️ L'offset e' tornato a zero: restare alla pagina 2 dopo aver cambiato
    // filtro mostrerebbe una fetta di mezzo di una popolazione DIVERSA, e la
    // pagina non direbbe niente.
    expect(ultimaUrl()).not.toContain("offset=");
  });

  it("l'ordinamento va al server", async () => {
    renderWith({ setups: [setup], stats, total: 70, has_more: true });
    await screen.findByText(/supporto 180\.00/i);
    await userEvent.selectOptions(screen.getByRole("combobox"), "waiting");
    await waitFor(() => expect(ultimaUrl()).toContain("sort=waiting"));
  });

  it("la paginazione compare solo quando c'e' altro da vedere", async () => {
    renderWith({ setups: [setup], stats, total: 1, has_more: false });
    await screen.findByText(/supporto 180\.00/i);
    // ⚠️ Il pavimento: senza, l'asserzione sulla comparsa sarebbe soddisfatta
    // anche da controlli sempre presenti.
    expect(screen.queryByRole("button", { name: /Successivi/ })).not.toBeInTheDocument();
  });

  it("dichiara che le misure contano TUTTI i setup del database", async () => {
    /* Decisione dell'utente, 2026-09-16: le misure non si limitano alla
     * shortlist, e la nota lo dice con il numero della popolazione accanto. */
    renderWith({
      setups: [setup],
      stats: { ...stats, scope: "all", total: 2267 },
      total: 70,
    }, MISURAZIONE);
    const nota = await screen.findByText(/tutti i setup registrati nel database/i);
    expect(nota.closest("p")?.textContent).toMatch(/2\.?267/);
  });

  it("il titolo degli esiti conta la POPOLAZIONE, non la pagina", async () => {
    /* Diceva "50 setup chiusi" perche' 50 erano le righe rese, su 795. */
    renderWith({
      setups: [{ ...setup, status: "converted" }],   // UNA riga in pagina
      stats,
      total: 795,
      has_more: true,
    }, "/setups?vista=esiti");
    expect(await screen.findByText(/Esiti — 795 setup chiusi/)).toBeInTheDocument();
  });

  it("ogni gruppo conta i titoli della condizione in tutta la popolazione", async () => {
    renderWith({
      setups: [setup],
      stats,
      total: 70,
      has_more: true,
      counts_by_condition: { [conditionKey(setup)]: 42 },
    });
    expect(await screen.findByText(/Setup attivi — 70 in 1 condizioni/)).toBeInTheDocument();
    // Il gruppo dice 42, non 1: la riga in pagina e' una sola.
    expect(screen.getByText("42")).toBeInTheDocument();
  });
});

describe("SetupsPage", () => {
  it("leads with what still has to happen — the actionable part", async () => {
    /* Unchanged in intent, changed in shape: the condition used to be printed
     * on every card and is now the heading its group is named after. What must
     * keep holding is that the wait is stated in words, prominently. */
    renderWith({ setups: [setup], stats });
    expect(
      await screen.findByText(/la barra deve chiudere sopra la sua apertura/i),
    ).toBeInTheDocument();
    // The trigger level stays on the row — it is what you would set an alert on.
    expect(screen.getByText(/supporto 180\.00/i)).toBeInTheDocument();
  });

  it("states the condition ONCE however many stocks are waiting for it", async () => {
    /* The redesign in one assertion. Fifty cards carried five distinct
     * sentences; three setups sharing a condition must now produce one
     * heading and three rows, not three copies of the sentence. */
    const three = [
      { ...setup, id: 1, ticker: "AAPL" },
      { ...setup, id: 2, ticker: "MSFT", missing: "la barra deve girare al livello 400.00" },
      { ...setup, id: 3, ticker: "NVDA", missing: "la barra deve girare al livello 120.00" },
    ];
    renderWith({ setups: three, stats: { ...stats, active: 3 } });
    expect(
      await screen.findAllByText(/la barra deve chiudere sopra la sua apertura/i),
    ).toHaveLength(1);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    // The count sits in its own <b>, so the text spans two nodes — match on
    // the heading's normalised content rather than on a single element.
    const heading = screen
      .getByText(/la barra deve chiudere sopra la sua apertura/i)
      .closest("div")!;
    expect(heading.textContent!.replace(/\s+/g, " ")).toMatch(/3 titoli/i);
  });

  it("states how long the setup has been waiting — lead time is the product", async () => {
    renderWith({ setups: [setup], stats });
    // Now a compact "3g" beside a clock rather than the sentence, because at
    // fifty rows the sentence was a second line per row.
    expect(await screen.findByText("3g")).toBeInTheDocument();
  });

  it("never labels anything a probability", async () => {
    renderWith({ setups: [setup], stats });
    await screen.findByText(/la barra deve chiudere sopra la sua apertura/i);
    // Setups have no base rate; borrowing the signals' vocabulary would imply
    // a calibration that does not exist for them.
    expect(screen.queryByText(/probabilit/i)).not.toBeInTheDocument();
  });

  it("does not show the gate-chain share as a per-setup number", async () => {
    /* Measured on live data: `proximity` had ONE distinct value across the 20
     * trend_pullback setups and one across the 15 oversold_reversal ones. It
     * counts a fixed chain, so it belongs to the detector. Rendering it per
     * row — as a bar with a big percentage, which is what the cards did —
     * promised a variation that does not exist. It now appears once per group,
     * labelled "catena". */
    renderWith({ setups: [setup], stats });
    await screen.findByText(/la barra deve chiudere sopra la sua apertura/i);
    expect(screen.getByText(/catena 85%/i)).toBeInTheDocument();
    // ...and nowhere on the row itself.
    expect(screen.queryAllByText(/^85%$/)).toHaveLength(0);
  });

  it("shows an unresolved conversion rate as unknown, not as 0%", async () => {
    renderWith({ setups: [setup], stats }, MISURAZIONE);
    expect(await screen.findByText(/nessuno ancora risolto/i)).toBeInTheDocument();
    // "0%" would read as "setups never work" — a claim the data does not make.
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("shows a small resolved sample as a fraction, not as a percentage", async () => {
    /* This test used to assert "75%" on 3-of-4, which enshrined the defect:
     * a percentage in 2xl bold claims a rate, and four observations cannot
     * carry one. The live page was showing "100%" on six. The fraction says
     * exactly as much and claims nothing. */
    renderWith({
      setups: [setup],
      stats: {
        ...stats, active: 1, converted: 3, expired: 1, closed: 4,
        conversion_rate: 0.75, avg_lead_days: 2.5,
        median_lead_days: 2, lead_days_min: 1, lead_days_max: 6,
      },
    }, MISURAZIONE);
    expect(await screen.findByText("3/4")).toBeInTheDocument();
    expect(screen.queryByText("75%")).not.toBeInTheDocument();
    expect(screen.getByText(/troppo pochi per un tasso/i)).toBeInTheDocument();
    // The lead-time tile leads with the MEDIAN and keeps the mean in the
    // detail line. One mean cannot say whether the warning was reliably a
    // week or anywhere from a day to a month, and the wait is the product.
    expect(screen.getByText("2g")).toBeInTheDocument();
    expect(screen.getByText(/da 1g a 6g · media 2\.5g/)).toBeInTheDocument();
  });

  it("a perfect small record does not get to say 100%", async () => {
    // The observed live case: six converted, none expired.
    renderWith({
      setups: [setup],
      stats: { ...stats, active: 4, converted: 6, expired: 0, closed: 6, conversion_rate: 1, avg_lead_days: 3 },
    }, MISURAZIONE);
    expect(await screen.findByText("6/6")).toBeInTheDocument();
    expect(screen.queryByText("100%")).not.toBeInTheDocument();
  });

  it("renders a real conversion rate once the sample can carry one", async () => {
    renderWith({
      setups: [setup],
      stats: { ...stats, active: 1, converted: 18, expired: 6, closed: 24, conversion_rate: 0.75, avg_lead_days: 2.5 },
    }, MISURAZIONE);
    expect(await screen.findByText("75%")).toBeInTheDocument();
    expect(screen.getByText(/18 su 24/)).toBeInTheDocument();
    expect(screen.queryByText(/troppo pochi/i)).not.toBeInTheDocument();
  });

  it("«Esiti» conta TUTTI i chiusi e nomina a parte il denominatore del tasso", async () => {
    // I numeri di produzione del 2026-09-16: la tessera mostrava 695 (il
    // denominatore) sotto il nome di 797 (i chiusi).
    renderWith({
      setups: [setup],
      stats: {
        ...stats, converted: 334, expired: 361, closed: 695, decayed: 102,
        excluded_from_rate: 102, closed_total: 797, closed_without_reason: 322,
        conversion_rate: 0.481,
      },
    }, MISURAZIONE);
    expect(await screen.findByText("797")).toBeInTheDocument();
    expect(screen.queryByText("695")).not.toBeInTheDocument();
    expect(screen.getByText(/102 fuori dal tasso · 322 senza ragione registrata/)).toBeInTheDocument();
    expect(screen.getByText(/334 su 695 inclusi nel tasso/)).toBeInTheDocument();
  });

  it("una maggioranza di positivi su un campione non concludente non prende colore", async () => {
    const { container } = renderWith({
      setups: [setup],
      stats: {
        ...stats, converted: 334, expired: 361, closed: 695, conversion_rate: 0.481,
        converted_positive: 45, converted_negative: 38, converted_judged: 83,
        converted_hit_rate: 54.2, converted_ci_low: 6.4, converted_ci_high: 95.4,
        converted_effective_n: 1, converted_low_confidence: true,
        median_excess_pct: 0.82, median_return_pct: 1.5,
        converted_pending: 120, converted_outcome_unavailable: 156,
      },
    }, MISURAZIONE);
    expect(await screen.findByText("54%")).toBeInTheDocument();
    // Una tessera sola: la vecchia «Convertiti: esito» non c'e' piu'.
    expect(screen.queryByText(/Convertiti: esito/)).not.toBeInTheDocument();
    expect(screen.getByText(/45 positivi · 38 negativi/)).toBeInTheDocument();
    expect(screen.getByText(/non concludente · 120 in attesa · 156 non misurabili/)).toBeInTheDocument();
    // Ne' l'efficacia ne' il rendimento si colorano: l'intervallo contiene 50.
    expect(container.querySelector("[data-metrica] .text-emerald-800")).toBeNull();
    expect(container.querySelector("[data-metrica] .text-rose-700")).toBeNull();
  });

  it("il colore arriva quando l'intervallo esclude il 50", async () => {
    const { container } = renderWith({
      setups: [setup],
      stats: {
        ...stats, converted: 30, expired: 10, closed: 40, conversion_rate: 0.75,
        converted_positive: 400, converted_negative: 200, converted_judged: 600,
        converted_hit_rate: 66.7, converted_ci_low: 58, converted_ci_high: 74,
        converted_effective_n: 60, converted_low_confidence: false,
        median_excess_pct: 1.2, median_return_pct: 2,
      },
    }, MISURAZIONE);
    expect(await screen.findByText("67%")).toBeInTheDocument();
    expect(container.querySelectorAll("[data-metrica] .text-emerald-800").length).toBe(2);
  });

  it("filtri, ordinamento e pagina si leggono dall'URL: il ritorno li ritrova", async () => {
    // Collaudo in browser, 2026-09-16: filtrati i ribassisti di una condizione,
    // aperto un titolo e tornati indietro, la lista ripartiva da «Tutti».
    renderWith(
      { setups: [setup], stats, total: 120, has_more: true },
      "/setups?tono=ribassisti&condizione=oversold_reversal&ordina=waiting&pagina=2",
    );
    await screen.findByText(/51–51 di 120/);
    const chiesta = String(mockGet.mock.calls.at(-1)?.[0] ?? "");
    expect(chiesta).toContain("tone=bear");
    expect(chiesta).toContain("detector=oversold_reversal");
    expect(chiesta).toContain("sort=waiting");
    expect(chiesta).toContain("offset=50");
    expect(screen.getByRole("button", { name: "Ribassisti" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox")).toHaveValue("waiting");
  });

  it("un filtro scrive l'URL e riporta alla prima pagina", async () => {
    renderWith({ setups: [setup], stats, total: 120, has_more: true }, "/setups?pagina=3");
    await screen.findByText(/101–101 di 120/);
    await userEvent.click(screen.getByRole("button", { name: "Rialzisti" }));
    await waitFor(() =>
      expect(screen.getByTestId("url").textContent).toBe("?tono=rialzisti"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Tutti" }));
    await waitFor(() => expect(screen.getByTestId("url").textContent).toBe(""));
  });

  it("un valore sconosciuto nell'URL vale il default, non una lista vuota", async () => {
    renderWith({ setups: [setup], stats }, "/setups?tono=qualcosa&ordina=boh&pagina=-4");
    await screen.findByText(/nessun setup in formazione|Setup attivi/i);
    const chiesta = String(mockGet.mock.calls.at(-1)?.[0] ?? "");
    expect(chiesta).not.toContain("tone=");
    expect(chiesta).not.toContain("offset=");
    expect(chiesta).toContain("sort=convenience");
  });

  it("explains the empty state instead of looking broken", async () => {
    renderWith({ setups: [], stats: { ...stats, active: 0 } });
    expect(await screen.findByText(/nessun setup in formazione/i)).toBeInTheDocument();
  });
});

/* ─── FA-066: la lista davanti, le misure in una vista loro ─────────────── */

const rigaDetector: SetupDetectorStat = {
  detector: "oversold_reversal", converted: 3, expired: 1, resolved: 4,
  conversion_rate: 75, judged: 2, positive: 1, negative: 1, hit_rate: 50,
  effective_n: 2, horizon_days: 21, ci_low: 10, ci_high: 90,
  low_confidence: true, median_excess_pct: 0.5,
};

describe("SetupsPage — le viste (FA-066)", () => {
  const ultimaUrl = () => String(mockGet.mock.calls.at(-1)?.[0] ?? "");

  it("le misure stanno SOPRA la lista, con le principali in evidenza", async () => {
    /* Richiesta dell'utente, 2026-09-16: niente vista «Misurazione». */
    const { container } = renderWith({ setups: [setup], stats: { ...stats, by_detector: [rigaDetector] } });
    const lista = await screen.findByText(/la barra deve chiudere sopra la sua apertura/i);
    const misure = screen.getByRole("region", { name: "Misure dei setup" });
    // Sopra: nell'ordine del documento le misure precedono la lista.
    expect(misure.compareDocumentPosition(lista) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const principali = [...container.querySelectorAll('[data-metrica="principale"]')]
      .map((el) => el.textContent ?? "");
    expect(principali).toHaveLength(4);
    expect(principali.some((x) => /tasso conversione/i.test(x))).toBe(true);
    expect(principali.some((x) => /anticipo mediano/i.test(x))).toBe(true);
    expect(screen.queryByRole("button", { name: "Misurazione" })).not.toBeInTheDocument();
  });

  it("la tabella per tipo di setup si apre a richiesta", async () => {
    renderWith({ setups: [setup], stats: { ...stats, by_detector: [rigaDetector] } });
    const bottone = await screen.findByRole("button", { name: /le misure per tipo di setup/i });
    expect(bottone).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("heading", { name: /per tipo di setup/i })).not.toBeInTheDocument();
    await userEvent.click(bottone);
    expect(bottone).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("heading", { name: /per tipo di setup/i })).toBeInTheDocument();
  });

  it("la vista vive nell'URL, e il default non si scrive", async () => {
    renderWith({ setups: [setup], stats });
    await screen.findByText(/la barra deve chiudere sopra la sua apertura/i);

    await userEvent.click(screen.getByRole("button", { name: "Esiti" }));
    await waitFor(() => expect(screen.getByTestId("url")).toHaveTextContent("vista=esiti"));
    expect(screen.getByRole("button", { name: "Esiti" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "In formazione" })).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(screen.getByRole("button", { name: "In formazione" }));
    expect(await screen.findByText(/la barra deve chiudere sopra la sua apertura/i)).toBeInTheDocument();
    expect(screen.getByTestId("url")).not.toHaveTextContent("vista");
  });

  it("«Esiti» chiede al server i setup chiusi", async () => {
    renderWith({ setups: [], stats }, "/setups?vista=esiti");
    await waitFor(() => expect(ultimaUrl()).toContain("status=closed"));
  });

  it("una vista sconosciuta apre la lista invece di una pagina vuota", async () => {
    renderWith({ setups: [setup], stats }, "/setups?vista=qualcosaltro");
    expect(
      await screen.findByText(/la barra deve chiudere sopra la sua apertura/i),
    ).toBeInTheDocument();
  });

  it("?ticker= filtra sul server, si vede, e si toglie", async () => {
    renderWith({ setups: [setup], stats }, "/setups?ticker=aapl");
    await waitFor(() => expect(ultimaUrl()).toContain("ticker=AAPL"));

    await userEvent.click(await screen.findByRole("button", { name: /solo AAPL/i }));

    await waitFor(() => expect(ultimaUrl()).not.toContain("ticker="));
    expect(screen.getByTestId("url")).not.toHaveTextContent("ticker");
  });

  it("con un titolo filtrato le misure dicono che non sono solo di quel titolo", async () => {
    /* `conversion_stats` non guarda i filtri: accanto a «Solo AAPL» la nota
     * deve dire che i numeri sono di tutti i titoli. */
    renderWith({ setups: [setup], stats }, "/setups?ticker=AAPL");
    const nota = await screen.findByText(/tutti i setup registrati nel database/i);
    expect(nota.closest("p")?.textContent).toMatch(/non solo AAPL/);
  });

  it("dice quando un setup non viene rivisto da giorni, e solo allora", async () => {
    const giorniFa = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();
    renderWith({
      setups: [
        { ...setup, id: 1, ticker: "AAPL" },
        { ...setup, id: 2, ticker: "MSFT", last_seen_at: giorniFa(LAST_SEEN_STALE_DAYS - 1) },
        { ...setup, id: 3, ticker: "NVDA", last_seen_at: giorniFa(LAST_SEEN_STALE_DAYS) },
      ],
      stats: { ...stats, active: 3 },
    });
    expect(await screen.findByText(`visto ${LAST_SEEN_STALE_DAYS}g fa`)).toBeInTheDocument();
    // Una riga sola: sotto la soglia e' la cadenza della scansione, e «visto
    // oggi» su ogni riga sarebbe rumore che nasconde quella che conta.
    expect(screen.getAllByText(/^visto /)).toHaveLength(1);
  });
});
