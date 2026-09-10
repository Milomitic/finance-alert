import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Position } from "@/api/types";

import { PositionGeometry, geometry } from "./PositionGeometry";

/* La geometria di una posizione aperta.
 *
 * ⚠️ jsdom non carica nessun foglio di stile, quindi la BARRA non e
 * osservabile qui: larghezze, colori e sovrapposizioni non esistono. Cio che
 * si puo misurare sono i NUMERI che la posizionano e le frasi che la
 * descrivono a chi non la vede — ed e li che sta il difetto possibile, perche
 * una barra disegnata con la frazione sbagliata sembra perfettamente sana.
 */

function pos(over: Partial<Position> = {}): Position {
  return {
    id: 1,
    stock_id: 1,
    ticker: "ARGX.BR",
    name: "argenx SE",
    alert_id: null,
    side: "long",
    entry_price: 830.8,
    stop_price: 625.52,
    target_price: 1036.08,
    size: null,
    opened_at: "2026-08-01T10:00:00Z",
    closed_at: null,
    exit_price: null,
    exit_reason: null,
    notes: null,
    last_price: 865.2,
    price_source: "live",
    unrealized_pct: 4.14,
    unrealized_abs: 34.4,
    realized_pct: null,
    realized_abs: null,
    currency: "EUR",
    unrealized_usd: null,
    realized_usd: null,
    cost_usd: null,
    ...over,
  };
}

describe("la pista va sempre dallo stop al target", () => {
  it("su un long, misurata su una posizione vera", () => {
    // ARGX.BR, dati veri: entry 830.80, stop 625.52, target 1036.08, prezzo
    // 865.20. L'entry sta esattamente a meta perche stop e target sono
    // simmetrici attorno a lei, e il prezzo la supera di poco.
    const g = geometry(pos())!;

    expect(g.entryAt).toBeCloseTo(0.5, 3);
    expect(g.priceAt).toBeCloseTo(0.584, 3);
    expect(g.inProfit).toBe(true);
    expect(g.beyond).toBeNull();
  });

  it("su uno short, dove lo stop sta SOPRA il target", () => {
    // ⚠️ Il test che conta. La formula non guarda `side`: numeratore e
    // denominatore hanno lo stesso segno anche quando la pista scende, quindi
    // 0 resta lo stop e 1 resta il target. Chi la «sistemasse» aggiungendo un
    // ramo su `side` invertirebbe questa riga senza accorgersene.
    const g = geometry(
      pos({ side: "short", entry_price: 100, stop_price: 110, target_price: 80, last_price: 90 }),
    )!;

    expect(g.entryAt).toBeCloseTo(1 / 3, 3);
    expect(g.priceAt).toBeCloseTo(2 / 3, 3);
    // Il prezzo e SCESO da 100 a 90 su uno short: e guadagno.
    expect(g.inProfit).toBe(true);
  });

  it("su uno short in perdita il prezzo sta sotto l'ingresso sulla pista", () => {
    const g = geometry(
      pos({ side: "short", entry_price: 100, stop_price: 110, target_price: 80, last_price: 105 }),
    )!;

    expect(g.priceAt).toBeCloseTo(1 / 6, 3);
    expect(g.inProfit).toBe(false);
  });
});

