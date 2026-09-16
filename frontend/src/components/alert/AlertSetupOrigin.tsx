import { Hourglass } from "lucide-react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { detectorLabel } from "@/lib/setupGrouping";
import { conversionBarNote } from "@/lib/setupTimeline";

/* Da quale setup e' nato questo segnale (FA-066).
 *
 * Il dettaglio titolo racconta la storia di quel titolo, e un segnale che si
 * stava formando da una settimana e' una storia diversa da uno scattato dal
 * nulla. Il collegamento esisteva da FA-061 e non usciva dalla lista setup.
 *
 * ⚠️ E' un FATTO, non un merito. I setup non fanno previsioni e un segnale
 * preceduto da uno non e' per questo migliore: la riga dice quando le
 * condizioni hanno cominciato a formarsi e con quanto anticipo, e niente che
 * si legga come conferma.
 *
 * ⚠️ E porta a `/setups`, filtrato su esiti e titolo, invece di elencare qui
 * gli altri episodi: la scheda setup rimossa dal dettaglio titolo non torna,
 * e «In formazione» resta il luogo dove si confrontano le attese. */
export function AlertSetupOrigin({
  alert,
  onNavigate,
}: {
  alert: Alert;
  /** Chiamata seguendo il collegamento: il dialogo che la ospita si chiude. */
  onNavigate?: () => void;
}) {
  const o = alert.setup_origin;
  if (!o) return null;
  const dal = new Date(o.first_seen_at).toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
  });

  return (
    <div className="flex items-start gap-2 rounded-lg border border-border/60 px-3 py-2 text-sm">
      <Hourglass className="h-3.5 w-3.5 shrink-0 mt-0.5 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <div>
          Preceduto da un setup{" "}
          <span className="font-semibold">{detectorLabel(o.detector)}</span>, in formazione
          dal <span className="tabular-nums">{dal}</span>
          {o.lead_days != null && (
            <>
              {": "}
              <span className="font-semibold tabular-nums">
                {o.lead_days === 1 ? "1 giorno" : `${o.lead_days} giorni`}
              </span>{" "}
              di anticipo
            </>
          )}
          .
        </div>
        {/* ⚠️ Solo quando le due barre DIFFERISCONO: la scansione aggiorna il
            segnale finche' la condizione tiene, e chi legge la data del
            segnale deve sapere che la conversione e' avvenuta prima. */}
        {(() => {
          const nota = conversionBarNote(o.converted_signal_date, alert.signal_date);
          return nota ? <p className="text-xs text-muted-foreground mt-0.5">{nota}</p> : null;
        })()}
        {alert.ticker && (
          <Link
            to={`/setups?vista=esiti&ticker=${encodeURIComponent(alert.ticker)}`}
            onClick={onNavigate}
            className="text-xs font-medium text-muted-foreground hover:text-foreground hover:underline underline-offset-2"
          >
            Gli esiti dei setup di {alert.ticker}
          </Link>
        )}
      </div>
    </div>
  );
}
