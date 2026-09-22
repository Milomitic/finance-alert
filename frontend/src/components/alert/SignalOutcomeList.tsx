import {
  ArrowDown, ArrowRight, ArrowUp, ArrowUpDown, CircleSlash, Target, TrendingDown, XCircle,
} from "lucide-react";
import { useState, type CSSProperties, type MouseEvent } from "react";

import type { PlanOutcomeRow } from "@/api/planOutcomes";
import { DetectorChip } from "@/components/AlertChips";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { ColumnVisibilityMenu } from "@/components/ui/column-visibility-menu";
import { HintAnchor, HintLabel, HintUnderline } from "@/components/ui/info-hint";
import {
  COLONNE_ESITI_NASCONDIBILI, trackEsiti, type ColonnaEsitiId, type OrdineEsiti,
} from "@/lib/colonneEsiti";
import {
  ESITO_META, formatPL, formatR, giornoBreve, plPercentuale, raccontaPiano, sequenzaGambe,
  stopTroppoStretto, tracciaGara, type Gamba,
} from "@/lib/planOutcome";
import { cn } from "@/lib/utils";

/* ─── Che cosa e' successo al piano di ogni segnale ───────────────────────
 *
 * ⚠️ La colonna «Esito» della tabella dei segnali risponde a un'ALTRA
 * domanda, e le due non vanno lette come due misure della stessa cosa:
 *
 *   quella colonna   la DIREZIONE ha pagato a orizzonte fisso? (signal_outcomes)
 *   questa vista     il PIANO si sarebbe chiuso in guadagno?   (plan_outcomes)
 *
 * Un segnale puo' prendere il target in tre sedute e finire l'orizzonte sotto
 * il prezzo d'ingresso. Il primo numero lo chiama «mancato», il secondo
 * «target»: sono entrambi veri.
 *
 * ⚠️ UNA RIGA PER SEGNALE, alta una riga, come la tabella dei setup. La prima
 * versione impilava quattro righe per episodio — identita', geometria,
 * sequenza delle gambe, nota — e a quaranta episodi erano quattro schermate
 * per una lista che si legge scorrendo. Stessa aritmetica che ha tolto la
 * doppia riga dall'identita' dei setup: 50 righe x 66px erano 3.300px.
 *
 * ⚠️ E la colonna «Dopo chiusura» (era «Poi» fino al 2026-09-22) e' la
 * ragione per cui questa vista esiste. La
 * posizione si chiude alla PRIMA gamba toccata — e' una gara, non un «ha mai
 * toccato il target» — ma se lo stop e' arrivato il 5 e il target il 18, il
 * trade vale -1R *ed* era nel verso giusto con lo stop troppo stretto. Quel
 * secondo fatto non e' ricavabile dall'esito, e va tenuto a schermo come DATO
 * (la data), con la spiegazione in prosa nell'intestazione, una volta sola,
 * invece che ripetuta su ogni riga.
 */

const ICONA = {
  tp1: Target,
  stop: XCircle,
  ambigua: TrendingDown,
  scaduto: CircleSlash,
} as const;

/* Classi LETTERALI, mai composte: il purger di Tailwind vede solo stringhe
   intere e spoglierebbe una classe costruita a runtime — invisibile in dev. */
const PASTIGLIA: Record<string, string> = {
  ok: "border-emerald-300/60 bg-emerald-50 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-950/40 dark:text-emerald-300",
  bad: "border-rose-300/60 bg-rose-50 text-rose-700 dark:border-rose-800/50 dark:bg-rose-950/40 dark:text-rose-300",
  neutro: "border-border bg-muted/50 text-muted-foreground",
};

