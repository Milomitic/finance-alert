import { Star } from "lucide-react";

import { useStellaPreferito } from "@/hooks/usePreferiti";
import { cn } from "@/lib/utils";

/** La stella dei preferiti (FA-112), accanto al ticker nella pagina titolo.
 *
 *  `aria-pressed` e non due bottoni: e' un interruttore, e chi usa un lettore
 *  di schermo deve sentire lo STATO, non solo l'azione. Il bersaglio e' 36px,
 *  sopra il minimo di 24 che il gate tattile pretende. Il contorno pieno e'
 *  `amber-700`: `amber-600` sta a 3,19:1 sulla scheda e scende sotto il 3:1
 *  degli elementi grafici sul fondo muto — il censimento di FA-073 lo vieta
 *  anche sulle icone. */
export function StellaPreferito({ ticker }: { ticker: string }) {
  const { preferito, pronto, commuta, inCorso } = useStellaPreferito(ticker);
  return (
    <button
      type="button"
      onClick={commuta}
      disabled={!pronto || inCorso}
      aria-pressed={preferito}
      // Nome FISSO: lo stato lo dice `aria-pressed`. Un nome che cambia con lo
      // stato verrebbe annunciato due volte («Togli dai preferiti, premuto»).
      aria-label={`Preferito ${ticker}`}
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-muted disabled:opacity-50"
    >
      <Star
        className={cn(
          "h-6 w-6",
          preferito
            ? "fill-amber-400 text-amber-700 dark:fill-amber-300 dark:text-amber-300"
            : "text-muted-foreground",
        )}
        aria-hidden
      />
    </button>
  );
}
