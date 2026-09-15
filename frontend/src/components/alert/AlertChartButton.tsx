import { Crosshair } from "lucide-react";

import type { Alert } from "@/api/types";
import { Button } from "@/components/ui/button";

/** Cosa il dialogo di un segnale puo' chiedere al grafico della pagina (FA-066).
 *  Solo il dettaglio titolo ne ha uno: altrove la prop manca e il bottone non
 *  esiste, invece di esistere e non fare niente. */
export interface AlertChartLink {
  /** La barra di questo alert e' nella serie caricata? */
  has: (alert: Alert) => boolean;
  /** Centra il grafico su quella barra. */
  show: (alert: Alert) => void;
}

/* «Mostra sul grafico» (FA-066): la selezione di un evento nella cronologia
 * porta il grafico sulla sua barra.
 *
 * ⚠️ Tre stati, non due. Senza grafico non c'e' niente da offrire. Con un
 * grafico che non ha caricato quella barra — un segnale di marzo su un
 * intervallo di tre mesi — un bottone che non fa niente sarebbe peggio di una
 * frase che dice perche' e cosa fare. */
export function AlertChartButton({
  alert,
  chart,
  onClose,
}: {
  alert: Alert;
  chart?: AlertChartLink;
  onClose: () => void;
}) {
  if (!chart) return null;
  if (!chart.has(alert)) {
    return (
      <p className="text-xs text-muted-foreground">
        La barra di questo segnale non e' nell'intervallo caricato del grafico:
        allarga l'intervallo per vederla.
      </p>
    );
  }
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="h-7 text-xs"
      onClick={() => {
        // Prima si chiude: il dialogo copre il grafico che si chiede di vedere.
        onClose();
        chart.show(alert);
      }}
    >
      <Crosshair className="h-3.5 w-3.5 mr-1" aria-hidden />
      Mostra sul grafico
    </Button>
  );
}