/* ⚠️ Le tracce della griglia NON sono piu' quattro template letterali: dal
 * 2026-09-22 le colonne si nascondono, quindi le tracce si calcolano dalle
 * colonne visibili (`lib/colonneEsiti.ts`) e arrivano come variabili CSS. Le
 * classi che le leggono restano letterali, per il purger. Il numero di tracce
 * segue sempre quante celle sono VISIBILI a quella larghezza: una cella
 * `hidden` e' `display:none` e non occupa una traccia.
 *
 *   < sm    titolo · esito · P/L · R · sequenza
 *   >= sm   + chiusa
 *   >= lg   + «dopo chiusura» in fondo
 *   >= xl   + condizione, sedute
 *
 * ⚠️ «Dopo chiusura» da `lg` e non piu' da `sm` dal 2026-09-22, quando e'
 * arrivato il P/L: a 640px le colonne fisse avrebbero lasciato al TITOLO
 * ventotto pixel. Lo stesso conto che ha spostato condizione e sedute a `xl`.
 *
 * «Dopo chiusura» sta DOPO la sequenza dal 2026-09-22, su richiesta
 * dell'utente: e' il testo che dice in date cio' che il disegno accanto
 * mostra in forme, e si legge meglio subito dopo di esso.
 *
 * ⚠️ Condizione e sedute stanno da `xl` e non da `lg` dal 2026-09-22, quando
 * e' arrivata la sequenza. Il conto a 1024px: 240 di barra laterale, 48 di
 * margini, 652 di colonne fisse e 84 di spazi lasciavano al TITOLO zero
 * pixel — cioe' l'identita' della riga cedeva per far posto alla
 * decorazione, l'errore che questo repo ha gia' pagato tre volte. */
const COLONNE =
  "grid grid-cols-[var(--g)] items-center gap-x-2 sm:grid-cols-[var(--g-sm)] sm:gap-x-3 " +
  "lg:grid-cols-[var(--g-lg)] xl:grid-cols-[var(--g-xl)]";

type Visibile = (id: ColonnaEsitiId) => boolean;
const TUTTE: Visibile = () => true;

export interface OrdineAttivo {
  colonna: OrdineEsiti;
  verso: "asc" | "desc";
}

/** Un'intestazione che ordina, come `SortableHeader` della tabella Segnali:
 *  la parola (sottolineata a tratti se ha una spiegazione, che si apre al
 *  passaggio) e la freccia del verso. Senza `onOrdina` resta un'etichetta. */
function IntestazioneOrdinabile({
  etichetta, chiave, hint, ordine, onOrdina, className,
}: {
  etichetta: string;
  chiave: OrdineEsiti;
  hint?: string;
  ordine?: OrdineAttivo | null;
  onOrdina?: (o: OrdineEsiti) => void;
  className?: string;
}) {
  if (!onOrdina) {
    return (
      <span className={cn(INTESTAZIONE, className)}>
        {hint ? <HintLabel text={hint}>{etichetta}</HintLabel> : etichetta}
      </span>
    );
  }
  const attiva = ordine?.colonna === chiave;
  const bottone = (
    <button
      type="button"
      onClick={() => onOrdina(chiave)}
      className={cn(
        "inline-flex items-center gap-1 uppercase transition-colors hover:text-foreground",
        attiva && "text-foreground",
      )}
    >
      {hint ? <HintUnderline>{etichetta}</HintUnderline> : <span>{etichetta}</span>}
      {attiva && ordine?.verso === "desc" && <ArrowDown className="h-3 w-3" aria-hidden />}
      {attiva && ordine?.verso === "asc" && <ArrowUp className="h-3 w-3" aria-hidden />}
      {!attiva && <ArrowUpDown className="h-3 w-3 opacity-30" aria-hidden />}
    </button>
  );
  return (
    <span className={cn(INTESTAZIONE, className)}>
      {hint ? <HintAnchor text={hint}>{bottone}</HintAnchor> : bottone}
    </span>
  );
}

const INTESTAZIONE = "text-[0.6765rem] uppercase tracking-[0.14em] text-muted-foreground";

/** Titolo e nome su UNA riga. Stessa scelta di `InlineIdentity` nei setup, e
 *  per la stessa ragione: la seconda riga non dice niente che il titolo non
 *  dica gia', e su quaranta righe e' mezza schermata. */
function Identita({ riga }: { riga: PlanOutcomeRow }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <StockLogo ticker={riga.ticker} size="xs" />
      <span className="shrink-0 text-sm font-bold tabular-nums">{riga.ticker}</span>
      {riga.name && (
        <span className="truncate text-xs text-muted-foreground" title={riga.name}>
          {riga.name}
        </span>
      )}
      {riga.source === "ricostruito" && (
        /* Una ricostruzione sbagliata e' indistinguibile da una giusta finche'
           nessuno guarda il campo: quindi il campo si guarda, su ogni riga. Il
           perche' sta nella nota sotto la tabella, scritto una volta. */
        <span
          className="shrink-0 rounded border border-border px-1 text-[0.6176rem] font-semibold text-muted-foreground"
          title="Livello di invalidazione ricostruito all'indietro da un fatto delle barre"
        >
          ric
        </span>
      )}
    </span>
  );
}

