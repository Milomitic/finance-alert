import { describe, expect, it } from "vitest";

import type { PlanOutcomeRow } from "@/api/planOutcomes";

import { formatR, gambaChiudente, sequenzaGambe, stopTroppoStretto } from "./planOutcome";

function riga(p: Partial<PlanOutcomeRow> = {}): PlanOutcomeRow {
  return {
    alert_id: 1, ticker: "AAA", name: "AAA Inc.", detector: "sr_flip", tone: "bull",
    signal_date: "2026-03-01", entry_date: "2026-03-02", entry: 100, stop: 96,
    tp1: 108, tp2: 112, r: 4, horizon_days: 21, esito: "tp1",
    resolved_date: "2026-03-10", bars_to_outcome: 6, r_multiple: 2, mae_r: 0.3,
    mfe_r: 2.1, tp2_reached: false, stop_hit_date: null, tp1_hit_date: "2026-03-10",
    tp2_hit_date: null, source: "emesso",
    ...p,
  };
}

describe("sequenzaGambe", () => {
  it("le gambe escono in ordine cronologico, e quella che chiude e' marcata", () => {
    const g = sequenzaGambe(riga({
      esito: "tp1", resolved_date: "2026-03-10",
      tp1_hit_date: "2026-03-10", tp2_hit_date: "2026-03-14",
    }));
    expect(g.map((x) => x.chiave)).toEqual(["tp1", "tp2"]);
    expect(g[0].chiude).toBe(true);
    expect(g[1].chiude).toBe(false);
  });

  it("⚠️ una gamba toccata DOPO la chiusura e' dichiarata tale", () => {
    // Il caso che da' senso a tutta la vista: stop il 5, target il 18. La
    // posizione era chiusa, quindi vale -1R ed e' giusto — ma il prezzo al
    // target ci e' arrivato, e senza dirlo la riga nasconderebbe che quello
    // stop era troppo stretto.
    const g = sequenzaGambe(riga({
      esito: "stop", resolved_date: "2026-03-05", r_multiple: -1,
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-18",
    }));
    expect(g.map((x) => x.chiave)).toEqual(["stop", "tp1"]);
    expect(g[0]).toMatchObject({ chiude: true, dopo: false });
    expect(g[1]).toMatchObject({ chiude: false, dopo: true });
  });

  it("nella stessa barra lo stop viene per primo, e nessuna delle due e' «dopo»", () => {
    // ⚠️ `dopo` si misura sulla data di CHIUSURA, non sulla gamba precedente:
    // confrontandola con quella verrebbe marcato «dopo» un target toccato
    // nella stessa seduta dello stop, che e' falso.
    const g = sequenzaGambe(riga({
      esito: "ambigua", resolved_date: "2026-03-06", r_multiple: -1,
      stop_hit_date: "2026-03-06", tp1_hit_date: "2026-03-06",
    }));
    expect(g.map((x) => x.chiave)).toEqual(["stop", "tp1"]);
    expect(g.every((x) => !x.dopo)).toBe(true);
    expect(g[0].chiude).toBe(true);
    expect(g[1].chiude).toBe(false);
  });

  it("un piano scaduto non ha gambe da mostrare", () => {
    // Controllo negativo: se la funzione inventasse una gamba per l'esito
    // «scaduto», ogni riga scaduta racconterebbe un tocco mai avvenuto.
    expect(sequenzaGambe(riga({
      esito: "scaduto", resolved_date: "2026-03-30",
      stop_hit_date: null, tp1_hit_date: null,
    }))).toEqual([]);
  });
});

describe("gambaChiudente", () => {
  it("una barra ambigua si assegna allo STOP, non al target", () => {
    // La convenzione pessimista: il dato giornaliero non dice quale sia
    // venuto prima, e l'altra scelta si auto-elogia.
    expect(gambaChiudente("ambigua")).toBe("stop");
    expect(gambaChiudente("stop")).toBe("stop");
    expect(gambaChiudente("tp1")).toBe("tp1");
    expect(gambaChiudente("scaduto")).toBeNull();
  });
});

describe("stopTroppoStretto", () => {
  it("vero solo quando lo stop PRECEDE un target poi arrivato", () => {
    expect(stopTroppoStretto(riga({
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-18",
    }))).toBe(true);
  });

  it("⚠️ non e' «entrambe toccate»: l'ordine e' tutta la diagnosi", () => {
    expect(stopTroppoStretto(riga({
      stop_hit_date: "2026-03-18", tp1_hit_date: "2026-03-05",
    }))).toBe(false);
    expect(stopTroppoStretto(riga({
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-05",
    }))).toBe(false);
    expect(stopTroppoStretto(riga({ stop_hit_date: null }))).toBe(false);
  });
});

describe("formatR", () => {
  it("porta sempre il segno: la grandezza da sola non dice l'esito", () => {
    expect(formatR(2.44)).toBe("+2.4R");
    expect(formatR(-1)).toBe("−1.0R");
    expect(formatR(0)).toBe("0.0R");
  });
});
