import { describe, expect, it } from "vitest";

/* ─── L'ambra dell'avvertimento: 3,19 : 1 in ventuno file ──────────────────
 *
 * FA-073. `scoreMeta.contrasto.test.ts` aveva gia' corretto `amber-600` nei
 * toni di punteggio, e CLAUDE.md ne registra la lezione: «dove un colore
 * dipende da una soglia sui dati, il contrasto va calcolato sui TOKEN, non
 * cercato nel DOM». La correzione era rimasta dentro quel file. La stessa
 * classe, `text-amber-600 dark:text-amber-400`, stava in altri ventuno file:
 * l'RSI sotto 30 dello screener, il rapporto volumi sopra 2, la governance del
 * dettaglio titolo, le metriche scadute, i segnali in ritardo.
 *
 * ⚠️ Il gate e2e l'ha vista UNA volta sola, su /stocks, e non per merito del
 * seme: lo scan di avvio aveva scritto il prezzo live vero di 0016.HK sopra
 * barre sintetiche, l'RSI era sceso a 18,8 e la cella si era accesa. Tutte le
 * altre ventisei occorrenze sono invisibili al gate finche' i dati di quella
 * corsa non attraversano la loro soglia — cioe' sono invisibili per
 * costruzione a un controllo che guarda il DOM.
 *
 * Quindi si fanno due cose che non dipendono dai dati: l'aritmetica sui fondi
 * dove quei colori stanno davvero, e un censimento sui sorgenti.
 */

const HEX: Record<string, string> = {
  "amber-500": "#f59e0b",
  "amber-600": "#d97706",
  "amber-700": "#b45309",
  "amber-50": "#fffbeb",
  "amber-100": "#fef3c7",
};

/** Gli sfondi di `index.css` (verificati dall'HSL in `scoreMeta.contrasto.test.ts`). */
const CARD = "#ffffff";
const MUTED = "#f1f5f9";

function luminanza(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const l = c.map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
}

function rapporto(a: string, b: string): number {
  const [x, y] = [luminanza(a), luminanza(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

/** Un colore con opacita' sopra un fondo: `bg-amber-500/10` su una scheda
 *  bianca non e' ne' ambra ne' bianco, e il contrasto va misurato sul miscuglio. */
function sopra(colore: string, alfa: number, fondo: string): string {
  const [c, f] = [colore, fondo].map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));
  return `#${c
    .map((v, i) => Math.round(v * alfa + f[i] * (1 - alfa)).toString(16).padStart(2, "0"))
    .join("")}`;
}

const SORGENTI = import.meta.glob("/src/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const PRODOTTO = Object.entries(SORGENTI).filter(([f]) => !/\.test\.tsx?$/.test(f));

describe("il contrasto dell'ambra si calcola", () => {
  it("⚠️ la formula SA bocciare: amber-600 era davvero sotto la soglia", () => {
    /* Il controllo negativo. Il numero di riferimento e' indipendente da
     * questo file: CLAUDE.md registra amber-600 a 3,19 su scheda. */
    expect(rapporto(HEX["amber-600"], CARD)).toBeCloseTo(3.19, 1);
    expect(rapporto(HEX["amber-600"], CARD)).toBeLessThan(4.5);
    // Il pulsante `bg-amber-600 text-white` e' la stessa coppia rovesciata.
    expect(rapporto("#ffffff", HEX["amber-600"])).toBeLessThan(4.5);
  });

  it.each([
    { nome: "scheda", fondo: CARD },
    { nome: "fondo muto", fondo: MUTED },
    { nome: "tinta amber-50 (fonti dati)", fondo: HEX["amber-50"] },
    { nome: "banner amber-500/10 del dettaglio titolo", fondo: sopra(HEX["amber-500"], 0.1, CARD) },
    { nome: "pastiglia amber-100/60 del calendario", fondo: sopra(HEX["amber-100"], 0.6, CARD) },
  ])("amber-700 raggiunge AA su $nome", ({ fondo }) => {
    expect(rapporto(HEX["amber-700"], fondo)).toBeGreaterThanOrEqual(4.5);
  });

  it("il testo bianco sul pulsante amber-700 raggiunge AA", () => {
    expect(rapporto("#ffffff", HEX["amber-700"])).toBeGreaterThanOrEqual(4.5);
  });
});

describe("censimento: l'ambra sotto soglia non torna", () => {
  it("il censimento legge davvero i sorgenti", () => {
    /* Il pavimento. `import.meta.glob(...?raw)` torna stringa VUOTA sui fogli
     * di stile, e un censimento su file vuoti sarebbe verde per costruzione. */
    expect(PRODOTTO.length).toBeGreaterThan(150);
    const vuoti = PRODOTTO.filter(([, s]) => s.length === 0).map(([f]) => f);
    expect(vuoti).toEqual([]);
  });

  it("nessun testo o icona in text-amber-600", () => {
    /* ⚠️ Anche le icone, di proposito. Un'icona chiede 3:1 e amber-600 sulla
     * scheda ci arriva a 3,19 — ma sul fondo muto e sulle tinte ambrate scende
     * sotto, e distinguere a mano quale icona sta su quale fondo e' esattamente
     * il giudizio caso per caso che ha lasciato ventuno file indietro. */
    const colpevoli = PRODOTTO.filter(([, s]) => s.includes("text-amber-600")).map(([f]) => f);
    expect(colpevoli).toEqual([]);
  });

  it("nessun pulsante bg-amber-600 con testo bianco", () => {
    const colpevoli = PRODOTTO.filter(([, s]) => /bg-amber-600[^"'`]*text-white|text-white[^"'`]*bg-amber-600/.test(s))
      .map(([f]) => f);
    expect(colpevoli).toEqual([]);
  });

  it("la sostituzione e' arrivata: amber-700 sta dove stava amber-600", () => {
    /* Senza un pavimento sul rimpiazzo, cancellare le classi del tutto
     * passerebbe il censimento sopra — e toglierebbe l'avvertimento invece di
     * renderlo leggibile. */
    const conAmbra700 = PRODOTTO.filter(([, s]) => s.includes("text-amber-700")).length;
    expect(conAmbra700).toBeGreaterThanOrEqual(21);
  });
});
