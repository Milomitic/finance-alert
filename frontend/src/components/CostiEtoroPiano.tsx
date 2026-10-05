import { useState } from "react";

import { useEtoroCosti } from "@/hooks/useEtoro";
import { stimaCosti } from "@/lib/costiEtoro";
import { fmtPct } from "@/lib/etoroPortafoglio";
import { formatMoneyGrouped } from "@/lib/money";
import type { Playbook } from "@/lib/tradePlaybook";
import { cn } from "@/lib/utils";

/* ─── Quanto costa questo piano su eToro (FA-126) ─────────────────────────
 *
 * Sotto il piano operativo: il preventivo eToro di un ingresso CFD con la
 * geometria del piano (lato e stop), la leva e il margine scelti qui. Apertura
 * una volta, overnight a notte per le notti della tenuta attesa, e il totale
 * in % del margine e in R — perche' lo studio del 2026-09-23 ha trovato che
 * sul piano breve i costi valgono gia' ~0,05 R a operazione.
 *
 * ⚠️ La leva di partenza e' ×5, quella del conto vero (19 posizioni su 19 il
 * 2026-10-05). Il piano qui sopra resta col suo tetto a ×3: sono due domande
 * diverse — quanta leva servirebbe al budget di rischio, e quanto costa la
 * leva che si usa.
 */

const LEVE = [1, 2, 5, 10] as const;
const USD = (v: number | null) => (v == null ? "—" : formatMoneyGrouped(v, "USD"));

export function CostiEtoroPiano({ ticker, playbook }: { ticker: string; playbook: Playbook }) {
  const [leva, setLeva] = useState(5);
  const [importo, setImporto] = useState(500);
  const q = useEtoroCosti({ ticker, lato: playbook.side, leva, importo, stop: playbook.stop });
  if (q.data && !q.data.configurato) return null;
  if (q.data && !q.data.disponibile) {
    return <p className="text-xs text-muted-foreground">{ticker} non risulta negoziabile su eToro.</p>;
  }
  const stima = q.data
    ? stimaCosti({
        aperturaUsd: q.data.apertura_usd, notteUsd: q.data.notte_usd, tenuta: playbook.horizon,
        importo, leva, stopPct: playbook.stopPct,
      })
    : null;
  return (
    <section aria-label="Costi del piano su eToro" className="space-y-2 rounded-md border border-border/60 p-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[0.6765rem] font-semibold uppercase tracking-wider text-muted-foreground">
          Costi su eToro · CFD
        </span>
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label="Leva" className="flex rounded-md border border-border/60 p-0.5">
            {LEVE.map((l) => (
              <button
                key={l}
                type="button"
                aria-pressed={leva === l}
                onClick={() => setLeva(l)}
                className={cn(
                  "min-w-[2.25rem] rounded px-1.5 py-0.5 text-xs font-semibold",
                  leva === l ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
                )}
              >
                ×{l}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1 text-xs text-muted-foreground">
            margine $
            <input
              type="number"
              min={10}
              step={50}
              value={importo}
              onChange={(e) => setImporto(Math.max(0, Number(e.target.value) || 0))}
              className="h-7 w-20 rounded-md border bg-background px-1.5 text-xs tabular-nums text-foreground"
            />
          </label>
        </div>
      </div>
      {q.isError ? (
        <p className="text-xs text-red-600 dark:text-red-400">Preventivo eToro non disponibile in questo momento.</p>
      ) : !stima ? (
        <div className="h-[3.25rem] animate-pulse rounded-md bg-muted/40" aria-label="Carico il preventivo" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-1.5 text-xs sm:grid-cols-4">
            <Voce etichetta="Apertura" valore={USD(stima.apertura)} nota="commissione e spread" />
            <Voce etichetta="Overnight" valore={`${USD(q.data?.notte_usd ?? null)}/notte`} nota={`×${stima.notti} notti`} />
            <Voce etichetta="Tenuta" valore={USD(stima.detenzione)} nota={`${playbook.horizon.toLowerCase()}, stima`} />
            <Voce
              etichetta="Totale"
              valore={USD(stima.totale)}
              nota={stima.pctMargine == null ? "—" : `${fmtPct(stima.pctMargine)} del margine${stima.inR != null ? ` · ${stima.inR.toFixed(2)} R` : ""}`}
              forte
            />
          </div>
          <p className="text-[0.6765rem] text-muted-foreground">
            Con leva ×{leva} lo stop del piano vale{" "}
            <span className="font-semibold text-rose-600 dark:text-rose-400">{fmtPct(stima.stopPctMargine)}</span> del margine.
            Le notti sono il mezzo della tenuta attesa; il preventivo è di eToro, per un ordine ipotetico.
          </p>
        </>
      )}
    </section>
  );
}

function Voce({ etichetta, valore, nota, forte }: { etichetta: string; valore: string; nota: string; forte?: boolean }) {
  return (
    <div className="min-w-0 rounded-md bg-muted/30 px-2 py-1">
      <div className="truncate text-[0.6471rem] font-semibold uppercase tracking-wider text-muted-foreground">{etichetta}</div>
      <div className={cn("truncate tabular-nums", forte ? "font-bold" : "font-semibold")}>{valore}</div>
      <div className="truncate text-[0.6471rem] text-muted-foreground">{nota}</div>
    </div>
  );
}