function Esito({ riga }: { riga: PlanOutcomeRow }) {
  const meta = ESITO_META[riga.esito] ?? {
    label: riga.esito, tono: "neutro" as const, spiegazione: "",
  };
  const Icona = ICONA[riga.esito as keyof typeof ICONA] ?? CircleSlash;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 justify-self-start rounded-full border px-1.5 py-0.5 text-[0.6765rem] font-semibold whitespace-nowrap",
        PASTIGLIA[meta.tono],
      )}
      title={meta.spiegazione}
    >
      <Icona className="h-3 w-3 shrink-0" aria-hidden />
      {/* Sul telefono resta l'icona: l'identita' della riga e' il titolo, e lo
          stato vive nel colore e nel testo per gli assistivi. */}
      <span className="sr-only sm:not-sr-only">{meta.label}</span>
    </span>
  );
}

/** Il P/L percentuale alla chiusura. Verde un guadagno, rosso una perdita:
 *  la palette della direzione, perche' e' il verso del conto. */
function PL({ riga }: { riga: PlanOutcomeRow }) {
  const pl = plPercentuale(riga);
  return (
    <span
      className={cn(
        "justify-self-end whitespace-nowrap text-xs font-semibold tabular-nums",
        pl == null || pl === 0
          ? "text-muted-foreground"
          : pl > 0
            ? "text-emerald-800 dark:text-emerald-300"
            : "text-rose-700 dark:text-rose-300",
      )}
    >
      {formatPL(pl)}
    </span>
  );
}

/** Le gambe toccate DOPO la chiusura. Quasi sempre nessuna o una.
 *
 *  ⚠️ Fino al 2026-09-22 questa colonna era vuota per quasi ogni segnale
 *  recente, e non per mancanza di tocchi: la riga di `plan_outcomes` nasceva
 *  alla chiusura e non veniva piu' rimisurata, quindi un target arrivato dopo
 *  lo stop non entrava mai. Ora la maturazione segue la finestra fino alla
 *  fine dell'orizzonte (`legs_window_complete`). Un «—» su un segnale chiuso
 *  da poco vuol dire «non ancora», non «mai». */
function DopoChiusura({ riga }: { riga: PlanOutcomeRow }) {
  const dopo = sequenzaGambe(riga).filter((g) => g.dopo);
  if (dopo.length === 0) {
    return <span className="hidden text-xs text-muted-foreground lg:block">—</span>;
  }
  const stretto = stopTroppoStretto(riga);
  return (
    <span
      className={cn(
        "hidden items-center gap-1 whitespace-nowrap text-xs tabular-nums lg:flex",
        stretto ? "font-semibold text-foreground" : "text-muted-foreground",
      )}
      title={
        stretto
          ? "Lo stop è arrivato prima di un target poi raggiunto: il verso era giusto, la distanza dello stop no."
          : "Toccata dopo la chiusura della posizione: il prezzo ci è arrivato, ma la posizione non c'era più."
      }
    >
      <ArrowRight className="h-3 w-3 shrink-0" aria-hidden />
      {dopo.map((g) => `${g.etichetta} ${giornoBreve(g.data)}`).join(" · ")}
    </span>
  );
}

/* ─── La sequenza: la gara disegnata nel tempo ───────────────────────────
 *
 * Una riga d'orizzonte per segnale: a sinistra l'ingresso, a destra l'ultima
 * seduta dell'orizzonte del detector, e una barretta sul giorno in cui la
 * posizione si e' chiusa. Ogni gamba toccata e' un segno nella sua seduta.
 *
 * ⚠️ La forma porta il SIGNIFICATO, il colore lo ripete. Stop quadrato, target
 * cerchio, secondo target rombo: chi non distingue il rosso dal verde legge lo
 * stesso disegno. Pieno = toccato a posizione aperta, vuoto = dopo la
 * chiusura, cioe' un prezzo arrivato quando non c'era piu' niente da pagare.
 *
 * ⚠️ E il disegno non sostituisce il testo: la frase intera, date comprese,
 * e' il nome accessibile e il suggerimento. Una posizione stimata di qualche
 * seduta (le festivita' non sono contate) va bene per un'idea a colpo
 * d'occhio, non come fonte della data.
 */

