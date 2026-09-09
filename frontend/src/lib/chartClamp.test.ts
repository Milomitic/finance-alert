import { describe, expect, it } from "vitest";

import { clampLogicalRange, defaultVisibleRange, EDGE_MARGIN_BARS, MIN_VISIBLE_BARS } from "./chartClamp";

/* Panning was walled in six bars past the data, and hitting the wall while
 * zoomed out silently WIDENED the window to the whole series — the zoom
 * "reset" and the view snapped back to centred, which reads as the chart
 * fighting the user.
 *
 * The rule now: a pan that reaches the bound stops sliding and the window
 * width never changes. The width IS the zoom level, so a clamp that alters it
 * is not a clamp, it is a zoom command the user did not issue.
 */

const N = 200; // bars in the series

describe("il livello di zoom sopravvive a una pan fino al limite", () => {
  it("conserva la larghezza quando si spinge oltre il bordo destro", () => {
    const width = 60;
    const out = clampLogicalRange(500, 500 + width, N)!;

    expect(out.to - out.from).toBe(width);
  });

  it("conserva la larghezza quando si spinge oltre il bordo sinistro", () => {
    const width = 60;
    const out = clampLogicalRange(-500, -500 + width, N)!;

    expect(out.to - out.from).toBe(width);
  });

  it("conserva la larghezza anche con la finestra piu larga della serie", () => {
    // The exact case that used to collapse: zoomed out past the full span AND
    // panned to a bound, so both edges capped and the width was rewritten.
    const width = N * 3;
    const out = clampLogicalRange(900, 900 + width, N)!;

    expect(out.to - out.from).toBe(width);
  });
});

describe("si puo andare ben oltre i dati, ma non fino a perderli", () => {
  it("permette di spingere le candele fuori a sinistra", () => {
    // Room to the right of the last bar is the whole point: it is where you
    // look at what price might do next.
    const out = clampLogicalRange(1000, 1060, N)!;

    expect(out.from).toBeGreaterThan(N - 20);
  });

  it("lascia sempre almeno la soglia di barre reali sullo schermo", () => {
    const out = clampLogicalRange(1000, 1060, N)!;

    const visibleBars = N - 1 - out.from + 1;
    expect(visibleBars).toBeGreaterThanOrEqual(MIN_VISIBLE_BARS);
  });

  it("vale anche nell'altra direzione", () => {
    const out = clampLogicalRange(-1000, -940, N)!;

    const visibleBars = out.to + 1;
    expect(visibleBars).toBeGreaterThanOrEqual(MIN_VISIBLE_BARS);
  });

  it("da molto piu spazio del vecchio margine di sei barre", () => {
    // The regression this fixes: the old bound stopped at barCount-1+6.
    const out = clampLogicalRange(1000, 1060, N)!;

    expect(out.from).toBeGreaterThan(N - 1 + 6 - 60);
  });
});

describe("una vista gia valida non viene toccata", () => {
  it("lascia in pace una finestra interna", () => {
    const out = clampLogicalRange(50, 110, N)!;

    expect(out).toEqual({ from: 50, to: 110 });
  });

  it("lascia in pace la posizione di riposo appena oltre l'ultima barra", () => {
    // The chart rests at rightOffset = 6 bars past the end; the clamp must not
    // pull it back, or every load would visibly jump.
    const out = clampLogicalRange(N - 1 + 6 - 120, N - 1 + 6, N)!;

    expect(out.to).toBe(N - 1 + 6);
  });
});

describe("serie troppo corte", () => {
  it("non clampa una serie di meno di due barre", () => {
    expect(clampLogicalRange(0, 10, 1)).toBeNull();
    expect(clampLogicalRange(0, 10, 0)).toBeNull();
  });

  it("non pretende piu barre di quante ne esistano", () => {
    // With 4 bars and a floor of 8, demanding 8 visible would make the range
    // unsatisfiable and the chart unpannable. The floor drops to the series.
    const out = clampLogicalRange(1000, 1030, 4)!;

    expect(out.to - out.from).toBe(30);
    expect(out.from).toBeLessThanOrEqual(0);
  });
});

/* La finestra di riposo, ora una funzione sola.
 *
 * Il pulsante "reimposta zoom" nasce insieme alla pan piu libera: prima il
 * limite era sei barre oltre i dati e non ci si poteva perdere, adesso si
 * spinge il prezzo quasi fuori schermo — ed e giusto che si possa, ma senza una
 * via di ritorno il gesto e a senso unico e l'unico rimedio era ricaricare.
 *
 * Il punto di questi test: il reset deve atterrare ESATTAMENTE dove il grafico
 * si apre. Una seconda definizione di "vista predefinita" e una seconda cosa
 * che puo divergere, e un reset che atterra dove il grafico non parte mai non
 * e un reset.
 */
describe("la finestra di riposo", () => {
  it("mostra le ultime N barre piu il margine destro", () => {
    const out = defaultVisibleRange(1000, 252)!;

    expect(out.from).toBe(1000 - 252);
    expect(out.to).toBe(1000 - 1 + EDGE_MARGIN_BARS);
  });

  it("la larghezza include il margine, come il rightOffset del grafico", () => {
    // Se il margine sparisse da qui, l'ultima candela resterebbe incollata al
    // bordo dopo ogni reset mentre al caricamento no.
    const out = defaultVisibleRange(1000, 252)!;

    expect(out.to - out.from).toBe(252 - 1 + EDGE_MARGIN_BARS);
  });

  it("una serie piu corta del default non ha finestra: si adatta tutta", () => {
    // null significa `fitContent()`, che non e un intervallo logico.
    expect(defaultVisibleRange(100, 252)).toBeNull();
  });

  it("nemmeno quando combacia esattamente", () => {
    expect(defaultVisibleRange(252, 252)).toBeNull();
  });

  it("un timeframe senza default si adatta tutto", () => {
    // Le chiavi legacy (1y/3m/6m/5y) restituiscono null da defaultVisibleBars.
    expect(defaultVisibleRange(1000, null)).toBeNull();
  });

  it("la finestra che produce sopravvive al clamp della pan", () => {
    // La verifica che lega le due funzioni: il reset non deve atterrare in una
    // posizione che il clamp poi corregge, o la vista salterebbe subito dopo.
    const out = defaultVisibleRange(1000, 252)!;
    const clamped = clampLogicalRange(out.from, out.to, 1000)!;

    expect(clamped).toEqual(out);
  });
});
