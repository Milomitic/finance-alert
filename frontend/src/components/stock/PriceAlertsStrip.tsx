import { Bell, BellOff, Check } from "lucide-react";

import type { PriceAlert } from "@/api/types";
import { cn } from "@/lib/utils";

/* I price alert del titolo, come riga di chip sotto al grafico.
 *
 * Si potevano CREARE e mai piu' toccare: il percorso di creazione (click sul
 * grafico, dialog) era completo, gli hook di modifica ed eliminazione pure —
 * e nessuna schermata li montava. Gli endpoint PATCH e DELETE del backend
 * sono vivi e senza chiamanti da allora.
 *
 * PERCHE' UNA STRISCIA E NON UNA CARD. Una `PriceAlertsCard` nella barra
 * laterale ESISTEVA, ed e' stata rimossa su richiesta esplicita
 * dell'utente — "la lista dei price alert non vale una card intera nella
 * sidebar" (vedi il commento in StockDetailPage). Ricostruirla annullerebbe
 * una sua decisione. Quindi gli alert restano dove gia' sono, annotazioni sul
 * grafico, e guadagnano una riga compatta subito sotto: gestisci la linea
 * dove la vedi, e quando non ce ne sono la riga non esiste.
 *
 * Nessuno stato vuoto, di proposito: un riquadro che occupa spazio per dire
 * "non hai alert" direbbe quello che il grafico dice gia' non avendo linee. */

const fmt = (v: number) =>
  v >= 1000 ? v.toLocaleString("it-IT", { maximumFractionDigits: 0 }) : v.toFixed(2);

export function PriceAlertsStrip({
  alerts,
  onEdit,
}: {
  alerts: PriceAlert[];
  onEdit: (a: PriceAlert) => void;
}) {
  if (alerts.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-1">
      <span className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
        Price alert
      </span>
      {alerts.map((a) => {
        const fired = a.triggered_at != null;
        const off = !a.enabled;
        // Uno scattato o disattivato non e' assente, ed e' la distinzione che
        // conta qui: una linea sul grafico che non allertera' piu' deve
        // dirlo, altrimenti si continua ad aspettarla.
        const state = fired ? "scattato" : off ? "disattivo" : null;
        const Icon = fired ? Check : off ? BellOff : Bell;
        return (
          <button
            key={a.id}
            type="button"
            onClick={() => onEdit(a)}
            title={`Modifica o elimina questo price alert${a.note ? ` — ${a.note}` : ""}`}
            className={cn(
              // min-h-[36px] e' la soglia di tocco usata nel resto dell'app.
              "inline-flex min-h-[36px] items-center gap-1.5 rounded-md border px-2 py-1",
              "text-[0.7059rem] tabular-nums transition-colors hover:bg-accent",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              fired || off
                ? "border-border/60 text-muted-foreground"
                : a.direction === "above"
                  ? "border-emerald-300/60 text-emerald-800 dark:border-emerald-800/60 dark:text-emerald-300"
                  : "border-rose-300/60 text-rose-700 dark:border-rose-800/60 dark:text-rose-300",
            )}
          >
            <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="font-semibold">
              {a.direction === "above" ? "↑" : "↓"} ${fmt(a.target_price)}
            </span>
            {a.note && (
              <span className="max-w-[10rem] truncate text-muted-foreground">
                {a.note}
              </span>
            )}
            {state && (
              <span className="rounded bg-muted px-1 text-[0.6471rem] uppercase tracking-wider">
                {state}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