/* Classi LETTERALI per la stessa ragione delle pastiglie. */
const FORMA: Record<Gamba["chiave"], string> = {
  stop: "rounded-[1px]",
  tp1: "rounded-full",
  tp2: "rotate-45 rounded-[1px]",
};
const PIENO: Record<Gamba["chiave"], string> = {
  stop: "bg-rose-600 dark:bg-rose-400",
  tp1: "bg-emerald-600 dark:bg-emerald-400",
  tp2: "bg-emerald-600 dark:bg-emerald-400",
};
const VUOTO: Record<Gamba["chiave"], string> = {
  stop: "border-[1.5px] border-rose-600 bg-card dark:border-rose-400",
  tp1: "border-[1.5px] border-emerald-600 bg-card dark:border-emerald-400",
  tp2: "border-[1.5px] border-emerald-600 bg-card dark:border-emerald-400",
};
/* Due segni nella stessa seduta: il secondo sale, il terzo scende. */
const QUOTA = ["50%", "18%", "82%"];

function Segno({ chiave, vuoto, className, style }: {
  chiave: Gamba["chiave"];
  vuoto: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      aria-hidden
      className={cn("h-2 w-2 shrink-0", FORMA[chiave], vuoto ? VUOTO[chiave] : PIENO[chiave], className)}
      style={style}
    />
  );
}

function Sequenza({ riga }: { riga: PlanOutcomeRow }) {
  const { chiusura, punti } = tracciaGara(riga);
  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
  const storia = raccontaPiano(riga);
  return (
    /* `role="img"` con un nome: il disegno e' UNA affermazione, e gli
       assistivi devono sentirla intera invece di una fila di forme. */
    <span role="img" aria-label={storia} title={storia} className="block px-1">
      <span className="relative block h-4">
        {/* L'orizzonte intero. */}
        <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
        {/* Il tratto in cui la posizione era APERTA. */}
        <span
          className="absolute left-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-muted-foreground/25"
          style={{ width: pct(chiusura) }}
        />
        {/* La chiusura. */}
        <span
          className="absolute inset-y-0 w-px -translate-x-1/2 bg-foreground/60"
          style={{ left: pct(chiusura) }}
        />
        {punti.map((p) => (
          <Segno
            key={p.chiave}
            chiave={p.chiave}
            vuoto={p.dopo}
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: pct(p.x), top: QUOTA[Math.min(p.impilato, QUOTA.length - 1)] }}
          />
        ))}
      </span>
    </span>
  );
}

function Riga({ riga, onApri, vis }: {
  riga: PlanOutcomeRow;
  onApri?: (id: number) => void;
  vis: Visibile;
}) {
  return (
    <li>
      {/* Un bottone, non un link: la domanda che una riga di questo elenco
          solleva e' «perche' e' finita cosi'», e la risposta e' il segnale —
          non la scheda dell'azienda. E un'ancora dentro un bottone sarebbe
          HTML non valido, quindi il titolo NON e' un link qui. */}
      <button
        type="button"
        onClick={() => onApri?.(riga.alert_id)}
        className={cn(COLONNE, "w-full px-3 py-1 text-left transition-colors hover:bg-accent/30")}
      >
        <Identita riga={riga} />

        {/* La stessa pastiglia della home: icona, forma breve, verso nel colore. */}
        {vis("condizione") && (
          <span className="hidden min-w-0 xl:block">
            <DetectorChip detector={riga.detector} tone={riga.tone} />
          </span>
        )}

        {vis("esito") && <Esito riga={riga} />}

        {vis("chiusa") && (
          <span className="hidden whitespace-nowrap text-xs tabular-nums text-muted-foreground sm:block">
            {giornoBreve(riga.resolved_date)}
          </span>
        )}

        {vis("pl") && <PL riga={riga} />}

        {vis("r") && (
          <span
            className={cn(
              "justify-self-end text-sm font-bold tabular-nums",
              riga.r_multiple > 0
                ? "text-emerald-800 dark:text-emerald-300"
                : riga.r_multiple < 0
                  ? "text-rose-700 dark:text-rose-300"
                  : "text-muted-foreground",
            )}
          >
            {formatR(riga.r_multiple)}
          </span>
        )}

        {vis("sedute") && (
          <span className="hidden justify-self-end whitespace-nowrap text-xs tabular-nums text-muted-foreground xl:block">
            {riga.bars_to_outcome}
          </span>
        )}

        {vis("sequenza") && <Sequenza riga={riga} />}

        {vis("dopo") && <DopoChiusura riga={riga} />}
      </button>
    </li>
  );
}

