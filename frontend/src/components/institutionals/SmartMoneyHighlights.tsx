import { TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import type { ActionAggregate, AggregateStats, InstitutionalSummary } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { MetricTile } from "@/components/ui/metric-tile";
import { SectionTitle } from "@/components/ui/section-title";
import { fmtBig } from "@/lib/format";
import {
  AZIONE_LABEL, azioneDecisiva, mossePiuPesanti, settoreDominante, statisticheFondi,
} from "@/lib/smartMoney";
import { cn } from "@/lib/utils";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";

/* ─── La fascia in cima a /institutionals ─────────────────────────────────── *
 *
 * Risponde alla domanda per cui si apre questa pagina: che cosa hanno fatto,
 * di recente, i soldi che vale la pena guardare. Prima bisognava scorrere fino
 * a due tabelle in mezzo alla pagina e confrontarle a mente.
 *
 * ⚠️ Questa fascia SOSTITUISCE le due schede «Acquisti recenti» e «Vendite
 * recenti»: sono gli stessi dati, con lo stesso ordinamento del server. Averle
 * in due posti sarebbe la stessa duplicazione che la striscia d'umore aveva
 * col cruscotto — due posti da tenere allineati e, il giorno che divergono,
 * nessuno sa a quale credere.
 *
 * ⚠️ Quello che questa fascia NON dice, e che sarebbe facile scriverci:
 * quanti acquisti contro quante vendite. Le due liste arrivano TAGLIATE dal
 * server (`recent_actions_limit`), quindi il loro rapporto misura il limite,
 * non il mercato.
 */

interface Props {
  agg: AggregateStats | undefined;
  fondi: InstitutionalSummary[] | undefined;
  /** Quante righe per colonna restano a schermo prima dello scorrimento. */
  righeVisibili?: number;
  trimestri?: number;
  onTrimestri?: (valore: number) => void;
}

function trimestreBreve(s: string | null | undefined): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  if (!y || !m || !d) return s;
  return `${d}/${m}/${y.slice(2)}`;
}

/** Una riga della tabella delle mosse dichiarate. */
function Mossa({ row, kind }: { row: ActionAggregate; kind: "buy" | "sell" }) {
  const decisiva = azioneDecisiva(row.action);
  const etichetta = AZIONE_LABEL[row.action ?? ""] ?? row.action ?? "—";
  /* Aprire o chiudere del tutto e' una mossa netta e la pastiglia e' piena;
   * un aumento o una riduzione sono manutenzione e restano in punta. Il colore
   * dice il VERSO (comprato/venduto), che e' l'informazione, non l'intensita'. */
  const pastiglia = decisiva
    ? kind === "buy"
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
      : "bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300"
    : kind === "buy"
      ? "border border-emerald-300 text-emerald-800 dark:border-emerald-800 dark:text-emerald-300"
      : "border border-rose-300 text-rose-700 dark:border-rose-800 dark:text-rose-300";
  return (
    <tr className="border-b border-border/40 last:border-0">
      <td className="py-1 pr-2">
        <div className="flex items-center gap-1.5">
          <StockLogo ticker={row.ticker} size="xs" />
          <div className="min-w-0">
            <Link to={`/stocks/${encodeURIComponent(row.ticker)}`} className="font-bold hover:underline">{row.ticker}</Link>
            <span className="block truncate text-muted-foreground" title={row.company_name ?? undefined}>{row.company_name}</span>
          </div>
        </div>
      </td>
      <td className="pr-2"><Link to={`/institutionals/${row.institutional_slug}`}
        className="block truncate hover:underline" title={row.institutional_name}>{row.institutional_name}</Link></td>
      <td><span className={cn("rounded px-1 text-[0.6471rem] font-bold uppercase", pastiglia)}>{etichetta}</span></td>
      <td className="text-right font-semibold tabular-nums" title={row.qoq_change_pct != null
        ? `Variazione trimestrale: ${row.qoq_change_pct.toFixed(1)}%` : undefined}>{fmtBig(row.value_usd)}</td>
      <td className="text-right tabular-nums">{row.portfolio_pct != null ? `${row.portfolio_pct.toFixed(1)}%` : "—"}</td>
      <td className="pl-2 text-right tabular-nums">{trimestreBreve(row.period_end_date)}</td>
    </tr>
  );
}

