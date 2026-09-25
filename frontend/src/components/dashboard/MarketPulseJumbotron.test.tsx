import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CalendarEvent, IndexBreadth, MarketGlobal, MoversBlock } from "@/api/types";
import type { LiveAsset } from "@/hooks/useLiveAssets";

/* Le interrogazioni vive sono finte: qui si verifica cosa la fascia DICHIARA a
 * partire da un certo stato del mondo, non la rete. I finti RESTITUISCONO
 * sempre — nessuno lancia — perche' un `vi.fn()` che lancia fa fallire il test
 * anche quando l'errore e' gestito (CLAUDE.md, trappole dell'armamentario). */
let assets: LiveAsset[] = [];
let premarket: unknown = undefined;
let liveMovers: unknown = undefined;
let eventi: CalendarEvent[] = [];
/** Quotazioni del paniere a leva (`/api/stocks/quotes`). */
let quotazioni: unknown[] = [];

vi.mock("@/hooks/useLiveAssets", () => ({
  useLiveAssets: () => ({ data: { assets }, isLoading: false }),
}));
vi.mock("@/hooks/usePremarketMovers", () => ({
  usePremarketMovers: () => ({ data: premarket }),
}));
vi.mock("@/hooks/useLiveUniverseMovers", () => ({
  useLiveUniverseMovers: () => ({ data: liveMovers }),
}));
vi.mock("@/hooks/useCalendar", () => ({
  useCalendar: () => ({ data: { events: eventi } }),
}));
vi.mock("@/hooks/useLiveQuote", () => ({
  useLiveQuotes: () => ({ data: { quotes: quotazioni } }),
}));

const { MarketPulseJumbotron } = await import("./MarketPulseJumbotron");

function indice(symbol: string, opts: Partial<LiveAsset> & { change?: number } = {}): LiveAsset {
  const { change = 0.5, ...resto } = opts;
  return {
    symbol,
    name: symbol,
    category: "index",
    flag: "us",
    history: null,
    quote: {
      ticker: symbol, price: 100, prev_close: 99, change_abs: 1, change_pct: change,
      day_open: null, day_high: null, day_low: null, volume: null,
      market_state: "OPEN", currency: "USD", fetched_at: 1, error: null,
    },
    ...resto,
  } as LiveAsset;
}

function mover(ticker: string, change_pct: number, extra: Record<string, unknown> = {}) {
  return {
    // Il nome e' DIVERSO dal simbolo di proposito: con i due uguali una
    // ricerca per testo trova due nodi e non distingue la colonna che li
    // porta — il test passerebbe anche se una delle due sparisse.
    ticker, name: `${ticker} Inc.`, price: 100, prev_close: 99, change_pct,
    volume: 500_000, instrument_type: "equity", ...extra,
  };
}

const AMERICANE = ["^GSPC", "^IXIC", "^DJI"];

/** Venerdi' 18 settembre 2026, 15:00 a New York: seduta in corso secondo
 *  l'orologio. E' l'unico istante in cui la domanda «e' davvero aperta?» ha un
 *  senso, ed e' quello su cui i dati possono smentire il calendario. */
const SEDUTA = new Date("2026-09-18T19:00:00Z");
/** 08:00 a New York: dentro la finestra del pre-market. */
const PREMARKET = new Date("2026-09-18T12:00:00Z");

const GLOBAL: MarketGlobal = {
  stocks_total: 998, stocks_with_data: 993, advancers: 639, decliners: 348,
  unchanged: 6, avg_change_pct: 0.77, pct_above_ema200: 51.9, pct_above_ema50: 33.7,
  rsi_oversold_count: 62, rsi_overbought_count: 16, near_52w_high_count: 158,
  near_52w_low_count: 125, mood: "bullish",
};
const PER_INDICE: IndexBreadth[] = [
  { code: "SP500", name: "S&P 500", n: 500, pct_above_ema200: 55, pct_above_ema50: 40,
    rsi_oversold_count: 10, rsi_overbought_count: 8, avg_change_pct: 0.4,
    advancers: 300, decliners: 190, new_52w_highs: 40, new_52w_lows: 5,
    volume_spikes_count: 12 },
];

/** I movers della SEDUTA, cioe' il ripiego sempre disponibile del riquadro
 *  «si muove adesso». Pochi campi: la riga ne rende tre. */
const SEDUTA_MOVERS = {
  gainers: [{ ticker: "SALE", name: "Sale SpA", index: null, sector: null,
    change_pct: 7.1, last_close: 42.5, prev_close: 39.7 }],
  losers: [{ ticker: "SCENDE", name: "Scende SpA", index: null, sector: null,
    change_pct: -5.4, last_close: 12.0, prev_close: 12.7 }],
  volume_spikes: [], new_52w_high: [], new_52w_low: [],
} as unknown as MoversBlock;