function Intestazione({ vis, ordine, onOrdina, onMenu }: {
  vis: Visibile;
  ordine?: OrdineAttivo | null;
  onOrdina?: (o: OrdineEsiti) => void;
  onMenu?: (e: MouseEvent) => void;
}) {
  const o = { ordine, onOrdina };
  return (
    // Clic destro sull'intestazione: il menu delle colonne, come nella tabella
    // Segnali. Il bottone «Colonne» sopra la lista fa lo stesso, ed e' quello
    // che si trova senza saperlo.
    <li className={cn(COLONNE, "border-b bg-muted/20 px-3 py-1")} onContextMenu={onMenu}>
      <IntestazioneOrdinabile etichetta="Titolo" chiave="ticker" {...o} />
      {vis("condizione") && (
        <IntestazioneOrdinabile etichetta="Condizione" chiave="detector" className="hidden xl:block" {...o} />
      )}
      {vis("esito") && <IntestazioneOrdinabile etichetta="Esito" chiave="esito" {...o} />}
      {vis("chiusa") && (
        <IntestazioneOrdinabile etichetta="Chiusa" chiave="resolved_date" className="hidden sm:block" {...o} />
      )}
      {vis("pl") && (
        <IntestazioneOrdinabile
          etichetta="P/L"
          chiave="pl"
          className="justify-self-end"
          hint={
            "Il guadagno o la perdita della posizione alla chiusura, in percentuale del prezzo d'ingresso: sul target, sullo stop o, se non è stato toccato niente, alla chiusura dell'ultima seduta dell'orizzonte. Per uno short un prezzo sceso è un guadagno. " +
            "Senza leva e senza costi: il piano dimensiona la posizione sulla distanza dello stop, quindi due righe con lo stesso P/L possono valere guadagni diversi in conto — ed è per questo che R resta accanto."
          }
          {...o}
        />
      )}
      {vis("r") && <IntestazioneOrdinabile etichetta="R" chiave="r_multiple" className="justify-self-end" {...o} />}
      {vis("sedute") && (
        <IntestazioneOrdinabile
          etichetta="Sedute"
          chiave="bars_to_outcome"
          className="hidden justify-self-end xl:block"
          hint="Sedute dall'ingresso alla chiusura della posizione."
          {...o}
        />
      )}
      {vis("sequenza") && (
        <span className={INTESTAZIONE}>
          <HintLabel
            text={
              "La gara disegnata nel tempo: a sinistra l'ingresso, a destra l'ultima seduta dell'orizzonte del segnale, e la barretta verticale è il giorno in cui la posizione si è chiusa. Quadrato = stop, cerchio = target, rombo = secondo target; pieno se toccato a posizione aperta, vuoto se dopo la chiusura. " +
              "A sinistra della barretta non può esserci niente se non ciò che è successo nella stessa seduta: la posizione si chiude alla prima gamba toccata. Le posizioni sono in sedute, senza contare le festività: la data esatta è nel testo, passando sopra al disegno."
            }
          >
            Sequenza
          </HintLabel>
        </span>
      )}
      {vis("dopo") && (
        <span className={cn(INTESTAZIONE, "hidden lg:block")}>
          {/* La prosa sta qui, una volta, e non su ogni riga: e' una
              spiegazione, non un dato. Il dato — la data — resta a schermo. */}
          <HintLabel
            text={
              "Le gambe toccate DOPO che la posizione si era chiusa, fino alla fine dell'orizzonte del segnale. La posizione si chiude alla prima fra stop e target, quindi qui non c'è mai la gamba che ha chiuso. " +
              "Quando è un target dopo uno stop, il verso del segnale era giusto e la distanza dello stop no: è la sola diagnosi che questo magazzino sa dare, e non è ricavabile dall'esito. " +
              "«—» su un segnale chiuso da poco vuol dire «non ancora»: la finestra resta aperta fino alla fine dell'orizzonte."
            }
          >
            Dopo chiusura
          </HintLabel>
        </span>
      )}
    </li>
  );
}

