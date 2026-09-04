import { AlertTriangle, CheckCircle2, Database, GitCommitHorizontal } from "lucide-react";

import type { DataHealth, DeployHealth } from "@/api/platformHealth";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { cn } from "@/lib/utils";

/* Freschezza dei dati + stato del deploy, dentro l'app.
 *
 * Le domande che un controllo manuale poneva a mano — quanti giorni ha il dato
 * piu' recente, quali chiavi API mancano, quale commit sta girando — vivevano
 * sparse fra kubectl, psql e la API di Prometheus. Stanno qui perche' la
 * risposta appartiene a dove l'utente gia' e', dietro l'autenticazione
 * dell'app e non dietro un secondo login.
 *
 * La freschezza e' il guasto che non si vede: la pagina si disegna, il pod
 * resta 1/1 Running, e il numero a schermo e' semplicemente vecchio. Il
 * calendario macro e' rimasto fermo 60 giorni con la chiave FRED non
 * configurata senza che nulla lo segnalasse. */

type Tone = "ok" | "warn" | "bad" | "muted";

const TONE: Record<Tone, string> = {
  ok: "text-emerald-700 dark:text-emerald-300",
  warn: "text-amber-700 dark:text-amber-300",
  bad: "text-rose-700 dark:text-rose-300",
  muted: "text-muted-foreground",
};

function toneFor(v: number | null, warn: number, bad: number): Tone {
  if (v == null) return "muted";
  if (v >= bad) return "bad";
  if (v >= warn) return "warn";
  return "ok";
}

function Metric({
  label,
  value,
  tone = "muted",
  hint,
}: {
  label: string;
  value: string;
  tone?: Tone;
  hint?: string;
}) {
  return (
    <div className="min-w-0" title={hint}>
      <div className="truncate text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className={cn("text-[0.8235rem] font-semibold tabular-nums", TONE[tone])}>
        {value}
      </div>
    </div>
  );
}

const AGE = (v: number | null | undefined) =>
  v == null ? "—" : v === 0 ? "oggi" : `${v}g`;

