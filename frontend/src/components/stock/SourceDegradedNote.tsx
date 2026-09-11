import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { fetchDegradedSources } from "@/api/platformHealth";

/* ─── La sorgente degradata, detta dove il dato si consuma ────────────────
 *
 * Voce 4.4 del piano, audit §7.5. La pagina Salute sapeva che Marketaux era
 * fuori servizio; la scheda News mostrava semplicemente meno articoli, e il
 * degrado era visibile solo a chi andava a cercarlo. Questa riga trasforma
 * un'assenza inspiegata in un'assenza spiegata — la stessa distinzione fra
 * `—` e `0` che il repo applica ai numeri.
 *
 * ⚠️ LA CATENA E FONTE -> TIPO DI DATO -> SCHEDA, E SI FERMA LI. Il componente
 * nomina la fonte e il suo ruolo, e non dice nulla su QUESTO titolo: quanti
 * articoli in meno abbia AAPL per via di Marketaux non lo sa nessuno, e
 * affermarlo sarebbe inventare una misura che il contratto non supporta.
 *
 * ⚠️ Il ruolo non e decorazione. Una primaria giu spiega un'ASSENZA; una
 * riserva giu spiega al piu un impoverimento. Appiattirli sovrastima o
 * sottostima il danno, e in entrambe le direzioni il lettore sbaglia
 * conclusione.
 */

const RUOLO: Record<string, string> = {
  primary: "fonte principale",
  fallback: "fonte di riserva",
  scheduled: "fonte pianificata",
};

export function SourceDegradedNote({ op, className }: { op: string; className?: string }) {
  const q = useQuery({
    queryKey: ["platform", "source-health", op],
    queryFn: () => fetchDegradedSources(op),
    // Contesto, non un segnale vivo: la scheda non deve inseguire lo stato
    // delle fonti come fa la pagina Salute, che ha uno stream apposta.
    staleTime: 2 * 60 * 1000,
    // ⚠️ Nessun retry e nessun avviso in caso di errore. Una riga che compare
    // perche NON si e riusciti a sapere se c'e un problema e un falso allarme:
    // direbbe «degrado» quando l'unico degrado e la richiesta di diagnostica.
    retry: false,
  });

  const giu = q.data ?? [];
  if (giu.length === 0) return null;

  return (
    <div
      role="status"
      className={`flex items-start gap-1.5 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-300 ${className ?? ""}`}
    >
      <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-px" aria-hidden />
      {/* L'identita della fonte e la traccia flessibile: se lo spazio manca
          va a capo, non si tronca. CLAUDE.md, tre volte in un pomeriggio. */}
      <span className="min-w-0">
        {giu.map((s, i) => (
          <span key={s.source}>
            {i > 0 && "; "}
            <b className="font-semibold">{s.label}</b>
            {" ("}
            {RUOLO[s.role] ?? s.role}
            {") non risponde"}
          </span>
        ))}
        .
      </span>
    </div>
  );
}
