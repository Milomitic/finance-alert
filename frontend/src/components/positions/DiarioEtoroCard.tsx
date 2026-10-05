import { BookOpen } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { EtoroGruppo, EtoroOperazione } from "@/api/etoro";
import { Card, CardContent } from "@/components/ui/card";
import { InfoHint } from "@/components/ui/info-hint";
import { SectionTitle } from "@/components/ui/section-title";
import { useEtoroDiario } from "@/hooks/useEtoro";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { fmtPct } from "@/lib/etoroPortafoglio";
import { formatMoneyGrouped, formatMoneyGroupedSigned } from "@/lib/money";
import { cn } from "@/lib/utils";

/* ─── Il diario delle operazioni eToro (FA-128) ───────────────────────────
 *
 * Le operazioni chiuse dei 12 mesi che eToro conserva, e per ognuna il
 * segnale dell'app che l'ha PRECEDUTA, se c'e', con l'esito vero in R contro
 * quello del piano. In fondo alla pagina Posizioni: arriva con una chiamata
 * sua, e da qui non sposta niente quando arriva (FA-106).
 *
 * ⚠️ «Preceduta da», mai «aperta per»: lo stesso titolo, lo stesso verso,
 * nei cinque giorni prima. E' una coincidenza temporale, e il diario non
 * pretende di sapere perche' un'operazione e' stata aperta.
 */

const RIGHE = 15;

function tono(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-muted-foreground";
  return v > 0 ? "text-emerald-800 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
}

function giorno(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

const USD = (v: number | null | undefined) => formatMoneyGroupedSigned(v ?? null, "USD");

function Tessera({ etichetta, valore, sotto, className }: {
  etichetta: string; valore: React.ReactNode; sotto?: React.ReactNode; className?: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border/60 px-2.5 py-1.5">
      <div className="truncate text-[0.6471rem] font-semibold uppercase tracking-wider text-muted-foreground">{etichetta}</div>
      <div className={cn("truncate text-sm font-semibold tabular-nums", className)}>{valore}</div>
      {sotto && <div className="truncate text-[0.6471rem] text-muted-foreground tabular-nums">{sotto}</div>}
    </div>
  );
}

function confronto(g: EtoroGruppo | null): string {
  if (!g || g.n === 0) return "nessuna";
  const tasso = g.vincenti_pct == null ? "" : ` · ${g.vincenti_pct.toFixed(0)}% in utile`;
  return `${g.n} · ${USD(g.profitto_usd)}${tasso}`;
}

function Riga({ o, onApriSegnale }: { o: EtoroOperazione; onApriSegnale: (id: number) => void }) {
  const nome = o.ticker ?? o.simbolo ?? `#${o.instrument_id}`;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5 text-xs">
      <span className="w-16 shrink-0 tabular-nums text-muted-foreground">{giorno(o.chiusa_il)}</span>
      {o.ticker ? (
        <Link to={`/stocks/${encodeURIComponent(o.ticker)}`} className="w-16 shrink-0 truncate font-semibold hover:underline">{nome}</Link>
      ) : (
        <span className="w-16 shrink-0 truncate font-semibold">{nome}</span>
      )}
      <span className="shrink-0 text-muted-foreground">
        {o.lato === "long" ? "Long" : "Short"} ×{o.leva}
        {o.giorni != null && ` · ${o.giorni < 1 ? "<1" : Math.round(o.giorni)} g`}
      </span>
      {o.alert_id != null ? (
        <button
          type="button"
          onClick={() => onApriSegnale(o.alert_id!)}
          className="min-w-0 truncate rounded border border-border/60 px-1.5 py-0.5 text-[0.6765rem] hover:bg-muted"
          title="Il segnale dell'app nato nei 5 giorni prima, sullo stesso titolo e nello stesso verso"
        >
          dopo {getAlertKindMeta(`signal:${o.detector}`).short}
          {o.r_reale != null && ` · ${o.r_reale >= 0 ? "+" : ""}${o.r_reale.toFixed(1)} R`}
          {o.r_piano != null && ` (piano ${o.r_piano >= 0 ? "+" : ""}${o.r_piano.toFixed(1)} R)`}
        </button>
      ) : (
        <span className="text-[0.6765rem] text-muted-foreground">senza segnale</span>
      )}
      <span className={cn("ml-auto shrink-0 font-semibold tabular-nums", tono(o.profitto_netto_usd))}>
        {USD(o.profitto_netto_usd)}
        {o.pct_investimento != null && <span className="text-[0.6765rem]"> ({fmtPct(o.pct_investimento)})</span>}
      </span>
    </li>
  );
}

