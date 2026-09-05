import { Loader2, TrendingUp } from "lucide-react";

import type { DetectorPerfCell, DetectorPerfRow } from "@/api/platformHealth";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useDetectorPerformance } from "@/hooks/useDetectorPerformance";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* Efficacia dei segnali, letta dal magazzino degli esiti.
 *
 * Questo pannello leggeva un replay separato di ohlcv_daily che riportava il
 * solo hit ASSOLUTO su finestre 1/5/20 giorni, in verde grassetto sopra il
 * 55%. Due difetti sovrapposti:
 *
 *   - L'hit assoluto contiene il beta. `sr_flip` bull dava 57,9% assoluto e
 *     51,5% market-neutral sul magazzino vero: sei di quei punti erano
 *     semplicemente l'essere long mentre il mercato saliva.
 *   - Il numero di righe non e' la dimensione del campione. Con una finestra
 *     forward di 21 giorni, due segnali a tre giorni di distanza condividono
 *     18/21 dell'esito; venti segnali dello stesso giorno su venti titoli
 *     condividono tutto. `macd_divergence` bull leggeva 81,8% su "n=99", che
 *     erano 34 giornate dentro un solo trimestre — circa tre finestre
 *     indipendenti.
 *
 * Quindi: skill accanto ad assoluto, finestre indipendenti accanto alle
 * righe, e un verdetto solo dove l'intervallo supera davvero la moneta. Il
 * verdetto e' una PAROLA, non un colore: un verde afferma "buono" senza
 * dirlo, e non lascia modo al lettore di sapere quanto stretto sia. */

const VERDICT: Record<string, { label: string; className: string }> = {
  above: {
    label: "sopra il mercato",
    className:
      "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  },
  below: {
    label: "sotto il mercato",
    className: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200",
  },
  inconclusive: {
    label: "non concludente",
    className: "bg-muted text-muted-foreground",
  },
};

const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${v.toFixed(1).replace(".", ",")}%`;

function Verdict({ cell }: { cell: DetectorPerfCell }) {
  const v = cell.skill_verdict ? VERDICT[cell.skill_verdict] : null;
  if (!v) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className={cn(
        "inline-block whitespace-nowrap rounded px-1.5 py-px text-[0.6765rem] font-semibold uppercase tracking-wider",
        v.className,
      )}
      title={
        cell.skill_verdict === "inconclusive"
          ? "L'intervallo di confidenza al 95% contiene il 50%: su questo campione il segnale non e' distinguibile da una moneta."
          : "L'intervallo di confidenza al 95% non contiene il 50%."
      }
    >
      {v.label}
    </span>
  );
}

export function SignalEffectivenessTable({ rows }: { rows: DetectorPerfRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        Nessun segnale maturato. Un esito nasce solo quando la sua finestra
        forward e' interamente trascorsa, quindi i segnali piu' recenti non
        compaiono ancora.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm tabular-nums">
        <thead className="border-b bg-muted/30 text-muted-foreground">
          <tr className="text-left">
            <th className="px-3 py-2 font-semibold">Segnale</th>
            <th className="px-3 py-2 text-right font-semibold" title="Esiti maturati nel magazzino.">
              Righe
            </th>
            <th
              className="px-3 py-2 text-right font-semibold"
              title="Finestre forward non sovrapposte coperte da quelle righe. E' questo il numero che decide quanto la percentuale sia affidabile."
            >
              Finestre
            </th>
            <th
              className="px-3 py-2 text-right font-semibold"
              title="Il prezzo si e' mosso nella direzione segnalata. Include il beta: in un mercato che sale, ogni segnale rialzista parte avvantaggiato."
            >
              Hit assoluto
            </th>
            <th
              className="px-3 py-2 text-right font-semibold"
              title="Ha battuto la mediana dell'universo nella propria direzione. E' la parte che non si spiega col mercato."
            >
              Skill
            </th>
            <th className="px-3 py-2 text-right font-semibold" title="Intervallo di Wilson al 95% sulla skill, dimensionato sulle finestre indipendenti.">
              Intervallo 95%
            </th>
            <th className="px-3 py-2 text-left font-semibold">Verdetto</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const c = r.total;
            const meta = getAlertKindMeta(r.detector);
            const Icon = meta.icon;
            return (
              <tr key={r.detector} className="border-b border-border/40 hover:bg-muted/30">
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-2">
                    <Icon className="h-3.5 w-3.5 shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-semibold leading-tight">{meta.label}</span>
                      <span className="block font-mono text-[0.6765rem] leading-tight text-muted-foreground">
                        {r.detector}
                        {c.horizon_days != null && (
                          <span title="Orizzonte forward: decide la lunghezza delle finestre indipendenti.">
                            {" · "}
                            {c.horizon_days}g
                          </span>
                        )}
                      </span>
                    </span>
                  </span>
                </td>
                <td className="px-3 py-2 text-right">{c.n}</td>
                <td
                  className={cn(
                    "px-3 py-2 text-right font-semibold",
                    c.effective_n != null && c.effective_n < 10 && "text-amber-700 dark:text-amber-300",
                  )}
                  title="Finestre forward indipendenti."
                >
                  {c.effective_n ?? "—"}
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">
                  {pct(c.abs_hit_rate)}
                </td>
                <td className="px-3 py-2 text-right font-semibold">
                  {pct(c.mkt_neutral_hit_rate)}
                </td>
                <td className="px-3 py-2 text-right text-[0.7059rem] text-muted-foreground">
                  {c.skill_ci_low == null || c.skill_ci_high == null
                    ? "—"
                    : `${c.skill_ci_low.toFixed(1).replace(".", ",")}–${c.skill_ci_high
                        .toFixed(1)
                        .replace(".", ",")}%`}
                </td>
                <td className="px-3 py-2">
                  <Verdict cell={c} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function SignalEffectivenessPanel() {
  const q = useDetectorPerformance();
  const rows = q.data?.detectors ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={TrendingUp}
          label="Efficacia segnali — esiti maturati"
          className="mb-1"
        />
        <p className="mb-3 max-w-3xl text-[0.7647rem] leading-snug text-muted-foreground">
          Dal magazzino <code className="font-mono">signal_outcomes</code>: un
          esito viene scritto solo quando la sua finestra forward e' gia'
          trascorsa, quindi nessuna riga qui guarda al futuro. La colonna che
          conta e' <strong>Finestre</strong> — le righe si sovrappongono, e una
          percentuale vale quanto le finestre indipendenti che ha sotto.{" "}
          <strong>Aspettati "non concludente" quasi ovunque</strong>, e non e'
          un difetto: il magazzino copre pochi mesi, e un detector a 21 giorni
          ci sta dentro tre volte. Per distinguere un vantaggio di 5 punti da
          una moneta servono centinaia di finestre indipendenti. Questa tabella
          diventa informativa con il tempo, non con altri titoli.
        </p>

        {q.isLoading ? (
          <div className="inline-flex w-full items-center justify-center gap-2 py-8 text-center text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Lettura del magazzino…
          </div>
        ) : q.isError ? (
          <div className="py-8">
            <QueryError
              message="degli esiti maturati"
              onRetry={q.refetch}
              isRetrying={q.isFetching}
            />
          </div>
        ) : (
          <SignalEffectivenessTable rows={rows} />
        )}
      </CardContent>
    </Card>
  );
}
