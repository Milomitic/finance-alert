import { ChevronDown, ChevronRight, Loader2, Target } from "lucide-react";
import { useState } from "react";

import type { PlanPerfRow, PlanPerformance } from "@/api/platformHealth";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { InfoHint } from "@/components/ui/info-hint";
import { SectionTitle } from "@/components/ui/section-title";
import { usePlanPerformance } from "@/hooks/usePlanPerformance";
import { expectancyInterval, expectancyLabel, verdictTone } from "@/lib/planPerformance";
import { cn } from "@/lib/utils";

/* ─── PlanPerformancePanel — il piano avrebbe pagato? ────────────────────── *
 *
 * Il magazzino `plan_outcomes`: per ogni segnale, quale fra stop e target è
 * stato toccato PRIMA. È una domanda diversa da quella del pannello accanto,
 * e le due non vanno confuse:
 *
 *   Esiti per detector   il detector prevede la deriva a orizzonte fisso?
 *   questo               il piano mostrato a schermo avrebbe pagato?
 *
 * ⚠️ L'intestazione di ogni riga è l'ATTESA IN R, non il tasso di successo, e
 * non è una scelta estetica. TP1 sta a R:R fino a 4,0: per costruzione questo
 * motore fa piani a bassa frequenza di vincita e alto guadagno unitario,
 * quindi un tasso letto da solo sembrerebbe pessimo mentre il sistema guadagna
 * — un 35% a 4:1 batte un 60% a 1:1. Il tasso resta a schermo, accanto e non
 * al posto.
 *
 * Collassato di default: il fetch parte alla prima apertura.
 */
export function PlanPerformancePanel() {
  const [aperto, setAperto] = useState(false);
  const q = usePlanPerformance(aperto);

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Target}
          label="Piano di trade · stop contro target"
          right={
            <InfoHint
              label="Piano di trade"
              text={
                "Per ogni segnale con un piano, quale fra stop e target è stato toccato per primo. " +
                "Risponde a «il piano avrebbe pagato», che è una domanda diversa da «il detector " +
                "prevede la deriva»: un trade può chiudersi in guadagno al target e finire " +
                "l'orizzonte sotto il prezzo d'ingresso, e viceversa."
              }
            />
          }
        />

        <Button
          variant="ghost"
          size="sm"
          className="mt-2 w-full justify-start gap-2 px-2"
          onClick={() => setAperto((v) => !v)}
          aria-expanded={aperto}
        >
          {aperto ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {aperto ? "Nascondi" : "Mostra"}
        </Button>

        {aperto && (
          <div className="mt-3">
            {q.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Calcolo in corso…
              </div>
            ) : q.isError ? (
              /* `red` e non `rose`: qui è un GUASTO, non una direzione di
                 mercato. È la regola di palette del progetto — rose/emerald
                 dicono su/giù, red/green dicono rotto/a posto. */
              <div className="py-6 text-center text-sm text-red-700 dark:text-red-400">
                Non è stato possibile leggere il magazzino dei piani.
              </div>
            ) : q.data ? (
              <Contenuto dati={q.data} />
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Contenuto({ dati }: { dati: PlanPerformance }) {
  const { meta, rows } = dati;

  if (meta.rows === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Nessun esito di piano ancora maturato. Una riga nasce quando il prezzo tocca
        lo stop o il target, quindi le prime compaiono entro pochi giorni dai segnali
        con un piano.
      </p>
    );
  }

  const scoperti = meta.coverage.filter((c) => c.without_plan > 0);

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {meta.rows} esiti su {meta.detectors_present} detector
        {meta.date_range.from && ` · dal ${meta.date_range.from} al ${meta.date_range.to}`}
        {meta.reconstructed > 0 && ` · ${meta.reconstructed} con livello ricostruito`}
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="py-2 pr-3 font-medium">Detector</th>
              <th className="py-2 pr-3 text-right font-medium">
                Attesa
                <InfoHint label="Attesa" text="Il guadagno medio in multipli di R (R = la distanza dello stop). È l'unico numero che aggrega: un tasso di successo del 35% con target a 4:1 batte un 60% a 1:1." />
              </th>
              <th className="py-2 pr-3 text-right font-medium">
                Campione
                <InfoHint label="Campione" text="Righe, e fra parentesi le FINESTRE INDIPENDENTI. Due segnali a tre giorni di distanza etichettati a 21 sedute condividono quasi tutta la finestra: non sono due osservazioni." />
              </th>
              <th className="py-2 pr-3 text-right font-medium">Esiti</th>
              <th className="py-2 text-right font-medium">
                Stop stretto
                <InfoHint label="Stop stretto" text="Quante volte lo stop è stato colpito PRIMA di un target che poi è arrivato lo stesso. Quei trade avevano ragione e lo stop era nel posto sbagliato." />
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Riga key={r.detector} r={r} />
            ))}
          </tbody>
        </table>
      </div>

      {scoperti.length > 0 && (
        <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Copertura</p>
          <p className="mt-1">
            Questi detector hanno alert SENZA un piano, quindi non compaiono nella
            tabella o vi compaiono solo in parte. Senza questa nota la classifica
            sembrerebbe completa.
          </p>
          <ul className="mt-2 space-y-0.5">
            {scoperti.slice(0, 8).map((c) => (
              <li key={c.detector} className="flex flex-wrap justify-between gap-2">
                <span className="min-w-0 break-words">{c.detector}</span>
                <span className="shrink-0 tabular-nums">
                  {c.with_plan}/{c.alerts} con piano
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Riga({ r }: { r: PlanPerfRow }) {
  const tono = verdictTone(r.verdict);

  return (
    <tr className="border-b last:border-0">
      <td className="py-2 pr-3">
        <span className="break-words">{r.detector}</span>
        <span className="ml-1 text-xs text-muted-foreground">{r.horizon_days}s</span>
      </td>
      <td className={cn("py-2 pr-3 text-right tabular-nums", tono)}>
        {expectancyLabel(r)}
        <div className="text-xs font-normal text-muted-foreground">
          {expectancyInterval(r)}
        </div>
      </td>
      <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">
        {r.n}
        <span className="text-xs"> ({r.effective_n})</span>
        <div className="text-xs">{r.win_rate.toFixed(0)}% al target</div>
      </td>
      <td className="py-2 pr-3 text-right text-xs tabular-nums text-muted-foreground">
        {r.esiti.tp1 ?? 0}·{r.esiti.stop ?? 0}·{r.esiti.ambigua ?? 0}·{r.esiti.scaduto ?? 0}
        <div className="text-[10px]">tp·stop·amb·scad</div>
      </td>
      <td className="py-2 text-right tabular-nums text-muted-foreground">
        {r.stop_too_tight}
      </td>
    </tr>
  );
}
