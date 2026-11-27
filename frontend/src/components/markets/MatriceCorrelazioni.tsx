import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import { Segmentato } from "@/components/ui/segmentato";
import { useIsPhone } from "@/hooks/useMediaQuery";
import { cambiata, coppie, tintaCorrelazione } from "@/lib/correlazioni";
import { numero } from "@/lib/numeri";
import { cn } from "@/lib/utils";

/* ─── Le correlazioni fra mercati (FA-189) ────────────────────────────────
 *
 * «L'oro si muove ancora contro le azioni?» La correlazione dei rendimenti
 * giornalieri, coppia per coppia, e la stessa misura un anno prima. Una cella
 * apre il confronto della coppia in base 100. */

export interface Correlazioni {
  simboli: { symbol: string; name: string; category: string }[];
  matrice: (number | null)[][];
  un_anno_fa: (number | null)[][];
  sedute: number;
  al: string | null;
}

function url(a: string, b: string): string {
  return `/markets?confronta=${encodeURIComponent(`${a},${b}`)}&periodo=1a#confronto`;
}

export function MatriceCorrelazioni() {
  const [sedute, setSedute] = useState<60 | 250>(60);
  const isPhone = useIsPhone();
  const q = useQuery({
    queryKey: ["markets", "correlazioni", sedute],
    queryFn: ({ signal }) => api<Correlazioni>(`/api/markets/correlazioni?sedute=${sedute}`, { signal }),
    staleTime: 30 * 60_000,
    placeholderData: (prev) => prev,
  });
  const d = q.data;
  const nome = (s: string) => d?.simboli.find((x) => x.symbol === s)?.name ?? s;
  return (
    <section aria-label="Correlazioni fra mercati" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Correlazioni</h2>
        <Segmentato etichetta="Finestra delle correlazioni" valore={sedute} onCambia={setSedute}
          voci={[{ id: 60, label: "60 sedute" }, { id: 250, label: "Un anno" }]} />
      </div>
      {!d ? (
        <div className="h-[300px] animate-pulse rounded bg-muted/30" aria-hidden />
      ) : isPhone ? (
        <ElencoCoppie d={d} nome={nome} />
      ) : (
        <div className="overflow-x-auto">
          <table className="text-xs tabular-nums">
            <thead>
              <tr>
                <th />
                {d.simboli.slice(0, -1).map((s) => (
                  <th key={s.symbol} scope="col" className="h-24 w-11 align-bottom font-medium text-muted-foreground">
                    <span className="inline-block w-24 origin-bottom-left translate-x-5 -rotate-45 whitespace-nowrap text-left">{s.name}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.simboli.slice(1).map((r, ii) => {
                const i = ii + 1;
                return (
                  <tr key={r.symbol}>
                    <th scope="row" className="whitespace-nowrap pr-2 text-right font-medium text-muted-foreground">{r.name}</th>
                    {d.simboli.slice(0, -1).map((c, j) => {
                      if (j >= i) return <td key={c.symbol} />;
                      const v = d.matrice[i][j];
                      const p = d.un_anno_fa[i][j];
                      const mosso = v != null && cambiata({ ora: v, prima: p });
                      return (
                        <td key={c.symbol} className="p-0">
                          {v == null ? (
                            <span className="block h-8 w-11 text-center leading-8 text-muted-foreground">·</span>
                          ) : (
                            <Link to={url(r.symbol, c.symbol)}
                              title={`${r.name} e ${c.name}: ${numero(v, 2)}${p != null ? ` (un anno fa ${numero(p, 2)})` : ""}`}
                              className={cn("block h-8 w-11 text-center leading-8 hover:ring-1 hover:ring-ring", tintaCorrelazione(v),
                                mosso && "font-bold underline decoration-dotted")}>
                              {numero(v, 2)}
                            </Link>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        Correlazione dei rendimenti giornalieri sulle ultime {d?.sedute ?? sedute} sedute comuni a ogni coppia. In grassetto
        sottolineato le coppie che si sono spostate di almeno 0,3 in un anno. Fra borse in fusi diversi è sottostimata: chiudono
        in ore diverse.
      </p>
    </section>
  );
}

function ElencoCoppie({ d, nome }: { d: Correlazioni; nome: (s: string) => string }) {
  const tutte = coppie(d.simboli.map((s) => s.symbol), d.matrice, d.un_anno_fa);
  const sezione = (titolo: string, righe: typeof tutte) => (
    <div>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{titolo}</h3>
      <ul className="space-y-1">
        {righe.map((c) => (
          <li key={`${c.a}-${c.b}`}>
            <Link to={url(c.a, c.b)} className="flex items-center justify-between gap-2 text-sm">
              <span className="min-w-0 truncate">{nome(c.a)} · {nome(c.b)}</span>
              <span className={cn("shrink-0 rounded px-1.5 tabular-nums", tintaCorrelazione(c.ora))}>{numero(c.ora, 2)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
  return (
    <div className="space-y-3">
      {sezione("Si muovono insieme", tutte.slice(0, 6))}
      {sezione("Si muovono al contrario", [...tutte].reverse().slice(0, 6))}
    </div>
  );
}
