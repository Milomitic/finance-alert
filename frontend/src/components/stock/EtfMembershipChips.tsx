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
