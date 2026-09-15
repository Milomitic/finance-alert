import { describe, expect, it } from "vitest";

import type { Alert, OhlcvBar } from "@/api/types";
import { alertBarIndex, buildSignalOverlay } from "@/lib/signalMarkers";

/* «Mostra sul grafico» (FA-066) centra il grafico sulla barra di un alert.
 *
 * ⚠️ La proprieta' che conta non e' «trova una barra» ma «trova LA barra che
 * porta la freccia»: un grafico centrato accanto al marker direbbe al lettore
 * che il segnale e' scattato un altro giorno. */

const barre = (date: string[]): OhlcvBar[] => date.map((d) => ({ date: d }) as OhlcvBar);

const alert = (signal_date: string | null, triggered_at = "2026-07-20T10:00:00Z"): Alert =>
  ({ id: 1, signal_date, triggered_at, snapshot: { tone: "bull" } }) as unknown as Alert;

const GIORNALIERE = barre(["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"]);

describe("alertBarIndex", () => {
  it("una barra giornaliera: la barra del giorno del segnale", () => {
    expect(alertBarIndex(GIORNALIERE, alert("2026-07-08"))).toBe(2);
  });

  it("una barra settimanale: la barra che contiene il giorno", () => {
    const settimanali = barre(["2026-06-29", "2026-07-06", "2026-07-13"]);
    // Mercoledi' 8 luglio appartiene alla barra di lunedi' 6.
    expect(alertBarIndex(settimanali, alert("2026-07-08"))).toBe(1);
  });

  it("un alert piu' vecchio della serie caricata non ha una barra", () => {
    // Il bottone non deve centrare il grafico sulla prima barra fingendo che
    // sia quella giusta.
    expect(alertBarIndex(GIORNALIERE, alert("2026-06-01"))).toBeNull();
  });

  it("un alert legacy senza signal_date ricade sul giorno di rilevazione", () => {
    expect(alertBarIndex(GIORNALIERE, alert(null, "2026-07-09T22:00:00Z"))).toBe(3);
  });

  it("⚠️ intraday: la prima barra DENTRO il giorno, non l'ultima del giorno prima", () => {
    /* Il caso in cui le due regole plausibili divergono, ed e' l'unico che le
     * distingue: sulle barre giornaliere «prima barra del giorno» e «barra che
     * contiene il giorno» coincidono sempre. FA-063 ha spostato i marker dalla
     * seconda alla prima; il grafico va centrato dove sta la freccia. */
    const intraday = barre(["2026-07-08T19:30:00Z", "2026-07-09T13:30:00Z", "2026-07-09T14:30:00Z"]);
    const a = alert("2026-07-09");

    const i = alertBarIndex(intraday, a);

    expect(i).toBe(1);
    const [marker] = buildSignalOverlay(intraday, [a]).markers;
    expect(Math.floor(Date.parse(intraday[i!].date) / 1000)).toBe(marker.time);
  });

  it("⚠️ intraday, primo giorno caricato: nessuna barra, come nessun marker", () => {
    // La mezzanotte del giorno precede la prima barra della seduta: i marker
    // scartano l'alert, e il bottone non deve centrare dove non c'e' freccia.
    const intraday = barre(["2026-07-09T13:30:00Z", "2026-07-09T14:30:00Z"]);
    const a = alert("2026-07-09");

    expect(buildSignalOverlay(intraday, [a]).markers).toHaveLength(0);
    expect(alertBarIndex(intraday, a)).toBeNull();
  });

  it("⚠️ coincide con la barra del marker, per costruzione e alla prova", () => {
    const alerts = ["2026-07-06", "2026-07-09", "2026-07-10"].map((d) => alert(d));
    const tempiMarker = buildSignalOverlay(GIORNALIERE, alerts).markers.map((m) => m.time);
    const tempiIndice = alerts.map((a) => {
      const i = alertBarIndex(GIORNALIERE, a);
      return i === null ? null : Math.floor(Date.parse(GIORNALIERE[i].date) / 1000);
    });
    // Il pavimento: tre alert, tre marker — altrimenti l'uguaglianza sotto
    // sarebbe vera anche di due liste vuote.
    expect(tempiMarker).toHaveLength(3);
    expect(tempiIndice).toEqual(tempiMarker);
  });
});
