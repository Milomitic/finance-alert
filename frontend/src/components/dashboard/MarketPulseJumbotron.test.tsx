import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MarketGlobal } from "@/api/types";
import type { LiveAsset } from "@/hooks/useLiveAssets";

/* Le tre interrogazioni vive sono finte: qui si verifica cosa la fascia
 * DICHIARA a partire da un certo stato del mondo, non la rete. I finti
 * RESTITUISCONO sempre — nessuno lancia — perche' un `vi.fn()` che lancia fa
 * fallire il test anche quando l'errore e' gestito (CLAUDE.md, trappole
 * dell'armamentario). */
let assets: LiveAsset[] = [];
let premarket: unknown = undefined;
let liveMovers: unknown = undefined;

vi.mock("@/hooks/useLiveAssets", () => ({
  useLiveAssets: () => ({ data: { assets }, isLoading: false }),
}));
vi.mock("@/hooks/usePremarketMovers", () => ({
  usePremarketMovers: () => ({ data: premarket }),
}));
vi.mock("@/hooks/useLiveUniverseMovers", () => ({
  useLiveUniverseMovers: () => ({ data: liveMovers }),
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

const AMERICANE = ["^GSPC", "^IXIC", "^DJI"];

/** Venerdi' 18 settembre 2026, 15:00 a New York: seduta in corso secondo
 *  l'orologio. E' l'unico istante in cui la domanda «e' davvero aperta?» ha un
 *  senso, ed e' quello su cui i dati possono smentire il calendario. */
const SEDUTA = new Date("2026-09-18T19:00:00Z");

function montaA(istante: Date, global?: MarketGlobal, computedAt?: string) {
  vi.setSystemTime(istante);
  return render(
    <MemoryRouter>
      <MarketPulseJumbotron global={global} computedAt={computedAt} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  assets = [];
  premarket = undefined;
  liveMovers = undefined;
});
afterEach(() => vi.useRealTimers());

describe("la fase la dicono i dati, non l'orologio", () => {
  it("con le americane sul cash durante la seduta dice che Wall Street e' aperta", () => {
    assets = AMERICANE.map((s) => indice(s, { using_futures: false, is_live: true }));
    montaA(SEDUTA);
    expect(screen.getByText("Wall Street aperta")).toBeInTheDocument();
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
    // La fascia non puo' spegnersi quando la rete tace: l'orologio e' il
    // ripiego dichiarato.
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
    expect(container.textContent).not.toContain("0.00%");
  });

  it("il vuoto dice PERCHE' e' vuoto", () => {
    // Sabato: «nessun dato» manderebbe a cercare un guasto che non esiste.
    montaA(new Date("2026-09-19T15:00:00Z"));
    expect(screen.getByText(/Fuori dalla finestra del pre-market/)).toBeInTheDocument();
  });
});

describe("l'ampiezza non si spaccia per un dato live", () => {
  const global: MarketGlobal = {
    stocks_total: 1000, stocks_with_data: 996, advancers: 512, decliners: 400,
    unchanged: 84, avg_change_pct: 0.42, pct_above_ema200: 51.4, pct_above_ema50: 33.7,
    rsi_oversold_count: 7, rsi_overbought_count: 11, near_52w_high_count: 128,
    near_52w_low_count: 9, mood: "bullish",
  };

  it("dichiara l'ora dell'istantanea accanto ai numeri che ne vengono", () => {
    assets = AMERICANE.map((s) => indice(s));
    montaA(SEDUTA, global, "2026-09-18T16:30:00Z");
    expect(screen.getByText(/istantanea delle \d{2}:\d{2}/)).toBeInTheDocument();
    expect(screen.getByText("512")).toBeInTheDocument();
    expect(screen.getByText("51.4%")).toBeInTheDocument();
  });

  it("senza titoli misurati non stampa zeri", () => {
    // Stessa dottrina della striscia d'umore: zero titoli in rialzo su zero
    // misurati non e' una lettura di mercato, e' l'assenza di una lettura.
    montaA(SEDUTA, { ...global, stocks_with_data: 0 });
    expect(screen.getByText(/Nessuna istantanea di ampiezza/)).toBeInTheDocument();
    expect(screen.queryByText("512")).not.toBeInTheDocument();
  });
});

describe("il pre-market e' il soggetto della fascia", () => {
  it("mostra i titoli in movimento con la seduta a cui appartengono", () => {
    premarket = {
      available: true, market_open: false, as_of: "2026-09-18", computed_at: null,
      refreshing: false, progress_pct: 0,
      gainers: [{ ticker: "NVDA", name: "Nvidia", price: 180, prev_close: 170, change_pct: 5.88, volume: 1_200_000 }],
      losers: [{ ticker: "TSLA", name: "Tesla", price: 240, prev_close: 250, change_pct: -4.0, volume: 900_000 }],
    };
    montaA(new Date("2026-09-18T12:00:00Z")); // 08:00 a New York
    expect(screen.getByText("Si muove nel pre-market")).toBeInTheDocument();
    expect(screen.getByText("seduta 2026-09-18")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("+5.88%")).toBeInTheDocument();
    expect(screen.getByText("-4.00%")).toBeInTheDocument();
  });

  it("nella sua finestra dice quanto manca all'apertura", () => {
    montaA(new Date("2026-09-18T12:00:00Z")); // 08:00 ET → 90 minuti
    expect(screen.getByText("Pre-market USA")).toBeInTheDocument();
    expect(screen.getByText("1h 30m")).toBeInTheDocument();
  });
});
