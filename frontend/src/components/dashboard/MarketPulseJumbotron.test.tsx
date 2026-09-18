import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CalendarEvent, IndexBreadth, MarketGlobal } from "@/api/types";
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

function montaA(istante: Date, global?: MarketGlobal, computedAt?: string) {
  vi.setSystemTime(istante);
  return render(
    <MemoryRouter>
      <MarketPulseJumbotron global={global} byIndex={PER_INDICE} computedAt={computedAt} />
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

  it("il vuoto dice PERCHE' e' vuoto", () => {
    // Sabato: «nessun dato» manderebbe a cercare un guasto che non esiste.
    montaA(new Date("2026-09-19T15:00:00Z"));
    expect(screen.getByText(/Fuori dalla finestra del pre-market/)).toBeInTheDocument();
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

describe("il paniere a leva e le icone", () => {
  it("mostra gli ETF a leva con la loro quotazione", () => {
    quotazioni = [
      { ticker: "YINN", price: 23.45, change_pct: 2.1, market_state: "OPEN" },
      { ticker: "NUGT", price: 88.2, change_pct: -1.4, market_state: "OPEN" },
    ];
    montaA(SEDUTA);
    expect(screen.getByText("Leva")).toBeInTheDocument();
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

describe("l'ampiezza non si spaccia per un dato live", () => {
  it("dice quanto e' VECCHIA, non a che ora e' stata presa", () => {
    /* «istantanea delle 23:54» letto alle 10:34 del mattino dopo si legge come
     * recente, e quel dato ha undici ore. L'eta' relativa non si puo'
     * fraintendere. */
    montaA(SEDUTA, GLOBAL, new Date(SEDUTA.getTime() - 11 * 3600_000).toISOString());
    expect(screen.getByText("11h fa")).toBeInTheDocument();
  });

  it("ogni numero ha il suo nome accanto", () => {
    // Prima diceva «in rialzo 639 · 348»: il 348 era rosa e basta.
    montaA(SEDUTA, GLOBAL, SEDUTA.toISOString());
    expect(screen.getByText("639")).toBeInTheDocument();
    expect(screen.getByText("su")).toBeInTheDocument();
    expect(screen.getByText("giù")).toBeInTheDocument();
    expect(screen.getByText("348")).toBeInTheDocument();
    expect(screen.getByText("Bullish")).toBeInTheDocument();
  });

  it("senza titoli misurati non stampa zeri", () => {
    // Stessa dottrina della striscia che questa banda ha assorbito: zero
    // titoli in rialzo su zero misurati non e' una lettura di mercato.
    montaA(SEDUTA, { ...GLOBAL, stocks_with_data: 0 });
    expect(screen.getByText(/Nessun dato di ampiezza/)).toBeInTheDocument();
    expect(screen.queryByText("639")).not.toBeInTheDocument();
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

  it("mostra i titoli in movimento con la seduta a cui appartengono", () => {
    montaA(PREMARKET);
    expect(screen.getByText("Si muove nel pre-market")).toBeInTheDocument();
    expect(screen.getByText("seduta 2026-09-18")).toBeInTheDocument();
    expect(screen.getByText("PURR")).toBeInTheDocument();
    expect(screen.getByText("+6,43%")).toBeInTheDocument();
    expect(screen.getByText("−2,51%")).toBeInTheDocument();
  });

  it("⚠️ i fondi non stanno nella lista delle aziende, ma non spariscono", () => {
    /* Su otto righe misurate a schermo QUATTRO erano fondi a leva 3x: si
     * muovono del triplo per costruzione, quindi comparire fra i movers non e'
     * una notizia. Toglierli in silenzio sarebbe pero' peggio — stanno in una
     * riga loro, marcati. */
    const { container } = montaA(PREMARKET);
    const listaPrincipale = screen.getByText("Su").closest("div")?.parentElement;
    expect(listaPrincipale?.textContent).not.toContain("SOXL");
    expect(container.textContent).toContain("SOXL");
    expect(container.textContent).toContain("SOXS");
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
