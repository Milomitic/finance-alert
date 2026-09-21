import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HintAnchor, HintLabel, HintUnderline } from "./info-hint";

/* ─── Le intestazioni spiegano senza l'icona «i» ───────────────────────────
 *
 * L'icona allargava ogni colonna che ne aveva una, su tutte le righe della
 * tabella. Ora il grilletto è la parola stessa, sottolineata a tratti.
 *
 * ⚠️ I due casi sono diversi e vanno provati entrambi:
 *  - `HintLabel`: l'etichetta non fa altro, quindi un tap la apre;
 *  - `HintAnchor`: l'etichetta è ANCHE il bottone di ordinamento. Il click
 *    deve ordinare e non aprire niente, e la spiegazione arriva dall'hover o
 *    dalla pressione lunga. Il test che conta di più è il controllo negativo:
 *    un click che ordina E apre sarebbe passato inosservato a chi prova solo
 *    l'apertura.
 */

const TESTO = "Base rate del detector";

afterEach(() => vi.useRealTimers());

describe("HintLabel", () => {
  it("non porta nessuna icona, e la parola è sottolineata a tratti", () => {
    const { container } = render(<HintLabel text={TESTO}>Prob.</HintLabel>);
    expect(container.querySelector("svg")).toBeNull();
    const bottone = screen.getByRole("button", { name: "Prob." });
    expect(bottone).toHaveClass("decoration-dashed", "underline");
  });

  it("tiene la spiegazione fuori dal documento finché non la si chiede", () => {
    render(<HintLabel text={TESTO}>Prob.</HintLabel>);
    expect(screen.queryByText(TESTO)).not.toBeInTheDocument();
  });

  it("si apre passandoci sopra col mouse", async () => {
    const user = userEvent.setup();
    render(<HintLabel text={TESTO}>Prob.</HintLabel>);
    await user.hover(screen.getByRole("button", { name: "Prob." }));
    expect(await screen.findByText(TESTO)).toBeVisible();
  });

  it("si apre al TAP — il caso che `title` non poteva servire", async () => {
    const user = userEvent.setup();
    render(<HintLabel text={TESTO}>Prob.</HintLabel>);
    await user.click(screen.getByRole("button", { name: "Prob." }));
    expect(await screen.findByText(TESTO)).toBeVisible();
  });

  it("il click non risale: una cella cliccabile attorno non riceve niente", async () => {
    const user = userEvent.setup();
    const cella = vi.fn();
    render(
      <div onClick={cella}>
        <HintLabel text={TESTO}>Prob.</HintLabel>
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "Prob." }));
    expect(cella).not.toHaveBeenCalled();
  });

  it("si chiude con Escape", async () => {
    const user = userEvent.setup();
    render(<HintLabel text={TESTO}>Prob.</HintLabel>);
    await user.click(screen.getByRole("button", { name: "Prob." }));
    expect(await screen.findByText(TESTO)).toBeVisible();
    await user.keyboard("{Escape}");
    expect(screen.queryByText(TESTO)).not.toBeInTheDocument();
  });
});

function Ordinabile({ onSort }: { onSort: () => void }) {
  return (
    <HintAnchor text={TESTO}>
      <button type="button" onClick={onSort}>
        <HintUnderline>Prob.</HintUnderline>
      </button>
    </HintAnchor>
  );
}

describe("HintAnchor — sul bottone di ordinamento", () => {
  it("⚠️ il click ORDINA e non apre niente", async () => {
    const user = userEvent.setup();
    const onSort = vi.fn();
    render(<Ordinabile onSort={onSort} />);
    await user.click(screen.getByRole("button", { name: "Prob." }));
    expect(onSort).toHaveBeenCalledTimes(1);
    // Oltre il ritardo dell'hover: il `pointerdown` del click deve averlo
    // annullato, altrimenti il pannello comparirebbe subito DOPO l'ordinamento.
    await new Promise((r) => setTimeout(r, 400));
    expect(screen.queryByText(TESTO)).not.toBeInTheDocument();
  });

  it("la spiegazione arriva in hover", async () => {
    const user = userEvent.setup();
    render(<Ordinabile onSort={vi.fn()} />);
    await user.hover(screen.getByRole("button", { name: "Prob." }));
    expect(await screen.findByText(TESTO)).toBeVisible();
  });

  it("⚠️ la pressione lunga su touch apre la spiegazione SENZA ordinare", () => {
    vi.useFakeTimers();
    const onSort = vi.fn();
    render(<Ordinabile onSort={onSort} />);
    const bottone = screen.getByRole("button", { name: "Prob." });

    fireEvent.pointerDown(bottone, { pointerType: "touch" });
    act(() => { vi.advanceTimersByTime(500); });
    fireEvent.pointerUp(bottone, { pointerType: "touch" });
    // Il click che il browser emette al rilascio.
    fireEvent.click(bottone);

    expect(screen.getByText(TESTO)).toBeInTheDocument();
    expect(onSort).not.toHaveBeenCalled();
  });

  it("un tap BREVE su touch ordina, come prima", () => {
    // Controllo negativo del caso sopra: senza, un'ancora che mangiasse ogni
    // click passerebbe il test della pressione lunga.
    vi.useFakeTimers();
    const onSort = vi.fn();
    render(<Ordinabile onSort={onSort} />);
    const bottone = screen.getByRole("button", { name: "Prob." });

    fireEvent.pointerDown(bottone, { pointerType: "touch" });
    act(() => { vi.advanceTimersByTime(100); });
    fireEvent.pointerUp(bottone, { pointerType: "touch" });
    fireEvent.click(bottone);
    act(() => { vi.advanceTimersByTime(1000); });

    expect(onSort).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(TESTO)).not.toBeInTheDocument();
  });

  it("senza testo rende il bottone così com'è", () => {
    const onSort = vi.fn();
    render(
      <HintAnchor text={undefined}>
        <button type="button" onClick={onSort}>Ticker</button>
      </HintAnchor>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Ticker" }));
    expect(onSort).toHaveBeenCalledTimes(1);
  });

  it("il bottone non promette un pannello che non esiste", () => {
    // `PopoverAnchor` e non `PopoverTrigger`: niente `aria-controls` verso un
    // id che a riposo non c'è — la forma che axe ha già segnalato una volta.
    render(<Ordinabile onSort={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Prob." })).not.toHaveAttribute("aria-controls");
  });
});
