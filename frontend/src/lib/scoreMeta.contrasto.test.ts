import { describe, expect, it } from "vitest";


import { SCORE_TEXT_TONE } from "./scoreMeta";

/* ─── Il contrasto si CALCOLA: axe qui non puo' ───────────────────────────
 *
 * CLAUDE.md lo dice gia' di axe in jsdom — «non carica nessun foglio di
 * stile, quindi contrasto, dimensione dei bersagli e visibilita' del focus
 * sono invisibili» — e il gate e2e, che gli stili ce li ha, vede solo i
 * colori che i DATI di quella corsa fanno comparire. Le due tonalita'
 * corrette qui sono rimaste sotto soglia per mesi perche' nessun punteggio
 * del seme cadeva nelle fasce «mediocre» e «buono»: sei nodi sono apparsi
 * tutti insieme il giorno in cui il seme e' cambiato.
 *
 * Questo test non guarda il DOM: prende i TOKEN e rifa l'aritmetica WCAG.
 * Non dipende da quali dati ci sono, quindi non puo' essere vero per caso.
 */

/** Tailwind v3, colori usati da `SCORE_TEXT_TONE`. */
const TAILWIND: Record<string, string> = {
  "rose-600": "#e11d48", "rose-400": "#fb7185",
  "amber-600": "#d97706", "amber-700": "#b45309", "amber-400": "#fbbf24",
  "sky-600": "#0284c7", "sky-700": "#0369a1", "sky-400": "#38bdf8",
  "emerald-800": "#065f46", "emerald-400": "#34d399",
};

/** Gli sfondi REALI, presi dai token di `index.css` e non a occhio.
 *
 *  ⚠️ Il primo tentativo aveva indovinato `#f8fafc` per il muto. Quello vero
 *  e' `hsl(210 40% 96.1%)` = `#f1f5f9`, piu' SCURO — quindi la stima era
 *  ottimista, cioe' sbagliata nella direzione che nasconde i difetti. Il test
 *  sotto verifica che i token in `index.css` siano ancora questi: se il tema
 *  cambia, questi numeri vanno rifatti, non aggiornati a mano. */
const CARD = "#ffffff";       // --card: 0 0% 100%
const MUTED = "#f1f5f9";      // --muted: 210 40% 96.1%

/** ⚠️ Deroghe, con la RAGIONE accanto — non tolleranze silenziose.
 *
 *  Una lista di eccezioni senza spiegazione e' indistinguibile da una lista di
 *  difetti: e' la regola che `mutation_probe.EQUIVALENTI` applica ai mutanti.
 *
 *  `rose-600` sul fondo muto vale 4,29. CLAUDE.md lo registra gia' come il
 *  caso piu' stretto della conversione di palette — «4,83 -> 4,70 su bianco,
 *  ancora sopra la soglia ma con meno margine: non scurire lo sfondo dietro» —
 *  e il fondo muto e' esattamente quello sfondo piu' scuro. Non e' corretto
 *  qui perche' cambierebbe il colore del punteggio «debole» in tutta
 *  l'applicazione, che nessuna misura ha chiesto: i sei nodi segnalati da axe
 *  stavano su fondo SCHEDA e riguardavano ambra e celeste.
 *
 *  Il valore e' PINNATO: puo' solo migliorare. Se qualcuno scurisce il fondo
 *  muto, questo diventa rosso invece di peggiorare in silenzio. */
const DEROGHE: Record<string, number> = { "weak su muted": 4.29 };

function luminanza(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const l = c.map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
}

