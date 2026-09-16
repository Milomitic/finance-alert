import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./dialog";

/* Chiuso un dialogo, il focus torna a chi l'aveva aperto.
 *
 * Trovato nel collaudo in browser (2026-09-16): dal pulsante «segnale» di un
 * setup il dialogo si apriva, Esc lo chiudeva, e il focus finiva sul BODY —
 * chi naviga da tastiera ripartiva dall'inizio della pagina. La forma che lo
 * produce e' quella di quasi tutti i dialoghi dell'app: aperti da uno STATO
 * (`open={x !== null}`) invece che da un `DialogTrigger`, con il contenuto che
 * sparisce appena lo stato torna nullo. Il test la riproduce, dato asincrono
 * compreso: il segnale arriva da una richiesta, non subito.
 */

function Harness({ asincrono }: { asincrono: boolean }) {
  const [id, setId] = useState<number | null>(null);
  return (
    <>
      <button type="button" onClick={() => (asincrono ? setTimeout(() => setId(1), 20) : setId(1))}>
        apri
      </button>
      {id === null ? (
        <Dialog open={false} onOpenChange={() => setId(null)} />
      ) : (
        <Dialog open onOpenChange={(o) => !o && setId(null)}>
          <DialogContent>
            <DialogTitle>Segnale {id}</DialogTitle>
            <DialogDescription>dettaglio</DialogDescription>
            <button type="button">dentro</button>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

describe("il focus torna a chi ha aperto il dialogo", () => {
  it.each([false, true])("con il dato asincrono = %s", async (asincrono) => {
    const user = userEvent.setup();
    render(<Harness asincrono={asincrono} />);
    const apri = screen.getByRole("button", { name: "apri" });
    await user.click(apri);
    await screen.findByRole("dialog");
    await waitFor(() => expect(apri).not.toHaveFocus());

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(apri).toHaveFocus());
  });

  it("non sovrascrive un focus che l'app ha mandato altrove", async () => {
    function Altrove() {
      const [aperto, setAperto] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setAperto(true)}>apri</button>
          <input aria-label="ricerca" />
          <Dialog open={aperto} onOpenChange={(o) => !o && setAperto(false)}>
            {/* Il contratto di Radix per mandare il focus altrove: annullare
                `onCloseAutoFocus`. Il ripristino non deve scavalcarlo. */}
            <DialogContent
              onCloseAutoFocus={(e) => {
                e.preventDefault();
                document.querySelector<HTMLInputElement>("input")?.focus();
              }}
            >
              <DialogTitle>t</DialogTitle>
              <DialogDescription>d</DialogDescription>
            </DialogContent>
          </Dialog>
        </>
      );
    }
    const user = userEvent.setup();
    render(<Altrove />);
    await user.click(screen.getByRole("button", { name: "apri" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.getByRole("textbox", { name: "ricerca" })).toHaveFocus();
  });
});
