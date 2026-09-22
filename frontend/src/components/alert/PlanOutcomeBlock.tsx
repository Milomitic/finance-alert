import { CircleSlash, Hourglass, Target, TrendingDown, XCircle } from "lucide-react";

import type { PlanBrief } from "@/api/types";
import { InfoHint } from "@/components/ui/info-hint";
import {
  ESITO_META, formatR, giornoBreve, sequenzaGambe, stopTroppoStretto,
} from "@/lib/planOutcome";
import { cn } from "@/lib/utils";

/* ─── Com'e' andato il piano, dentro la scheda di un segnale ──────────────
 *
 * ⚠️ E' la SECONDA domanda, accanto a «la direzione ha pagato a orizzonte
 * fisso» che il blocco sopra risponde. Le due non si fondono:
 *
 *   Direzione   il detector prevede la deriva a N sedute? (signal_outcomes)
 *   Piano       il piano mostrato a schermo avrebbe pagato? (plan_outcomes)
 *
 * Un segnale puo' prendere il target in tre sedute e finire l'orizzonte sotto
 * il prezzo d'ingresso — «mancato» e «target», entrambi veri. Fonderle
 * cambierebbe in silenzio il significato di ogni numero d'efficacia a schermo:
 * calibrazione, monitor di deriva, cubo dei detector e curva di equity sono
 * tutti costruiti sulla chiusura a orizzonte fisso.
 *
 * ⚠️ E la gara si RACCONTA per intero, gambe successive comprese. La
 * posizione si chiude alla prima toccata — contare i soli tocchi del target
 * produrrebbe un tasso lusinghiero per costruzione — ma «stop il 5, target il
 * 18» dice due cose, e la seconda non e' ricavabile dall'esito ne' dall'R.
 */

const ICONA = {
  tp1: Target,
  stop: XCircle,
  ambigua: TrendingDown,
  scaduto: CircleSlash,
} as const;

/* Classi LETTERALI, mai composte: il purger di Tailwind legge solo stringhe
   intere e spoglierebbe una classe costruita a runtime. */
const PASTIGLIA: Record<string, string> = {
  ok: "border-emerald-300/60 bg-emerald-50 text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-950/40 dark:text-emerald-300",
  bad: "border-rose-300/60 bg-rose-50 text-rose-700 dark:border-rose-800/50 dark:bg-rose-950/40 dark:text-rose-300",
  neutro: "border-border bg-muted/50 text-muted-foreground",
};

function Livello({ label, valore }: { label: string; valore: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[0.6765rem] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="truncate text-sm font-semibold tabular-nums">{valore}</div>
    </div>
  );
}

