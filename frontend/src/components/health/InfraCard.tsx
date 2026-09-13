import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  CloudOff,
  GitBranch,
  RotateCcw,
  Server,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { InfraHealth } from "@/api/platformHealth";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { cn } from "@/lib/utils";

/* Infrastruttura — quello che finora sapeva solo Grafana.
 *
 * Le domande che un controllo manuale poneva via kubectl e PromQL — tutti i
 * target sono su, sta scattando qualche alert, il pod si e' riavviato stanotte,
 * quanto manca alla scadenza dei certificati, cosa dice ArgoCD — vivono qui,
 * dietro l'autenticazione dell'app e non dietro un secondo login.
 *
 * REGOLA DELLA SCHEDA: quando Prometheus non risponde NON si disegnano zeri.
 * "0 target giu'" e "non ho potuto chiedere" sono affermazioni opposte, e
 * mostrare la seconda come la prima e' il modo in cui un pannello di
 * monitoraggio diventa verde perche' e' cieco. Qui e' successo davvero:
 * l'endpoint delle metriche dell'app e' rimasto giu' per mesi mentre ogni
 * cruscotto era calmo. */

type Tone = "ok" | "warn" | "bad" | "muted";

const TONE: Record<Tone, string> = {
  ok: "text-emerald-800 dark:text-emerald-300",
  warn: "text-amber-700 dark:text-amber-300",
  bad: "text-rose-700 dark:text-rose-300",
  muted: "text-muted-foreground",
};

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

/** Una riga di dettaglio: icona, titolo, e l'elenco di cosa non va. */
function Dettaglio({
  icona: Icona,
  titolo,
  children,
}: {
  icona: LucideIcon;
  titolo: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5">
        <Icona className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
          {titolo}
        </span>
      </div>
      <ul className="mt-1 space-y-1 pl-5 text-[0.7059rem]">{children}</ul>
    </div>
  );
}

/** Da quanto e' attivo, in forma breve.
 *
 *  ⚠️ Un istante ISO dice al lettore «quando», non «da quanto», e la seconda e'
 *  la domanda che si fa guardando un alert. Se la data non si legge si
 *  restituisce la stringa originale invece di inventare una durata. */
function da(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const min = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (min < 60) return `${min}m`;
  const ore = Math.round(min / 60);
  return ore < 48 ? `${ore}h` : `${Math.round(ore / 24)}g`;
}

