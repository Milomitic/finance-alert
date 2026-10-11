import { ArrowLeft, Building2, Globe2, Landmark, Shield, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import {
  PicksCard,
  SortableStocksTable,
} from "@/components/sectors/SectorDetailTables";
import {
  DistributionCard,
  IndustryBreakdownCard,
  PillarAveragesCard,
  ScoreDistributionCard,
} from "@/components/sectors/SectorDistributionCards";
import {
  AmpiezzaCard,
  AndamentoCard,
  SegnaliSettoreCard,
  TrainaFrenaCard,
} from "@/components/sectors/SectorPerformance";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useSectorDetail } from "@/hooks/useSectorDetail";
import { fmtNum } from "@/lib/format";
import { getSectorIcon, getSectorIconColor, getSectorTone } from "@/lib/sectorMeta";
import { formatRendimento, quota, tonoRendimento, variazioneUltimoGiorno } from "@/lib/sectorPerformance";
import { cn } from "@/lib/utils";

/* Sector recap page — route /sectors/:name.

   Riassetto del 2026-10-11. La pagina apriva su otto tessere di fondamentali
   mediani e non diceva una cosa sola su come il settore si fosse MOSSO. Ora,
   dall'alto:

     1. Intestazione: nome, quante aziende, l'ETF settoriale, e quattro numeri
        che rispondono a «come sta andando»: l'ultima seduta, l'anno contro
        l'S&P 500, la partecipazione, i due punteggi medi.
     2. Andamento (grafico + rendimenti su sei finestre) accanto all'Ampiezza.
     3. Chi traina e chi frena nel mese, e i segnali del motore.
     4. Punteggi e fondamentali mediani in una scheda sola, poi le
        distribuzioni, i migliori e i peggiori per punteggio, la tabella.

   I blocchi vivono in components/sectors/*; questo file li dispone. L'andamento
   puo' mancare (barre insufficienti, calcolo fallito): la pagina resta quella
   di prima, senza buchi.
*/

function Numero({ etichetta, children, sotto }: { etichetta: string; children: ReactNode; sotto?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-lg border border-border/60 bg-muted/20 px-3 py-2">
      <div className="truncate text-[0.6765rem] font-semibold uppercase tracking-wider text-muted-foreground">
        {etichetta}
      </div>
      <div className="mt-0.5 text-xl font-bold leading-tight tabular-nums">{children}</div>
      {sotto && <div className="truncate text-xs text-muted-foreground">{sotto}</div>}
    </div>
  );
}

function Valore({ etichetta, valore, nota }: { etichetta: string; valore: string; nota?: string }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-xs text-muted-foreground">{etichetta}</dt>
      <dd className="text-base font-semibold tabular-nums">{valore}</dd>
      {nota && <dd className="truncate text-[0.7059rem] text-muted-foreground">{nota}</dd>}
    </div>
  );
}

