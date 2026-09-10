import { Activity, Stethoscope } from "lucide-react";
import { Suspense, lazy } from "react";
import { useSearchParams } from "react-router-dom";

import { cn } from "@/lib/utils";

const PlatformHealthPage = lazy(() => import("@/pages/PlatformHealthPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));

/* Diagnostica — una destinazione, due schede.
 *
 * L'app aveva DUE pagine di diagnostica con nomi diversi e posti diversi nel
 * menu, e una delle due si chiamava «Impostazioni» pur non contenendo una sola
 * impostazione: otto pannelli, tutti diagnostici, sotto un ingranaggio in fondo
 * alla barra laterale — cioe' nel posto dove ogni applicazione mette le
 * preferenze. Chi cercava «perche' il motore dice questo» doveva sapere che la
 * risposta stava sotto un ingranaggio; chi cercava una preferenza la cercava li'
 * e non la trovava.
 *
 * ⚠️ La separazione fra le due schede non e' organizzativa, e' una distinzione
 * di significato che il resto del progetto applica ovunque: **disponibilita' del
 * sistema** e **capacita' predittiva del motore** sono due domande diverse. Una
 * sorgente dati che non risponde e un guasto; un detector che legge «non
 * concludente» non lo e' — e' la misura che dice la verita'. Metterle nella
 * stessa pagina senza separarle inviterebbe a leggere la seconda come un
 * allarme.
 *
 * ⚠️ Le vecchie rotte NON spariscono. `/health` e `/settings` reindirizzano
 * qui sulla scheda giusta: i segnalibri esistenti continuano a funzionare, e
 * la scheda vive nell'URL cosi' anche un link a una singola vista resta
 * condivisibile.
 */

const TABS = [
  {
    id: "piattaforma",
    label: "Piattaforma",
    icon: Activity,
    hint: "Sorgenti dati, scheduler, scan e log",
  },
  {
    id: "motore",
    label: "Motore",
    icon: Stethoscope,
    hint: "Efficacia dei segnali, calibrazione, studi",
  },
] as const;

type TabId = (typeof TABS)[number]["id"];

/** La scheda richiesta dall'URL, con un default esplicito.
 *
 *  Piattaforma per prima perche' risponde alla domanda piu' urgente delle due:
 *  «qualcosa e' rotto?». La qualita' del motore e' una domanda che si fa con
 *  calma. */
function tabFrom(raw: string | null): TabId {
  return TABS.some((t) => t.id === raw) ? (raw as TabId) : "piattaforma";
}

export default function DiagnosticsPage() {
  const [params, setParams] = useSearchParams();
  const active = tabFrom(params.get("vista"));

  return (
    <div className="space-y-4">
      <header className="space-y-3">
        <div className="space-y-1">
          <div className="text-[0.6765rem] font-mono font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            Amministrazione
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight leading-tight">
            Diagnostica
          </h1>
        </div>

        <div
          role="tablist"
          aria-label="Vista diagnostica"
          className="inline-flex items-center gap-1 rounded-md border bg-muted/30 p-0.5"
        >
          {TABS.map(({ id, label, icon: Icon, hint }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={id === active}
              title={hint}
              // `replace` per non riempire la storia del browser di un passo
              // per ogni cambio scheda: tornare indietro deve uscire da
              // Diagnostica, non ripercorrere le schede una a una.
              onClick={() => setParams({ vista: id }, { replace: true })}
              className={cn(
                "inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium transition-colors",
                id === active
                  ? "bg-background shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              {label}
            </button>
          ))}
        </div>
      </header>

      {/* Solo la scheda attiva viene montata. Non e' solo peso: la vista
          Piattaforma tiene aperta una connessione SSE per tutta la propria
          vita, e montarla dietro una scheda chiusa la lascerebbe aperta
          mentre si guarda l'altra. */}
      <Suspense
        fallback={<div className="h-64 animate-pulse rounded-lg bg-muted/30" />}
      >
        {active === "piattaforma" ? (
          <PlatformHealthPage embedded />
        ) : (
          <SettingsPage embedded />
        )}
      </Suspense>
    </div>
  );
}
