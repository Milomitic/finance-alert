import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { useNowTick } from "@/hooks/useNowTick";
import { type Fase, NOME_FASE, prossimoCambio } from "@/lib/sessioni";
import { cn } from "@/lib/utils";

/* ─── Gli orari delle borse (FA-191) ──────────────────────────────────────
 *
 * Una fascia sottile: per ogni borsa la fase e quanto manca al prossimo
 * cambio. Le festivita' sono note solo dove il calendario dell'app le ha
 * (oggi New York, FA-205), e la fascia lo dice. */

export interface Borsa {
  regione: string;
  nome: string;
  fase: Fase;
  fino_alle: string | null;
  prossima_fase: string | null;
  dalle: string | null;
  festivita_note: boolean;
}

export interface Sessioni {
  adesso: string;
  borse: Borsa[];
}

const PUNTO: Record<Fase, string> = {
  seduta: "bg-emerald-500",
  pre: "bg-amber-500",
  after: "bg-amber-500",
  chiusa: "bg-muted-foreground/40",
};

export function OrariBorse() {
  const adesso = useNowTick(30_000);
  const q = useQuery({
    queryKey: ["markets", "sessioni"],
    queryFn: ({ signal }) => api<Sessioni>("/api/markets/sessioni", { signal }),
    // Ogni minuto: il conto alla rovescia si aggiorna da solo, il server
    // dice quando una fase e' finita davvero.
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });
  if (!q.data) return <div className="h-8" aria-hidden />;
  const senza = q.data.borse.filter((b) => !b.festivita_note).map((b) => b.nome);
  return (
    <section aria-label="Orari delle borse" className="space-y-1">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {q.data.borse.map((b) => (
          <li key={b.regione} className="flex items-center gap-1.5">
            <span className={cn("h-2 w-2 shrink-0 rounded-full", PUNTO[b.fase])} aria-hidden />
            <span className="font-semibold">{b.nome}</span>
            <span className="text-muted-foreground">
              {NOME_FASE[b.fase]}
              {prossimoCambio(b, adesso) ? ` · ${prossimoCambio(b, adesso)}` : ""}
            </span>
          </li>
        ))}
      </ul>
      {senza.length > 0 && (
        <p className="text-[0.7059rem] text-muted-foreground">Festività note solo per New York; per {senza.join(", ")} conta solo il calendario dei giorni feriali.</p>
      )}
    </section>
  );
}
