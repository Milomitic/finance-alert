import { Layers } from "lucide-react";
import { Link } from "react-router-dom";

/* I fondi che tengono questo titolo fra le posizioni piu' grandi.
 *
 * E' il verso inverso della vista "Componenti ETF": quella parte da un ETF e
 * mostra cosa contiene, questa parte da un'azione e dice chi la contiene. Il
 * dato esce dalla stessa cache, invertita.
 *
 * PERCHE' LA FORMULAZIONE E' "TRA I PRIMI" E NON "DENTRO". La cache tiene 25
 * posizioni per fondo. SPY ne ha 503: il duecentesimo titolo dell'indice non
 * comparirebbe mai qui, ed e' corretto cosi'. Ma vuol dire che l'ASSENZA di
 * una chip SPY significa "non e' fra i suoi pesi massimi", MAI "non e'
 * nell'S&P 500". Scrivere "in SPY" renderebbe l'app affermativa su una cosa
 * che non ha misurato — lo stesso difetto di un numero sbagliato.
 *
 * L'icona separa queste chip da quelle accanto (borsa, settore), che sono
 * appartenenze piene e non "fra i primi N". */
export function EtfMembershipChips({
  ticker,
  funds,
}: {
  ticker: string;
  funds: string[] | undefined;
}) {
  if (!funds?.length) return null;

  return (
    <>
      {funds.map((fund) => (
        <Link
          key={fund}
          to={`/stocks/${encodeURIComponent(fund)}`}
          title={`${ticker} è fra le 25 posizioni più grandi di ${fund} — apri ${fund}`}
          className="inline-flex items-center gap-1.5 rounded-md bg-muted/70 dark:bg-muted/40 hover:bg-muted px-2.5 py-1 text-sm font-medium transition-colors"
        >
          <Layers className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
          {fund}
        </Link>
      ))}
    </>
  );
}

/* ─── La stessa informazione, in EVIDENZA ─────────────────────────────────
 *
 * Le chip dei fondi stavano nella fila di borsa, settore e indici, alla
 * stessa taglia: si leggevano come un'etichetta in piu' e non come la notizia
 * che sono — «questo titolo muove quei fondi». L'utente l'aveva chiesto in
 * evidenza; ora e' una fascia propria, con un titolo che dice la misura.
 *
 * ⚠️ Il titolo dice «fra le prime 25 posizioni» e non «componente di», per la
 * stessa ragione scritta sopra: la cache tiene 25 posizioni per fondo, quindi
 * la fascia afferma solo cio' che ha misurato. E l'ASSENZA della fascia non
 * vuol dire «in nessun ETF»: vuol dire che nessun fondo in cache lo tiene fra
 * i suoi pesi massimi.
 */
export function EtfMembershipStrip({
  ticker,
  funds,
}: {
  ticker: string;
  funds: string[] | undefined;
}) {
  if (!funds?.length) return null;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary/[0.06] px-3 py-2">
      <span className="inline-flex shrink-0 items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-foreground/85">
        <Layers className="h-4 w-4 shrink-0" aria-hidden />
        Fra le prime 25 posizioni di {funds.length} ETF
      </span>
      <EtfMembershipChips ticker={ticker} funds={funds} />
    </div>
  );
}
