import { FlaskConical } from "lucide-react";
import { Link } from "react-router-dom";

import { domandePronte } from "@/lib/studio";

/* ─── Domande pronte per lo Studio (FA-199, F15) ──────────────────────────
 *
 * Lo Studio aveva un solo ingresso dalle altre pagine. Da un titolo o da un
 * mercato ci si arriva con la domanda gia' scritta sul simbolo che si sta
 * guardando. */

export function DomandePronte({ simbolo, tipo }: { simbolo: string; tipo: "titolo" | "mercato" }) {
  return (
    <nav aria-label={`Domande pronte per lo Studio su ${simbolo}`} className="space-y-1.5">
      {/* Un paragrafo, non un <h3>: nella scheda del titolo non c'e' un h2
          sopra, e un livello saltato e' «heading-order» nel gate (28/11). Il
          nome della sezione lo da' gia' l'aria-label del nav. */}
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        <FlaskConical className="h-3.5 w-3.5" aria-hidden /> Studia il passato
      </p>
      <ul className="space-y-1">
        {domandePronte(simbolo, tipo).map((d) => (
          <li key={d.testo}>
            <Link to={d.url} className="text-sm text-primary underline-offset-2 hover:underline">{d.testo}</Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
