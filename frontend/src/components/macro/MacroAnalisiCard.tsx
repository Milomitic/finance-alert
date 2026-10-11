import { Activity, BarChart3, Flame, Link2, Mountain, Timer } from "lucide-react";
import type { ReactNode } from "react";

import type { MacroAnalisi } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InfoHint } from "@/components/ui/info-hint";
import { formatMacroValue } from "@/lib/macroFormat";
import { cn } from "@/lib/utils";
import { forzaCorrelazione, formatVariazioneMacro, tonoEsito, tonoVariazione } from "@/lib/variazioneMacro";

/* ─── Numeri e correlazioni di un indicatore macro (2026-10-11) ────────────
 *
 * Tutto calcolato dai dati che l'app ha gia' (`macro_analisi_service`): le
 * osservazioni FRED, le date dei rilasci passati, le barre dello SPY.
 *
 * ⚠️ Ogni tessera porta il suo CAMPIONE. Quaranta mesi e sedici rilasci sono
 * pochi, e un numero senza il suo n si legge come piu' solido di quanto e'.
 * Dove i dati non bastano la tessera lo dice invece di sparire: il riquadro
 * non cambia forma da un indicatore all'altro.
 */

function data(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("it-IT", { month: "short", year: "numeric" });
}

function Tessera({ icona: Icona, titolo, spiegazione, children, sotto }: {
  icona: typeof Activity;
  titolo: string;
  spiegazione: string;
  children: ReactNode;
  sotto?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-lg border border-border/60 bg-muted/20 p-3">
      <div className="flex items-center gap-1.5 text-[0.6765rem] font-semibold uppercase tracking-wider text-muted-foreground">
        <Icona className="h-3.5 w-3.5 shrink-0" aria-hidden />
        <span className="truncate">{titolo}</span>
        <InfoHint label={titolo} text={spiegazione} />
      </div>
      <div className="text-lg font-bold leading-tight tabular-nums">{children}</div>
      {sotto && <div className="text-xs leading-snug text-muted-foreground">{sotto}</div>}
    </div>
  );
}

function nonBasta(motivo: string) {
  return <span className="text-sm font-normal italic text-muted-foreground">{motivo}</span>;
}

