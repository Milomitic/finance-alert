import { CalendarClock, Users } from "lucide-react";
import { Link } from "react-router-dom";

import type { PariRiga, Reazione } from "@/api/titoloConfronti";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { usePari, useReazioni } from "@/hooks/useTitoloConfronti";
import { capCompatta, numero, percentuale, toneDiRendimento } from "@/lib/confronti";
import { cn } from "@/lib/utils";

/* ─── Il titolo a confronto (FA-156) ─────────────────────────────────────
 *
 * Due domande accanto ai fondamentali, fuori dalla loro riga perche' quella
 * scheda fissa l'altezza della riga (CLAUDE.md):
 *
 * - com'e' messo rispetto ai titoli simili: stessa industria, capitalizzazione
 *   in dollari piu' vicina;
 * - quanto si e' mosso alle trimestrali passate: la misura del rischio che la
 *   prossima data porta. Non una previsione, e lo dice. */

// `whitespace-nowrap`: «177 B» andava a capo dentro la cella (richiesta del
// 2026-11-22, da telefono). La tabella scorre di lato invece di spezzare.
const CELLA = "whitespace-nowrap py-1.5 pr-3 text-right tabular-nums";

function RigaPari({ r, mia }: { r: PariRiga; mia: boolean }) {
  return (
    <tr className={cn("border-b last:border-0", mia && "bg-muted/40 font-semibold")}>
      <td className="whitespace-nowrap py-1.5 pr-3">
        {mia ? r.ticker : (
          <Link to={`/stocks/${encodeURIComponent(r.ticker)}`} className="hover:underline">{r.ticker}</Link>
        )}
        <span className="ml-1 hidden text-xs font-normal text-muted-foreground sm:inline">{r.nome}</span>
      </td>
      <td className={CELLA}>{capCompatta(r.cap_usd)}</td>
      <td className={CELLA}>{numero(r.qualita, 0)}</td>
      <td className={CELLA}>{numero(r.tecnico, 0)}</td>
      <td className={CELLA}>{numero(r.pe, 1)}</td>
      <td className={CELLA}>{numero(r.pe_forward, 1)}</td>
      {/* I ricavi colorati come i rendimenti: verde se crescono, rosso se calano. */}
      <td className={cn(CELLA, toneDiRendimento(r.crescita_ricavi))}>{percentuale(r.crescita_ricavi)}</td>
      <td className={cn(CELLA, toneDiRendimento(r.rendimento_3m))}>{percentuale(r.rendimento_3m)}</td>
    </tr>
  );
}

function Pari({ ticker }: { ticker: string }) {
  const q = usePari(ticker);
  if (q.isError) return <QueryError message="dei titoli simili" errore={q.error} onRetry={q.refetch} isRetrying={q.isFetching} />;
  if (!q.data) return <div className="h-48 animate-pulse rounded-md bg-muted/40" aria-hidden />;
  const { righe, base, gruppo } = q.data;
  if (righe.length <= 1) {
    return <p className="text-xs text-muted-foreground">Nessun titolo simile nel catalogo.</p>;
  }
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">
        Stessa {base} ({gruppo}), capitalizzazione in dollari più vicina.
        {base === "settore" && " L'industria ha meno di tre titoli nel catalogo."}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="py-1.5 pr-3 font-medium">Titolo</th>
              <th className="py-1.5 pr-3 text-right font-medium">Cap. $</th>
              <th className="py-1.5 pr-3 text-right font-medium">Qualità</th>
              <th className="py-1.5 pr-3 text-right font-medium">Tecnico</th>
              <th className="whitespace-nowrap py-1.5 pr-3 text-right font-medium">P/E</th>
              <th className="whitespace-nowrap py-1.5 pr-3 text-right font-medium">P/E fwd</th>
              <th className="py-1.5 pr-3 text-right font-medium">Ricavi</th>
              <th className="py-1.5 pr-3 text-right font-medium">3 mesi</th>
            </tr>
          </thead>
          <tbody>
            {righe.map((r, i) => <RigaPari key={r.ticker} r={r} mia={i === 0} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RigaReazione({ r }: { r: Reazione }) {
  return (
    <tr className="border-b last:border-0">
      <td className="py-1.5 pr-3 tabular-nums">
        {r.data}
        <span className="ml-1 text-xs text-muted-foreground">
          {r.quando === "pre" ? "prima apertura" : r.quando === "after" ? "dopo chiusura" : r.due_sedute ? "ora ignota, 2 sedute" : ""}
        </span>
      </td>
      <td className={CELLA}>{r.sorpresa_pct == null ? "—" : `${r.sorpresa_pct > 0 ? "+" : ""}${r.sorpresa_pct.toFixed(1)}%`}</td>
      <td className={cn(CELLA, toneDiRendimento(r.reazione_pct))}>{percentuale(r.reazione_pct)}</td>
      <td className={cn(CELLA, toneDiRendimento(r.cinque_sedute_pct))}>{percentuale(r.cinque_sedute_pct)}</td>
    </tr>
  );
}

function Reazioni({ ticker }: { ticker: string }) {
  const q = useReazioni(ticker);
  if (q.isError) return <QueryError message="delle reazioni alle trimestrali" errore={q.error} onRetry={q.refetch} isRetrying={q.isFetching} />;
  if (!q.data) return <div className="h-48 animate-pulse rounded-md bg-muted/40" aria-hidden />;
  const { righe, mediana_assoluta_pct } = q.data;
  if (righe.length === 0) {
    return <p className="text-xs text-muted-foreground">Nessuna trimestrale passata con l'utile riportato.</p>;
  }
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">
        Movimento tipico alla trimestrale: {percentuale(mediana_assoluta_pct)} in una seduta, in valore
        assoluto. Quanto rischio porta la data, non una previsione del verso.
      </p>
      <div className="max-h-56 overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="py-1.5 pr-3 font-medium">Trimestrale</th>
              <th className="py-1.5 pr-3 text-right font-medium">Sorpresa</th>
              <th className="py-1.5 pr-3 text-right font-medium">Seduta</th>
              <th className="py-1.5 pr-3 text-right font-medium">5 sedute</th>
            </tr>
          </thead>
          <tbody>
            {righe.map((r) => <RigaReazione key={r.data} r={r} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ConfrontiTitoloCard({ ticker }: { ticker: string }) {
  return (
    <Card className="min-h-[18rem]">
      <CardContent className="grid gap-4 p-4 lg:grid-cols-[3fr_2fr] [&>*]:min-w-0">
        <div className="space-y-2">
          <SectionTitle icon={Users} label="Titoli simili" />
          <Pari ticker={ticker} />
        </div>
        <div className="space-y-2">
          <SectionTitle icon={CalendarClock} label="Reazioni alle trimestrali" />
          <Reazioni ticker={ticker} />
          <Link to={`/studio?simbolo=${encodeURIComponent(ticker)}&modello=evento`}
            className="inline-block text-xs font-semibold underline-offset-2 hover:underline">
            Studia il percorso attorno alle trimestrali
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