function montaA(
  istante: Date, global?: MarketGlobal, computedAt?: string, movers?: MoversBlock,
) {
  vi.setSystemTime(istante);
  return render(
    <MemoryRouter>
      <MarketPulseJumbotron
        global={global} byIndex={PER_INDICE} computedAt={computedAt} movers={movers}
      />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  assets = [];
  premarket = undefined;
  liveMovers = undefined;
  eventi = [];
  quotazioni = [];
});
afterEach(() => vi.useRealTimers());

describe("la fase la dicono i dati, non l'orologio", () => {
  it("con le americane sul cash durante la seduta dice che Wall Street e' aperta", () => {
    assets = AMERICANE.map((s) => indice(s, { using_futures: false, is_live: true }));
    const { container } = montaA(SEDUTA);
    expect(screen.getByText("Wall Street aperta")).toBeInTheDocument();
    // Il pallino «live» ha un RUOLO, altrimenti il suo `aria-label` sarebbe un
    // attributo proibito su uno span generico; e cercarlo per ruolo prova che
    // il ramo viene reso davvero.
    expect(screen.getAllByRole("img", { name: "prezzo live" })).toHaveLength(3);
    // Un commento JSX fuori posto finirebbe a schermo come testo.
    expect(container.textContent).not.toContain("aria-prohibited-attr");
  });

  it("⚠️ se alle 15:00 di New York TUTTE e tre sono sul future, la borsa e' chiusa", () => {
    /* E' il giorno di festa: nessun calendario scritto a mano lo saprebbe, e
     * una lista di date invecchia in silenzio proprio quando conta. Il backend
     * scambia il cash col future SOLO quando il cash non e' aperto, quindi lo
     * scambio E' la prova. */
    assets = AMERICANE.map((s) => indice(s, { using_futures: true }));
    montaA(SEDUTA);
    expect(screen.getByText(/non e' un giorno di seduta/)).toBeInTheDocument();
    expect(screen.queryByText("Wall Street aperta")).not.toBeInTheDocument();
  });

  it("una sola sul future non basta a dichiarare chiusa la borsa", () => {
    // Controllo negativo del caso sopra: serve che siano tutte, altrimenti un
    // singolo simbolo che non risponde spegnerebbe la seduta.
    assets = [
      indice("^GSPC", { using_futures: true }),
      indice("^IXIC", { using_futures: false }),
      indice("^DJI", { using_futures: false }),
    ];
    montaA(SEDUTA);
    expect(screen.getByText("Wall Street aperta")).toBeInTheDocument();
  });

  it("senza nessun dato live resta l'orologio, che a quell'ora dice aperta", () => {
    montaA(SEDUTA);
    expect(screen.getByText("Wall Street aperta")).toBeInTheDocument();
  });
});

describe("quello che non si sa non diventa un numero", () => {
  it("un indice senza quotazione dice n/d, non 0,00%", () => {
    /* «S&P 500 0,00%» non e' una cella vuota: e' l'affermazione che l'indice
     * non si e' mosso, resa con la stessa sicurezza di un dato vero. */
    assets = [{
      symbol: "^GSPC", name: "S&P 500", category: "index", flag: "us",
      history: null, quote: null,
    } as LiveAsset];
    const { container } = montaA(SEDUTA);
    expect(screen.getAllByText("n/d").length).toBeGreaterThan(0);
    expect(container.textContent).not.toContain("0,00%");
  });

  it("fuori dalle finestre live mostra i TOP DELLA SEDUTA, non un messaggio", () => {
    /* ⚠️ Sabato, o un pomeriggio italiano prima dell'apertura: il riquadro
     * diceva «niente da mostrare in tempo reale» — vero e inutile, perche' i
     * movers della seduta erano nell'istantanea che la pagina aveva gia'
     * scaricato. E' per questo che non poteva sostituire la scheda sotto. */
    montaA(new Date("2026-09-19T15:00:00Z"), GLOBAL, undefined, SEDUTA_MOVERS);
    expect(screen.getByText("Top della seduta")).toBeInTheDocument();
    expect(screen.getByText("SALE")).toBeInTheDocument();
    expect(screen.getByText("SCENDE")).toBeInTheDocument();
    // ⚠️ E DICE che non e' live: un dato di chiusura accanto a numeri che
    // battono ogni quindici secondi si legge come fresco se nessuno lo nega.
    expect(screen.getByText(/ultima chiusura dell'istantanea/)).toBeInTheDocument();
    // E quindi niente punto che lampeggia: un'istantanea di chiusura non e'
    // un dato live, e il punto direbbe il contrario della fonte scritta.
    expect(screen.queryByRole("img", { name: "dati live" })).not.toBeInTheDocument();
  });

  it("senza nemmeno l'istantanea dice PERCHE' e' vuoto", () => {
    // Controllo negativo del test sopra, e la vecchia dottrina: «nessun dato»
    // manderebbe a cercare un guasto che non esiste.
    montaA(new Date("2026-09-19T15:00:00Z"));
    expect(screen.getByText(/istantanea dei movers non è ancora arrivata/)).toBeInTheDocument();
    expect(screen.queryByText("Top della seduta")).not.toBeInTheDocument();
  });
});

describe("i numeri parlano una lingua sola", () => {
  it("il punto separa le migliaia e la virgola i decimali, nella stessa riga", () => {
    /* ⚠️ Il difetto misurato a schermo: «NIKKEI 65.620» accanto ad «ARGENTO
     * 67.63». Lo stesso segno per due significati, a due centimetri. */
    assets = [
      indice("^N225", { category: "index", flag: "jp",
        quote: { price: 65620, change_pct: 0.6 } as LiveAsset["quote"] }),
      indice("SI=F", { category: "commodity", flag: null,
        quote: { price: 67.63, change_pct: 1.57 } as LiveAsset["quote"] }),
    ];
    montaA(SEDUTA);
    expect(screen.getByText("65.620")).toBeInTheDocument();
    expect(screen.getByText("67,63")).toBeInTheDocument();
    expect(screen.getByText("+1,57%")).toBeInTheDocument();
  });

  it("raggruppa il contesto invece di allinearlo tutto uguale", () => {
    assets = [
      indice("^N225", { category: "index" }),
      indice("GC=F", { category: "commodity" }),
      indice("BTC-USD", { category: "crypto" }),
    ];
    montaA(SEDUTA);
    expect(screen.getByText("Indici")).toBeInTheDocument();
    expect(screen.getByText("Materie prime")).toBeInTheDocument();
    expect(screen.getByText("Cripto")).toBeInTheDocument();
  });
});

describe("la riga ETF e le icone", () => {
  it("mostra gli ETF a leva con la loro quotazione, sotto il nome «ETF»", () => {
    quotazioni = [
      { ticker: "YINN", price: 23.45, change_pct: 2.1, market_state: "OPEN" },
      { ticker: "NUGT", price: 88.2, change_pct: -1.4, market_state: "OPEN" },
    ];
    montaA(SEDUTA);
    // «Leva» e' diventato «ETF»: la riga ora porta anche i fondi che si
    // muovono nel pre-market, e non tutti sono a leva.
    expect(screen.getByText("ETF")).toBeInTheDocument();
    expect(screen.queryByText("Leva")).not.toBeInTheDocument();
    expect(screen.getByText("YINN")).toBeInTheDocument();
    expect(screen.getByText("23,45")).toBeInTheDocument();
    expect(screen.getByText("NUGT")).toBeInTheDocument();
    expect(screen.getByText("−1,40%")).toBeInTheDocument();
  });

  it("⚠️ un ETF senza quotazione resta a schermo come n/d, non sparisce", () => {
    /* Se il titolo non e' in catalogo, `/api/stocks/quotes` non lo rende e la
     * voce sparirebbe in silenzio: l'utente vedrebbe una fascia coerente e non
     * saprebbe che manca. YINN e' esattamente questo caso — non aveva una riga
     * in catalogo, e per questo non si trovava nemmeno dalla ricerca. */
    quotazioni = [{ ticker: "NUGT", price: 88.2, change_pct: -1.4, market_state: "OPEN" }];
    montaA(SEDUTA);
    expect(screen.getByText("YINN")).toBeInTheDocument();
    const senzaQuota = screen.getByTitle(/YINN: quotazione non disponibile/);
    expect(senzaQuota.textContent).toBe("n/d");
  });

  it("chi non ha una bandiera ha un'icona: oro, petrolio, bitcoin", () => {
    // Senza un segno la riga di contesto e' una fila di parole tutte uguali.
    // Le bandiere restano `<img>`, le altre classi diventano un glifo.
    assets = [
      indice("^N225", { category: "index", flag: "jp" }),
      indice("GC=F", { category: "commodity", flag: null }),
      indice("BTC-USD", { category: "crypto", flag: null }),
    ];
    montaA(SEDUTA);
    const nikkei = screen.getByText("Nikkei").closest("a")!;
    const oro = screen.getByText("Oro").closest("a")!;
    const btc = screen.getByText("Bitcoin").closest("a")!;
    expect(nikkei.querySelector("img")).not.toBeNull();
    expect(oro.querySelector("img")).toBeNull();
    expect(oro.querySelector("svg")).not.toBeNull();
    expect(btc.querySelector("svg")).not.toBeNull();
  });
});

describe("i riquadri delle americane", () => {
  it("portano la bandiera, i punti e l'apertura accanto alla percentuale", () => {
    /* La percentuale su un indice a cinque cifre non da' la misura del
     * movimento, e un indice sopra o sotto la propria apertura racconta due
     * sedute diverse a parita' di segno. */
    assets = [indice("^GSPC", {
      quote: {
        price: 7622, change_pct: -0.2, change_abs: -15.3, day_open: 7640,
        day_low: 7620, day_high: 7657, market_state: "OPEN",
      } as LiveAsset["quote"],
    })];
    const { container } = montaA(SEDUTA);
    expect(screen.getByText("−15,30 pt")).toBeInTheDocument();
    expect(screen.getByText("ap. 7.640")).toBeInTheDocument();
    expect(container.querySelector('img[src="/flags/us.svg"]')).not.toBeNull();
  });
});

describe("la riga di contesto sta allineata", () => {
  it("⚠️ nessun separatore verticale fra i gruppi", () => {
    /* Ce n'era uno davanti a ogni gruppo tranne il primo, e quando la riga
     * andava a capo il gruppo che apriva la riga nuova se lo portava dietro:
     * «CRIPTO» partiva piu' a destra di «INDICI», per un tratto che li' non
     * separava niente. Il CSS non sa dove cade il ritorno a capo, quindi
     * l'unica forma che regge e' non averlo. */
    assets = [
      indice("^N225", { category: "index" }),
      indice("GC=F", { category: "commodity" }),
      indice("BTC-USD", { category: "crypto" }),
    ];
    montaA(SEDUTA);
    const contesto = screen.getByText("Indici").closest("div")!;
    expect(contesto.querySelectorAll(".w-px")).toHaveLength(0);
    // Controllo negativo: il gruppo c'e' davvero, quindi «zero separatori» non
    // e' il risultato di una riga che non e' stata resa.
    expect(contesto.textContent).toContain("Cripto");
  });

  it("le icone di materie prime e cripto sono a colori, e non sono la palette direzionale", () => {
    // Ambra = oro, indaco = il rombo di Ethereum: dicono DI COSA si parla.
    // Verde e rosa restano riservati al verso del prezzo.
    // ⚠️ `flag: null` non e' un dettaglio: la fixture mette "us" di default e
    // la bandiera VINCE sull'icona, quindi senza questa riga si misurerebbe
    // un ramo che in produzione non esiste per oro e cripto.
    assets = [
      indice("GC=F", { category: "commodity", flag: null }),
      indice("ETH-USD", { category: "crypto", flag: null }),
    ];
    const { container } = montaA(SEDUTA);
    const oro = screen.getByText("Oro").closest("a")!;
    const eth = screen.getByText("Ethereum").closest("a")!;
    expect(oro.querySelector("svg")?.getAttribute("class")).toContain("text-amber-500");
    expect(eth.querySelector("svg")?.getAttribute("class")).toContain("text-indigo-400");
    expect(container.querySelector("svg.text-emerald-500")).toBeNull();
  });
});

describe("«si muove adesso» lavora come la scheda Top movers", () => {
  it("mostra dieci righe per lato, non quattro", () => {
    liveMovers = {
      swept: 786,
      gainers: Array.from({ length: 14 }, (_, i) => ({
        ticker: `SU${i}`, name: `Su ${i}`, change_pct: 10 - i * 0.1, price: 100 + i,
      })),
      losers: Array.from({ length: 14 }, (_, i) => ({
        ticker: `GIU${i}`, name: `Giu ${i}`, change_pct: -10 + i * 0.1, price: 50 + i,
      })),
    };
    montaA(SEDUTA);
    expect(screen.getByText("SU9")).toBeInTheDocument();
    expect(screen.queryByText("SU10")).not.toBeInTheDocument();
    expect(screen.getByText("GIU9")).toBeInTheDocument();
    expect(screen.queryByText("GIU10")).not.toBeInTheDocument();
  });

  it("ogni riga porta il prezzo accanto alla variazione", () => {
    // Un +9% su un titolo da 2 dollari e uno su un titolo da 400 non sono la
    // stessa notizia, e senza il prezzo la riga non lo dice.
    liveMovers = {
      swept: 10,
      gainers: [{ ticker: "MSTR", name: "MicroStrategy", change_pct: 9.19, price: 412.5 }],
      losers: [],
    };
    montaA(SEDUTA);
    expect(screen.getByText("+9,19%")).toBeInTheDocument();
    expect(screen.getByText("412,50")).toBeInTheDocument();
  });

  it("dichiara che e' live col punto, e il campione sta nel suo suggerimento", () => {
    liveMovers = {
      swept: 786,
      gainers: [{ ticker: "MSTR", name: "MicroStrategy", change_pct: 9.19, price: 412.5 }],
      losers: [],
    };
    montaA(SEDUTA);
    const punto = screen.getByRole("img", { name: "dati live" });
    expect(punto).toHaveAttribute("title", expect.stringContaining("786 titoli"));
  });

  it("senza i titoletti «Su» e «Giù»: il verso lo dice il colore", () => {
    liveMovers = {
      swept: 10,
      gainers: [{ ticker: "MSTR", name: "MicroStrategy", change_pct: 9.19, price: 412.5 }],
      losers: [{ ticker: "NUE", name: "Nucor", change_pct: -2.36, price: 258.88 }],
    };
    montaA(SEDUTA);
    expect(screen.queryByText("Su")).not.toBeInTheDocument();
    expect(screen.queryByText("Giù")).not.toBeInTheDocument();
    // ⚠️ Ma chi non vede il colore sente ancora quale lista e' quale.
    expect(screen.getByRole("group", { name: "In rialzo" })).toHaveTextContent("MSTR");
    expect(screen.getByRole("group", { name: "In ribasso" })).toHaveTextContent("NUE");
  });
});

describe("l'ampiezza non si spaccia per un dato live", () => {
  it("dice quanto e' VECCHIA, non a che ora e' stata presa", () => {
    /* «istantanea delle 23:54» letto alle 10:34 del mattino dopo si legge come
     * recente, e quel dato ha undici ore. L'eta' relativa non si puo'
     * fraintendere. */
    montaA(SEDUTA, GLOBAL, new Date(SEDUTA.getTime() - 11 * 3600_000).toISOString());
    expect(screen.getByText("11h fa")).toBeInTheDocument();
  });

  it("⚠️ TRE continenti confrontabili, non un umore unico", () => {
    /* Un solo verdetto sul catalogo intero media tre mercati che quel giorno
     * possono fare cose opposte: «Neutrale» nasceva da un'America ferma,
     * un'Europa in rosso e un'Asia in verde — tre notizie, nessuna delle quali
     * era «neutrale». */
    montaA(SEDUTA, GLOBAL, SEDUTA.toISOString());
    for (const continente of ["USA", "Europa", "Asia"]) {
      expect(screen.getByText(continente)).toBeInTheDocument();
    }
    // I conteggi dell'unica regione MISURATA dalla fixture (solo SP500).
    expect(screen.getByText("300")).toBeInTheDocument();
    expect(screen.getByText("190")).toBeInTheDocument();
  });

  it("una regione senza titoli lo DICE, invece di disegnare uno zero", () => {
    /* ⚠️ Il controllo che conta in una vista confrontabile: una barra vuota
     * accanto a «Neutrale» si legge come un verdetto sul mercato europeo,
     * mentre e' l'assenza di una misura. La fixture ha il solo S&P 500,
     * quindi Europa e Asia non hanno titoli. */
    montaA(SEDUTA, GLOBAL, SEDUTA.toISOString());
    expect(screen.getAllByText("nessun titolo misurato")).toHaveLength(2);
    expect(screen.getAllByText("n/d").length).toBeGreaterThanOrEqual(2);
  });

  it("le misure che NON hanno un equivalente regionale restano dichiarate globali", () => {
    // I conteggi 52 settimane del globale contano i titoli VICINI
    // all'estremo, quelli per indice i NUOVI estremi: due definizioni, e
    // spacchettarle a occhio darebbe due numeri con lo stesso nome.
    montaA(SEDUTA, GLOBAL, SEDUTA.toISOString());
    expect(screen.getByText("993")).toBeInTheDocument();     // catalogo
    expect(screen.getByText("158")).toBeInTheDocument();     // al max 52s
  });

  it("senza titoli misurati non stampa zeri", () => {
    // Stessa dottrina della striscia che questa banda ha assorbito: zero
    // titoli in rialzo su zero misurati non e' una lettura di mercato.
    montaA(SEDUTA, { ...GLOBAL, stocks_with_data: 0 });
    expect(screen.getByText(/Nessun dato di ampiezza/)).toBeInTheDocument();
    // Nessuna riga per continente: senza misure non c'e' niente da
    // confrontare, e tre righe di zeri sarebbero tre verdetti sul nulla.
    expect(screen.queryByText("USA")).not.toBeInTheDocument();
    expect(screen.queryByText("300")).not.toBeInTheDocument();
  });
});

describe("il pre-market e' il soggetto della fascia", () => {
  beforeEach(() => {
    premarket = {
      available: true, market_open: false, as_of: "2026-09-18", computed_at: null,
      refreshing: false, progress_pct: 0,
      gainers: [
        mover("PURR", 6.43, { volume: 396_000 }),
        mover("SOXL", 3.33, { instrument_type: "etf", volume: null }),
        mover("ARM", 3.27, { volume: 97_000 }),
      ],
      losers: [
        mover("SOXS", -3.07, { instrument_type: "etf" }),
        mover("EYPT", -2.51, { volume: 2_000 }),
      ],
    };
  });

  it("si chiama «Pre-market» e dice che e' live col punto, non con la data", () => {
    montaA(PREMARKET);
    expect(screen.getByText("Pre-market")).toBeInTheDocument();
    expect(screen.queryByText("Si muove nel pre-market")).not.toBeInTheDocument();
    // La seduta non e' piu' scritta accanto al titolo: resta nel
    // suggerimento del punto, per chi la cerca.
    expect(screen.queryByText("seduta 2026-09-18")).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "dati live" })).toHaveAttribute(
      "title", expect.stringContaining("2026-09-18"),
    );
    expect(screen.getByText("PURR")).toBeInTheDocument();
    expect(screen.getByText("+6,43%")).toBeInTheDocument();
    expect(screen.getByText("−2,51%")).toBeInTheDocument();
  });

  it("⚠️ i fondi non stanno nella lista delle aziende, ma non spariscono", () => {
    /* Su otto righe misurate a schermo QUATTRO erano fondi a leva 3x: si
     * muovono del triplo per costruzione, quindi comparire fra i movers non e'
     * una notizia. Toglierli in silenzio sarebbe pero' peggio — stanno nella
     * riga ETF della fascia sopra, marcati «pre». */
    montaA(PREMARKET);
    for (const lista of ["In rialzo", "In ribasso"]) {
      const g = screen.getByRole("group", { name: lista });
      expect(g.textContent).not.toContain("SOXL");
      expect(g.textContent).not.toContain("SOXS");
    }
    const soxs = screen.getByTitle(/SOXS Inc\. — in movimento nel pre-market/);
    expect(soxs).toHaveTextContent("pre");
    expect(soxs).toHaveTextContent("−3,07%");
  });

  it("un fondo gia' nel paniere non compare due volte", () => {
    // SOXL e' nel paniere fisso a leva E fra i movers del pre-market: una
    // riga con due SOXL darebbe due numeri diversi per lo stesso fondo.
    montaA(PREMARKET);
    expect(screen.getAllByText("SOXL")).toHaveLength(1);
    expect(screen.queryByTitle(/SOXL Inc\. — in movimento/)).not.toBeInTheDocument();
  });

  it("la riga in fondo al riquadro non c'e' piu'", () => {
    // Controllo negativo sulla vecchia forma: un'etichetta «ETF» sola, con la
    // spiegazione nel suo `title`, sotto le due liste.
    montaA(PREMARKET);
    expect(screen.getAllByText("ETF")).toHaveLength(1);
  });

  it("un movimento su scambi sottili lo dichiara invece di darlo per buono", () => {
    // EYPT: −2,5% su duemila azioni. Il prezzo lo fa un pugno di ordini.
    montaA(PREMARKET);
    const cella = screen.getByTitle(/Scambi sottili/);
    expect(cella).toBeInTheDocument();
    expect(cella.textContent).toBe("2k");
  });

  it("nella sua finestra dice quanto manca all'apertura", () => {
    montaA(PREMARKET); // 08:00 ET → 90 minuti
    expect(screen.getByText("Pre-market USA")).toBeInTheDocument();
    expect(screen.getByText("1h 30m")).toBeInTheDocument();
    // La barra dice fra cosa e cosa, altrimenti e' una barra e basta.
    expect(screen.getByText("04:00")).toBeInTheDocument();
    expect(screen.getByText("09:30 New York")).toBeInTheDocument();
  });
});

describe("l'agenda del giorno", () => {
  it("mette in riga i rilasci macro con l'ora di New York e le trimestrali", () => {
    eventi = [
      { kind: "macro", date: "2026-09-18", label: "Richieste sussidi", importance: "high",
        region: "US", release_time: "12:30", series_id: 1 } as CalendarEvent,
      { kind: "earnings", date: "2026-09-18", ticker: "AAPL", name: "Apple",
        eps_estimate: null, revenue_estimate: null, sector: null, market_cap: 3e12,
        earnings_when: "pre" } as CalendarEvent,
    ];
    montaA(PREMARKET);
    expect(screen.getByText("Oggi")).toBeInTheDocument();
    expect(screen.getByText("08:30")).toBeInTheDocument();
    expect(screen.getByText("Richieste sussidi")).toBeInTheDocument();
    expect(screen.getByText(/trimestrali prima dell'apertura/)).toBeInTheDocument();
    expect(screen.getByText(/\(AAPL\)/)).toBeInTheDocument();
  });

  it("⚠️ senza eventi la riga non c'e': non scrive «nessun evento»", () => {
    // Una riga intera per dire zero e' spazio tolto a cio' che ha qualcosa da
    // dire. E' anche il controllo negativo del test qui sopra.
    montaA(PREMARKET);
    expect(screen.queryByText("Oggi")).not.toBeInTheDocument();
  });
});

/* ─── Umore e ampiezza: i continenti e le loro borse ─────────────────────── */

function borsa(code: string, avg: number, n = 50, extra: Partial<IndexBreadth> = {}): IndexBreadth {
  return {
    code, name: code, n, pct_above_ema200: 50, pct_above_ema50: 40,
    rsi_oversold_count: 0, rsi_overbought_count: 0, avg_change_pct: avg,
    advancers: 10, decliners: 10, new_52w_highs: 0, new_52w_lows: 0,
    volume_spikes_count: 0, ...extra,
  };
}

/** Le nove borse dell'istantanea di produzione del 2026-09-25, con medie
 *  scelte perche' la somma e la base giusta diano numeri DIVERSI: un test in
 *  cui coincidono passerebbe anche col totale sbagliato. */
const TUTTE: IndexBreadth[] = [
  borsa("SP500", 0.4, 500, { advancers: 300, decliners: 190 }),
  borsa("NDX", -2.0, 100),
  borsa("DJI", -1.0, 30),
  borsa("EUSTX50", 1.0, 50),
  borsa("FTSE100", -1.0, 50),
  borsa("FTSEMIB", -3.0, 40),
  borsa("N225", 1.0, 40),
  borsa("KOSPI20", 0.5, 20),
  borsa("HSI30", -0.5, 50),
];

function montaAmpiezza(byIndex: IndexBreadth[]) {
  vi.setSystemTime(SEDUTA);
  return render(
    <MemoryRouter>
      <MarketPulseJumbotron global={GLOBAL} byIndex={byIndex} computedAt={SEDUTA.toISOString()} />
    </MemoryRouter>,
  );
}

describe("umore e ampiezza: ogni continente con le sue borse", () => {
  it("si chiama «Umore e ampiezza», e porta una riga per ogni borsa", () => {
    montaAmpiezza(TUTTE);
    expect(screen.getByText("Umore e ampiezza")).toBeInTheDocument();
    for (const nome of ["S&P 500", "Nasdaq 100", "Dow Jones", "Euro Stoxx 50", "FTSE 100",
      "FTSE MIB", "Nikkei", "KOSPI", "Hang Seng"]) {
      // Nella sezione del suo continente, non da qualche parte della pagina:
      // «S&P 500» e' anche il nome di un riquadro in cima.
      expect(screen.getAllByText(nome).length).toBeGreaterThanOrEqual(1);
    }
    const europa = screen.getByRole("region", { name: "Europa" });
    expect(europa).toHaveTextContent("FTSE 100");
    expect(europa).toHaveTextContent("FTSE MIB");
    expect(europa).not.toHaveTextContent("Nikkei");
  });

  it("ogni borsa porta alla lista dei suoi titoli", () => {
    montaAmpiezza(TUTTE);
    const asia = screen.getByRole("region", { name: "Asia" });
    const kospi = within(asia).getByText("KOSPI").closest("a")!;
    expect(kospi).toHaveAttribute("href", "/stocks?index=KOSPI20");
  });

  it("⚠️ il totale USA e' l'S&P 500, NON la somma di tre panieri sovrapposti", () => {
    /* Nasdaq e Dow stanno quasi per intero dentro l'S&P: sommarli contava due
     * o tre volte i grandi nomi. Con queste medie la vecchia somma pesata
     * darebbe (0,4·500 − 2·100 − 1·30) / 630 = −0,05%; la base giusta +0,40%. */
    montaAmpiezza(TUTTE);
    const usa = screen.getByRole("region", { name: "USA" });
    const intestazione = within(usa).getByText("totale su S&P 500").parentElement!;
    expect(intestazione).toHaveTextContent("+0,40%");
    expect(intestazione).not.toHaveTextContent("−0,05%");
  });

  it("⚠️ l'Europa somma Euro Stoxx e FTSE 100, e lascia FUORI il FTSE MIB dichiarandolo", () => {
    // (1·50 − 1·50) / 100 = 0: col FTSE MIB dentro sarebbe −0,86%.
    montaAmpiezza(TUTTE);
    const europa = screen.getByRole("region", { name: "Europa" });
    const intestazione = within(europa).getByText("totale su Euro Stoxx 50 + FTSE 100").parentElement!;
    expect(intestazione).toHaveTextContent("0,00%");
    expect(intestazione).not.toHaveTextContent("−0,86%");
    // Fuori dal totale, ma a schermo e con la ragione scritta.
    const mib = within(europa).getByText("FTSE MIB").closest("a")!;
    expect(mib).toHaveTextContent("fuori dal totale del continente");
    expect(screen.getByText(/i suoi titoli maggiori sono già contati in un altro indice/)).toBeInTheDocument();
  });

  it("anche Nasdaq e Dow portano la nota: i loro titoli sono gia' nell'S&P", () => {
    montaAmpiezza(TUTTE);
    const usa = screen.getByRole("region", { name: "USA" });
    expect(within(usa).getByText("Nasdaq 100").closest("a")).toHaveTextContent("fuori dal totale");
    expect(within(usa).getByText("S&P 500").closest("a")).not.toHaveTextContent("fuori dal totale");
  });

  it("senza borse fuori dal totale non stampa una nota che non riguarda niente", () => {
    montaAmpiezza(TUTTE.filter((i) => !["NDX", "DJI", "FTSEMIB"].includes(i.code)));
    expect(screen.queryByText(/già contati in un altro indice/)).not.toBeInTheDocument();
  });

  it("una borsa che l'istantanea non porta manca, non diventa una riga di zeri", () => {
    montaAmpiezza(TUTTE.filter((i) => i.code !== "KOSPI20"));
    const asia = screen.getByRole("region", { name: "Asia" });
    expect(within(asia).queryByText("KOSPI")).not.toBeInTheDocument();
    expect(within(asia).getByText("Nikkei")).toBeInTheDocument();
  });
});

/* ─── Il VIX ─────────────────────────────────────────────────────────────── */

function conVix(vixCambio: number, spCambio = 0.27) {
  assets = [
    indice("^GSPC", {
      quote: {
        price: 7725, prev_close: 7704.06, change_abs: 20.94, change_pct: spCambio,
        market_state: "OPEN",
      } as LiveAsset["quote"],
    }),
    indice("^VIX", {
      quote: { price: 15.68, prev_close: 15.67, change_pct: vixCambio, market_state: "OPEN" } as LiveAsset["quote"],
    }),
  ];
}

describe("il VIX tradotto in movimento atteso", () => {
  it("dice di quanto si muove l'S&P in una seduta, in percento e in punti", () => {
    // 15,68 / radice(252) = 0,99%; attorno alla chiusura precedente 7.704.
    conVix(0.06);
    montaA(SEDUTA);
    expect(screen.getByText("±0,99%")).toBeInTheDocument();
    expect(screen.getByText("7.628–7.780")).toBeInTheDocument();
    expect(screen.getByText("±4,5%")).toBeInTheDocument();       // 30 giorni di calendario
  });

  it("mette la variazione di oggi a confronto con l'atteso", () => {
    // 0,27 / 0,99 = 0,3.
    conVix(0.06, 0.27);
    montaA(SEDUTA);
    expect(screen.getByText("0,3×")).toBeInTheDocument();
  });

  it("⚠️ una seduta oltre l'atteso si nota in ambra, non nel colore di una direzione", () => {
    conVix(0.06, -1.5);
    montaA(SEDUTA);
    expect(screen.getByText("1,5×").className).toContain("amber");
  });

  it("⚠️ un VIX che SALE ha il colore di un mercato che scende", () => {
    conVix(3.2);
    montaA(SEDUTA);
    expect(screen.getByText("+3,20%").className).toContain("rose");
  });

  it("e uno che scende quello di un mercato che sale", () => {
    // Controllo negativo del test sopra: senza, un colore fisso lo supererebbe.
    conVix(-3.2);
    montaA(SEDUTA);
    expect(screen.getByText("−3,20%").className).toContain("emerald");
  });
});
