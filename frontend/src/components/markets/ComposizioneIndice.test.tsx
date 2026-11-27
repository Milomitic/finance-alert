import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Composizione } from "@/hooks/useMercati";

import { ComposizioneIndice } from "./ComposizioneIndice";

/* FA-186: la composizione di un indice, con i denominatori a schermo. */

const base = (pesatoSulPrezzo: boolean): Composizione => ({
  indice: { code: "SP500", nome: "S&P 500", titoli_nel_catalogo: 503, nota: null, pesato_sul_prezzo: pesatoSulPrezzo },
  ampiezza: { avanzano: 402, scendono: 98, sopra_ema50_pct: 61.2, sopra_ema200_pct: 55, nuovi_massimi_52s: 41,
    nuovi_minimi_52s: 6, rsi_sopra_70: 22, rsi_sotto_30: 4, var_media_pct: 1.1 },
  settori: [{ settore: "Technology", titoli: 68, var_media_pct: 1.4, peso_pct: pesatoSulPrezzo ? null : 31 }],
  migliori: [{ ticker: "NVDA", nome: "Nvidia", settore: "Technology", var_pct: 4.2,
    peso_pct: pesatoSulPrezzo ? null : 7, contributo_pp: pesatoSulPrezzo ? null : 0.294 }],
  peggiori: [{ ticker: "KO", nome: "Coca-Cola", settore: "Staples", var_pct: -1.5, peso_pct: null, contributo_pp: null }],
  alla_scansione_del: "2026-11-27T22:30:00Z",
});

function monta(c: Composizione) {
  return render(<MemoryRouter><ComposizioneIndice c={c} /></MemoryRouter>);
}

describe("ComposizioneIndice", () => {
  it("ampiezza col suo denominatore, variazioni in punti, link allo screener filtrato", () => {
    monta(base(false));
    expect(screen.getByText("402 in rialzo")).toBeInTheDocument();
    expect(screen.getAllByText("su 503")).toHaveLength(4);
    expect(screen.getByText("55%")).toBeInTheDocument();
    // 4,2 sono gia' punti percentuali: non va moltiplicato per cento.
    expect(screen.getByText("+4,20%")).toBeInTheDocument();
    expect(screen.getByText("+0,29%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Apri i 503 titoli nello screener/ })).toHaveAttribute("href", "/stocks?index=SP500");
    expect(screen.getByRole("link", { name: /NVDA/ })).toHaveAttribute("href", "/stocks/NVDA");
    expect(screen.getByText(/stimato sulla capitalizzazione del catalogo/)).toBeInTheDocument();
  });

  it("un indice pesato sul prezzo non ha contributi e lo dice", () => {
    monta(base(true));
    expect(screen.queryByText("+0,29%")).toBeNull();
    expect(screen.getByText(/Indice pesato sul prezzo/)).toBeInTheDocument();
    expect(screen.getByText("Settori per numero di titoli")).toBeInTheDocument();
    expect(screen.getByText("68 titoli")).toBeInTheDocument();
  });
});
