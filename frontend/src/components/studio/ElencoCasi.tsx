import { Download } from "lucide-react";
import { useState } from "react";

import type { Caso } from "@/api/studio";
import { Button } from "@/components/ui/button";
import { useIsPhone } from "@/hooks/useMediaQuery";
import { csvDeiCasi, nomeFileCasi } from "@/lib/csvCasi";
import { pct } from "@/lib/studio";
import { cn } from "@/lib/utils";

/* ─── I casi di uno studio, uno per uno (FA-193) ──────────────────────────
 *
 * Il primo controllo di chiunque davanti a «22 casi» e' guardare quali: se il
 * 2020 pesa da solo, se tre giorni di fila sono un episodio solo. Gli episodi
 * sono le finestre indipendenti contate nel verdetto (stessa regola, un
 * proprietario solo). */

function scarica(testo: string, nome: string) {
  const url = URL.createObjectURL(new Blob([testo], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  URL.revokeObjectURL(url);
}

export function ElencoCasi({ casi, totale, episodi, simbolo, modello, etichettaMossa }: {
  casi: Caso[];
  /** I casi contati in tutto (l'elenco puo' essere tagliato ai piu' recenti). */
  totale: number;
  episodi: number;
  simbolo: string;
  modello: string;
  /** «Mossa» per «dopo un movimento»; assente per gli eventi. */
  etichettaMossa?: string;
}) {
  const isPhone = useIsPhone();
  const [soloPrimi, setSoloPrimi] = useState(false);
  if (casi.length === 0) return null;
  const visibili = soloPrimi ? casi.filter((c) => c.primo) : casi;
  const conMossa = etichettaMossa != null;
  return (
    <details className="rounded-md border">
      <summary className="cursor-pointer select-none px-3 py-2 text-sm font-semibold">
        I {totale} casi ({episodi} episodi)
      </summary>
      <div className="space-y-2 border-t px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={soloPrimi} onChange={(e) => setSoloPrimi(e.target.checked)} />
            Solo il primo giorno di ogni episodio
          </label>
          <Button type="button" variant="outline" size="sm"
            onClick={() => scarica(csvDeiCasi(casi, conMossa), nomeFileCasi(simbolo, modello))}>
            <Download className="mr-1 h-3.5 w-3.5" aria-hidden /> Esporta CSV
          </Button>
        </div>
        {casi.length < totale && (
          <p className="text-xs text-muted-foreground">I {casi.length} più recenti; il verdetto usa tutti i {totale}.</p>
        )}
        <div className="max-h-72 overflow-y-auto">
          {isPhone ? (
            <ul className="space-y-1">
              {visibili.map((c) => (
                <li key={c.data} className={cn("flex justify-between rounded px-2 py-1 text-sm", c.primo ? "bg-muted/40" : "pl-5")}>
                  <span className="tabular-nums">{c.data}</span>
                  {conMossa && <span className="tabular-nums text-muted-foreground">{pct(c.mossa ?? null, 1)}</span>}
                  <span className="font-semibold tabular-nums">{pct(c.esito, 1)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-card">
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-1 pr-3 font-medium">Data</th>
                  {conMossa && <th className="py-1 pr-3 text-right font-medium">{etichettaMossa}</th>}
                  <th className="py-1 pr-3 text-right font-medium">Esito</th>
                  <th className="py-1 text-right font-medium">Episodio</th>
                </tr>
              </thead>
              <tbody>
                {visibili.map((c) => (
                  <tr key={c.data} className={cn("border-b last:border-0", !c.primo && "text-muted-foreground")}>
                    <td className={cn("py-1 pr-3 tabular-nums", !c.primo && "pl-4")}>{c.data}</td>
                    {conMossa && <td className="py-1 pr-3 text-right tabular-nums">{pct(c.mossa ?? null, 1)}</td>}
                    <td className="py-1 pr-3 text-right font-semibold tabular-nums">{pct(c.esito, 1)}</td>
                    <td className="py-1 text-right tabular-nums">{c.episodio}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </details>
  );
}
