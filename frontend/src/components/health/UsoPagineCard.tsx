import { MousePointerClick } from "lucide-react";

import type { UsoPagine } from "@/api/platformHealth";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { nomePagina } from "@/lib/rotteUso";

/* ─── Quante volte si apre ogni pagina (FA-114) ───────────────────────────
 *
 * Esiste per decidere su basi misurate cosa tenere e cosa togliere (FA-115):
 * l'analisi del 2026-09-26 ha dovuto ricostruire l'uso dai log, e 30 giorni di
 * Loki lo hanno mandato in OOM.
 *
 * ⚠️ «Dal» viaggia accanto ai numeri, e non per scrupolo: a contatore appena
 * acceso la colonna «30 giorni» copre due giorni, e una pagina con 3 aperture
 * si leggerebbe come una pagina che nessuno usa.
 *
 * `null` e' NON SO (lettura fallita) e la scheda lo dice; una lista vuota e'
 * «nessuna apertura contata ancora», che e' un'altra cosa.
 */

function data(iso: string): string {
  const [a, m, g] = iso.split("-");
  return `${g}/${m}/${a}`;
}

export default function UsoPagineCard({ uso }: { uso?: UsoPagine | null }) {
  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle
          icon={MousePointerClick}
          label="Uso delle pagine"
          className="mb-1.5"
          right={
            <span className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
              {uso?.dal ? `contate dal ${data(uso.dal)}` : "aperture"}
            </span>
          }
        />
        {uso == null ? (
          <p className="py-2 text-[0.7059rem] text-muted-foreground">
            Conteggio non disponibile in questo momento.
          </p>
        ) : uso.rotte.length === 0 ? (
          <p className="py-2 text-[0.7059rem] text-muted-foreground">
            Nessuna apertura contata ancora.
          </p>
        ) : (
          <table className="w-full text-[0.7059rem]">
            <thead>
              <tr className="text-muted-foreground">
                <th className="py-1 text-left font-normal">Pagina</th>
                <th className="py-1 text-right font-normal">7 giorni</th>
                <th className="py-1 text-right font-normal">30 giorni</th>
              </tr>
            </thead>
            <tbody>
              {uso.rotte.map((r) => (
                <tr key={r.rotta} className="border-t border-border/40">
                  {/* Il nome va a capo invece di troncarsi: e' l'identita'
                      della riga, e senza di lui i due numeri accanto non
                      dicono niente (CLAUDE.md, «quando lo spazio finisce»). */}
                  <td className="py-1 pr-2 break-words">{nomePagina(r.rotta)}</td>
                  <td className="py-1 text-right tabular-nums">{r.ultimi_7}</td>
                  <td className="py-1 text-right font-semibold tabular-nums">{r.ultimi_30}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
