import { Layers } from "lucide-react";

import type { GiornataMercato } from "@/api/alerts";
import { Card, CardContent } from "@/components/ui/card";
import { giornoDelTesto, verso } from "@/lib/giornateDiMercato";
import { Button } from "@/components/ui/button";

/* ─── Giornate di mercato (FA-152) ───────────────────────────────────────
 *
 * Un giorno con cento segnali nello stesso verso e' il mercato visto cento
 * volte. Sull'universo quei segnali escono dalla lista, nel loro verso, e
 * questa striscia dice quali giorni mancano e come riaprirli. I segnali sui
 * titoli in posizione e fra i preferiti restano sempre in lista. */

const MAX = 4;
export function GiornateDiMercato({
  giornate, comprime, onApri, onMostraTutte, onComprimi,
}: {
  giornate: GiornataMercato[] | undefined;
  comprime: boolean;
  onApri: (g: GiornataMercato) => void;
  onMostraTutte: () => void;
  onComprimi: () => void;
}) {
  if (!giornate || giornate.length === 0) return null;
  if (!comprime) {
    return (
      <p className="text-xs text-muted-foreground">
        Giornate di mercato in lista per intero.{" "}
        <Button type="button" variant="testo" size="testo" onClick={onComprimi}>
          Comprimile
        </Button>
      </p>
    );
  }
  const visibili = giornate.slice(0, MAX);
  return (
    <Card>
      <CardContent className="space-y-1.5 p-3 text-sm">
        <div className="flex items-start gap-2">
          <Layers className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <p className="min-w-0 text-muted-foreground">
            <span className="font-semibold text-foreground">Giornate di mercato compresse.</span>{" "}
            In questi giorni un verso ha superato il 95° percentile dei due mesi precedenti: sono il
            mercato, non i titoli. I segnali sui tuoi titoli restano in lista.
          </p>
        </div>
        <ul className="flex flex-wrap gap-x-4 gap-y-1 pl-6">
          {visibili.map((g) => (
            <li key={`${g.giorno}-${g.tono}`} className="text-xs">
              <span className="font-medium tabular-nums">{giornoDelTesto(g.giorno)}</span>
              {" · "}
              <span className="tabular-nums">{g.segnali}</span> {verso(g.tono, g.segnali)}{" "}
              <Button
                type="button"
                variant="testo" size="testo" className="font-semibold"
                onClick={() => onApri(g)}
                aria-label={`Mostra i ${g.segnali} segnali ${verso(g.tono, g.segnali)} del ${g.giorno}`}
              >
                Mostra
              </Button>
            </li>
          ))}
          {giornate.length > MAX && (
            <li className="text-xs text-muted-foreground">e altre {giornate.length - MAX}</li>
          )}
          <li className="text-xs">
            <Button type="button" variant="testo" size="testo" onClick={onMostraTutte}>
              Non comprimere
            </Button>
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}