export function SignalOutcomeList({
  righe, onApriSegnale, ordine, onOrdina, colonne,
}: {
  righe: PlanOutcomeRow[];
  onApriSegnale?: (alertId: number) => void;
  /** L'ordinamento attivo, e chi lo cambia. ⚠️ Lo fa il SERVER, sull'intera
   *  popolazione filtrata: la lista e' paginata. */
  ordine?: OrdineAttivo | null;
  onOrdina?: (o: OrdineEsiti) => void;
  /** Le colonne visibili, dallo stato che possiede la vista (e il bottone
   *  «Colonne»). Assente: tutte, senza menu. */
  colonne?: { isVisible: (id: string) => boolean; toggle: (id: string) => void };
}) {
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const vis: Visibile = colonne ? (id) => colonne.isVisible(id) : TUTTE;
  if (righe.length === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          Nessun piano ancora risolto con questi filtri. Una riga nasce quando il prezzo tocca
          lo stop o il target, oppure quando l'orizzonte del segnale è trascorso senza che
          succeda né l'uno né l'altro.
        </CardContent>
      </Card>
    );
  }
  const ricostruiti = righe.filter((r) => r.source === "ricostruito").length;
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        {colonne && (
          <ColumnVisibilityMenu
            columns={COLONNE_ESITI_NASCONDIBILI}
            isVisible={colonne.isVisible}
            toggle={colonne.toggle}
            open={menu !== null}
            onOpenChange={(v) => { if (!v) setMenu(null); }}
            anchor={menu ?? { x: 0, y: 0 }}
          />
        )}
        {/* Le tracce della griglia, per le colonne visibili: variabili CSS che
            le righe ereditano dall'elenco. */}
        <ul className="divide-y divide-border/40" style={trackEsiti(vis) as CSSProperties}>
          <Intestazione
            vis={vis}
            ordine={ordine}
            onOrdina={onOrdina}
            onMenu={
              colonne
                ? (e) => {
                    e.preventDefault();
                    setMenu({ x: e.clientX, y: e.clientY });
                  }
                : undefined
            }
          />
          {righe.map((r) => (
            <Riga key={r.alert_id} riga={r} onApri={onApriSegnale} vis={vis} />
          ))}
        </ul>
        {/* La legenda del disegno, a schermo e non in un suggerimento: un
            codice di forme che non si vede non si impara. */}
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t bg-muted/20 px-3 py-1.5 text-[0.7059rem] text-muted-foreground">
          <span className="font-semibold uppercase tracking-[0.14em]">Sequenza</span>
          <span className="inline-flex items-center gap-1"><Segno chiave="stop" vuoto={false} /> stop</span>
          <span className="inline-flex items-center gap-1"><Segno chiave="tp1" vuoto={false} /> target</span>
          <span className="inline-flex items-center gap-1"><Segno chiave="tp2" vuoto={false} /> secondo target</span>
          <span className="inline-flex items-center gap-1">
            <Segno chiave="tp1" vuoto /> vuoto = toccato dopo la chiusura
          </span>
          <span className="inline-flex items-center gap-1">
            <span aria-hidden className="inline-block h-3 w-px bg-foreground/60" /> chiusura della posizione
          </span>
        </p>
        {ricostruiti > 0 && (
          <p className="border-t bg-muted/20 px-3 py-1.5 text-[0.7059rem] text-muted-foreground">
            <b className="tabular-nums text-foreground">{ricostruiti}</b> righe marcate{" "}
            <b>ric</b>: il detector non emetteva un livello di invalidazione quando il segnale è
            scattato, e lo stop è stato ricostruito all'indietro da un fatto delle barre — la
            chiusura precedente di un gap, l'estremo del pivot di una divergenza.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
