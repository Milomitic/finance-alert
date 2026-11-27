import { Globe2 } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useLiveAssets, type LiveAsset } from "@/hooks/useLiveAssets";
import { coloreDirezione } from "@/lib/coloriGrafico";
import { percentuale } from "@/lib/numeri";
import { prezzoMercato } from "@/lib/prezzoMercato";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";
import { cn } from "@/lib/utils";

/* ─── Mercati: la porta degli strumenti che non sono titoli (C-55) ─────────
 *
 * Indici, materie prime e cripto avevano pagine di dettaglio complete e
 * nessun ingresso: si aprivano solo dal paniere della home. Questa pagina e'
 * l'elenco, con gli stessi dati del paniere (una richiesta sola, in cache
 * condivisa), e il dettaglio torna qui. */

const CATEGORIE: { id: LiveAsset["category"]; titolo: string }[] = [
  { id: "index", titolo: "Indici" },
  { id: "commodity", titolo: "Materie prime" },
  { id: "crypto", titolo: "Cripto" },
];


function Linea({ serie }: { serie: number[] | null }) {
  if (!serie || serie.length < 2) return <span className="inline-block w-20" aria-hidden />;
  const min = Math.min(...serie);
  const max = Math.max(...serie);
  const span = max - min || 1;
  const punti = serie.map((v, i) => `${(i / (serie.length - 1)) * 80},${20 - ((v - min) / span) * 18 - 1}`).join(" ");
  // Il colore segue la linea che si vede (primo contro ultimo), non la
  // variazione del giorno: una linea e il suo colore dicono la stessa cosa.
  return (
    <svg width="80" height="20" viewBox="0 0 80 20" className="shrink-0" aria-hidden>
      <polyline points={punti} fill="none" stroke={coloreDirezione(serie[serie.length - 1] - serie[0])} strokeWidth="1.5" />
    </svg>
  );
}

/* FA-183: la bandiera e' un'immagine, non il codice paese stampato come
 * testo («us Nasdaq…», che nella colonna stretta diventava «us…»); il nome ha
 * la riga intera e il prezzo sta SOTTO la variazione, cosi' su un telefono il
 * nome non si riduce a due lettere. Il link porta sempre allo strumento
 * (la pagina dell'indice mostra da sola il future fuori orario, FA-180). */
function Riga({ a }: { a: LiveAsset }) {
  const q = a.quote;
  const ch = q?.change_pct ?? null;
  return (
    <li>
      <Link
        to={`/markets/${encodeURIComponent(a.symbol)}`}
        className="flex items-center gap-3 rounded px-2 py-1.5 hover:bg-muted/50"
      >
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 text-sm font-semibold">
            {a.flag && (
              <img src={`/flags/${a.flag}.svg`} alt="" width={18} height={12}
                className="h-3 w-[18px] shrink-0 rounded-sm object-cover" />
            )}
            <span className="truncate">{a.name}</span>
          </span>
          <span className="block text-xs text-muted-foreground">
            {a.symbol}{a.using_futures && a.quote_symbol ? ` · future ${a.quote_symbol}` : ""}
          </span>
        </span>
        <Linea serie={a.history} />
        <span className="flex w-24 shrink-0 flex-col items-end tabular-nums">
          <span className="text-sm">{prezzoMercato(q?.price, a.category)}</span>
          <span className={cn("text-xs font-semibold", ch == null ? "text-muted-foreground" : ch >= 0 ? TESTO_SU : TESTO_GIU)}>
            {percentuale(ch)}
          </span>
        </span>
      </Link>
    </li>
  );
}

export default function MarketsPage() {
  const q = useLiveAssets();
  const assets = q.data?.assets ?? [];
  return (
    <div className="space-y-4">
      <h1 className="sr-only">Mercati</h1>
      {q.isError && (
        <QueryError message="dei mercati" errore={q.error} onRetry={() => q.refetch()} isRetrying={q.isFetching} />
      )}
      <div className="grid gap-4 lg:grid-cols-3 [&>*]:min-w-0">
        {CATEGORIE.map((c) => {
          const righe = assets.filter((a) => a.category === c.id);
          return (
            <Card key={c.id}>
              <CardContent className="p-3">
                <SectionTitle icon={Globe2} label={c.titolo} className="mb-2" />
                {q.isLoading ? (
                  <div className="h-48 animate-pulse rounded bg-muted/40" aria-hidden />
                ) : righe.length === 0 ? (
                  <p className="py-2 text-sm text-muted-foreground">Nessuno strumento.</p>
                ) : (
                  <ul className="divide-y divide-border/40">{righe.map((a) => <Riga key={a.symbol} a={a} />)}</ul>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
