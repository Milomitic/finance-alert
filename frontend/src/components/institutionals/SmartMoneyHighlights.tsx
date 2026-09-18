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
}

function trimestreBreve(s: string | null | undefined): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  if (!y || !m || !d) return s;
  return `${d}/${m}/${y.slice(2)}`;
}

/** Una mossa. Due righe strette: sopra CHI e QUANTO, sotto il contesto — il
 *  fondo che l'ha fatta, il peso in portafoglio e il trimestre. */
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
    <li className="border-b border-border/40 py-1 last:border-b-0">
      <div className="flex min-w-0 items-center gap-2">
        <StockLogo ticker={row.ticker} size="xs" />
        <Link
          to={`/stocks/${encodeURIComponent(row.ticker)}`}
          className="shrink-0 text-sm font-bold tabular-nums hover:underline"
        >
          {row.ticker}
        </Link>
        <span
          className={cn(
            "shrink-0 rounded px-1 text-[0.6471rem] font-bold uppercase tracking-wide",
            pastiglia,
          )}
        >
          {etichetta}
        </span>
        <span className="min-w-0 flex-1 truncate text-[0.7059rem] text-muted-foreground">
          {row.company_name}
        </span>
        <span
          className="shrink-0 text-sm font-semibold tabular-nums"
          title={
            row.qoq_change_pct != null
              ? `Variazione della posizione sul trimestre: ${row.qoq_change_pct.toFixed(1)}%`
              : "Variazione sul trimestre non disponibile"
          }
        >
          {fmtBig(row.value_usd)}
        </span>
      </div>
      <div className="flex min-w-0 items-baseline gap-1.5 pl-7 text-[0.7059rem] text-muted-foreground">
        <Link
          to={`/institutionals/${row.institutional_slug}`}
          className="min-w-0 truncate hover:underline"
          title={row.institutional_name}
        >
          {row.institutional_name}
        </Link>
        {row.portfolio_pct != null && (
          <span className="shrink-0 tabular-nums" title="Peso della posizione nel portafoglio del fondo">
            · {row.portfolio_pct.toFixed(1)}% ptf
          </span>
        )}
        <span className="shrink-0 tabular-nums">· {trimestreBreve(row.period_end_date)}</span>
      </div>
    </li>
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
    ? "text-emerald-800 dark:text-emerald-300"
    : "text-rose-700 dark:text-rose-300";
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
        /* ⚠️ role + tabIndex + aria-label: un contenitore che scorre e non puo'
           ricevere il fuoco non e' raggiungibile da tastiera, e cio' che sta
           oltre il taglio non esiste per chi non usa il mouse. Il gate UI
           l'aveva gia' trovato sulle schede che questa fascia sostituisce. */
        <ul
          role="region"
          aria-label={`${titolo} piu' rilevanti dei fondi tracciati`}
          tabIndex={0}
          className="overflow-y-auto"
          style={{ maxHeight: `${righeVisibili * 2.9}rem` }}
        >
          {righe.map((row, i) => (
            <Mossa key={`${row.ticker}-${row.institutional_slug}-${i}`} row={row} kind={kind} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function SmartMoneyHighlights({ agg, fondi, righeVisibili = 6 }: Props) {
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
          right={
            <span className="text-[0.7059rem] text-muted-foreground">
              dall'ultima dichiarazione di ogni fondo
            </span>
          }
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

        <div className="grid gap-x-4 gap-y-3 md:grid-cols-2 [&>*]:min-w-0">
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
