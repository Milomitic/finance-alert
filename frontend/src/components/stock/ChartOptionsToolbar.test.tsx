import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChartOptionsToolbar } from "./ChartOptionsToolbar";

/* Il comando di reset esiste perche la pan e diventata libera.
 *
 * Prima il limite era sei barre oltre i dati: non ci si poteva perdere e la
 * mancanza non si sentiva. Ora il limite e "tieni almeno otto barre reali sullo
 * schermo", quindi si spinge il prezzo quasi fuori — ed e giusto che si possa,
 * ma senza una via di ritorno il gesto e a senso unico e l'unico rimedio era
 * ricaricare la pagina.
 */

function toolbar(over: Partial<React.ComponentProps<typeof ChartOptionsToolbar>> = {}) {
  const props = {
    chartType: "candle" as const,
    onChartType: vi.fn(),
    benchmark: "",
    onBenchmark: vi.fn(),
    compareTicker: "",
    onCompareTicker: vi.fn(),
    onExport: vi.fn(),
    onResetZoom: vi.fn(),
    ...over,
  };
  render(<ChartOptionsToolbar {...props} />);
  return props;
}

describe("si puo tornare alla vista di partenza", () => {
  it("il comando ha un nome accessibile", () => {
    toolbar();

    expect(screen.getByRole("button", { name: /reimposta zoom/i })).toBeInTheDocument();
  });

  it("un click chiede il reset", async () => {
    const props = toolbar();

    await userEvent.click(screen.getByRole("button", { name: /reimposta zoom/i }));

    expect(props.onResetZoom).toHaveBeenCalledTimes(1);
  });

  it("non e lo stesso pulsante dell'export", async () => {
    // Stanno affiancati e hanno la stessa forma: uno scambio fra i due handler
    // scaricherebbe un PNG al posto di riportare la vista, e viceversa.
    const props = toolbar();

    await userEvent.click(screen.getByRole("button", { name: /reimposta zoom/i }));

    expect(props.onExport).not.toHaveBeenCalled();
  });

  it("l'export resta al suo posto", async () => {
    const props = toolbar();

    await userEvent.click(screen.getByRole("button", { name: /esporta png/i }));

    expect(props.onExport).toHaveBeenCalledTimes(1);
    expect(props.onResetZoom).not.toHaveBeenCalled();
  });
});
