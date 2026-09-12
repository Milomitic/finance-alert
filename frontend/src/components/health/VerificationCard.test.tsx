import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Verification } from "@/api/platformHealth";

import VerificationCard from "./VerificationCard";

/* ⚠️ Il test che conta e' quello sullo stato IGNOTO, come per la provenienza
 * dell'immagine. «351 su 1366» e «102 su 10 rotte» sono facili; il modo di
 * sbagliare questa scheda e' stampare 0 quando la linea di base non c'e',
 * perche' uno 0 qui si legge «nessun arretrato» — l'opposto della verita'. */

function dati(over: Partial<Verification> = {}): Verification {
  return {
    codice_mai_eseguito: { conteggio: 351, totale: 1366, perche: "Arretrato misurato, non obiettivo: molte sono legittime." },
    violazioni_a11y: { conteggio: 103, totale: 10, perche: "Violazioni preesistenti; il cancello vieta la crescita." },
    mutanti_sopravvissuti: { conteggio: 85, totale: 130, perche: "Righe eseguite la cui correttezza nessuno verifica." },
    ...over,
  };
}

describe("VerificationCard", () => {
  it("mostra ogni conteggio col suo denominatore", () => {
    render(<VerificationCard verification={dati()} />);
    expect(screen.getByText("351")).toBeInTheDocument();
    // Il testo e' spezzato su piu' nodi (numero e denominatore sono elementi
    // distinti), quindi si interroga il contenuto renderizzato invece del
    // singolo nodo — `getByText` su una stringa che attraversa elementi non la
    // trova mai, ed e' una trappola classica di testing-library.
    /* Testo NORMALIZZATO prima del confronto: numero e denominatore sono nodi
     * distinti, e il separatore delle migliaia dipende dall'ICU disponibile
     * (it-IT da' "1.366", un runtime senza dati locali "1,366"). Confrontare
     * la stringa esatta legherebbe il test all'ambiente invece che al
     * comportamento. */
    const testo = (document.body.textContent ?? "").replace(/[.,\s  ]/g, "");
    expect(testo).toContain("su1366censite");
    expect(screen.getByText("103")).toBeInTheDocument();
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(testo).toContain("su130mutanti");
    expect(testo).toContain("su10rotte");
  });

  it("dice che i cancelli vietano la CRESCITA, non pretendono lo zero", () => {
    /* Senza questa frase il numero si legge come una pagella, e la reazione
     * giusta («non deve salire») diventa quella sbagliata («va azzerato»). */
    render(<VerificationCard verification={dati()} />);
    expect(screen.getByText(/crescano/)).toBeInTheDocument();
  });

  it("⚠️ un arretrato IGNOTO non diventa zero", () => {
    render(<VerificationCard verification={dati({ codice_mai_eseguito: null })} />);
    expect(screen.getByText("non dichiarato")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("non si disegna affatto se non c'e' niente da dire", () => {
    const { container } = render(<VerificationCard verification={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("regge un payload vecchio senza il campo", () => {
    const { container } = render(<VerificationCard />);
    expect(container).toBeEmptyDOMElement();
  });
});
