import { ShieldCheck } from "lucide-react";

import type { Verification } from "@/api/platformHealth";
import { InfoHint } from "@/components/ui/info-hint";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";

/* ─── Quanto e' sorvegliata questa build ──────────────────────────────────
 *
 * ⚠️ Mostra ARRETRATI MISURATI, non obiettivi, e la differenza e' tutta la
 * scheda. Entrambi i numeri contengono voci LEGITTIME — script one-off e rami
 * difensivi da un lato, link di testo dentro tabelle dense dall'altro — quindi
 * i cancelli che li sorvegliano vietano la CRESCITA e non pretendono lo zero.
 *
 * Perche' portarli a schermo: un arretrato che nessuno vede non cala mai. E
 * perche' la ragione viaggia col numero: un arretrato mostrato nudo diventa un
 * obiettivo da azzerare a forza, che qui sarebbe la correzione sbagliata.
 *
 * ⚠️ Tre stati, non due. `null` significa NON SO (la linea di base non e'
 * nell'immagine) e si scrive «non dichiarato» — mai «0», che si leggerebbe
 * come «nessun arretrato», cioe' l'opposto della verita'. E' la stessa
 * distinzione fra assenza e zero che il resto dell'app applica ai prezzi.
 */

function Riga({
  etichetta,
  conteggio,
  totale,
  unita,
  perche,
}: {
  etichetta: string;
  conteggio: number | null;
  totale: number | null;
  unita: string;
  perche: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-t border-border/40 py-2 first:border-t-0">
      <span className="flex min-w-0 items-center gap-1 text-[0.7059rem] text-muted-foreground">
        <span className="truncate">{etichetta}</span>
        {perche && <InfoHint label={etichetta} text={perche} />}
      </span>
      {conteggio == null ? (
        <span className="shrink-0 text-[0.7059rem] text-muted-foreground">
          non dichiarato
        </span>
      ) : (
        <span className="shrink-0 text-sm tabular-nums">
          <span className="font-semibold">{conteggio.toLocaleString("it-IT")}</span>
          {totale != null && (
            /* Il denominatore sta accanto al numeratore: un conteggio senza il
               suo campione non si puo' interpretare, ed e' la regola che questo
               progetto applica ai tassi ovunque. */
            <span className="ml-1 text-[0.7059rem] font-normal text-muted-foreground">
              su {totale.toLocaleString("it-IT")} {unita}
            </span>
          )}
        </span>
      )}
    </div>
  );
}

export default function VerificationCard({
  verification,
}: {
  verification?: Verification | null;
}) {
  if (!verification) return null;
  const codice = verification.codice_mai_eseguito;
  const a11y = verification.violazioni_a11y;
  if (!codice && !a11y) return null;

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle
          icon={ShieldCheck}
          label="Verifica"
          className="mb-1.5"
          right={
            <span className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
              arretrati sorvegliati
            </span>
          }
        />
        <Riga
          etichetta="Funzioni mai eseguite"
          conteggio={codice?.conteggio ?? null}
          totale={codice?.totale ?? null}
          unita="censite"
          perche={codice?.perche ?? ""}
        />
        <Riga
          etichetta="Violazioni a11y note"
          conteggio={a11y?.conteggio ?? null}
          totale={a11y?.totale ?? null}
          unita="rotte"
          perche={a11y?.perche ?? ""}
        />
        <p className="mt-1 text-[0.6471rem] leading-snug text-muted-foreground">
          I cancelli vietano che questi numeri <strong>crescano</strong>; non
          pretendono lo zero, perché entrambi contengono voci legittime.
        </p>
      </CardContent>
    </Card>
  );
}
