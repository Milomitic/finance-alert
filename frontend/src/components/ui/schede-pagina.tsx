import type { LucideIcon } from "lucide-react";
import { useId } from "react";

import { cn } from "@/lib/utils";

/* Le schede di una pagina: UN componente per Segnali, Diagnostica,
 * Superinvestor e Calendario (2026-09-22, richiesta dell'utente).
 *
 * Erano cinque selettori con cinque stili — un bordo sottile e testo da 12px
 * in Segnali, pillole piene del colore primario in Superinvestor, una riga
 * muta in Diagnostica — e nessuno dei tre in cima a una pagina si leggeva come
 * «qui si cambia vista»: sembravano filtri, o etichette. Qui la scheda attiva
 * e' una tessera in rilievo sul binario incassato, con l'icona nel colore
 * primario e una barra sotto; le altre reagiscono al passaggio del mouse.
 *
 * ⚠️ Bottoni con `aria-pressed`, non `role="tab"`, per tutte. Un gruppo di tab
 * promette un `tabpanel` e la navigazione con le frecce; senza, axe segnala il
 * `aria-controls` pendente — gia' costato due corse rosse del gate UI — e gli
 * assistivi annunciano una struttura che non c'e'. Un segmentato con
 * `aria-pressed` dice esattamente cio' che e'.
 *
 * ⚠️ Il NOME accessibile e' la sola etichetta; la descrizione e' collegata
 * con `aria-describedby`. Messa dentro il nome, «Esiti» diventerebbe
 * «Esiti L'episodio si è chiuso…», e ogni `getByRole(…, { name })` — dei test
 * e degli assistivi — smetterebbe di trovarla.
 *
 * Due taglie: `grande` per le schede in cima a una pagina, `compatta` per un
 * selettore DENTRO una scheda (Esiti › Segnali / Setup), cosi' la gerarchia si
 * vede: il livello di sotto non compete con quello di sopra.
 *
 * Letterali interi, per il purger di Tailwind. */

export interface VoceScheda<T extends string> {
  id: T;
  label: string;
  icon?: LucideIcon;
  /** Una riga sotto l'etichetta, da `md`: che cosa si trova nella scheda. */
  descrizione?: string;
}

const BINARIO = {
  grande: "flex w-full gap-1 overflow-x-auto rounded-xl border bg-muted/60 p-1 shadow-inner sm:inline-flex sm:w-auto",
  compatta: "inline-flex max-w-full gap-0.5 overflow-x-auto rounded-lg border bg-muted/60 p-0.5 shadow-inner",
};

/* ⚠️ Su telefono le schede si stringono (gap e padding minori): a 375px le
   tre di Segnali, con l'icona, stanno in 325px invece di 364, cioe' nella
   riga senza scorrere. Con quattro (Superinvestor) il binario scorre di lato,
   ed e' un contenitore che scorre di proposito. */
const SCHEDA = {
  grande:
    "min-h-11 flex-1 gap-1.5 px-2.5 py-1.5 text-sm sm:flex-none sm:gap-2 sm:px-4",
  compatta: "min-h-9 gap-1.5 px-3 py-1 text-xs",
};

const ATTIVA =
  "bg-card text-foreground shadow-md ring-1 ring-primary/25";
/* ⚠️ Non `text-muted-foreground`: sul binario (`bg-muted/60` sopra il fondo)
   quel grigio vale ~4,49 : 1, un soffio sotto la soglia AA di 4,5 per un testo
   da 14px — e il gate UI misura il contrasto con gli stili veri. Il 75% del
   colore del testo sta sopra 9 : 1 e resta visibilmente «spento» accanto
   alla scheda attiva. Stesso conto per la descrizione, al 60%. */
const INATTIVA =
  "text-foreground/75 hover:bg-background/70 hover:text-foreground hover:shadow-sm";

export function SchedePagina<T extends string>({
  voci, attiva, onCambia, etichetta, dimensione = "grande", className,
}: {
  voci: readonly VoceScheda<T>[];
  attiva: T;
  onCambia: (id: T) => void;
  /** Il nome del gruppo per gli assistivi: «Scheda», «Vista diagnostica». */
  etichetta: string;
  dimensione?: "grande" | "compatta";
  className?: string;
}) {
  const base = useId();
  return (
    <div role="group" aria-label={etichetta} className={cn(BINARIO[dimensione], className)}>
      {voci.map(({ id, label, icon: Icon, descrizione }) => {
        const on = id === attiva;
        // Solo dove la descrizione viene resa: un `aria-describedby` verso un id
        // che non esiste e' la relazione inventata che questo file evita.
        const idDescrizione = descrizione && dimensione === "grande" ? `${base}-${id}` : undefined;
        return (
          <button
            key={id}
            type="button"
            aria-pressed={on}
            // ⚠️ `aria-label` esplicito: il nome calcolato dal contenuto
            // includerebbe la descrizione, che sta dentro il bottone.
            aria-label={label}
            aria-describedby={idDescrizione}
            onClick={() => onCambia(id)}
            className={cn(
              "group relative inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-lg font-semibold",
              "transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
              SCHEDA[dimensione],
              on ? ATTIVA : INATTIVA,
            )}
          >
            {Icon && (
              <Icon
                aria-hidden
                className={cn(
                  "shrink-0 transition-colors",
                  dimensione === "grande" ? "h-4 w-4" : "h-3.5 w-3.5",
                  on ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                )}
              />
            )}
            <span className="flex flex-col items-start leading-tight">
              <span>{label}</span>
              {idDescrizione && (
                <span
                  id={idDescrizione}
                  className="hidden text-[0.7059rem] font-normal text-foreground/60 md:block"
                >
                  {descrizione}
                </span>
              )}
            </span>
            {/* La barra sotto la scheda attiva: il segno che si nota per primo. */}
            {on && (
              <span
                aria-hidden
                className="pointer-events-none absolute inset-x-3 bottom-0.5 h-0.5 rounded-full bg-primary"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
