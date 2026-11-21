import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Segmentato } from "./segmentato";

describe("Segmentato", () => {
  it("un gruppo con nome, un bottone premuto, e il cambio passa l'id", () => {
    const onCambia = vi.fn();
    render(
      <Segmentato etichetta="Quali titoli" valore="miei" onCambia={onCambia}
        voci={[{ id: "miei", label: "I miei" }, { id: "tutti", label: "Tutti" }]} />,
    );
    expect(screen.getByRole("group", { name: "Quali titoli" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I miei" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Tutti" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "Tutti" }));
    expect(onCambia).toHaveBeenCalledWith("tutti");
  });

  it("non promette pannelli: niente tab ne' aria-controls", () => {
    const { container } = render(
      <Segmentato etichetta="Vista" valore="a" onCambia={() => {}} voci={[{ id: "a", label: "A" }, { id: "b", label: "B" }]} />,
    );
    expect(container.querySelector("[role=tab], [aria-controls]")).toBeNull();
  });
});