export function PlanOutcomeBlock({ plan }: { plan: PlanBrief | null | undefined }) {
  if (!plan) {
    return (
      <div className="rounded-lg border border-dashed border-border/60 p-3 text-xs italic text-muted-foreground">
        {/* ⚠️ DUE ragioni, e dall'alert non sono distinguibili: dirne una sola
            sarebbe un'affermazione che chi legge non puo' controllare. */}
        Nessun piano risolto: o questo detector non emetteva un livello di invalidazione quando
        il segnale è scattato — sei su diciassette non lo facevano, e i loro segnali non avranno
        mai un piano da misurare — oppure la gara fra stop e target non si è ancora chiusa.
      </div>
    );
  }

  const meta = ESITO_META[plan.esito] ?? {
    label: plan.esito, tono: "neutro" as const, spiegazione: "",
  };
  const Icona = ICONA[plan.esito as keyof typeof ICONA] ?? CircleSlash;
  const gambe = sequenzaGambe(plan);
  const stretto = stopTroppoStretto(plan);

  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-semibold",
            PASTIGLIA[meta.tono],
          )}
        >
          <Icona className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {meta.label}
        </span>
        <span
          className={cn(
            "text-lg font-bold tabular-nums",
            plan.r_multiple > 0
              ? "text-emerald-800 dark:text-emerald-300"
              : plan.r_multiple < 0
                ? "text-rose-700 dark:text-rose-300"
                : "text-muted-foreground",
          )}
        >
          {formatR(plan.r_multiple)}
        </span>
        <InfoHint
          label="R"
          text={
            "Il guadagno in multipli di R, dove R è la distanza dello stop: dice quanto il piano ha reso rispetto a ciò che rischiava, che è la sola lettura confrontabile fra segnali con stop diversi. " +
            "Un target vale il suo rapporto rischio/rendimento (fino a 4,0), uno stop vale −1 per costruzione."
          }
        />
        <span className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground tabular-nums">
          <Hourglass className="h-3 w-3 shrink-0" aria-hidden />
          {plan.bars_to_outcome} sedute · orizzonte {plan.horizon_days}g
        </span>
      </div>

      {/* La geometria CONGELATA: quella su cui la gara è stata corsa, non
          quella che si ricalcolerebbe oggi con le costanti di adesso. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Livello
          label={`Ingresso ${giornoBreve(plan.entry_date)}`}
          valore={plan.entry.toFixed(2)}
        />
        <Livello label="Stop" valore={plan.stop.toFixed(2)} />
        {/* ⚠️ «1° target» e non «Target»: la pastiglia dell'esito qui sopra
            porta gia' la parola «Target» per dire QUALE gamba ha chiuso, e due
            cose diverse con lo stesso nome nello stesso riquadro si leggono
            come la stessa cosa. */}
        <Livello label="1° target" valore={plan.tp1.toFixed(2)} />
        <Livello
          label="2° target"
          valore={plan.tp2 != null ? plan.tp2.toFixed(2) : "—"}
        />
      </div>

      {/* ⚠️ La sequenza, ed è il motivo per cui questo blocco esiste. */}
      <div>
        <div className="mb-1 flex items-center gap-1 text-[0.6765rem] uppercase tracking-wider text-muted-foreground">
          Cosa ha toccato il prezzo
          <InfoHint
            label="Cosa ha toccato il prezzo"
            text={
              "Il primo tocco di ogni gamba nell'orizzonte, anche dopo che la posizione si era chiusa. La posizione si chiude alla PRIMA fra stop e target: è una gara, non un «ha mai toccato il target». " +
              "Una gamba toccata dopo non ha pagato nessuno — ma se è il target dopo uno stop, il verso del segnale era giusto e la distanza dello stop no."
            }
          />
        </div>
        {gambe.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Né lo stop né il target, per tutto l'orizzonte: il piano è stato valorizzato alla
            chiusura dell'ultima seduta.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {gambe.map((g) => (
              <li
                key={g.chiave}
                className={cn(
                  "flex items-baseline gap-2 text-xs tabular-nums",
                  g.dopo ? "text-muted-foreground" : "",
                )}
              >
                <span className="w-24 shrink-0 font-semibold">{g.etichetta}</span>
                <span className="w-16 shrink-0">{giornoBreve(g.data)}</span>
                <span>
                  {g.chiude
                    ? "ha chiuso la posizione"
                    : g.dopo
                      ? "a posizione già chiusa"
                      : "toccata nella stessa seduta"}
                </span>
              </li>
            ))}
          </ul>
        )}
        {stretto && (
          <p className="mt-1.5 text-xs">
            Lo stop è arrivato <strong>prima</strong> di un target poi raggiunto: il verso era
            giusto, la distanza dello stop no.
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[0.7059rem] text-muted-foreground tabular-nums">
        <span title="Quanto il prezzo è andato CONTRO la posizione prima che si chiudesse">
          escursione avversa {formatR(plan.mae_r)}
        </span>
        <span title="Quanto il prezzo è andato a FAVORE prima che la posizione si chiudesse">
          a favore {formatR(plan.mfe_r)}
        </span>
      </div>
    </div>
  );
}