export function MacroAnalisiCard({ a, unita, valueKind, sourceScale, esitoUltima = null }: {
  a: MacroAnalisi;
  unita: string;
  valueKind: string;
  sourceScale: string | null;
  /** L'esito dell'ultimo rilascio contro la sua stima: colora l'ultima
   *  variazione. Le statistiche (media, ritmo, serie) restano senza colore:
   *  non hanno una stima contro cui leggersi, e il segno non e' un giudizio. */
  esitoUltima?: string | null;
}) {
  const v = (x: number | null | undefined) => formatVariazioneMacro(x, unita);
  const percentile = a.percentile != null ? Math.round(a.percentile) : null;
  const rapporto = a.reazione_rilascio != null && a.reazione_altri ? a.reazione_rilascio / a.reazione_altri : null;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Numeri e correlazioni</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Tessera
          icona={Activity}
          titolo="Ultima variazione"
          spiegazione="La variazione dell'ultimo periodo confrontata con tutte quelle della storia disponibile. Lo z-score dice di quante deviazioni standard si scosta dalla media: oltre ±2 è un periodo insolito."
          sotto={a.zscore != null
            ? <>z-score {a.zscore >= 0 ? "+" : ""}{a.zscore.toFixed(1)} · più alta del {percentile}% dei periodi</>
            : `Servono almeno 12 variazioni per confrontarla (ne abbiamo ${a.n_variazioni ?? 0}).`}
        >
          <span className={tonoEsito(esitoUltima)}>{v(a.ultima)}</span>
        </Tessera>

        <Tessera
          icona={BarChart3}
          titolo="Variazione tipica"
          spiegazione="La media delle variazioni di ogni periodo e la loro deviazione standard, cioè di quanto si scostano di solito dalla media."
          sotto={a.media != null ? `su ${a.n_variazioni} periodi` : undefined}
        >
          {a.media != null && a.dev_std != null
            ? <>{v(a.media)}{" "}
                <span className="text-sm font-normal text-muted-foreground">± {formatVariazioneMacro(a.dev_std, unita).replace(/^\+/, "")}</span></>
            : nonBasta("Storia troppo corta")}
        </Tessera>

        <Tessera
          icona={Timer}
          titolo="Ritmo degli ultimi 3 mesi"
          spiegazione="La crescita degli ultimi tre mesi riportata a un anno. Più alta della variazione annua vuol dire che la tendenza sta accelerando, più bassa che sta rallentando."
          sotto={a.annualizzata_3m != null ? "annualizzato" : "Solo per le serie mensili di indici e livelli."}
        >
          {a.annualizzata_3m != null
            ? formatVariazioneMacro(a.annualizzata_3m, "%", 1)
            : nonBasta("Non applicabile")}
        </Tessera>

        <Tessera
          icona={Flame}
          titolo="Di fila"
          spiegazione="Quanti periodi consecutivi la variazione è andata nello stesso verso, fino all'ultimo."
          sotto={a.serie ? `${Math.abs(a.serie)} ${Math.abs(a.serie) === 1 ? "periodo" : "periodi"} consecutivi` : undefined}
        >
          {a.serie
            ? <>{a.serie > 0 ? "▲" : "▼"} {Math.abs(a.serie)} {a.serie > 0 ? "rialzi" : "ribassi"}</>
            : nonBasta("Nessuna serie in corso")}
        </Tessera>

        <Tessera
          icona={Mountain}
          titolo="Massimo e minimo"
          spiegazione="Il valore più alto e più basso della storia disponibile, con il periodo in cui è stato toccato."
          sotto={a.minimo != null ? <>minimo {formatMacroValue(a.minimo, valueKind, sourceScale)} · {data(a.minimo_il)}</> : undefined}
        >
          {a.massimo != null
            ? <>{formatMacroValue(a.massimo, valueKind, sourceScale)} <span className="text-sm font-normal text-muted-foreground">{data(a.massimo_il)}</span></>
            : nonBasta("—")}
        </Tessera>

        <Tessera
          icona={Activity}
          titolo="S&P 500 nel giorno del rilascio"
          spiegazione="Il movimento medio dello SPY, in valore assoluto da chiusura a chiusura, nei giorni in cui questo dato è uscito, contro gli altri giorni dello stesso periodo. Si usa il valore assoluto perché un dato sopra o sotto le attese muove il mercato in versi opposti: la media col segno si annullerebbe."
          sotto={a.reazione_n != null
            ? <>contro ±{a.reazione_altri?.toFixed(1)}% negli altri giorni · {a.reazione_n} rilasci</>
            : "Servono almeno 6 rilasci passati in giorni di seduta."}
        >
          {a.reazione_rilascio != null && rapporto != null
            ? <>±{a.reazione_rilascio.toFixed(1)}%{" "}
                <span className={cn("text-sm", rapporto >= 1.2 ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground")}>
                  ×{rapporto.toFixed(1)}
                </span></>
            : nonBasta("Dati insufficienti")}
          {a.reazione_ultimi && a.reazione_ultimi.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[0.7059rem] font-normal">
              {a.reazione_ultimi.slice().reverse().map((g) => (
                <span key={g.data} className="tabular-nums">
                  <span className="text-muted-foreground">
                    {new Date(`${g.data}T12:00:00Z`).toLocaleDateString("it-IT", { day: "numeric", month: "short" })}
                  </span>{" "}
                  <span className={tonoVariazione(g.rendimento)}>{formatVariazioneMacro(g.rendimento, "%", 1)}</span>
                </span>
              ))}
            </div>
          )}
        </Tessera>

        <Tessera
          icona={Link2}
          titolo="Correlazione con l'S&P 500"
          spiegazione="La correlazione fra la variazione del mese e il rendimento dello SPY nello stesso mese (r di Pearson, da −1 a +1). È contemporanea, non predittiva: il dato di un mese esce il mese dopo, quindi dice se economia e borsa si sono mosse insieme, non che il dato anticipi la borsa. E una correlazione non è una causa."
          sotto={a.correlazione_n != null
            ? <>{a.correlazione_n} mesi · {data(a.correlazione_dal)} – {data(a.correlazione_al)}</>
            : "Solo per le serie mensili, con almeno 18 mesi in comune."}
        >
          {a.correlazione_r != null
            ? <>r {a.correlazione_r >= 0 ? "+" : "−"}{Math.abs(a.correlazione_r).toFixed(2)}{" "}
                <span className="text-sm font-normal text-muted-foreground">{forzaCorrelazione(a.correlazione_r)}</span></>
            : nonBasta("Non applicabile")}
        </Tessera>
      </CardContent>
    </Card>
  );
}
