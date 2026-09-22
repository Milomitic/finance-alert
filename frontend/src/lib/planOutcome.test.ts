import { describe, expect, it } from "vitest";

import type { PlanOutcomeRow } from "@/api/planOutcomes";

import {
  formatPL, formatR, gambaChiudente, plPercentuale, raccontaPiano, sedute, sequenzaGambe,
  stopTroppoStretto, tracciaGara,
} from "./planOutcome";

function riga(p: Partial<PlanOutcomeRow> = {}): PlanOutcomeRow {
  return {
    alert_id: 1, ticker: "AAA", name: "AAA Inc.", detector: "sr_flip", tone: "bull",
    signal_date: "2026-03-01", entry_date: "2026-03-02", entry: 100, stop: 96,
    tp1: 108, tp2: 112, r: 4, horizon_days: 21, esito: "tp1",
    resolved_date: "2026-03-10", bars_to_outcome: 6, r_multiple: 2, mae_r: 0.3,
    mfe_r: 2.1, tp2_reached: false, stop_hit_date: null, tp1_hit_date: "2026-03-10",
    tp2_hit_date: null,
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

describe("raccontaPiano", () => {
  it("dice quale gamba ha chiuso e quanto ha reso", () => {
    expect(raccontaPiano(riga())).toBe("Target colpito il 10 mar (+2.0R).");
  });

  it("⚠️ e dice anche che cosa e' successo DOPO, con la diagnosi", () => {
    // È la seconda metà della storia: la posizione era chiusa allo stop,
    // quindi −1R è giusto, e il prezzo al target ci è arrivato lo stesso.
    const s = raccontaPiano(riga({
      esito: "stop", r_multiple: -1, resolved_date: "2026-03-05",
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-18",
    }));
    expect(s).toContain("Stop colpito il 5 mar (−1.0R)");
    expect(s).toContain("target il 18 mar");
    expect(s).toContain("la distanza dello stop no");
  });

  it("non aggiunge la diagnosi quando l'ordine e' l'altro", () => {
    // Controllo negativo: «entrambe toccate» non è una diagnosi, l'ORDINE lo è.
    const s = raccontaPiano(riga({
      esito: "tp1", resolved_date: "2026-03-10",
      tp1_hit_date: "2026-03-10", stop_hit_date: "2026-03-20",
    }));
    expect(s).toContain("stop il 20 mar");
    expect(s).not.toContain("la distanza dello stop no");
  });

  it("uno scaduto dice che non ha toccato niente, invece di tacere", () => {
    expect(raccontaPiano(riga({
      esito: "scaduto", r_multiple: 0.4, resolved_date: "2026-03-30",
      tp1_hit_date: null, stop_hit_date: null,
    }))).toBe("Orizzonte trascorso il 30 mar senza toccare né stop né target (+0.4R).");
  });
});

describe("sedute", () => {
  it("conta i giorni feriali DOPO l'ingresso, fino alla data compresa", () => {
    // 2 marzo 2026 e' un lunedi'. La gara parte dalla barra successiva
    // all'ingresso, quindi il giorno stesso vale zero.
    expect(sedute("2026-03-02", "2026-03-02")).toBe(0);
    expect(sedute("2026-03-02", "2026-03-06")).toBe(4);   // mar-ven
    // Venerdi' -> lunedi': il fine settimana non e' una seduta.
    expect(sedute("2026-03-06", "2026-03-09")).toBe(1);
  });

  it("una data illeggibile o all'indietro vale zero, non un numero inventato", () => {
    expect(sedute("2026-03-10", "2026-03-02")).toBe(0);
    expect(sedute("non-una-data", "2026-03-02")).toBe(0);
  });
});

describe("tracciaGara", () => {
  it("⚠️ stop e poi target: lo stop sulla barretta, il target DOPO e vuoto", () => {
    // Il caso che la colonna esiste per far vedere a colpo d'occhio.
    const t = tracciaGara(riga({
      esito: "stop", r_multiple: -1, resolved_date: "2026-03-05", bars_to_outcome: 3,
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-18",
    }));
    expect(t.chiusura).toBeCloseTo(3 / 21);
    const [stop, target] = t.punti;
    expect(stop).toMatchObject({ chiave: "stop", chiude: true, dopo: false });
    expect(stop.x).toBeCloseTo(t.chiusura);
    expect(target).toMatchObject({ chiave: "tp1", chiude: false, dopo: true });
    expect(target.x).toBeCloseTo(12 / 21);                 // 12 sedute dal 2 al 18 marzo
    expect(target.x).toBeGreaterThan(t.chiusura);
  });

  it("la chiusura usa le sedute VERE, non la stima dal calendario", () => {
    // bars_to_outcome e' esatto; le date contano solo i fine settimana.
    const t = tracciaGara(riga({ bars_to_outcome: 7, resolved_date: "2026-03-10" }));
    expect(t.chiusura).toBeCloseTo(7 / 21);
    expect(t.punti[0].x).toBeCloseTo(7 / 21);
  });

  it("⚠️ una gamba dopo la chiusura non finisce MAI a sinistra della barretta", () => {
    // Le festivita' non sono contate: con qualche seduta di scarto la stima
    // di una gamba successiva potrebbe cadere prima della chiusura, e il
    // disegno direbbe il contrario dell'ordine vero.
    const t = tracciaGara(riga({
      esito: "stop", r_multiple: -1, resolved_date: "2026-03-04", bars_to_outcome: 10,
      stop_hit_date: "2026-03-04", tp1_hit_date: "2026-03-05",
    }));
    const target = t.punti.find((p) => p.chiave === "tp1")!;
    expect(target.dopo).toBe(true);
    expect(target.x).toBeGreaterThanOrEqual(t.chiusura);
  });

  it("stop e target nella stessa barra stanno nello stesso punto, uno sopra l'altro", () => {
    const t = tracciaGara(riga({
      esito: "ambigua", r_multiple: -1, resolved_date: "2026-03-05", bars_to_outcome: 3,
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-05",
    }));
    expect(t.punti.map((p) => p.x)).toEqual([t.chiusura, t.chiusura]);
    expect(t.punti.map((p) => p.impilato)).toEqual([0, 1]);
    // Nessuno dei due e' «dopo»: e' la stessa seduta.
    expect(t.punti.every((p) => !p.dopo)).toBe(true);
  });

  it("uno scaduto chiude a fine orizzonte e non ha segni", () => {
    const t = tracciaGara(riga({
      esito: "scaduto", r_multiple: 0.4, resolved_date: "2026-03-30", bars_to_outcome: 21,
      tp1_hit_date: null, stop_hit_date: null,
    }));
    expect(t.chiusura).toBe(1);
    expect(t.punti).toEqual([]);
  });
});

describe("plPercentuale", () => {
  it("long a target: il guadagno sul prezzo d'ingresso", () => {
    // Ingresso 100, stop a 96 (R = 4), target a 2,0R: uscita a 108 = +8%.
    expect(plPercentuale({ r_multiple: 2, r: 4, entry: 100 })).toBeCloseTo(8, 9);
  });

  it("allo stop: meno la distanza dello stop, per entrambi i versi", () => {
    expect(plPercentuale({ r_multiple: -1, r: 4, entry: 100 })).toBeCloseTo(-4, 9);
    // Short: ingresso 50, stop a 52 (R = 2), preso: la perdita e' −4%.
    expect(plPercentuale({ r_multiple: -1, r: 2, entry: 50 })).toBeCloseTo(-4, 9);
  });

  it("short a target: il prezzo e' sceso e il P/L e' POSITIVO", () => {
    // Ingresso 50, R = 2, target a 3R: uscita a 44 = +12% per chi e' short.
    expect(plPercentuale({ r_multiple: 3, r: 2, entry: 50 })).toBeCloseTo(12, 9);
  });

  it("un ingresso inservibile rende null, non infinito", () => {
    expect(plPercentuale({ r_multiple: 1, r: 4, entry: 0 })).toBeNull();
    expect(plPercentuale({ r_multiple: Number.NaN, r: 4, entry: 100 })).toBeNull();
  });
});

describe("formatPL", () => {
  it("il segno sempre, e il meno tipografico", () => {
    expect(formatPL(8.44)).toBe("+8.4%");
    expect(formatPL(-2.06)).toBe("\u22122.1%");
    expect(formatPL(0)).toBe("0.0%");
    expect(formatPL(null)).toBe("—");
  });
});