export default function DataHealthCard({
  data,
  deploy,
}: {
  data?: DataHealth | null;
  deploy?: DeployHealth | null;
}) {
  if (!data && !deploy) return null;

  const keys = Object.entries(data?.api_keys ?? {});
  const missing = keys.filter(([, ok]) => !ok).map(([k]) => k);
  const resolved = (data?.setups_converted ?? 0) + (data?.setups_expired ?? 0);

  // Sotto le 20 risoluzioni si mostra la frazione, non una percentuale: a
  // 6-su-6 il limite inferiore di Wilson al 95% sta al 61%, quindi "100%"
  // sarebbe compatibile con un lancio di moneta. Stessa regola della pagina
  // Setup, e vale la pena ripeterla qui invece di importarla: e' una scelta
  // editoriale, non una costante condivisa.
  const conv =
    resolved === 0
      ? "—"
      : resolved < 20
        ? `${data?.setups_converted ?? 0}/${resolved}`
        : `${Math.round((100 * (data?.setups_converted ?? 0)) / resolved)}%`;

  const up = deploy?.uptime_seconds;
  const upLabel =
    up == null
      ? "—"
      : up < 3600
        ? `${Math.round(up / 60)}m`
        : up < 86400
          ? `${Math.round(up / 3600)}h`
          : `${Math.round(up / 86400)}g`;

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle icon={Database} label="Dati & deploy" className="mb-2.5" />

        <div className="grid grid-cols-2 gap-x-3 gap-y-2.5 sm:grid-cols-3">
          <Metric
            label="Prezzi"
            value={AGE(data?.ohlcv_age_days)}
            tone={toneFor(data?.ohlcv_age_days ?? null, 4, 8)}
            hint="Giorni dall'ultima barra memorizzata. Weekend e festivi giustificano 3-4 giorni."
          />
          <Metric
            label="Calendario macro"
            value={AGE(data?.macro_age_days)}
            tone={toneFor(data?.macro_age_days ?? null, 8, 20)}
            hint="Giorni dall'ultima osservazione FRED. E' rimasto fermo 60 giorni con la chiave API non configurata, mentre la pagina continuava a disegnarsi."
          />
          <Metric
            label="Ultimo segnale"
            value={AGE(data?.alert_age_days)}
            tone={toneFor(data?.alert_age_days ?? null, 3, 7)}
            hint="Uno scan puo' completare senza emettere nulla: questo distingue i due casi."
          />
          <Metric
            label="Prezzi vecchi"
            value={data?.stale_ohlcv_stocks == null ? "—" : String(data.stale_ohlcv_stocks)}
            tone={toneFor(data?.stale_ohlcv_stocks ?? null, 15, 40)}
            hint="Titoli oltre la finestra di staleness. Una manciata e' normale (simboli delistati): conta la tendenza, non il valore assoluto."
          />
          <Metric
            label="Rotture di basis"
            value={data?.basis_breaks == null ? "—" : String(data.basis_breaks)}
            tone={toneFor(data?.basis_breaks ?? null, 1, 4)}
            hint="Titoli con uno split non riparato nella storia memorizzata. Ricalcolato dal job giornaliero, quindi puo' avere fino a un giorno di ritardo."
          />
          <Metric
            label="Catalogo"
            value={data?.catalog_stocks == null ? "—" : String(data.catalog_stocks)}
            hint="Dimensione dell'universo. Un calo improvviso significa che qualcosa ha cancellato righe."
          />
          <Metric
            label="Setup attivi"
            value={data?.setups_active == null ? "—" : String(data.setups_active)}
            hint="In formazione, non ancora risolti."
          />
          <Metric
            label="Conversione setup"
            value={conv}
            hint={
              resolved > 0 && resolved < 20
                ? `Solo ${resolved} risolti: si mostra la frazione, non un tasso.`
                : "Convertiti sui risolti. Gli scaduti sono la meta' onesta del rapporto."
            }
          />
          <Metric
            label="In esecuzione da"
            value={upLabel}
            hint={deploy?.started_at ? `Avviato ${deploy.started_at}` : undefined}
          />
        </div>

        {/* La sola risposta diretta a "la mia modifica e' a schermo". CI verde e
            ArgoCD Synced non la danno: il bump del tag immagine e' un commit
            SUCCESSIVO a quello del codice, quindi esiste sempre una finestra in
            cui ogni semaforo e' verde e gira l'immagine precedente. */}
        <div className="mt-3 flex items-center gap-2 border-t border-border/50 pt-2.5">
          <GitCommitHorizontal className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
            Commit in esecuzione
          </span>
          <code
            className="font-mono text-[0.7059rem] tabular-nums"
            title={deploy?.git_sha ?? "Immagine costruita senza build-arg GIT_SHA"}
          >
            {deploy?.git_sha ? deploy.git_sha.slice(0, 8) : "sconosciuto"}
          </code>
        </div>

        {/* Una chiave mancante degrada un'intera funzione a un WARNING nei log e
            nient'altro: nessun alert, nessuna pagina rotta, nessun segno. */}
        {keys.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
              Chiavi API
            </span>
            {missing.length === 0 ? (
              <span className="inline-flex items-center gap-1 text-[0.7059rem] text-emerald-700 dark:text-emerald-300">
                <CheckCircle2 className="h-3 w-3" /> tutte configurate
              </span>
            ) : (
              missing.map((k) => (
                <span
                  key={k}
                  className="inline-flex items-center gap-1 rounded border border-rose-300/60 bg-rose-50 px-1.5 py-0.5 text-[0.6765rem] text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/40 dark:text-rose-300"
                  title={`La chiave ${k} non e' configurata: la funzione che la usa e' silenziosamente degradata.`}
                >
                  <AlertTriangle className="h-3 w-3" /> {k}
                </span>
              ))
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
