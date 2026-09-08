import { Link } from "react-router-dom";

import type { IndexOption } from "@/api/types";

/* Gli indici di cui questo titolo fa parte.
 *
 * Il dato era gia' in catalogo — 813 titoli su 986 ne hanno almeno uno — e non
 * lo leggeva nessuno fuori dall'elenco dei filtri dello screener.
 *
 * A DIFFERENZA delle chip ETF accanto, qui l'appartenenza e' COMPLETA: il
 * catalogo tiene tutti i costituenti che ingerisce, non i primi venticinque.
 * Percio' l'assenza di una chip SP500 significa davvero "non e' nell'S&P 500",
 * e la formulazione puo' dire "nell'indice" senza attenuazioni. E' esattamente
 * la distinzione che le due componenti esistono per tenere separata: sembrano
 * la stessa chip e affermano cose diverse.
 *
 * Nessuna icona, come le chip di borsa e settore: sono appartenenze piene, e
 * l'icona a strati resta il segno di "solo fra i primi N". */
export function IndexMembershipChips({
  ticker,
  indices,
}: {
  ticker: string;
  indices: IndexOption[] | undefined;
}) {
  if (!indices?.length) return null;

  return (
    <>
      {indices.map((idx) => (
        <Link
          key={idx.code}
          to={`/stocks?index=${encodeURIComponent(idx.code)}`}
          title={`${ticker} fa parte di ${idx.name} — vedi i titoli dell'indice`}
          className="inline-flex items-center rounded-md bg-muted/70 dark:bg-muted/40 hover:bg-muted px-2.5 py-1 text-sm font-medium transition-colors"
        >
          {idx.code}
        </Link>
      ))}
    </>
  );
}
