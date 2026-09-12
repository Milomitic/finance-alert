import { Info } from "lucide-react";
import * as React from "react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/* ─── InfoHint — la spiegazione che si apre anche su un telefono ──────────
 *
 * ⚠️ Sostituisce `title="…"`, e il motivo NON è l'estetica.
 *
 * Misurato su questo repo: 112 attributi `title` portano spiegazioni lunghe,
 * quasi tutte su intestazioni di tabella. Su un dispositivo touch `title`
 * non si apre mai — non c'è un hover da produrre, e il long-press apre il
 * menu contestuale del sistema operativo. Quelle 112 spiegazioni sono quindi
 * scritte, spedite, e invisibili a metà degli utenti.
 *
 * Perché Popover e non Tooltip:
 *  - il Tooltip di Radix è hover/focus e si CHIUDE su `pointerdown`, che è
 *    esattamente il gesto di un tap. Sarebbe lo stesso difetto con un'altra
 *    libreria;
 *  - Popover apre al click, che touch e mouse producono entrambi, e qui
 *    l'hover è aggiunto a mano sopra (sotto) per non togliere nulla a chi
 *    ha un mouse.
 *
 * Perché un portale e non un `absolute` fatto in casa: il grilletto vive
 * dentro `overflow-x-auto` (ogni tabella di questa app scorre in orizzontale
 * su mobile), e un figlio posizionato verrebbe TAGLIATO dal contenitore che
 * scorre. Il portale esce dal ritaglio; è l'unico motivo per cui questo
 * componente dipende da Radix.
 */

interface Props {
  /** Di cosa è la spiegazione — la stessa parola che l'utente legge accanto
   *  (es. "Forza"). Finisce nel nome accessibile del grilletto: un bottone
   *  chiamato "info" non dice a cosa si riferisce quando se ne leggono otto
   *  di fila con uno screen reader. */
  label: string;
  /** Il testo della spiegazione. Sta fuori dal documento finché non serve. */
  text: string;
  className?: string;
}

export function InfoHint({ label, text, className }: Props) {
  const [open, setOpen] = React.useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Spiegazione: ${label}`}
          className={cn(
            // `shrink-0` perché la regola di questo repo è che a cedere non
            // sia mai l'identità della colonna: se lo spazio manca, a
            // stringersi è l'etichetta, non il suo aiuto.
            "inline-flex shrink-0 items-center justify-center rounded-full text-muted-foreground/70",
            "transition-colors hover:text-foreground focus-visible:outline-none",
            "focus-visible:ring-1 focus-visible:ring-ring align-middle",
            className,
          )}
          // Il tap è già coperto dal click di Radix. Questi due handler
          // servono solo al mouse: `pointerType` evita che un browser touch
          // che sintetizza eventi mouse apra e richiuda da solo.
          onPointerEnter={(e) => { if (e.pointerType === "mouse") setOpen(true); }}
          onPointerLeave={(e) => { if (e.pointerType === "mouse") setOpen(false); }}
          // Il click APRE, non commuta — e la differenza non è di gusto.
          // Con un mouse, `user.click` (e una persona) produce prima
          // `pointerenter`, che ha già aperto: un toggle richiuderebbe
          // subito, quindi col mouse il pannello non si aprirebbe MAI al
          // click. `preventDefault` disinnesca il toggle interno di Radix,
          // che compone i propri handler solo se l'evento non è prevenuto.
          // Si chiude con Escape, cliccando fuori, o allontanando il mouse.
          //
          // `stopPropagation` invece serve alla tabella: un'intestazione
          // ordinabile è essa stessa un bottone, e senza questo un tap
          // sull'aiuto riordinerebbe anche le righe.
          onClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
            setOpen(true);
          }}
        >
          <Info className="h-3.5 w-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent
        // `w-72` del default è troppo per una riga di spiegazione e su 375px
        // tocca entrambi i bordi.
        className="w-auto max-w-[15rem] p-2.5 text-xs font-normal normal-case tracking-normal leading-snug"
        side="top"
        align="center"
        // ⚠️ Senza questo il pannello si incolla al bordo dello schermo: la
        // rilevazione di collisione di Radix ha `collisionPadding: 0` di
        // default, e misurato su 375px il bordo destro cadeva a 376 — un
        // pixel FUORI, dove `overflow-x: clip` su <html> lo taglia. Otto
        // pixel di margine sono anche cio' che lo rende leggibile invece che
        // schiacciato contro la cornice.
        collisionPadding={8}
        // Senza questo, aprendo in hover il focus salta dentro al popover e
        // il `pointerleave` non lo richiude più.
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        {text}
      </PopoverContent>
    </Popover>
  );
}
