import type { CalendarEvent, EarningsEvent } from "@/api/types";

import { agendaDelGiorno, type VoceMacro } from "./oggiMercato";
import type { Rilevanza } from "./settimana";

/* ─── I quattro giorni dell'agenda nel jumbotron (2026-10-12) ──────────────
 *
 * Oggi — o il primo giorno lavorativo, se oggi e' sabato o domenica — e i tre
 * lavorativi dopo, in due righe da due. Il riquadro ha un'altezza FISSA e
 * nessuno scorrimento: le righe si dividono quell'altezza in proporzione a
 * quante voci hanno, e un giorno che ne ha piu' di quante ne entrano lo dice
 * con «+N altre» invece di tagliarle in silenzio.
 *
 * ⚠️ Fissa e non «quanto serve»: il calendario arriva dopo il resto della
 * fascia, e un riquadro che cresce all'arrivo dei dati sposterebbe tutto cio'
 * che sta sotto (il cancello CLS, FA-106). E l'altezza si divide per CONTO di
 * voci, non misurando il DOM: e' aritmetica, quindi un test la puo' fissare.
 *
 * I giorni sono quelli di New York, come in `oggiMercato.ts`. Le festivita'
 * di borsa non sono note qui: un giorno feriale di festa compare, vuoto, ed e'
 * un'informazione anche quella.
 */

export interface TrimestraleAgenda {
  evento: EarningsEvent;
  /** Se il titolo e' fra i tuoi: in posizione o preferito. */
  rilevanza: Rilevanza | null;
}

export interface GiornoAgenda {
  giorno: string;
  /** Giorni di calendario da oggi: 0 = oggi. */
  distanza: number;
  /** Oggi tutti i rilasci macro; gli altri giorni solo quelli importanti. */
  macro: VoceMacro[];
  /** Tutte le trimestrali del giorno, prima le tue, poi per capitalizzazione. */
  trimestrali: TrimestraleAgenda[];
}

/** Quante voci entrano nel riquadro, sommando le due righe. */
export const LINEE_AGENDA = 10;

function piuGiorni(giorno: string, n: number): string {
  // Mezzogiorno UTC: nessuna ora legale puo' spostarlo nel giorno accanto.
  const t = new Date(`${giorno}T12:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}

function feriale(giorno: string): boolean {
  const d = new Date(`${giorno}T12:00:00Z`).getUTCDay();
  return d !== 0 && d !== 6;
}

const ORDINE: Record<Rilevanza, number> = { posizione: 0, preferito: 1 };

export function giorniAgenda(
  eventi: readonly CalendarEvent[] | undefined,
  oggiET: string,
  titoli: ReadonlyMap<string, Rilevanza>,
  quanti = 4,
): GiornoAgenda[] {
  const out: GiornoAgenda[] = [];
  for (let i = 0; out.length < quanti && i < 14; i++) {
    const giorno = piuGiorni(oggiET, i);
    if (!feriale(giorno)) continue;
    const a = agendaDelGiorno(eventi, giorno);
    const trimestrali = [...a.primaDellApertura, ...a.dopoLaChiusura, ...a.senzaOrario]
      .map((evento) => ({ evento, rilevanza: titoli.get(evento.ticker) ?? null }))
      .sort((x, y) => {
        const rx = x.rilevanza ? ORDINE[x.rilevanza] : 2;
        const ry = y.rilevanza ? ORDINE[y.rilevanza] : 2;
        return rx - ry || (y.evento.market_cap ?? -1) - (x.evento.market_cap ?? -1);
      });
    out.push({
      giorno,
      distanza: i,
      macro: i === 0 ? a.macro : a.macro.filter((m) => m.importanza === "high"),
      trimestrali,
    });
  }
  return out;
}

export function vociDelGiorno(g: GiornoAgenda): number {
  return g.macro.length + g.trimestrali.length;
}

/** Le linee di ciascuna riga, in proporzione alle voci del giorno piu' pieno
 *  della riga. Almeno due per riga: una vuota deve poter dire che e' vuota,
 *  e una piena deve poter mostrare una voce e il suo «+N». */
export function ripartisciRighe(bisogni: readonly [number, number], totale = LINEE_AGENDA): [number, number] {
  const [a, b] = bisogni.map((x) => Math.max(1, x));
  const prima = Math.min(totale - 2, Math.max(2, Math.round((totale * a) / (a + b))));
  return [prima, totale - prima];
}

/** Quante voci mostrare in `linee` linee, e quante restano fuori. Quando non
 *  entrano tutte, l'ultima linea e' il «+N altre». */
export function taglia(voci: number, linee: number): { mostrate: number; altre: number } {
  if (voci <= linee) return { mostrate: voci, altre: 0 };
  const mostrate = Math.max(0, linee - 1);
  return { mostrate, altre: voci - mostrate };
}
