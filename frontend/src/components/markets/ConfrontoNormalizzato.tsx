import { X } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { GraficoSvg } from "@/components/ui/grafico-svg";
import { Segmentato } from "@/components/ui/segmentato";
import { PERIODI_CONFRONTO, type PeriodoConfronto, useConfronto } from "@/hooks/useMercati";
import { CATEGORICA } from "@/lib/coloriGrafico";
import { conConfronto, ETICHETTA_PERIODO, MAX_CONFRONTO, periodoDaUrl, simboliDaUrl } from "@/lib/confronto";
import { numero, percentuale } from "@/lib/numeri";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";
import { cn } from "@/lib/utils";

/* ─── Il confronto fra mercati e titoli, in base 100 (FA-187) ─────────────
 *
 * «L'oro ha fatto meglio del Nasdaq quest'anno?» Ogni linea parte da 100 lo
 * stesso giorno; sotto, il rendimento del periodo e il peggior calo lungo la
 * strada. Accetta anche titoli del catalogo. Lo stato sta nell'URL. */

function dataCorta(iso: string): string {
  const [a, m, g] = iso.split("-");
  return `${Number(g)}/${Number(m)}/${a.slice(2)}`;
}

export function ConfrontoNormalizzato({ nomi }: { nomi: Record<string, string> }) {
  const [sp, setSp] = useSearchParams();
  const simboli = simboliDaUrl(sp);
  const periodo = periodoDaUrl(sp);
  const [nuovo, setNuovo] = useState("");
  const q = useConfronto(simboli, periodo);
  const imposta = (s: string[], p: PeriodoConfronto) => setSp(conConfronto(sp, s, p), { replace: true });

  const aggiungi = (e: FormEvent) => {
    e.preventDefault();
    const s = nuovo.trim().toUpperCase();
    if (s && !simboli.includes(s) && simboli.length < MAX_CONFRONTO) imposta([...simboli, s], periodo);
    setNuovo("");
  };

  const d = q.data;
  const righe = d ? d.date.map((g, i) => ({ g, ...Object.fromEntries(simboli.map((s) => [s, d.serie[s]?.[i] ?? null])) })) : [];
  const sconosciuto = q.error instanceof ApiError && q.error.status === 404 ? q.error.message : null;
  const disponibili = Object.keys(nomi).filter((s) => !simboli.includes(s));

  return (
    <section id="confronto" className="space-y-3" aria-label="Confronto fra mercati">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Confronto, in base 100</h2>
        <Segmentato etichetta="Periodo del confronto" valore={periodo} onCambia={(p) => imposta(simboli, p)}
          voci={PERIODI_CONFRONTO.map((p) => ({ id: p, label: ETICHETTA_PERIODO[p] }))} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {simboli.map((s, i) => (
          <span key={s} className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs">
            <span className="h-2 w-2 rounded-full" style={{ background: CATEGORICA[i % CATEGORICA.length] }} aria-hidden />
            {nomi[s] ?? s}
            <button type="button" aria-label={`Togli ${nomi[s] ?? s} dal confronto`} className="text-muted-foreground hover:text-foreground"
              onClick={() => imposta(simboli.filter((x) => x !== s), periodo)}>
              <X className="h-3 w-3" aria-hidden />
            </button>
          </span>
        ))}
        {simboli.length < MAX_CONFRONTO && (
          <>
            {disponibili.length > 0 && (
              <select aria-label="Aggiungi un mercato" className="h-7 rounded-md border bg-background px-1 text-xs" value=""
                onChange={(e) => e.target.value && imposta([...simboli, e.target.value], periodo)}>
                <option value="">+ mercato</option>
                {disponibili.map((s) => <option key={s} value={s}>{nomi[s]}</option>)}
              </select>
            )}
            <form onSubmit={aggiungi} className="flex items-center gap-1">
              <input aria-label="Aggiungi un titolo (es. AAPL)" placeholder="+ titolo" value={nuovo}
                onChange={(e) => setNuovo(e.target.value)}
                className="h-7 w-20 rounded-md border bg-background px-1.5 text-xs uppercase" />
              <Button type="submit" size="sm" variant="outline" className="h-7 px-2 text-xs">Aggiungi</Button>
            </form>
          </>
        )}
      </div>

      {sconosciuto ? (
        <p className="text-sm text-muted-foreground">{sconosciuto}: togli quel simbolo per vedere il confronto.</p>
      ) : simboli.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aggiungi almeno un mercato o un titolo.</p>
      ) : !d ? (
        <div className="h-[220px] animate-pulse rounded bg-muted/40 sm:h-[280px]" aria-hidden />
      ) : (
        <>
          <div className="h-[220px] sm:h-[280px]">
            <GraficoSvg dati={righe} x={(r) => r.g as string} formatoX={dataCorta} formatoY={(v) => numero(v, 0)}
              riferimenti={[{ y: 100, tratteggio: "2 2" }]}
              etichetta={`Confronto in base 100 dal ${d.dal ? dataCorta(d.dal) : ""}: ${simboli.map((s) => nomi[s] ?? s).join(", ")}`}
              serie={simboli.map((s, i) => ({
                chiave: s, nome: nomi[s] ?? s, valore: (r: Record<string, unknown>) => r[s] as number | null,
                colore: CATEGORICA[i % CATEGORICA.length], spessore: 1.75,
              }))} />
          </div>
          <ul className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {simboli.map((s, i) => {
              const r = d.riepilogo[s];
              return (
                <li key={s} className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: CATEGORICA[i % CATEGORICA.length] }} aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{nomi[s] ?? s}</span>
                  <span className={cn("font-semibold tabular-nums", r && (r.rendimento >= 0 ? TESTO_SU : TESTO_GIU))}>
                    {r ? percentuale(r.rendimento * 100, 1) : "—"}
                  </span>
                  <span className="w-24 text-right text-xs tabular-nums text-muted-foreground" title="Peggior calo nel periodo">
                    {r ? `calo ${percentuale(r.peggior_calo * 100, 1)}` : ""}
                  </span>
                </li>
              );
            })}
          </ul>
          {d.dal && (
            <p className="text-xs text-muted-foreground">
              Dal {dataCorta(d.dal)} al {d.al ? dataCorta(d.al) : ""}, prima data in cui tutti hanno una chiusura. Nei giorni in cui un mercato è chiuso
              resta all&apos;ultima chiusura.
            </p>
          )}
        </>
      )}
    </section>
  );
}