describe("senza due estremi non c'e una pista", () => {
  it.each([
    { name: "manca lo stop", over: { stop_price: null } },
    { name: "manca il target", over: { target_price: null } },
    { name: "stop e target coincidono", over: { stop_price: 900, target_price: 900 } },
  ])("$name → nessuna geometria", ({ over }) => {
    // Inventare un estremo sarebbe un'affermazione che i dati non fanno —
    // lo stesso criterio con cui `money.ts` non inventa una valuta.
    expect(geometry(pos(over))).toBeNull();
  });

  it("i numeri che ci sono restano, e il posto vuoto lo dice", () => {
    render(<PositionGeometry p={pos({ stop_price: null })} />);

    expect(screen.getByText("Nessuno stop")).toBeInTheDocument();
    expect(screen.getByText(/830\.80/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});

describe("un prezzo oltre un estremo viene detto, non appiattito", () => {
  it("oltre lo stop", () => {
    // Su una posizione APERTA significa che lo stop non e stato eseguito, ed e
    // la cosa piu importante della riga: limitarlo al bordo in silenzio la
    // farebbe leggere come «sono sullo stop».
    const g = geometry(pos({ last_price: 600 }))!;

    expect(g.beyond).toBe("stop");
    expect(g.priceAt).toBe(0);
    expect(g.inProfit).toBe(false);
  });

  it("oltre il target", () => {
    const g = geometry(pos({ last_price: 1100 }))!;

    expect(g.beyond).toBe("target");
    expect(g.priceAt).toBe(1);
    expect(g.inProfit).toBe(true);
  });

  it("senza prezzo la pista resta, il cursore no", () => {
    const g = geometry(pos({ last_price: null }))!;

    expect(g.priceAt).toBeNull();
    expect(g.beyond).toBeNull();
    expect(g.inProfit).toBeNull();
    expect(g.entryAt).toBeCloseTo(0.5, 3);
  });
});

describe("uno stop spostato oltre l'ingresso non e un errore", () => {
  it("l'ingresso finisce fuori dalla pista e viene marcato", () => {
    // Entry 100, prezzo salito a 130, stop alzato a 115 per bloccare il
    // guadagno, target 140. La geometria e coerentissima: l'ingresso e ormai
    // dietro il bordo sinistro. Rifiutarla toglierebbe la barra proprio alle
    // posizioni gestite meglio.
    const g = geometry(
      pos({ entry_price: 100, stop_price: 115, target_price: 140, last_price: 130 }),
    )!;

    expect(g.entryOffTrack).toBe(true);
    expect(g.entryAt).toBe(0); // portato al bordo, non nascosto
    expect(g.priceAt).toBeCloseTo(0.6, 3);
    expect(g.inProfit).toBe(true);
  });
});

describe("chi non vede la barra deve avere la risposta, non il disegno", () => {
  it("l'etichetta accessibile contiene i tre prezzi e dove sta ora", () => {
    render(<PositionGeometry p={pos()} />);

    const label = screen.getByRole("img").getAttribute("aria-label") ?? "";

    expect(label).toContain("625.52"); // stop
    expect(label).toContain("1036.08"); // target
    expect(label).toContain("830.80"); // ingresso
    expect(label).toContain("58%"); // dove sta il prezzo sulla corsa
    // Il controllo negativo: se descrivesse il disegno invece della misura,
    // parlerebbe di barre e cursori.
    expect(label).not.toMatch(/barra|cursore|grafico/i);
  });

  it("oltre lo stop l'etichetta lo dice a parole", () => {
    render(<PositionGeometry p={pos({ last_price: 600 })} />);

    expect(screen.getByRole("img").getAttribute("aria-label")).toContain(
      "oltre lo stop",
    );
  });
});

describe("ogni numero porta la propria valuta", () => {
  it("i tre prezzi sono in euro, non in dollari", () => {
    // ⚠️ La pagina formattava il denaro con un helper che ricadeva su USD
    // quando la valuta mancava o non era tre lettere maiuscole. 312 titoli su
    // 1010 non sono quotati in dollari: qui la valuta e nel dato e deve
    // arrivare a schermo, su TUTTI e tre i numeri e non solo sul prezzo.
    render(<PositionGeometry p={pos()} />);

    expect(screen.getByText(/€625\.52/)).toBeInTheDocument();
    expect(screen.getByText(/€830\.80/)).toBeInTheDocument();
    expect(screen.getByText(/€1036\.08/)).toBeInTheDocument();
  });

  it("una valuta assente non diventa un dollaro", () => {
    render(<PositionGeometry p={pos({ currency: null })} />);

    expect(screen.getByRole("img").getAttribute("aria-label")).not.toContain("$");
  });
});