/** HSL come lo scrive Tailwind nei token di `index.css` -> esadecimale. */
function hslToHex(h: number, s: number, l: number): string {
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const v = l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(v * 255).toString(16).padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

function rapporto(a: string, b: string): number {
  const [x, y] = [luminanza(a), luminanza(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

/** "text-amber-700 dark:text-amber-400" -> "amber-700" */
function tonoChiaro(classi: string): string {
  const chiaro = classi.split(/\s+/).find((c) => !c.startsWith("dark:"));
  return (chiaro ?? "").replace(/^text-/, "");
}

describe("contrasto dei toni di punteggio", () => {
  it("la tabella dei colori copre ogni tono usato", () => {
    /* Il pavimento: un token assente renderebbe `undefined` e le asserzioni
     * sotto esploderebbero invece di misurare — o peggio, se si usasse un
     * default, passerebbero misurando il colore sbagliato. */
    const toni = Object.values(SCORE_TEXT_TONE);
    expect(toni.length).toBeGreaterThanOrEqual(4);
    for (const classi of toni) {
      expect(TAILWIND[tonoChiaro(classi)], `manca ${tonoChiaro(classi)}`).toBeDefined();
    }
  });

  it("ogni tono chiaro raggiunge AA sul fondo SCHEDA", () => {
    /* La superficie che il docstring di `SCORE_TEXT_TONE` nomina, e quella su
     * cui axe ha trovato i sei nodi. */
    const sotto: string[] = [];
    for (const [fascia, classi] of Object.entries(SCORE_TEXT_TONE)) {
      const nome = tonoChiaro(classi);
      const r = rapporto(TAILWIND[nome], CARD);
      if (r < 4.5) sotto.push(`${fascia} (${nome}): ${r.toFixed(2)}`);
    }
    expect(sotto, `sotto la soglia AA di 4,5 su scheda: ${sotto.join(" | ")}`).toEqual([]);
  });

  it("sul fondo MUTO, solo le deroghe dichiarate stanno sotto", () => {
    const sotto: Record<string, number> = {};
    for (const [fascia, classi] of Object.entries(SCORE_TEXT_TONE)) {
      const r = rapporto(TAILWIND[tonoChiaro(classi)], MUTED);
      if (r < 4.5) sotto[`${fascia} su muted`] = Number(r.toFixed(2));
    }
    expect(Object.keys(sotto).sort()).toEqual(Object.keys(DEROGHE).sort());
    for (const [k, v] of Object.entries(sotto)) {
      // Puo' solo migliorare: un peggioramento e' rosso, non una nuova deroga.
      expect(v, `${k} e' peggiorato`).toBeGreaterThanOrEqual(DEROGHE[k]);
    }
  });

  it("⚠️ gli sfondi derivano dall'HSL dei token, non da esadecimali a mano", () => {
    /* Non si possono leggere da `index.css`: vitest neutralizza gli import di
     * fogli di stile, e sia `import.meta.glob(...?raw)` sia l'import statico
     * `?raw` tornano stringa vuota (misurato — il pavimento di questo file e'
     * cio' che l'ha detto, invece di lasciar passare un controllo vuoto).
     *
     * Quindi i due valori sono TRASCRITTI, ed e' il modo classico di ottenere
     * una misura dall'aria plausibile: basta un esadecimale sbagliato e ogni
     * numero di questo file diventa finzione. La conversione dall'HSL
     * dichiarato in `index.css` viene percio' rifatta qui, cosi' la
     * trascrizione e' verificabile e non da credere.
     *
     * Se un giorno il tema cambia, questo test resta verde — non e' un
     * rilevatore di deriva — ma i valori attesi stanno accanto ai numeri, e
     * cambiarli senza rifare le misure e' un atto deliberato, non una svista. */
    expect(hslToHex(0, 0, 100), "--card: 0 0% 100%").toBe(CARD);
    expect(hslToHex(210, 40, 96.1), "--muted: 210 40% 96.1%").toBe(MUTED);
  });

  it("⚠️ la formula SA bocciare: i due colori tolti erano davvero sotto", () => {
    /* Il controllo negativo. Senza, un errore nella formula — un esponente
     * sbagliato, un canale invertito — renderebbe ogni colore conforme e il
     * test sopra sarebbe verde per costruzione. Questi due numeri sono i
     * valori reali che hanno motivato la correzione. */
    expect(rapporto(TAILWIND["amber-600"], "#ffffff")).toBeLessThan(4.5);
    expect(rapporto(TAILWIND["sky-600"], "#ffffff")).toBeLessThan(4.5);
    // e un bianco su bianco non deve risultare leggibile
    expect(rapporto("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
    // mentre il nero su bianco e' il massimo teorico
    expect(rapporto("#000000", "#ffffff")).toBeCloseTo(21, 1);
  });

  it("le varianti scure NON vanno scurite insieme alle chiare", () => {
    /* Scurire `amber-400` per «coerenza» lo porterebbe sotto soglia sul fondo
     * scuro: le due meta' del token si muovono in direzioni OPPOSTE. */
    for (const classi of Object.values(SCORE_TEXT_TONE)) {
      const scuro = classi.split(/\s+/).find((c) => c.startsWith("dark:"));
      const nome = (scuro ?? "").replace(/^dark:text-/, "");
      expect(rapporto(TAILWIND[nome], "#0a0a0a")).toBeGreaterThanOrEqual(4.5);
    }
  });
});