export default function InfraCard({ data }: { data?: InfraHealth | null }) {
  if (!data) return null;

  // Il caso che non deve mai somigliare a "tutto bene".
  if (!data.available) {
    return (
      <Card>
        <CardContent className="p-3">
          <SectionTitle icon={Server} label="Infrastruttura" className="mb-2.5" />
          <div className="flex items-start gap-2 rounded border border-amber-300/60 bg-amber-50 p-2.5 dark:border-amber-800/60 dark:bg-amber-950/40">
            <CloudOff className="mt-px h-4 w-4 shrink-0 text-amber-700 dark:text-amber-300" />
            <div className="min-w-0 text-[0.7647rem] leading-snug">
              <div className="font-semibold text-amber-800 dark:text-amber-200">
                Prometheus non raggiungibile — nessun dato, non "tutto a posto"
              </div>
              <div className="mt-0.5 text-muted-foreground">
                {data.error ?? "causa non riportata"}
                {data.prometheus_url ? (
                  <>
                    {" · "}
                    <code className="font-mono">{data.prometheus_url}</code>
                  </>
                ) : null}
              </div>
              <div className="mt-1 text-muted-foreground">
                Normale in locale: il servizio risolve solo dentro al cluster.
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  const down = data.targets_down ?? 0;
  const firing = data.alerts_firing ?? 0;
  const restarts = data.restarts_24h ?? 0;
  // Quante cose hanno un dettaglio da mostrare. Si contano le LISTE, non i
  // contatori: un contatore puo' dire 3 mentre le liste sono vuote (Prometheus
  // ha risposto al conteggio e non all'elenco), e in quel caso non c'e' niente
  // da scrivere sotto.
  const problemi =
    data.firing_alerts.length +
    data.down_targets.length +
    (data.restart_details ?? []).length;
  const mem = data.memory_pct;
  const cert = data.cert_days;

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle icon={Server} label="Infrastruttura" className="mb-2.5" />

        <div className="grid grid-cols-2 gap-x-3 gap-y-2.5 sm:grid-cols-3">
          <Metric
            label="Target attivi"
            value={data.targets_up == null ? "—" : String(data.targets_up)}
            tone="muted"
            hint="Endpoint che Prometheus sta interrogando con successo."
          />
          <Metric
            label="Target giù"
            value={data.targets_down == null ? "—" : String(down)}
            tone={down === 0 ? "ok" : "bad"}
            hint="Un target giù non degrada nulla di visibile: è così che le metriche dell'app sono rimaste assenti per mesi. Quali, nel dettaglio qui sotto."
          />
          <Metric
            label="Alert attivi"
            value={data.alerts_firing == null ? "—" : String(firing)}
            tone={firing === 0 ? "ok" : "bad"}
            hint="Watchdog escluso di proposito: deve sempre suonare, è il canarino che certifica che Alertmanager consegna. Quali stanno scattando, nel dettaglio qui sotto."
          />
          <Metric
            label="Riavvii (24h)"
            value={data.restarts_24h == null ? "—" : String(restarts)}
            tone={restarts === 0 ? "ok" : restarts < 3 ? "warn" : "bad"}
            hint="Un OOM-kill compare qui prima che altrove. Quale contenitore e perché, nel dettaglio qui sotto."
          />
          <Metric
            label="Memoria"
            value={mem == null ? "—" : `${mem.toFixed(0)}%`}
            tone={mem == null ? "muted" : mem >= 90 ? "bad" : mem >= 75 ? "warn" : "ok"}
            hint="Percentuale del LIMITE del container, non della memoria del nodo. Subito dopo un riavvio resta vuota per un ciclo di scrape: la serie del container nuovo non esiste ancora."
          />
          <Metric
            label="Certificati TLS"
            value={cert == null ? "—" : `${Math.round(cert)}g`}
            tone={cert == null ? "muted" : cert < 20 ? "bad" : cert < 30 ? "warn" : "ok"}
            hint="Giorni alla scadenza più vicina. cert-manager rinnova intorno ai 30: sotto i 20 il rinnovo non sta funzionando."
          />
        </div>

        {/* ─── Che cosa NON va, per nome ─────────────────────────────────
            ⚠️ I dettagli stavano in un attributo `title`: su un telefono non
            si apre mai, e anche su desktop andavano cercati col mouse. Un
            numero che dice «3» e manda a `kubectl` non e' una diagnosi — e la
            scheda esiste proprio per non dover aprire un terminale.
            ⚠️ Il blocco compare SOLO quando c'e' qualcosa da dire: una sezione
            «nessun problema» sempre presente e' rumore che si impara a
            saltare, e allora non la si legge nemmeno quando si riempie. */}
        {problemi > 0 && (
          <div className="mt-3 space-y-2 border-t border-border/50 pt-2.5">
            {data.firing_alerts.length > 0 && (
              <Dettaglio icona={Bell} titolo="Alert attivi">
                {data.firing_alerts.map((a) => (
                  <li key={a.name} className="leading-snug">
                    <span className="font-semibold">{a.name}</span>
                    {a.severity && (
                      <span className="ml-1.5 rounded bg-rose-100 px-1 py-px text-[0.6176rem] font-semibold uppercase text-rose-800 dark:bg-rose-900/40 dark:text-rose-200">
                        {a.severity}
                      </span>
                    )}
                    {a.target && (
                      <span className="ml-1.5 text-muted-foreground">su {a.target}</span>
                    )}
                    {a.since && (
                      <span className="ml-1.5 text-muted-foreground">· da {da(a.since)}</span>
                    )}
                    {a.summary && (
                      <div className="text-muted-foreground">{a.summary}</div>
                    )}
                  </li>
                ))}
              </Dettaglio>
            )}

            {data.down_targets.length > 0 && (
              <Dettaglio icona={Server} titolo="Target giù">
                {data.down_targets.map((t) => (
                  <li key={`${t.namespace}/${t.job}/${t.instance ?? ""}`}>
                    <span className="font-semibold">
                      {t.namespace}/{t.job}
                    </span>
                    {/* ⚠️ Assente, non "?": Prometheus puo' non esporre
                        l'etichetta, ed e' diverso da un'istanza vuota. */}
                    {t.instance && (
                      <span className="ml-1.5 text-muted-foreground">{t.instance}</span>
                    )}
                  </li>
                ))}
              </Dettaglio>
            )}

            {(data.restart_details ?? []).length > 0 && (
              <Dettaglio icona={RotateCcw} titolo="Riavvii (24h)">
                {(data.restart_details ?? []).map((r) => (
                  <li key={`${r.pod}/${r.container}`}>
                    <span className="font-semibold">{r.container}</span>
                    <span className="ml-1.5 text-muted-foreground">in {r.pod}</span>
                    <span className="ml-1.5 tabular-nums">×{r.count}</span>
                    {r.reason ? (
                      <span className="ml-1.5 rounded bg-amber-100 px-1 py-px text-[0.6176rem] font-semibold text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                        {r.reason}
                      </span>
                    ) : (
                      /* ⚠️ Non si scrive «Unknown»: il motivo dell'ultima
                         terminazione puo' mancare legittimamente, e una parola
                         inventata la farebbe sembrare una lettura. */
                      <span className="ml-1.5 text-muted-foreground">
                        motivo non registrato
                      </span>
                    )}
                  </li>
                ))}
              </Dettaglio>
            )}
          </div>
        )}

        {/* ArgoCD. Assente finché nessuno raccoglie argocd-metrics — e in quel
            caso lo dice, invece di inventare uno stato di sync. */}
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border/50 pt-2.5">
          <GitBranch className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
            ArgoCD
          </span>
          {data.argocd ? (
            <>
              <span
                className={cn(
                  "rounded px-1.5 py-px text-[0.6765rem] font-semibold",
                  data.argocd.sync === "Synced"
                    ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
                    : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
                )}
              >
                {data.argocd.sync}
              </span>
              <span
                className={cn(
                  "rounded px-1.5 py-px text-[0.6765rem] font-semibold",
                  data.argocd.health === "Healthy"
                    ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
                    : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
                )}
              >
                {data.argocd.health}
              </span>
              <span
                className="text-[0.6765rem] text-muted-foreground"
                title="Synced significa che i manifest di quel commit sono stati applicati — non che il pod stia già eseguendo la tua immagine. Il bump del tag è un commit successivo. La riga «Commit in esecuzione» qui sopra è la risposta diretta."
              >
                · non basta per dire "è a schermo"
              </span>
            </>
          ) : (
            <span className="text-[0.6765rem] text-muted-foreground">
              non monitorato — nessuno raccoglie <code className="font-mono">argocd-metrics</code>
            </span>
          )}
        </div>

        {/* I componenti, quelli giù per primi. */}
        {data.components.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {data.components.map((c) => (
              <span
                key={`${c.namespace}/${c.job}`}
                className={cn(
                  "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[0.6765rem]",
                  c.up
                    ? "border-border/60 text-muted-foreground"
                    : "border-rose-300/60 bg-rose-50 font-semibold text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/40 dark:text-rose-300",
                )}
                title={`${c.namespace}/${c.job} — ${c.up ? "raggiungibile" : "non risponde allo scrape"}`}
              >
                {c.up ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <AlertTriangle className="h-3 w-3" />
                )}
                {c.job}
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
