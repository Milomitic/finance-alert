import type { Escursioni, PuntoPercorso } from "@/api/studio";
import { GraficoSvg, type SerieGrafico } from "@/components/ui/grafico-svg";
import { NEUTRO } from "@/lib/coloriGrafico";
import { pct } from "@/lib/studio";

/* ─── Il percorso di uno studio, con la banda (FA-194) ────────────────────
 *
 * Il rendimento cumulato seduta per seduta: banda dal 10° al 90° percentile
 * dei casi, mediana piena, media tratteggiata, base grigia tratteggiata. Per
 * un evento, i percorsi dei singoli eventi in grigio sottile e una linea sul
 * giorno dell'evento. Una frase sotto dice quanto bisognava sopportare
 * lungo la strada (MAE), la geometria di uno stop. */

type Riga = PuntoPercorso & { singoli: (number | null)[] };

export function GraficoPercorso({ percorso, singoli, giornoEvento, etichetta, conBase = true }: {
  percorso: PuntoPercorso[];
  singoli?: { data: string; valori: number[] }[];
  /** L'indice della riga dell'evento (la seduta 0), per la linea verticale. */
  giornoEvento?: number;
  etichetta: string;
  conBase?: boolean;
}) {
  if (percorso.length < 2) return null;
  const righe: Riga[] = percorso.map((p, i) => ({ ...p, singoli: (singoli ?? []).map((s) => s.valori[i] ?? null) }));
  const serieSingoli: SerieGrafico<Riga>[] = (singoli ?? []).map((s, k) => ({
    chiave: `ev${k}`, nome: s.data, valore: (r) => r.singoli[k], colore: "hsl(var(--muted-foreground) / 0.28)", spessore: 1,
  }));
  const haBanda = percorso.some((p) => p.p10 != null && p.p90 != null);
  return (
    <div className="h-[180px] sm:h-[240px]">
      <GraficoSvg
        dati={righe}
        x={(r) => (r.seduta > 0 ? `+${r.seduta}` : String(r.seduta))}
        formatoY={(v) => pct(v, 1)}
        riferimenti={[{ y: 0, tratteggio: "2 2" }]}
        verticali={giornoEvento != null ? [giornoEvento] : []}
        bande={haBanda ? [{ chiave: "banda", da: (r) => r.p10, a: (r) => r.p90, colore: "hsl(var(--primary))", opacita: 0.15 }] : []}
        etichetta={etichetta}
        serie={[
          ...serieSingoli,
          ...(conBase && percorso.some((p) => p.base != null)
            ? [{ chiave: "base", nome: "Base (media)", valore: (r: Riga) => r.base, colore: NEUTRO, tratteggio: "4 3", spessore: 1.5 }]
            : []),
          { chiave: "media", nome: "Media", valore: (r) => r.media, colore: "hsl(var(--primary))", tratteggio: "5 3", spessore: 1.5 },
          { chiave: "mediana", nome: "Mediana", valore: (r) => r.mediana ?? null, colore: "hsl(var(--primary))", spessore: 2.25 },
        ]}
      />
    </div>
  );
}

export function LegendaPercorso({ conSingoli, conBase = true }: { conSingoli: boolean; conBase?: boolean }) {
  return (
    <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
      <span><span className="text-primary">━</span> mediana</span>
      <span><span className="text-primary">╌</span> media</span>
      <span><span className="inline-block h-2 w-3 rounded-sm bg-primary/20 align-middle" /> dal 10° al 90° percentile</span>
      {conBase && <span><span style={{ color: NEUTRO }}>╌</span> base</span>}
      {conSingoli && <span><span className="text-muted-foreground/60">─</span> i singoli eventi</span>}
    </p>
  );
}

/** «Nel caso tipico la discesa massima e' stata −4,1%; in un caso su dieci
 *  ha superato −11,2%.» */
export function FraseEscursioni({ e, orizzonte }: { e: Escursioni; orizzonte: number }) {
  return (
    <p className="text-sm">
      Lungo le {orizzonte} sedute, nel caso tipico la discesa massima è stata{" "}
      <strong className="tabular-nums">{pct(e.mae_mediana, 1)}</strong>; in un caso su dieci ha superato{" "}
      <strong className="tabular-nums">{pct(e.mae_p10, 1)}</strong>. La salita massima tipica è stata{" "}
      <span className="tabular-nums">{pct(e.mfe_mediana, 1)}</span>.
    </p>
  );
}
