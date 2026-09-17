import { describe, expect, it } from "vitest";

import { buildPlaybook } from "./tradePlaybook";
// ⚠️ `?raw` di Vite e non un import JSON: questo pacchetto non ha
// `@types/node`, e la stessa scelta e' gia' fatta e commentata in
// `lensGap.test.ts`. Il file e' comunque JSON valido e lo verifica il parse.
import sorgenteVettori from "./playbookVectors.json?raw";

/* I vettori d'oro della geometria del piano.
 *
 * Questo file e' UNA delle due meta' del ponte: l'altra e'
 * `backend/tests/signals/test_piano_di_trade.py`, che pretende gli stessi
 * numeri dal gemello Python (`app/signals/trade_plan.py`). Il gemello serve a
 * far correre stop e target sulle barre per l'esito basato sul piano.
 *
 * Perche' entrambe le meta' servono: se ci fosse solo il test Python, chi
 * cambia la geometria QUI romperebbe un test che sta in un'altra cartella e
 * che gira in un altro job — e la reazione naturale sarebbe rigenerare i
 * vettori, cioe' spostare il metro invece di accorgersi della divergenza.
 * Rosso da questo lato significa: hai cambiato la geometria, aggiorna anche
 * il Python e RIGENERA i vettori nello stesso commit.
 */
interface CasoAtteso {
  side: "long" | "short";
  entry: number;
  stop: number;
  stopPct: number;
  stopCapped: boolean;
  horizon: string;
  targets: { label: string; price: number; rr: number }[];
}
interface Caso {
  nome: string;
  name: string;
  entry: number;
  snapshot: Record<string, unknown>;
  atteso: CasoAtteso | null;
}

const { casi } = JSON.parse(sorgenteVettori) as { casi: Caso[] };

describe("vettori d'oro del piano di trade", () => {
  it("il file porta i casi limite, non solo quelli facili", () => {
    // Pavimento sul contenuto: senza, svuotare il file renderebbe verde ogni
    // confronto qui sotto. E' la forma «un test puo' essere vero di niente».
    const nomi = new Set(casi.map((c) => c.nome));
    for (const atteso of [
      "long_breve", "short_breve", "stop_al_pavimento", "stop_al_tetto",
      "senza_atr_ripiego_2pct", "target_degeneri_tp2_uguale_tp1",
      "senza_invalidazione_nessun_piano",
    ]) {
      expect(nomi.has(atteso), `manca il caso limite «${atteso}»`).toBe(true);
    }
    expect(nomi.size).toBeGreaterThanOrEqual(12);
  });

  it.each(casi.map((c) => [c.nome, c] as const))(
    "%s: buildPlaybook rende i numeri versionati",
    (_nome, caso) => {
      const pb = buildPlaybook(caso.snapshot, caso.entry, caso.name);

      if (caso.atteso === null) {
        expect(pb).toBeNull();
        return;
      }
      expect(pb).not.toBeNull();
      const p = pb!;
      expect(p.side).toBe(caso.atteso.side);
      expect(p.horizon).toBe(caso.atteso.horizon);
      expect(p.stopCapped).toBe(caso.atteso.stopCapped);
      expect(p.entry).toBeCloseTo(caso.atteso.entry, 9);
      expect(p.stop).toBeCloseTo(caso.atteso.stop, 9);
      expect(p.stopPct).toBeCloseTo(caso.atteso.stopPct, 9);
      expect(p.targets).toHaveLength(caso.atteso.targets.length);
      caso.atteso.targets.forEach((suo, i) => {
        expect(p.targets[i].price).toBeCloseTo(suo.price, 9);
        expect(p.targets[i].rr).toBeCloseTo(suo.rr, 9);
      });
    },
  );
});
