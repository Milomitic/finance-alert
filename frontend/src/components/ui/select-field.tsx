import * as React from "react";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

/* ─── Etichetta visibile + tendina, cablate una volta sola ────────────────
 *
 * La forma «etichetta sopra, tendina sotto» era ricopiata sette volte nei
 * filtri Segnali e una nella finestra degli avvisi di prezzo, e in nessuna
 * delle otto l'etichetta era ASSOCIATA al controllo: testo a schermo per chi
 * vede, otto bottoni identici e senza nome per chi ascolta.
 *
 * ⚠️ Il cablaggio sta qui e non nel chiamante perche' e' fatto di id, e gli id
 * scritti a mano sono la via piu' breve per un duplicato: `useId` li genera
 * univoci anche quando lo stesso campo viene montato due volte nella stessa
 * pagina — cosa che succede davvero, la barra filtri esiste in due varianti di
 * larghezza. Un id doppio non e' un dettaglio: `aria-labelledby` punterebbe al
 * primo nodo trovato, cioe' all'etichetta di un ALTRO campo.
 *
 * ⚠️ Perche' `aria-labelledby` con DUE id, «etichetta trigger», e non solo il
 * primo. Radix rende nel bottone il VALORE corrente, e per `role="combobox"`
 * quel contenuto non conta come nome. Con il solo id dell'etichetta il nome
 * sarebbe «Archivio» e il valore scelto non verrebbe annunciato da nessuna
 * parte; includendo anche il trigger il nome diventa «Archivio Attivi» e si
 * aggiorna da solo a ogni scelta. Misurato con axe: entrambe le forme
 * chiudono `button-name`, ma solo questa porta anche il valore.
 *
 * ⚠️ Sta in un file suo e non dentro `ui/select.tsx` di proposito: quello e'
 * un file generato da shadcn e va tenuto vicino all'originale, o il prossimo
 * aggiornamento lo sovrascrive portandosi via questa aggiunta.
 */

interface Props {
  /** Testo visibile sopra il controllo — ed e' ANCHE il nome accessibile.
   *  Una sola fonte per la parola: non esiste modo di far divergere cio' che
   *  si legge da cio' che si sente. */
  label: string;
  value?: string;
  onValueChange?: (v: string) => void;
  /** Mostrato quando non c'e' un valore scelto. */
  placeholder?: string;
  disabled?: boolean;
  /** Le `SelectItem`. */
  children: React.ReactNode;
  /** Contenitore, etichetta e trigger sono stilabili separatamente: i
   *  chiamanti hanno griglie diverse e un solo `className` costringerebbe a
   *  rinunciare al componente proprio dove serve.
   *
   *  ⚠️ Nessuna tipografia di default sull'etichetta. Questo componente possiede
   *  il CABLAGGIO (gli id e il nome accessibile), non l'ASPETTO: incorporare le
   *  classi dei filtri Segnali avrebbe costretto la finestra degli avvisi di
   *  prezzo — dove l'etichetta e' un normale `text-sm` — a riscriverle al
   *  contrario con `normal-case tracking-normal`, cioe' a combattere il proprio
   *  primitivo. Chi ha uno stile lo passa; gli altri prendono quello di `Label`. */
  className?: string;
  labelClassName?: string;
  triggerClassName?: string;
}

export function SelectField({
  label,
  value,
  onValueChange,
  placeholder,
  disabled,
  children,
  className,
  labelClassName,
  triggerClassName,
}: Props) {
  const base = React.useId();
  const idEtichetta = `${base}-e`;
  const idTrigger = `${base}-t`;
  return (
    <div className={className}>
      <Label
        id={idEtichetta}
        htmlFor={idTrigger}
        className={labelClassName}
      >
        {label}
      </Label>
      <Select value={value} onValueChange={onValueChange} disabled={disabled}>
        <SelectTrigger
          id={idTrigger}
          aria-labelledby={`${idEtichetta} ${idTrigger}`}
          className={cn("mt-1", triggerClassName)}
        >
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>{children}</SelectContent>
      </Select>
    </div>
  );
}
