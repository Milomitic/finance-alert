import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { PlanOutcomeRow } from "@/api/planOutcomes";

import { SignalOutcomeList } from "./SignalOutcomeList";

/* ⚠️ Il contratto che questa vista esiste per rendere visibile: la posizione
 * si chiude alla PRIMA gamba toccata, e le altre si mostrano lo stesso con la
 * loro data. Un elenco che mostrasse solo la gamba vincente sarebbe un «ha mai
 * toccato il target», cioe' un tasso lusinghiero per costruzione che non
 * corrisponde a nessun guadagno. */

function riga(p: Partial<PlanOutcomeRow> = {}): PlanOutcomeRow {
  return {
    alert_id: 7, ticker: "AAA", name: "AAA Inc.", detector: "sr_flip", tone: "bull",
    signal_date: "2026-03-01", entry_date: "2026-03-02", entry: 100, stop: 96,
    tp1: 108, tp2: null, r: 4, horizon_days: 21, esito: "tp1",
    resolved_date: "2026-03-10", bars_to_outcome: 6, r_multiple: 2.4, mae_r: 0.3,
    mfe_r: 2.1, tp2_reached: false, stop_hit_date: null, tp1_hit_date: "2026-03-10",
    tp2_hit_date: null, source: "emesso",
    ...p,
  };
}

function monta(righe: PlanOutcomeRow[], onApri?: (id: number) => void) {
  return render(
    <MemoryRouter>
      <SignalOutcomeList righe={righe} onApriSegnale={onApri} />
    </MemoryRouter>,
  );
}