function ColonnaMosse({
  titolo, righe, kind, righeVisibili,
}: {
  titolo: string;
  righe: ActionAggregate[];
  kind: "buy" | "sell";
  righeVisibili: number;
}) {
  const Icona = kind === "buy" ? TrendingUp : TrendingDown;
  const tono = kind === "buy"
    ? TESTO_SU
    : TESTO_GIU;
  return (
    <div className="min-w-0">
      <div className={cn("mb-1 flex items-center gap-1.5 text-[0.7059rem] font-bold uppercase tracking-[0.14em]", tono)}>
        <Icona className="h-3.5 w-3.5" aria-hidden />
        {titolo}
      </div>
      {righe.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Nessuna mossa di questo tipo nelle ultime dichiarazioni.
        </p>
      ) : (
        <div
          role="region"
          aria-label={`${titolo} piu' rilevanti dei fondi tracciati`}
          tabIndex={0}
          className="max-w-full overflow-auto"
          style={{ maxHeight: `${righeVisibili * 2.9}rem` }}
        >
          <table aria-label={titolo} className="w-full min-w-[34rem] table-fixed text-left text-xs">
            <colgroup>
              <col className="w-[17%]" /><col className="w-[25%]" /><col className="w-[14%]" />
              <col className="w-[18%]" /><col className="w-[11%]" /><col className="w-[15%]" />
            </colgroup>
            <thead className="sticky top-0 bg-card text-muted-foreground">
              <tr><th scope="col">Titolo</th><th scope="col">Fondo</th><th scope="col">Azione</th>
                <th scope="col" className="text-right">Valore pos.</th><th scope="col" className="text-right">Peso</th>
                <th scope="col" className="text-right">Data 13F</th></tr>
            </thead>
            <tbody>{righe.map((row, i) => (
              <Mossa key={`${row.ticker}-${row.institutional_slug}-${row.period_end_date}-${i}`} row={row} kind={kind} />
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function SmartMoneyHighlights({ agg, fondi, righeVisibili = 6, trimestri = 0, onTrimestri }: Props) {
  const stat = statisticheFondi(fondi);
  const settore = settoreDominante(agg?.sector_tilt);
  const piuPosseduto = agg?.most_picked?.[0] ?? null;
  const acquisti = mossePiuPesanti(agg?.recent_buys, 15);
  const vendite = mossePiuPesanti(agg?.recent_sells, 15);

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle
          icon={TrendingUp}
          label="Le mosse che contano"
          className="mb-2"

        />

        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5 [&>*]:min-w-0">
          <MetricTile
            label="Fondi tracciati"
            value={String(stat.totale)}
            hint={stat.fermi > 0 ? `${stat.fermi} fermi da oltre 2 trimestri` : "tutti aggiornati"}
            note="Un fondo e' «fermo» quando la sua ultima dichiarazione ha piu' di due trimestri: con la finestra di deposito di 45 giorni, un fondo vivo ha sempre qualcosa di piu' recente."
          />
          <MetricTile
            label="Capitale dichiarato"
            value={stat.capitale != null ? fmtBig(stat.capitale) : "n/d"}
            hint="somma degli ultimi 13F"
            note="Somma dei portafogli nell'ULTIMA dichiarazione di ciascun fondo. Non e' una fotografia a una data sola: i trimestri sono diversi da fondo a fondo."
          />
          <MetricTile
            label="Ultimo trimestre"
            value={trimestreBreve(stat.ultimoTrimestre)}
            hint={`${stat.fondiSulTrimestre} fondi su ${stat.totale} ci sono arrivati`}
            note="I 13F arrivano scaglionati fino a 45 giorni dopo la chiusura del trimestre: a una certa data alcuni fondi sono gia' sul nuovo trimestre e altri no."
          />
          <MetricTile
            label="Titolo più posseduto"
            value={piuPosseduto?.ticker ?? "n/d"}
            hint={piuPosseduto ? `${piuPosseduto.holder_count} fondi lo hanno` : undefined}
          />
          <MetricTile
            label="Settore più pesato"
            value={settore ? `${settore.quota.toFixed(0)}%` : "n/d"}
            hint={settore?.settore}
            note="Quota del capitale dichiarato che sta nel settore piu' pesante, sommando le ultime dichiarazioni di tutti i fondi."
          />
        </div>

        {onTrimestri && (
          <label className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            Periodo delle mosse
            <select className="rounded border bg-background px-2 py-1.5" value={trimestri}
              onChange={(e) => onTrimestri(Number(e.target.value))}>
              <option value={0}>Ultima dichiarazione di ogni fondo</option>
              <option value={1}>Ultimo trimestre disponibile</option>
              <option value={2}>Ultimi 2 trimestri</option>
              <option value={4}>Ultimi 4 trimestri</option>
            </select>
          </label>
        )}
        <div className="grid gap-x-4 gap-y-3 xl:grid-cols-2 [&>*]:min-w-0">
          <ColonnaMosse titolo="Comprato" righe={acquisti} kind="buy" righeVisibili={righeVisibili} />
          <ColonnaMosse titolo="Venduto" righe={vendite} kind="sell" righeVisibili={righeVisibili} />
        </div>
        {/* Il modello editoriale, una riga sola: il 13F-HR e' long-only, quindi
            «comprato» non vuol dire «lungo contro corto» — vuol dire che la
            posizione lunga e' stata aperta o aumentata. */}
        <p className="mt-2 text-[0.7059rem] text-muted-foreground">
          Ordinate per valore della posizione. Il 13F è long-only: «comprato» significa posizione
          aperta o aumentata, «venduto» ridotta o chiusa.
        </p>
      </CardContent>
    </Card>
  );
}
