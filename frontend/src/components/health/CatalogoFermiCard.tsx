import { useMutation } from "@tanstack/react-query";
import { Briefcase, CircleSlash, Star } from "lucide-react";
import { Link } from "react-router-dom";

import { verificaFonte, type VerificaFonte } from "@/api/catalogo";
import type { Catalogo, TitoloFermo } from "@/api/platformHealth";
import { Card, CardContent } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SectionTitle } from "@/components/ui/section-title";

/* ─── I titoli fermi del catalogo (2026-09-29) ────────────────────────────
 *
 * La scansione salta un titolo la cui serie non avanza (FA-071), ma nessuna
 * schermata diceva quali: serviva una query nel pod. Qui l'elenco, con cio'
 * che l'app sa, e una verifica sulla fonte a richiesta.
 *
 * ⚠️ Nessuna «causa probabile» scritta a tavolino: dal catalogo non si
 * distingue un cambio di simbolo da una fusione o da un'uscita dal listino.
 * La verifica mostra cio' che Yahoo risponde e lascia la lettura a chi guarda.
 *
 * Il risultato si apre in un pannello e non allargando la riga: la risposta
 * arriva dopo mezzo secondo e sposterebbe la pagina (FA-106).
 */

function data(iso: string | null): string {
  if (!iso) return "—";
  const [a, m, g] = iso.slice(0, 10).split("-");
  return `${g}/${m}/${a}`;
}

function Esito({ v }: { v: VerificaFonte }) {
  return (
    <div className="space-y-2 text-xs">
      <p>
        {v.barre_recenti
          ? `Yahoo risponde di nuovo: ${v.barre_recenti} barre nell'ultimo mese, l'ultima del ${data(v.ultima_barra_fonte)}.`
          : v.barre_recenti === 0
            ? `Yahoo non ha barre di ${v.ticker} nell'ultimo mese.`
            : `Le barre di ${v.ticker} non si sono potute leggere.`}
      </p>
      {v.candidati.length > 0 ? (
        <div>
          <p className="text-muted-foreground">Simboli che la ricerca per nome restituisce:</p>
          <ul className="mt-1 space-y-0.5">
            {v.candidati.map((c) => (
              <li key={c.simbolo} className="break-words">
                <span className="font-semibold">{c.simbolo}</span>
                {[c.borsa, c.tipo, c.nome].filter(Boolean).map((x) => ` · ${x}`).join("")}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-muted-foreground">La ricerca per nome non restituisce altri simboli.</p>
      )}
      {v.errore && <p className="text-muted-foreground">Risposta parziale: {v.errore}</p>}
    </div>
  );
}

function Verifica({ f }: { f: TitoloFermo }) {
  const m = useMutation({ mutationFn: () => verificaFonte(f.ticker) });
  return (
    <Popover onOpenChange={(aperto) => aperto && m.isIdle && m.mutate()}>
      {/* ⚠️ `aria-label`, non uno `sr-only` dentro il testo: il calcolo del
          nome accessibile scarta lo spazio iniziale dello span e ne usciva
          «VerificaEA sulla fonte». Comincia col testo visibile, perche' chi
          comanda a voce dice quello che vede. */}
      <PopoverTrigger
        aria-label={`Verifica ${f.ticker} sulla fonte`}
        className="rounded border border-border/60 px-1.5 py-0.5 text-[0.6471rem] hover:bg-muted"
      >
        Verifica
      </PopoverTrigger>
      <PopoverContent align="end" collisionPadding={16} className="w-80 max-w-[calc(100vw-2rem)] p-3">
        {m.isPending ? (
          <p className="text-xs text-muted-foreground">Chiedo a Yahoo…</p>
        ) : m.isError ? (
          <p className="text-xs text-muted-foreground">Verifica non riuscita.</p>
        ) : m.data ? (
          <Esito v={m.data} />
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

export default function CatalogoFermiCard({ catalogo }: { catalogo?: Catalogo | null }) {
  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle
          icon={CircleSlash}
          label="Titoli fermi"
          className="mb-1.5"
          right={
            catalogo ? (
              <span className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
                {catalogo.fermi.length} su {catalogo.totale}
              </span>
            ) : undefined
          }
        />
        {catalogo == null ? (
          <p className="py-2 text-[0.7059rem] text-muted-foreground">
            Catalogo non disponibile in questo momento.
          </p>
        ) : (
          <>
            {catalogo.fermi.length === 0 ? (
              <p className="py-2 text-[0.7059rem] text-muted-foreground">
                Nessun titolo fermo: ogni serie avanza.
              </p>
            ) : (
              <table className="w-full text-[0.7059rem]">
                <thead>
                  <tr className="text-muted-foreground">
                    <th className="py-1 text-left font-normal">Titolo</th>
                    <th className="py-1 text-right font-normal">Ultima barra</th>
                    <th className="py-1 text-right font-normal">Tentativi</th>
                    <th className="py-1"><span className="sr-only">Verifica</span></th>
                  </tr>
                </thead>
                <tbody>
                  {catalogo.fermi.map((f) => (
                    <tr key={f.ticker} className="border-t border-border/40 align-top">
                      <td className="py-1 pr-2">
                        <span className="inline-flex items-center gap-1">
                          <Link to={`/stocks/${encodeURIComponent(f.ticker)}`} className="font-semibold hover:underline">
                            {f.ticker}
                          </Link>
                          {f.in_posizione && (
                            <Briefcase className="h-3 w-3 text-muted-foreground" aria-label="in posizione" />
                          )}
                          {f.preferito && (
                            <Star className="h-3 w-3 fill-amber-400 text-amber-700 dark:fill-amber-300 dark:text-amber-300" aria-label="preferito" />
                          )}
                        </span>
                        {/* Il nome va a capo invece di troncarsi: e' l'identita'
                            della riga (CLAUDE.md, «quando lo spazio finisce»). */}
                        {f.nome && <div className="break-words text-muted-foreground">{f.nome}</div>}
                        {f.indici.length > 0 && (
                          <div className="text-muted-foreground">in {f.indici.join(", ")}</div>
                        )}
                      </td>
                      <td className="py-1 text-right tabular-nums">{data(f.ultima_barra)}</td>
                      <td className="py-1 text-right tabular-nums">{f.tentativi}</td>
                      <td className="py-1 pl-2 text-right">
                        <Verifica f={f} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="mt-2 text-[0.6471rem] text-muted-foreground">
              Su {catalogo.totale} titoli: {catalogo.senza_settore} senza settore,{" "}
              {catalogo.senza_capitalizzazione} senza capitalizzazione.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
