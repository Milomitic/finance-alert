import { Info } from "lucide-react";
import * as React from "react";

import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
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
            // ⚠️ 24x24 e' il minimo di WCAG 2.2 SC 2.5.8 «Target Size», e
            // questo bottone nasceva a 15x15 — misurato dal gate e2e il
            // giorno stesso in cui e' stato scritto. L'icona resta di 14px:
            // a crescere e' l'area toccabile, non il disegno, con un margine
            // negativo che impedisce all'area piu' grande di allargare la
            // riga dell'intestazione.
            "inline-flex h-6 w-6 -my-1 shrink-0 items-center justify-center rounded-full text-muted-foreground/70",
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
      <Spiegazione text={text} />
    </Popover>
  );
}

/** Il pannello, uno solo per l'icona e per l'etichetta sottolineata: due
 *  copie dello stesso popover divergerebbero al primo ritocco dei margini. */
function Spiegazione({ text }: { text: string }) {
  return (
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
  );
}

/* ─── Intestazioni di tabella: la parola STESSA apre la spiegazione ───────
 *
 * ⚠️ Nelle intestazioni l'icona «i» costa una colonna. Un bottone da 24px
 * accanto a «Prob.» allarga la colonna di un terzo, su ogni riga della
 * tabella, per una spiegazione che si legge una volta. Qui il grilletto è
 * l'ETICHETTA, sottolineata a tratti: il segno tipografico convenzionale di
 * «questa parola ha una definizione», che non occupa un pixel in più.
 *
 * Come si apre, per dispositivo:
 *  - mouse: passandoci sopra, dopo un attimo — senza il ritardo, scorrere col
 *    mouse lungo la riga delle intestazioni aprirebbe un pannello per colonna;
 *  - tastiera: al focus, solo se VISIBILE (`:focus-visible`), cioè arrivando
 *    col Tab — il focus che un click lascia sul bottone non deve aprire niente;
 *  - touch: al tap se l'etichetta non fa altro (`HintLabel`); con la PRESSIONE
 *    LUNGA se è anche il bottone di ordinamento (`HintAnchor`), perché lì il
 *    tap ordina le righe e rubarglielo romperebbe l'azione principale.
 *
 * ⚠️ `PopoverAnchor` e non `PopoverTrigger`: il Trigger di Radix commuta al
 * click, e sul bottone di ordinamento il click appartiene all'ordinamento. Con
 * l'ancora l'apertura è tutta nostra, e il bottone non riceve un
 * `aria-controls` verso un pannello che a riposo non esiste.
 */

/** Il ritardo dell'hover: abbastanza da non aprire niente passando, poco
 *  abbastanza da non far aspettare chi si ferma a leggere. */
const RITARDO_HOVER_MS = 250;
/** La pressione lunga su touch. Sotto i ~400ms un tap lento diventa una
 *  pressione, sopra i ~600ms il sistema apre il proprio menu. */
const PRESSIONE_LUNGA_MS = 450;

function useApertura(apreAlClick: boolean) {
  const [open, setOpen] = React.useState(false);
  const timer = React.useRef<number | null>(null);
  // La pressione lunga che ha APERTO il pannello: il click che il browser
  // emette al rilascio non deve anche ordinare le righe.
  const daPressione = React.useRef(false);

  const annulla = React.useCallback(() => {
    if (timer.current != null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);
  React.useEffect(() => annulla, [annulla]);

  const handlers = {
    onPointerEnter: (e: React.PointerEvent) => {
      if (e.pointerType === "touch") return;
      annulla();
      timer.current = window.setTimeout(() => setOpen(true), RITARDO_HOVER_MS);
    },
    onPointerLeave: (e: React.PointerEvent) => {
      if (e.pointerType === "touch") return;
      annulla();
      setOpen(false);
    },
    onPointerDown: (e: React.PointerEvent) => {
      annulla();
      daPressione.current = false;
      if (e.pointerType !== "touch") return;
      timer.current = window.setTimeout(() => {
        daPressione.current = true;
        setOpen(true);
      }, PRESSIONE_LUNGA_MS);
    },
    onPointerUp: (e: React.PointerEvent) => {
      if (e.pointerType === "touch") annulla();
    },
    onPointerCancel: annulla,
    onContextMenu: (e: React.MouseEvent) => {
      // Su Android la pressione lunga apre anche il menu del sistema.
      if (daPressione.current) e.preventDefault();
    },
    onClickCapture: (e: React.MouseEvent) => {
      if (!daPressione.current) return;
      daPressione.current = false;
      e.preventDefault();
      e.stopPropagation();
    },
    onFocus: (e: React.FocusEvent<HTMLElement>) => {
      if (e.currentTarget.matches(":focus-visible")) setOpen(true);
    },
    onBlur: () => setOpen(false),
    ...(apreAlClick
      ? {
          // Come `InfoHint`: il click APRE, non commuta, e non risale — una
          // cella d'intestazione può essere cliccabile a sua volta.
          onClick: (e: React.MouseEvent) => {
            e.stopPropagation();
            e.preventDefault();
            annulla();
            setOpen(true);
          },
        }
      : {}),
  };
  return { open, setOpen, handlers };
}

/** La parola che ha una spiegazione, dentro un elemento che fa altro (il
 *  bottone di ordinamento). Un componente e non una costante esportata,
 *  perché questo file esporta solo componenti. */
export function HintUnderline({ children }: { children: React.ReactNode }) {
  return (
    <span className="underline decoration-muted-foreground/60 decoration-dashed underline-offset-[3px]">
      {children}
    </span>
  );
}

/** Aggancia una spiegazione a un elemento che ha GIA' un'azione propria —
 *  il bottone di ordinamento — senza togliergliela. Senza `text` rende il
 *  figlio così com'è. */
export function HintAnchor({
  text,
  children,
}: {
  text?: string | null;
  children: React.ReactElement;
}) {
  const { open, setOpen, handlers } = useApertura(false);
  if (!text) return children;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild {...handlers}>
        {children}
      </PopoverAnchor>
      <Spiegazione text={text} />
    </Popover>
  );
}

/** L'etichetta d'intestazione che È la spiegazione: il suo unico compito è
 *  aprirla, quindi al tap si apre. */
export function HintLabel({
  text,
  children,
  className,
}: {
  text: string;
  children: React.ReactNode;
  className?: string;
}) {
  const { open, setOpen, handlers } = useApertura(true);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild {...handlers}>
        <button
          type="button"
          className={cn(
            // ⚠️ Eredita tutto dall'intestazione: è testo, non un bottone
            // visibile. `cursor-help` dice «qui c'è una definizione», non
            // «qui succede qualcosa».
            // ⚠️ `min-h-6 -my-1`: 24px è il minimo di WCAG 2.2 SC 2.5.8, che
            // il gate e2e misura, e un'intestazione in `text-xs` rende una
            // riga da 16px. L'area toccabile cresce, la riga no — lo stesso
            // accorgimento dell'icona che questo bottone sostituisce.
            "inline-flex min-h-6 -my-1 items-center",
            "cursor-help rounded-sm bg-transparent p-0 [text-align:inherit] [font:inherit] [letter-spacing:inherit] [text-transform:inherit]",
            "underline decoration-muted-foreground/60 decoration-dashed underline-offset-[3px]",
            "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            className,
          )}
        >
          {children}
        </button>
      </PopoverAnchor>
      <Spiegazione text={text} />
    </Popover>
  );
}
