import { CircleSlash, Target, TrendingDown, XCircle } from "lucide-react";
import { Link } from "react-router-dom";

import type { PlanOutcomeRow } from "@/api/planOutcomes";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { InfoHint } from "@/components/ui/info-hint";
import {
  ESITO_META, formatR, giornoBreve, sequenzaGambe, stopTroppoStretto,
} from "@/lib/planOutcome";
import { detectorLabel } from "@/lib/setupGrouping";
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
 * ⚠️ E la riga mostra TUTTE le gambe toccate, non solo quella che ha chiuso.
 * La posizione si chiude alla prima — e' una gara, non un «ha mai toccato il
 * target» — ma «stop il 5, target il 18» dice due cose: che il trade e' andato
 * a -1R, e che quello stop era troppo stretto. La seconda non e' ricavabile
 * dall'esito, ed e' la sola ragione per cui le date delle gambe vengono
 * registrate anche dopo la chiusura.
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

function Riga({ riga, onApri }: { riga: PlanOutcomeRow; onApri?: (id: number) => void }) {
  const meta = ESITO_META[riga.esito] ?? {
    label: riga.esito, tono: "neutro" as const, spiegazione: "",
  };
  const Icona = ICONA[riga.esito as keyof typeof ICONA] ?? CircleSlash;
  const gambe = sequenzaGambe(riga);
  const stretto = stopTroppoStretto(riga);

  return (
    <li className="border-b border-border/50 transition-colors last:border-b-0 hover:bg-accent/40">
      <div className="flex min-w-0 items-start gap-3 px-3 py-2">
        <span
          className={cn(
            "mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[0.7059rem] font-semibold sm:px-2",
            PASTIGLIA[meta.tono],
          )}
          title={meta.spiegazione}
        >
          <Icona className="h-3 w-3" aria-hidden />
          {/* Sul telefono resta l'icona: l'identita' della riga e' il titolo,
              e lo stato vive nel colore e nel testo per gli assistivi. */}
          <span className="sr-only sm:not-sr-only">{meta.label}</span>
        </span>

        <StockLogo ticker={riga.ticker} size="xs" />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
            <Link
              to={`/stocks/${encodeURIComponent(riga.ticker)}`}
              className="text-sm font-semibold tabular-nums hover:underline"
            >
              {riga.ticker}
            </Link>
            <span className="min-w-0 truncate text-[0.7059rem] text-muted-foreground">
              {detectorLabel(riga.detector)} ·{" "}
              {riga.tone === "bear" ? "ribassista" : "rialzista"}
            </span>
          </div>

          {/* La geometria, com'era il giorno dell'ingresso. */}
          <p className="text-[0.7059rem] tabular-nums text-muted-foreground">
            ingresso {giornoBreve(riga.entry_date)} a {riga.entry.toFixed(2)} · stop{" "}
            {riga.stop.toFixed(2)} · target {riga.tp1.toFixed(2)}
            {riga.source === "ricostruito" && (
              <>
                {" · "}
                <span className="italic">livello ricostruito</span>
                <InfoHint
                  label="Livello ricostruito"
                  text={
                    "Questo detector non emetteva un livello di invalidazione quando il segnale è scattato: lo stop è stato ricostruito all'indietro da un fatto delle barre — la chiusura precedente di un gap, l'estremo del pivot di una divergenza. Resta dichiarato per sempre, perché una ricostruzione sbagliata è indistinguibile da una giusta finché nessuno guarda questo campo."
                  }
                />
              </>
            )}
          </p>

          {/* ⚠️ La sequenza. Ogni gamba con la sua data, e quella toccata dopo
              la chiusura dichiarata tale: senza, leggerebbe come un guadagno
              che non e' andato a nessuno. */}
          {gambe.length > 0 && (
            <p className="text-[0.7059rem] tabular-nums">
              {gambe.map((g, i) => (
                <span key={g.chiave}>
                  {i > 0 && <span className="text-muted-foreground"> → </span>}
                  <span
                    className={cn(
                      g.dopo
                        ? "text-muted-foreground"
                        : g.chiave === "stop"
                          ? "text-rose-700 dark:text-rose-300"
                          : "text-emerald-800 dark:text-emerald-300",
                    )}
                  >
                    {g.etichetta} {giornoBreve(g.data)}
                    {g.chiude && " · chiude"}
                    {g.dopo && " · a posizione chiusa"}
                  </span>
                </span>
              ))}
            </p>
          )}
          {stretto && (
            <p className="text-[0.7059rem] text-muted-foreground">
              Lo stop è arrivato <strong>prima</strong> di un target poi raggiunto: il verso era
              giusto, la distanza dello stop no.
            </p>
          )}
        </div>

        <div className="shrink-0 text-right">
          <span
            className={cn(
              "block text-sm font-bold tabular-nums",
              riga.r_multiple > 0
                ? "text-emerald-800 dark:text-emerald-300"
                : riga.r_multiple < 0
                  ? "text-rose-700 dark:text-rose-300"
                  : "text-muted-foreground",
            )}
          >
            {formatR(riga.r_multiple)}
          </span>
          <span className="block text-[0.7059rem] tabular-nums text-muted-foreground">
            {riga.bars_to_outcome} sedute
          </span>
          {onApri && (
            /* ⚠️ Fuori dall'ancora del titolo, non dentro: un controllo
               annidato in un `<a>` e' HTML non valido e si comporta male da
               tastiera. */
            <button
              type="button"
              onClick={() => onApri(riga.alert_id)}
              className="mt-0.5 text-[0.7059rem] font-semibold text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              segnale
            </button>
          )}
        </div>
      </div>
    </li>
  );
}

export function SignalOutcomeList({
  righe, onApriSegnale,
}: {
  righe: PlanOutcomeRow[];
  onApriSegnale?: (alertId: number) => void;
}) {
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
  return (
    <Card>
      <CardContent className="p-0">
        <ul>
          {righe.map((r) => (
            <Riga key={r.alert_id} riga={r} onApri={onApriSegnale} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
