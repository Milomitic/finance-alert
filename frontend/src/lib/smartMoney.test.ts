import { describe, expect, it } from "vitest";

import type { ActionAggregate, InstitutionalSummary } from "@/api/types";

import {
  azioneDecisiva, mossePiuPesanti, settoreDominante, statisticheFondi,
} from "./smartMoney";

const ADESSO = Date.parse("2026-09-18T12:00:00Z");

function fondo(
  slug: string, periodo: string | null, valore: number | null,
): InstitutionalSummary {
  return {
    id: 1, slug, name: slug, manager_name: null, type: "superinvestor",
    source: "sec", source_url: null, description: null, aum_usd: null,
    latest_period_end: periodo, total_value_usd: valore, total_positions: 10,
  };
}

function mossa(ticker: string, value_usd: number | null, action = "add"): ActionAggregate {
  return {
    ticker, company_name: ticker, institutional_slug: "f", institutional_name: "Fondo",
    period_end_date: "2026-06-30", action, qoq_change_pct: 10, portfolio_pct: 2,
    value_usd, stock_id: null,
  };
}

describe("statisticheFondi", () => {
  const fondi = [
    fondo("a", "2026-06-30", 1_000_000_000),
    fondo("b", "2026-06-30", 500_000_000),
    fondo("c", "2026-03-31", 200_000_000),   // in ritardo, non ancora fermo
    fondo("d", "2025-12-31", 100_000_000),   // fermo da oltre due trimestri
    fondo("e", null, null),                   // mai depositato
  ];

  it("il trimestre piu' recente e quanti fondi ci sono gia' arrivati", () => {
    /* ⚠️ I 13F arrivano scaglionati fino a 45 giorni dopo la chiusura: dire
     * «ultimo trimestre: giugno» senza dire quanti ci sono arrivati lascia
     * credere che la fotografia sia completa. */
    const s = statisticheFondi(fondi, ADESSO);
    expect(s.ultimoTrimestre).toBe("2026-06-30");
    expect(s.fondiSulTrimestre).toBe(2);
    expect(s.totale).toBe(5);
  });

  it("somma solo i portafogli dichiarati", () => {
    expect(statisticheFondi(fondi, ADESSO).capitale).toBe(1_800_000_000);
  });

  it("⚠️ senza nessun valore il capitale e' ignoto, non zero", () => {
    // Zero direbbe «questi fondi non possiedono niente»: e' un'affermazione,
    // non l'assenza di una misura.
    expect(statisticheFondi([fondo("x", "2026-06-30", null)], ADESSO).capitale).toBeNull();
  });

  it("conta fermi solo i fondi oltre due trimestri", () => {
    // Dicembre 2025 e' fermo a settembre 2026; marzo 2026 e' solo in ritardo,
    // ed e' normale per un fondo che deposita tardi.
    const s = statisticheFondi(fondi, ADESSO);
    expect(s.fermi).toBe(1);
  });

  it("un elenco vuoto non inventa niente", () => {
    const s = statisticheFondi([], ADESSO);
    expect(s).toEqual({
      totale: 0, capitale: null, ultimoTrimestre: null, fondiSulTrimestre: 0, fermi: 0,
    });
    expect(statisticheFondi(undefined, ADESSO).totale).toBe(0);
  });
});

describe("mossePiuPesanti", () => {
  it("ordina per valore della posizione e taglia alla lunghezza chiesta", () => {
    const righe = [mossa("A", 1e6), mossa("B", 9e9), mossa("C", 3e8)];
    expect(mossePiuPesanti(righe, 2).map((r) => r.ticker)).toEqual(["B", "C"]);
  });

  it("⚠️ una riga senza valore va in fondo, non trattata come zero", () => {
    // «Valore ignoto» e «posizione da zero dollari» sono cose diverse.
    const righe = [mossa("IGNOTA", null), mossa("PICCOLA", 1_000)];
    expect(mossePiuPesanti(righe, 5).map((r) => r.ticker)).toEqual(["PICCOLA", "IGNOTA"]);
  });

  it("non esplode su un elenco assente", () => {
    expect(mossePiuPesanti(undefined, 3)).toEqual([]);
  });
});

describe("settoreDominante", () => {
  it("rende il settore piu' pesante con la sua quota sul totale", () => {
    const d = settoreDominante({ Tech: 600, Energy: 300, Health: 100 });
    expect(d?.settore).toBe("Tech");
    expect(d?.quota).toBeCloseTo(60, 5);
  });

  it("su un totale nullo non calcola una quota", () => {
    // Una percentuale di zero non esiste, e stamparla come 0% o NaN sarebbe
    // peggio che non stampare niente.
    expect(settoreDominante({})).toBeNull();
    expect(settoreDominante({ Tech: 0 })).toBeNull();
    expect(settoreDominante(undefined)).toBeNull();
  });
});

describe("azioneDecisiva", () => {
  it("aprire e chiudere del tutto dicono qualcosa di netto", () => {
    expect(azioneDecisiva("new")).toBe(true);
    expect(azioneDecisiva("sold_out")).toBe(true);
  });

  it("un aumento o una riduzione sono manutenzione", () => {
    // Controllo negativo: senza, la funzione potrebbe rendere sempre vero e
    // l'evidenziazione perderebbe ogni significato.
    expect(azioneDecisiva("add")).toBe(false);
    expect(azioneDecisiva("reduce")).toBe(false);
    expect(azioneDecisiva(null)).toBe(false);
  });
});