export function DiarioEtoroCard({ onApriSegnale }: { onApriSegnale: (id: number) => void }) {
  const q = useEtoroDiario();
  const [tutte, setTutte] = useState(false);
  const d = q.data;
  if (!d || !d.tutte) return null;
  const operazioni = tutte ? d.operazioni : d.operazioni.slice(0, RIGHE);
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <SectionTitle
          icon={BookOpen}
          label="Diario eToro · 12 mesi"
          right={<span className="text-xs text-muted-foreground tabular-nums">{d.tutte.n} operazioni chiuse</span>}
        />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Tessera etichetta="Realizzato" valore={USD(d.tutte.profitto_usd)} className={tono(d.tutte.profitto_usd)} />
          <Tessera
            etichetta="In utile"
            valore={d.tutte.vincenti_pct == null ? "—" : `${d.tutte.vincenti_pct.toFixed(0)}%`}
            sotto={`${d.tutte.vincenti} su ${d.tutte.n}`}
          />
          <Tessera etichetta="Medio per operazione" valore={USD(d.tutte.profitto_medio_usd)} className={tono(d.tutte.profitto_medio_usd)} />
          <Tessera
            etichetta="R reale contro piano"
            valore={d.r_reale_medio == null ? "—" : `${d.r_reale_medio >= 0 ? "+" : ""}${d.r_reale_medio.toFixed(2)} R`}
            sotto={d.r_piano_medio == null ? "nessun piano confrontabile" : `piano ${d.r_piano_medio >= 0 ? "+" : ""}${d.r_piano_medio.toFixed(2)} R · su ${d.con_r}`}
          />
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
          <span>
            Precedute da un segnale: <span className="font-semibold text-foreground">{confronto(d.precedute)}</span>
          </span>
          <span>
            Senza segnale: <span className="font-semibold text-foreground">{confronto(d.non_precedute)}</span>
          </span>
          <InfoHint
            label="Come si lega un'operazione a un segnale"
            text="Un segnale dell'app sullo stesso titolo e nello stesso verso, nato nei 5 giorni prima dell'apertura. È una coincidenza nel tempo, non la prova che l'operazione sia stata aperta per quel segnale. Con poche operazioni i tassi sono indicativi; sotto le due operazioni non si mostrano."
          />
        </div>

        {d.anni.length > 0 && (
          <div>
            <div className="mb-1 flex items-center gap-1 text-[0.6471rem] font-semibold uppercase tracking-wider text-muted-foreground">
              Realizzato per anno
              <InfoHint
                label="Il realizzato in euro"
                text="Ogni operazione convertita al cambio EUR/USD del giorno di chiusura. È una somma da passare a chi fa la dichiarazione, non una consulenza fiscale: le regole le decide lui. Se manca il cambio di un giorno, l'euro non si mostra invece di sommare una parte."
              />
            </div>
            <ul className="divide-y divide-border/40 text-xs tabular-nums">
              {d.anni.map((a) => (
                <li key={a.anno} className="flex flex-wrap items-baseline gap-x-4 py-1">
                  <span className="w-10 font-semibold">{a.anno}</span>
                  <span className="text-muted-foreground">{a.n} operazioni</span>
                  <span className={cn("font-semibold", tono(a.profitto_usd))}>{USD(a.profitto_usd)}</span>
                  <span className="text-muted-foreground">
                    {a.profitto_eur == null ? "in euro: cambio non disponibile" : `≈ ${formatMoneyGroupedSigned(a.profitto_eur, "EUR")}`}
                  </span>
                  <span className="ml-auto text-muted-foreground">commissioni {formatMoneyGrouped(a.commissioni_usd, "USD")}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <ul className="divide-y divide-border/40">
          {operazioni.map((o) => <Riga key={o.position_id} o={o} onApriSegnale={onApriSegnale} />)}
        </ul>
        {d.operazioni.length > RIGHE && (
          <button type="button" onClick={() => setTutte(!tutte)} className="text-xs underline">
            {tutte ? "Mostra le ultime 15" : `Mostra tutte e ${d.operazioni.length}`}
          </button>
        )}
      </CardContent>
    </Card>
  );
}