export default function SectorDetailPage() {
  const { name = "" } = useParams<{ name: string }>();
  const decoded = decodeURIComponent(name);
  const q = useSectorDetail(decoded);

  // `getSectorIcon` is a lookup into a module-level Record<string, LucideIcon>,
  // so this reference is one of a fixed set of components — stable across
  // renders, not created during one. `react-hooks/static-components` sees a
  // capitalized local const used as JSX and cannot prove where it came from;
  // the disable is at the usage below, where the rule reports.
  const Icon = getSectorIcon(decoded);
  const iconColor = getSectorIconColor(decoded);

  if (q.isLoading) {
    // Lo scheletro rispecchia la pagina: intestazione, andamento e ampiezza,
    // le due schede sotto, la tabella.
    return (
      <div className="p-4 sm:p-6 space-y-4 max-w-[1400px] mx-auto">
        <CardSkeleton rows={3} className="h-[190px]" />
        <div className="grid gap-4 lg:grid-cols-3 [&>*]:min-w-0">
          <CardSkeleton rows={8} className="h-[480px] lg:col-span-2" />
          <CardSkeleton rows={6} className="h-[480px]" />
        </div>
        <CardSkeleton label="TUTTE LE AZIENDE" rows={12} strongHeader className="h-[500px]" />
      </div>
    );
  }
  if (q.isError || !q.data) {
    return (
      <div className="p-8">
        <Link to="/sectors" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:underline">
          <ArrowLeft className="h-4 w-4" /> Settori
        </Link>
        <div className="mt-4">
          {q.isError ? (
            // A genuine fetch failure is retryable — don't mislabel it "not found".
            <QueryError message={`del settore ${decoded}`} onRetry={q.refetch} isRetrying={q.isFetching} />
          ) : (
            <div className="text-red-600">Settore non trovato: {decoded}</div>
          )}
        </div>
      </div>
    );
  }

  const d = q.data;
  const a = d.andamento ?? null;
  const r = (k: string) => a?.rendimenti.find((x) => x.finestra === k) ?? null;
  const anno = r("1a");
  const ultimoGiorno = a ? variazioneUltimoGiorno(a.serie) : null;
  const p200 = a ? quota(a.sopra_ema200) : null;
  const industrie = d.kpis.industry_breakdown.filter((b) => !b.label.startsWith("(")).length;
  const scartoAnno = anno?.settore != null && anno?.spy != null ? anno.settore - anno.spy : null;

  return (
    <div className="p-4 sm:p-6 space-y-4 max-w-[1400px] mx-auto">
      {/* ─── Intestazione ─────────────────────────────────────────────── */}
      <Card>
        <CardContent className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <span className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border", getSectorTone(decoded))}>
                {/* eslint-disable-next-line react-hooks/static-components -- lookup, not a component created during render; see the const above */}
                <Icon className={cn("h-6 w-6", iconColor)} strokeWidth={1.75} />
              </span>
              <div className="min-w-0">
                <Link to="/sectors" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                  <ArrowLeft className="h-3.5 w-3.5" /> Settori
                </Link>
                <h1 className="text-2xl font-semibold leading-tight sm:text-3xl">{decoded}</h1>
                <div className="flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
                  <span>{d.kpis.stock_count} aziende</span>
                  {industrie > 0 && <span>· {industrie} industrie</span>}
                  {a?.etf_ticker && (
                    <span>
                      · ETF{" "}
                      <Link to={`/stocks/${encodeURIComponent(a.etf_ticker)}`} className="font-medium text-primary hover:underline">
                        {a.etf_ticker}
                      </Link>
                    </span>
                  )}
                </div>
              </div>
            </div>
            {/* Funnel verso lo screener: pre-filtra /stocks sul settore
                corrente (il param del browser stock è proprio `sector`). */}
            <Link
              to={`/stocks?sector=${encodeURIComponent(decoded)}`}
              className="inline-flex min-h-[40px] items-center gap-2 rounded-md border px-3 py-1.5 text-sm hover:bg-accent transition-colors"
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden />
              Apri nello screener
            </Link>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
            <Numero etichetta="Ultima seduta" sotto={a ? `${a.in_rialzo.n} su ${a.in_rialzo.su} in rialzo` : undefined}>
              <span className={tonoRendimento(ultimoGiorno)}>{formatRendimento(ultimoGiorno)}</span>
            </Numero>
            <Numero
              etichetta="Un anno"
              sotto={scartoAnno != null
                ? <span className={tonoRendimento(scartoAnno)}>{formatRendimento(scartoAnno).replace("%", "")} pp contro l'S&P 500</span>
                : undefined}
            >
              <span className={tonoRendimento(anno?.settore)}>{formatRendimento(anno?.settore)}</span>
            </Numero>
            <Numero etichetta="Sopra la media a 200" sotto={a ? `${a.sopra_ema200.n} su ${a.sopra_ema200.su} titoli` : undefined}>
              {p200 == null ? "—" : `${p200}%`}
            </Numero>
            <Numero
              etichetta="Qualità · Tecnico"
              sotto={d.kpis.technical_count > 0 ? `medie, tecnico su ${d.kpis.technical_count} titoli` : "medie"}
            >
              {fmtNum(d.kpis.avg_composite, 0)}
              <span className="mx-1 text-muted-foreground">·</span>
              {fmtNum(d.kpis.avg_technical, 0)}
            </Numero>
          </div>
        </CardContent>
      </Card>

      {/* ─── Andamento e ampiezza ─────────────────────────────────────── */}
      {a && (
        <div className="grid gap-4 lg:grid-cols-3 [&>*]:min-w-0">
          <div className="lg:col-span-2">
            <AndamentoCard a={a} nTitoli={d.kpis.stock_count} />
          </div>
          <AmpiezzaCard a={a} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
        <TrainaFrenaCard rows={d.stocks} />
        {d.segnali && <SegnaliSettoreCard s={d.segnali} />}
      </div>

      {/* ─── Punteggi e fondamentali ──────────────────────────────────── */}
      <Card>
        <CardContent className="p-4">
          <SectionTitle icon={Landmark} label="Punteggi e fondamentali mediani" className="mb-3" />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4 lg:grid-cols-8">
            <Valore etichetta="Qualità media" valore={fmtNum(d.kpis.avg_composite, 1)} />
            <Valore etichetta="Qualità mediana" valore={fmtNum(d.kpis.median_composite, 1)} />
            <Valore
              etichetta="Tecnico medio"
              valore={fmtNum(d.kpis.avg_technical, 1)}
              nota={d.kpis.technical_count > 0 ? `su ${d.kpis.technical_count} titoli` : undefined}
            />
            <Valore etichetta="P/E" valore={fmtNum(d.kpis.median_pe, 1)} />
            <Valore etichetta="P/B" valore={fmtNum(d.kpis.median_pb, 2)} />
            <Valore etichetta="ROE" valore={fmtNum(d.kpis.median_roe, 1, "%")} />
            <Valore etichetta="Crescita ricavi" valore={fmtNum(d.kpis.median_revenue_growth, 1, "%")} />
            <Valore etichetta="Dividendo" valore={fmtNum(d.kpis.median_dividend_yield, 2, "%")} />
          </dl>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 [&>*]:min-w-0">
        <ScoreDistributionCard distribution={d.kpis.score_distribution} />
        <PillarAveragesCard pa={d.kpis.pillar_averages} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 [&>*]:min-w-0">
        <IndustryBreakdownCard buckets={d.kpis.industry_breakdown} total={d.kpis.stock_count} />
        <DistributionCard
          title="Distribuzione paesi"
          buckets={d.kpis.country_distribution}
          total={d.kpis.stock_count}
          palette="blue"
          icon={Globe2}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 [&>*]:min-w-0">
        <DistributionCard
          title="Risk tier"
          buckets={d.kpis.risk_distribution}
          total={d.kpis.stock_count}
          palette="risk"
          icon={Shield}
        />
        <DistributionCard
          title="Capitalizzazione"
          buckets={d.kpis.market_cap_distribution}
          total={d.kpis.stock_count}
          palette="amber"
          preserveOrder
          icon={Building2}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 [&>*]:min-w-0">
        <PicksCard title="Top 5 per score composito" rows={d.top_picks} accent="green" />
        <PicksCard
          title="Bottom 5 per score composito"
          rows={d.bottom_picks}
          accent="red"
        />
      </div>

      <SortableStocksTable rows={d.stocks} />
    </div>
  );
}
