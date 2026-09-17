import { describe, expect, it } from "vitest";

import { deveAprireLaFinestra, serieVisibile } from "./chartInitialView";

/* ─── Lo zoom dell'utente sopravvive a un aggiornamento dei dati ───────────
 *
 * Difetto riportato il 2026-09-17: dopo qualche secondo lo zoom si resettava e
 * il grafico si ricentrava. I dati cambiano identita' da soli — la quotazione
 * live ogni ~15 s ricostruisce `mergedOhlcv`, la query del dettaglio si
 * riaggiorna dopo 30 s — e l'effetto rimetteva ogni volta la finestra
 * d'apertura.
 *
 * Qui si fissa la distinzione che separa i due casi: un DATO nuovo non e' una
 * SERIE nuova. I componenti del grafico non si possono montare in jsdom
 * (lightweight-charts vuole un canvas), quindi la regola vive qui, come
 * `chartClamp` e `timeframeZoom`.
 */

/** Il ciclo vero del componente: la chiave si consuma SOLO quando la finestra
 *  si apre davvero. Riprodurlo qui e' cio' che rende i test sotto una prova
 *  della sequenza e non di due funzioni isolate. */
function aperture(
  passi: { ticker?: string; tf?: string; definitivi?: boolean; barre: number; nota: string }[],
): string[] {
  let applicataPer: string | null = null;
  const aperte: string[] = [];
  for (const p of passi) {
    const serie = serieVisibile(p.ticker ?? "AAPL", p.tf ?? "1d", p.definitivi ?? true);
    if (deveAprireLaFinestra(applicataPer, serie, p.barre)) {
      applicataPer = serie;
      aperte.push(p.nota);
    }
  }
  return aperte;
}

describe("la finestra d'apertura", () => {
  it("si apre quando la serie arriva con delle barre", () => {
    expect(aperture([{ barre: 500, nota: "primo caricamento" }])).toEqual(["primo caricamento"]);
  });

  it("⚠️ NON si riapre a ogni aggiornamento della stessa serie", () => {
    // Il difetto vero: ogni quotazione live ricostruisce l'array, e una barra
    // nuova ne cambia anche la lunghezza. Nessuna delle due e' una serie nuova.
    expect(
      aperture([
        { barre: 500, nota: "primo caricamento" },
        { barre: 500, nota: "tick live" },
        { barre: 500, nota: "refetch dopo 30 s" },
        { barre: 501, nota: "barra nuova" },
      ]),
    ).toEqual(["primo caricamento"]);
  });

  it("si riapre cambiando timeframe: 30m non si apre su tutta la storia", () => {
    expect(
      aperture([
        { tf: "1d", barre: 500, nota: "1d" },
        { tf: "30m", barre: 900, nota: "30m" },
        { tf: "30m", barre: 900, nota: "tick su 30m" },
      ]),
    ).toEqual(["1d", "30m"]);
  });

  it("si riapre cambiando titolo, anche a timeframe uguale", () => {
    expect(
      aperture([
        { ticker: "AAPL", barre: 500, nota: "AAPL" },
        { ticker: "MSFT", barre: 480, nota: "MSFT" },
      ]),
    ).toEqual(["AAPL", "MSFT"]);
  });

  it("⚠️ i dati PROVVISORI del cambio timeframe non consumano la serie", () => {
    // Mentre si cambia timeframe la query tiene a schermo le barre precedenti.
    // Aprire li' la finestra la calcolerebbe sul numero di barre sbagliato, e
    // la serie risulterebbe gia' aperta quando arrivano le sue barre vere.
    expect(
      aperture([
        { tf: "1d", barre: 500, nota: "1d" },
        { tf: "30m", definitivi: false, barre: 500, nota: "barre di 1d sotto l'etichetta 30m" },
        { tf: "30m", definitivi: true, barre: 900, nota: "barre vere di 30m" },
      ]),
    ).toEqual(["1d", "barre vere di 30m"]);
  });

  it("una serie senza barre non si apre e non si consuma", () => {
    expect(
      aperture([
        { barre: 0, nota: "caricamento vuoto" },
        { barre: 500, nota: "dati arrivati" },
      ]),
    ).toEqual(["dati arrivati"]);
  });
});

describe("serieVisibile", () => {
  it("e' nulla finche' i dati non sono quelli della serie richiesta", () => {
    expect(serieVisibile("AAPL", "1d", false)).toBeNull();
  });

  it("e' nulla senza titolo o senza timeframe", () => {
    expect(serieVisibile(undefined, "1d", true)).toBeNull();
    expect(serieVisibile("AAPL", "", true)).toBeNull();
  });

  it("distingue titolo e timeframe", () => {
    expect(serieVisibile("AAPL", "1d", true)).not.toBe(serieVisibile("AAPL", "1h", true));
    expect(serieVisibile("AAPL", "1d", true)).not.toBe(serieVisibile("MSFT", "1d", true));
  });
});
