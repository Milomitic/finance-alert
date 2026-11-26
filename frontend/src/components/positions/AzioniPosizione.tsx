import { Trash2, XCircle } from "lucide-react";

import type { Position } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useConfermaInDuePassi } from "@/hooks/useConfermaInDuePassi";
import { cn } from "@/lib/utils";

/* ─── Chiudere o eliminare una posizione tracciata (D-34) ──────────────────
 *
 * Erano due `confirm()` del browser, senza il risultato che si stava per
 * realizzare, e un cestino da 28px a 4px da «Chiudi». Ora:
 *   - «Chiudi» al primo tocco dice cosa succede («Chiudi · P/L +3,2%») e
 *     chiude al secondo;
 *   - «Elimina» sta staccato, ha un nome, e chiede anch'esso il secondo tocco:
 *     su una posizione chiusa cancella un risultato realizzato. */

function pct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "";
  return `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(1).replace(".", ",")}%`;
}

export function AzioniPosizione({
  p, onClose, onDelete, inCorso,
}: {
  p: Position;
  onClose?: (p: Position) => void;
  onDelete: (p: Position) => void;
  inCorso?: boolean;
}) {
  const chiudi = useConfermaInDuePassi(() => onClose?.(p));
  const elimina = useConfermaInDuePassi(() => onDelete(p));
  const risultato = pct(p.closed_at == null ? p.unrealized_pct : p.realized_pct);
  return (
    <span className="inline-flex items-center gap-3 whitespace-nowrap">
      {onClose && (
        <Button
          size="sm"
          variant={chiudi.armato ? "default" : "outline"}
          onClick={chiudi.premi}
          disabled={inCorso}
          aria-label={chiudi.armato ? `Conferma: chiudi ${p.ticker}${risultato ? ` con P/L ${risultato}` : ""}` : `Chiudi ${p.ticker} al prezzo corrente`}
        >
          <XCircle className="mr-1 h-3.5 w-3.5" aria-hidden />
          {chiudi.armato ? `Chiudi${risultato ? ` · P/L ${risultato}` : ""}?` : "Chiudi"}
        </Button>
      )}
      <Button
        size="sm"
        variant="ghost"
        onClick={elimina.premi}
        className={cn(elimina.armato ? "text-red-700 dark:text-red-300" : "text-muted-foreground")}
        aria-label={elimina.armato ? `Conferma: elimina la posizione su ${p.ticker}` : `Elimina la posizione su ${p.ticker}`}
      >
        <Trash2 className="h-3.5 w-3.5" aria-hidden />
        {elimina.armato && <span className="ml-1">Elimina?</span>}
      </Button>
    </span>
  );
}
