import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { NAV } from "@/lib/nav";

import { BarraInferiore } from "./BarraInferiore";

describe("BarraInferiore", () => {
  it("le quattro destinazioni di ogni giorno, e «Altro» che apre il menu", () => {
    const onAltro = vi.fn();
    render(
      <MemoryRouter initialEntries={["/alerts"]}>
        <BarraInferiore onAltro={onAltro} altroAperto={false} />
      </MemoryRouter>,
    );
    const barra = within(screen.getByRole("navigation", { name: "Navigazione principale" }));
    const link = barra.getAllByRole("link");
    expect(link.map((l) => l.getAttribute("href"))).toEqual(["/", "/stocks", "/alerts", "/positions"]);
    expect(barra.getByRole("link", { name: "Segnali" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(barra.getByRole("button", { name: "Altro" }));
    expect(onAltro).toHaveBeenCalledTimes(1);
  });

  it("i nomi vengono dal menu, non da una copia", () => {
    render(
      <MemoryRouter>
        <BarraInferiore onAltro={() => {}} altroAperto={false} />
      </MemoryRouter>,
    );
    for (const to of ["/", "/stocks", "/alerts", "/positions"]) {
      const nome = NAV.find((e) => e.to === to)?.label ?? "";
      expect(screen.getByRole("link", { name: nome })).toHaveAttribute("href", to);
    }
  });
});
