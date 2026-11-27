import { useState } from "react";

import type { Calendario } from "@/hooks/useMercati";
import { useIsPhone } from "@/hooks/useMediaQuery";
import { percentuale } from "@/lib/numeri";
import { tintaRendimento } from "@/lib/tintaRendimento";
import { cn } from "@/lib/utils";

/* ─── Il calendario dei rendimenti: anni per mesi (FA-185, FA-195) ────────
 *
 * Un mese e' da fine mese a fine mese (`app/stats/calendario.py`, lo stesso
 * numero della stagionalita' dello Studio). Il fondo dice verso e intensita';
 * il testo resta neutro per il contrasto. In fondo la media di ogni mese,
 * quanti sono stati positivi e su quanti anni: un mese «forte» per tre anni
 * eccezionali si riconosce da li'. */

const MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];
const ANNI_DI_DEFAULT = 12;

function pp(v: number | null | undefined, decimali = 1): string {
  return v == null ? "—" : percentuale(v * 100, decimali);
}

export function CalendarioRendimenti({ calendario, titolo = "Rendimenti per mese" }: {
  calendario: Calendario;
  titolo?: string;
}) {
  const isPhone = useIsPhone();
  const [tutti, setTutti] = useState(false);
  const [scelto, setScelto] = useState<string | null>(null);
  const anni = tutti ? calendario.anni : calendario.anni.slice(0, ANNI_DI_DEFAULT);
  if (calendario.anni.length === 0) return null;

  const piede = (
    <p className="text-xs text-muted-foreground">
      Da fine mese a fine mese. L&apos;anno in corso è parziale. Descrive il passato, non lo prevede.
    </p>
  );
  const pulsante = calendario.anni.length > ANNI_DI_DEFAULT && (
    <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={() => setTutti((t) => !t)}>
      {tutti ? `Solo gli ultimi ${ANNI_DI_DEFAULT} anni` : `Mostra tutti i ${calendario.anni.length} anni`}
    </button>
  );

  if (isPhone) {
    return (
      <section className="space-y-2" aria-label={titolo}>
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">{titolo}</h2>
          <span className="min-h-[1rem] text-xs tabular-nums" aria-live="polite">{scelto ?? "Tocca un mese"}</span>
        </div>
        <ul className="space-y-1">
          {anni.map((a) => (
            <li key={a.anno} className="flex items-center gap-2">
              <span className="w-10 shrink-0 text-xs tabular-nums text-muted-foreground">{a.anno}</span>
              <span className="grid flex-1 grid-cols-12 gap-0.5">
                {a.mesi.map((v, m) => (
                  <button key={m} type="button"
                    aria-label={`${MESI[m]} ${a.anno}: ${pp(v)}`}
                    onClick={() => setScelto(`${MESI[m]} ${a.anno}: ${pp(v)}`)}
                    className={cn("h-5 rounded-sm border border-border/40", v == null ? "bg-muted/20" : tintaRendimento(v, "mese") || "bg-muted/40")} />
                ))}
              </span>
              <span className={cn("w-16 shrink-0 rounded px-1 text-right text-xs font-semibold tabular-nums",
                tintaRendimento(a.anno_totale, "anno"))}>
                {pp(a.anno_totale)}
              </span>
            </li>
          ))}
        </ul>
        {pulsante}
        {piede}
      </section>
    );
  }

  return (
    <section className="space-y-2" aria-label={titolo}>
      <h2 className="text-sm font-semibold">{titolo}</h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] table-fixed text-xs tabular-nums">
          <thead>
            <tr className="text-muted-foreground">
              <th scope="col" className="w-12 py-1 text-left font-medium">Anno</th>
              {MESI.map((m) => <th key={m} scope="col" className="py-1 text-right font-medium">{m}</th>)}
              <th scope="col" className="w-16 py-1 text-right font-medium">Anno</th>
            </tr>
          </thead>
          <tbody>
            {anni.map((a) => (
              <tr key={a.anno} className="border-t border-border/40">
                <th scope="row" className="py-1 text-left font-medium">{a.anno}{a.parziale ? "*" : ""}</th>
                {a.mesi.map((v, m) => (
                  <td key={m} className={cn("px-1 py-1 text-right", tintaRendimento(v, "mese"))}>{v == null ? "" : pp(v)}</td>
                ))}
                <td className={cn("px-1 py-1 text-right font-semibold", tintaRendimento(a.anno_totale, "anno"))}>{pp(a.anno_totale)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="text-muted-foreground">
            <tr className="border-t">
              <th scope="row" className="py-1 text-left font-medium">Media</th>
              {calendario.media_mesi.map((v, m) => <td key={m} className="px-1 py-1 text-right">{pp(v)}</td>)}
              <td />
            </tr>
            <tr>
              <th scope="row" className="py-1 text-left font-medium">Positivi</th>
              {calendario.positivi_mesi.map((v, m) => (
                <td key={m} className="px-1 py-1 text-right">
                  {v == null ? "—" : `${Math.round(v * 100)}%`}
                  <span className="sr-only"> su {calendario.casi_mesi[m]} anni</span>
                </td>
              ))}
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {piede}
        {pulsante}
      </div>
    </section>
  );
}
