import { Bell } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { OutcomesView } from "@/components/alert/OutcomesView";
import { SignalsView } from "@/components/alert/SignalsView";
import { SetupsView } from "@/components/setups/SetupsView";
import { SCHEDE, schedaDa, type SchedaId } from "@/lib/schedeSegnali";
import { cn } from "@/lib/utils";

/* ─── Segnali: una destinazione, il ciclo di vita intero ──────────────────
 *
 * Tre schede, nell'ordine in cui un'idea vive:
 *
 *   In formazione   le condizioni stanno convergendo, il segnale non c'e' ancora
 *   Segnali         il segnale e' scattato
 *   Esiti           l'episodio si e' chiuso — il piano, e il setup che l'ha annunciato
 *
 * ⚠️ «In formazione» era una destinazione a se' (`/setups`) con dentro il
 * proprio selettore «In formazione / Esiti». Cioe' esistevano DUE posti che si
 * chiamavano Esiti — uno dentro i setup, uno implicito nella colonna Esito
 * della lista segnali — e nessuno dei due conteneva l'altro. Il ciclo di vita
 * e' uno solo: setup → segnale → posizione, e `converted_alert_id` insieme a
 * `Position.alert_id` lo rendono percorribile nei dati. Tenerlo spezzato fra
 * due voci di menu obbligava a navigare per seguire una storia sola.
 *
 * ⚠️ `/setups` NON sparisce: reindirizza qui portandosi dietro la query, cosi'
 * i segnalibri e i link interni continuano a valere. Stessa scelta di
 * `/health` verso Diagnostica.
 *
 * ⚠️ Bottoni con `aria-pressed`, non `role="tab"`. Un gruppo di tab promette
 * un `tabpanel` con un id, e senza di quello axe segnala un `aria-controls`
 * pendente — gia' costato due corse rosse del gate UI su questo repo. Due
 * bottoni con `aria-pressed` sono la forma corretta di un controllo segmentato
 * e non promettono niente che non ci sia.
 */

export default function AlertsPage() {
  const [params, setParams] = useSearchParams();
  const scheda = schedaDa(params.get("vista"));

  /** ⚠️ Cambiare scheda azzera la PAGINA, non i filtri. La pagina 4 di una
   *  lista non significa niente in un'altra; `ticker`, `tono` e `condizione`
   *  invece descrivono che cosa si sta guardando e sopravvivono al passaggio,
   *  che e' il motivo per cui le tre viste stanno insieme. */
  const apri = (id: SchedaId) => {
    const p = new URLSearchParams(params);
    if (id === "segnali") p.delete("vista");
    else p.set("vista", id);
    p.delete("pagina");
    p.delete("page");
    setParams(p, { replace: true });
  };

  return (
    <div className="space-y-4">
      <div>
        {/* Il titolo e' l'IDENTITA' della destinazione e non cambia con la
            scheda: cio' che appartiene alla vista varia sotto. */}
        <h2 className="flex items-center gap-3 text-2xl font-semibold tracking-tight sm:text-3xl">
          <Bell className="h-7 w-7 text-muted-foreground" aria-hidden />
          Segnali
        </h2>
      </div>

      <div
        role="group"
        aria-label="Scheda"
        className="inline-flex overflow-hidden rounded-md border text-xs font-semibold"
      >
        {SCHEDE.map((s) => (
          <button
            key={s.id}
            type="button"
            aria-pressed={scheda === s.id}
            onClick={() => apri(s.id)}
            className={cn(
              "min-h-[36px] px-3 transition-colors",
              scheda === s.id
                ? "bg-accent text-foreground"
                : "text-muted-foreground hover:bg-accent/40",
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Una sola vista montata alla volta: `hidden` terrebbe in piedi due
          alberi e due serie di query, e quello nascosto verrebbe comunque
          letto dagli assistivi. */}
      {scheda === "formazione" ? (
        <SetupsView vista="formazione" />
      ) : scheda === "esiti" ? (
        <OutcomesView />
      ) : (
        <SignalsView />
      )}
    </div>
  );
}