describe("SignalOutcomeList", () => {
  it("una riga per segnale, sotto colonne che la nominano", () => {
    // ⚠️ Le intestazioni non sono decorazione: senza, la riga porta quattro
    // valori non etichettati e chi legge deve indovinare quale sia una data,
    // quale un multiplo e quale un conteggio. Stesso difetto che la tabella
    // dei setup aveva e ha chiuso.
    monta([riga()]);
    // «Sequenza» per ruolo: la parola compare anche nella legenda sotto.
    expect(screen.getByRole("button", { name: "Sequenza" })).toBeInTheDocument();
    for (const nome of ["Titolo", "Esito", "Chiusa", "Poi", "R"]) {
      expect(screen.getByText(nome)).toBeInTheDocument();
    }
    expect(screen.getByText("AAA")).toBeInTheDocument();
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.getByText("+2.4R")).toBeInTheDocument();
    expect(screen.getByText("10 mar")).toBeInTheDocument();
  });

  it("⚠️ un target toccato DOPO lo stop resta a schermo, con la sua data", () => {
    // Il caso FLNC: la posizione era chiusa allo stop, quindi -1R e' giusto —
    // e il prezzo al target ci e' arrivato lo stesso, il che dice che quello
    // stop era troppo stretto. Senza la seconda meta' la riga nasconde
    // l'unica diagnosi che questo magazzino sa dare.
    monta([riga({
      esito: "stop", r_multiple: -1, resolved_date: "2026-03-05",
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-18",
    })]);
    expect(screen.getByText("Stop")).toBeInTheDocument();
    expect(screen.getByText("−1.0R")).toBeInTheDocument();
    expect(screen.getByText("5 mar")).toBeInTheDocument();          // chiusa
    const poi = screen.getByText("target 18 mar");                   // poi
    expect(poi).toHaveAttribute("title", expect.stringContaining("la distanza dello stop no"));
  });

  it("non annuncia uno stop troppo stretto quando l'ordine e' l'altro", () => {
    // Controllo negativo: senza, la diagnosi comparirebbe ogni volta che
    // entrambe le gambe sono state toccate — e «entrambe toccate» non e' una
    // diagnosi, l'ORDINE lo e'.
    monta([riga({
      esito: "tp1", resolved_date: "2026-03-10",
      tp1_hit_date: "2026-03-10", stop_hit_date: "2026-03-20",
    })]);
    const poi = screen.getByText("stop 20 mar");
    expect(poi.getAttribute("title")).not.toContain("la distanza dello stop no");
    expect(poi).toHaveAttribute("title", expect.stringContaining("dopo la chiusura"));
  });

  it("senza gambe successive la colonna dice esplicitamente niente", () => {
    // Una cella vuota si legge come «non misurato»; il trattino dice «misurato
    // e non e' successo».
    monta([riga()]);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("un livello ricostruito e' marcato sulla riga E contato sotto la tabella", () => {
    // Una ricostruzione sbagliata e' indistinguibile da una giusta finche'
    // nessuno guarda il campo: quindi il campo si guarda. Il marcatore per
    // riga e' il DATO, la spiegazione in prosa sta una volta sola.
    monta([riga({ source: "ricostruito" }), riga({ alert_id: 8, source: "emesso" })]);
    // Per titolo, non per testo: «ric» compare anche nella nota sotto, e un
    // `getByText` che pesca due nodi non distingue il marcatore dalla
    // spiegazione — passerebbe anche se il marcatore sparisse dalla riga.
    expect(screen.getByTitle(/ricostruito all'indietro/)).toBeInTheDocument();
    expect(screen.getByText(/il detector non emetteva un livello/)).toBeInTheDocument();
  });

  it("senza righe ricostruite ne' marcatore ne' nota compaiono", () => {
    // Controllo negativo del test sopra: una nota sempre presente non
    // distingue piu' niente.
    monta([riga()]);
    expect(screen.queryByTitle(/ricostruito all'indietro/)).not.toBeInTheDocument();
    expect(screen.queryByText(/il detector non emetteva un livello/)).not.toBeInTheDocument();
  });

  it("la riga apre il SEGNALE, che e' la domanda che solleva", () => {
    const apri = vi.fn();
    monta([riga({ alert_id: 42 })], apri);
    // Una riga, un bersaglio: il titolo NON e' un link annidato nel bottone,
    // che sarebbe HTML non valido e si comporta male da tastiera.
    return userEvent.click(screen.getByRole("button", { name: /AAA/ })).then(() => {
      expect(apri).toHaveBeenCalledWith(42);
    });
  });

  it("un elenco vuoto spiega quando nasce una riga, invece di sembrare rotto", () => {
    monta([]);
    expect(screen.getByText(/Nessun piano ancora risolto/)).toBeInTheDocument();
  });

  it("⚠️ la sequenza disegna stop PIENO sulla chiusura e target VUOTO dopo", () => {
    // Il caso che la colonna esiste per far vedere: la posizione chiusa allo
    // stop il 5, e il target toccato il 18 quando non c'era piu' niente da
    // pagare. Il disegno deve dirlo con la forma, non solo col colore.
    monta([riga({
      esito: "stop", r_multiple: -1, resolved_date: "2026-03-05", bars_to_outcome: 3,
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-18",
    })]);
    const disegno = screen.getByRole("img", { name: /Stop colpito il 5 mar/ });
    // Il nome accessibile e' la frase INTERA, gambe successive comprese.
    expect(disegno).toHaveAccessibleName(/Dopo la chiusura il prezzo ha toccato target il 18 mar/);
    const segni = disegno.querySelectorAll("span[aria-hidden].h-2");
    expect(segni).toHaveLength(2);
    const [stop, target] = Array.from(segni);
    expect(stop.className).toMatch(/bg-rose-600/);       // pieno
    expect(target.className).toMatch(/border-emerald-600/); // vuoto
    expect(target.className).toMatch(/rounded-full/);    // la forma del target
  });

  it("uno scaduto ha la barretta in fondo e nessun segno", () => {
    monta([riga({
      esito: "scaduto", r_multiple: 0.4, resolved_date: "2026-03-30", bars_to_outcome: 21,
      tp1_hit_date: null, stop_hit_date: null,
    })]);
    const disegno = screen.getByRole("img", { name: /Orizzonte trascorso/ });
    expect(disegno.querySelectorAll("span[aria-hidden].h-2")).toHaveLength(0);
  });

  it("la legenda del disegno e' a schermo, non in un suggerimento", () => {
    // Un codice di forme che non si vede non si impara.
    monta([riga()]);
    expect(screen.getByText("secondo target")).toBeInTheDocument();
    expect(screen.getByText(/vuoto = toccato dopo la chiusura/)).toBeInTheDocument();
  });
});
