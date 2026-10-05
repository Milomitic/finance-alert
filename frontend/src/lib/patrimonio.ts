import type { EtoroAndamento, EtoroPeriodo, EtoroVivo } from "@/api/etoro";

/** La curva del conto eToro per la sezione in cima alla home (FA-127).
 *
 *  Logica pura e testabile: quale serie mostrare per un intervallo, e come
 *  disegnarla in un riquadro. Il componente ne fa solo la forma. */

export type Intervallo = "oggi" | "1S" | "1M" | "3M" | "1A";

export const INTERVALLI: { chiave: Intervallo; etichetta: string; giorni: number | null }[] = [
  { chiave: "oggi", etichetta: "Oggi", giorni: null },
  { chiave: "1S", etichetta: "1S", giorni: 7 },
  { chiave: "1M", etichetta: "1M", giorni: 30 },
  { chiave: "3M", etichetta: "3M", giorni: 90 },
  { chiave: "1A", etichetta: "1A", giorni: 365 },
];

export interface Punto {
  /** Millisecondi epoch. */
  t: number;
  v: number;
}

export interface Serie {
  punti: Punto[];
  /** Il valore da cui l'intervallo parte: la chiusura di ieri per «oggi»,
   *  il primo giorno per gli altri. La linea tratteggiata del grafico. */
  base: number | null;
}

function msGiorno(iso: string): number {
  // Mezzogiorno UTC: un giorno di calendario non deve scivolare nel fuso.
  return Date.parse(`${iso.slice(0, 10)}T12:00:00Z`);
}

/** La serie di un intervallo. L'ultimo punto e' sempre il valore DAL VIVO,
 *  cosi' la curva finisce dove finisce il numero grande accanto. */
export function serieDi(intervallo: Intervallo, a: EtoroAndamento | undefined, vivo: EtoroVivo | undefined, adesso = Date.now()): Serie {
  const valoreVivo = vivo?.valore ?? null;
  if (intervallo === "oggi") {
    const punti = (a?.oggi ?? []).map((p) => ({ t: Date.parse(p.istante), v: p.valore }));
    if (valoreVivo != null) punti.push({ t: adesso, v: valoreVivo });
    return { punti: ordina(punti), base: vivo?.valore_ieri ?? punti[0]?.v ?? null };
  }
  const giorni = INTERVALLI.find((i) => i.chiave === intervallo)?.giorni ?? 30;
  const soglia = adesso - giorni * 86_400_000;
  const nel = (a?.giorni ?? []).filter((g) => msGiorno(g.giorno) >= soglia - 86_400_000);
  if (valoreVivo != null) {
    // La riga di oggi (fonte «vivo») si sostituisce col dato piu' fresco.
    // ⚠️ Per FONTE e non per data: il giorno e' quello di Roma, e fra
    // mezzanotte e le 2 la data UTC e' ancora ieri — si scartava la chiusura
    // di ieri al posto della riga di oggi (trovato da un test alle 00:50).
    const punti = nel.filter((g) => g.fonte !== "vivo").map((g) => ({ t: msGiorno(g.giorno), v: g.valore }));
    punti.push({ t: adesso, v: valoreVivo });
    const o = ordina(punti);
    return { punti: o, base: o[0]?.v ?? null };
  }
  const o = ordina(nel.map((g) => ({ t: msGiorno(g.giorno), v: g.valore })));
  return { punti: o, base: o[0]?.v ?? null };
}

function ordina(p: Punto[]): Punto[] {
  return [...p].sort((x, y) => x.t - y.t);
}

/** Il periodo del server che corrisponde a un intervallo (per «oggi» nessuno:
 *  il guadagno del giorno lo dice eToro). */
export function periodoDi(intervallo: Intervallo, a: EtoroAndamento | undefined): EtoroPeriodo | null {
  if (intervallo === "oggi") return null;
  return a?.periodi.find((p) => p.chiave === intervallo) ?? null;
}

export interface Tracciato {
  linea: string;
  area: string;
  /** y della linea di base, se c'e'. */
  yBase: number | null;
  min: number;
  max: number;
  /** Le coordinate dei punti, per il cursore. */
  xy: { x: number; y: number; p: Punto }[];
}

/** Il percorso SVG di una serie in un riquadro `largo` x `alto`, con un
 *  margine verticale perche' il tratto non tocchi i bordi. Null sotto i due
 *  punti: una curva di un punto e' un punto, non un andamento. */
export function tracciato(s: Serie, largo: number, alto: number, margine = 6): Tracciato | null {
  if (s.punti.length < 2) return null;
  const valori = s.punti.map((p) => p.v).concat(s.base != null ? [s.base] : []);
  let min = Math.min(...valori);
  let max = Math.max(...valori);
  if (max - min < 1e-9) {
    min -= 1;
    max += 1;
  }
  const t0 = s.punti[0].t;
  const t1 = s.punti[s.punti.length - 1].t;
  const dx = t1 - t0 || 1;
  const sx = (t: number) => ((t - t0) / dx) * largo;
  const sy = (v: number) => margine + (1 - (v - min) / (max - min)) * (alto - 2 * margine);
  const xy = s.punti.map((p) => ({ x: sx(p.t), y: sy(p.v), p }));
  const linea = xy.map((q, i) => `${i ? "L" : "M"}${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" ");
  const area = `${linea} L${xy[xy.length - 1].x.toFixed(1)},${alto} L${xy[0].x.toFixed(1)},${alto} Z`;
  return { linea, area, yBase: s.base != null ? sy(s.base) : null, min, max, xy };
}

/** Il punto piu' vicino a una x, per il cursore sul grafico. */
export function piuVicino(t: Tracciato, x: number): Tracciato["xy"][number] {
  let migliore = t.xy[0];
  for (const q of t.xy) if (Math.abs(q.x - x) < Math.abs(migliore.x - x)) migliore = q;
  return migliore;
}

/** La serie sale o scende rispetto alla sua base. */
export function verso(s: Serie): "su" | "giu" | "piatto" {
  const ultimo = s.punti[s.punti.length - 1]?.v;
  if (ultimo == null || s.base == null || ultimo === s.base) return "piatto";
  return ultimo > s.base ? "su" : "giu";
}
