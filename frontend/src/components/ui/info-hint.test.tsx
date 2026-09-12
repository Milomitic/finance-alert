import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { InfoHint } from "./info-hint";

/* ─── Perché questo componente esiste, e cosa deve dimostrare il test ─────
 *
 * L'app porta 112 spiegazioni lunghe dentro l'attributo `title`. Su un
 * telefono `title` non si apre MAI: non esiste un hover da produrre, e il
 * long-press apre il menu contestuale del sistema. Quindi quelle spiegazioni
 * non sono "compatte", sono IRRAGGIUNGIBILI — il difetto è di accesso, non
 * di spazio.
 *
 * Il test che conta è quindi uno solo: la spiegazione si apre con un TAP.
 * Un `title` non può superarlo, e questo è ciò che lo rende un test vero e
 * non una conferma di quello che già c'era. */
describe("InfoHint", () => {
  it("tiene la spiegazione fuori dal documento finché non la si chiede", () => {
    render(<InfoHint label="Forza" text="Forza del pattern (0-100)" />);
    // Il punto dell'esercizio: la spiegazione non occupa spazio a riposo.
    expect(screen.queryByText("Forza del pattern (0-100)")).not.toBeInTheDocument();
  });

  it("si apre al TAP — il caso che `title` non può servire", async () => {
    const user = userEvent.setup();
    render(<InfoHint label="Forza" text="Forza del pattern (0-100)" />);

    await user.click(screen.getByRole("button", { name: /forza/i }));

    expect(await screen.findByText("Forza del pattern (0-100)")).toBeVisible();
  });

  it("si apre anche in hover, per chi ha un mouse", async () => {
    const user = userEvent.setup();
    render(<InfoHint label="Prob." text="Base rate del detector" />);

    await user.hover(screen.getByRole("button", { name: /prob/i }));

    expect(await screen.findByText("Base rate del detector")).toBeVisible();
  });

  it("il grilletto ha un nome accessibile che nomina la colonna", () => {
    /* Un'icona-bottone senza nome è esattamente la violazione che axe
     * intercetta (CLAUDE.md: la metà strutturale è ciò che jsdom vede).
     * Il nome deve dire DI COSA è la spiegazione, non "info". */
    render(<InfoHint label="Orizzonte" text="breve / medio / lungo" />);
    expect(
      screen.getByRole("button", { name: "Spiegazione: Orizzonte" }),
    ).toBeInTheDocument();
  });

  it("si chiude con Escape", async () => {
    const user = userEvent.setup();
    render(<InfoHint label="Esito" text="verde = direzione azzeccata" />);

    await user.click(screen.getByRole("button", { name: /esito/i }));
    expect(await screen.findByText("verde = direzione azzeccata")).toBeVisible();

    await user.keyboard("{Escape}");
    expect(screen.queryByText("verde = direzione azzeccata")).not.toBeInTheDocument();
  });
});
