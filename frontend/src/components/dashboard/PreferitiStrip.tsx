import { History, Star } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { LiveQuote } from "@/api/types";
import { useLiveQuotes } from "@/hooks/useLiveQuote";
import { usePreferiti } from "@/hooks/usePreferiti";
import { formatMoney } from "@/lib/money";
import { leggiRecenti } from "@/lib/titoliRecenti";
import { cn } from "@/lib/utils";

/* ─── Preferiti e recenti, in cima alla home (FA-112) ─────────────────────
 *
 * Accorcia il gesto piu' frequente dell'app: aprire un titolo, ~16 volte al
 * giorno. Prima si passava dalla ricerca o dalle liste del cruscotto.
 *
 * ⚠️ UNA riga che scorre di lato, di altezza fissa, e non una griglia che va a
 * capo. Il numero dei preferiti si sa solo quando la lista arriva: una griglia
 * crescerebbe di una riga a dati arrivati e spingerebbe giu' tutta la pagina —
 * il difetto chiuso con FA-106. Qui arrivano i valori, la forma c'e' gia'.
 */

const RECENTI_IN_STRISCIA = 5;

function Variazione({ pct }: { pct: number | null | undefined }) {
  if (pct == null || !Number.isFinite(pct)) return null;
  return (
    <span
      className={cn(
        "tabular-nums",
        pct > 0 ? "text-emerald-800 dark:text-emerald-400"
          : pct < 0 ? "text-rose-600 dark:text-rose-400"
            : "text-muted-foreground",
      )}
    >
      {pct > 0 ? "+" : ""}{pct.toFixed(2)}%
    </span>
  );
}

const PASTIGLIA =
  "inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md border " +
  "border-border/60 bg-card px-2.5 text-xs transition-colors hover:bg-muted";

export function PreferitiStrip() {
  const lista = usePreferiti();
  // Letti al montaggio: la pagina titolo li aggiorna, e tornando qui la home
  // si rimonta.
  const [recenti] = useState(leggiRecenti);
  const preferiti = lista.data ?? [];
  const tickers = preferiti.map((p) => p.ticker);
  const quotes = useLiveQuotes(tickers, tickers.length > 0);
  const perTicker = new Map<string, LiveQuote>(
    (quotes.data?.quotes ?? []).map((q) => [q.ticker, q]),
  );
  // ⚠️ Solo a lista arrivata: prima un preferito comparirebbe fra i recenti,
  // perche' una lista ancora vuota non esclude niente, e poi salterebbe fra i
  // preferiti. Trovato dal test, non a occhio.
  const listaArrivata = lista.data !== undefined || lista.isError;
  const altriRecenti = listaArrivata
    ? recenti.filter((t) => !tickers.includes(t)).slice(0, RECENTI_IN_STRISCIA)
    : [];

  return (
    <nav
      aria-label="Preferiti e titoli recenti"
      className="flex h-11 items-center gap-2 overflow-x-auto px-1"
    >
      <span className="inline-flex shrink-0 items-center gap-1 text-[0.6765rem] font-semibold uppercase tracking-wider text-muted-foreground">
        <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-700 dark:fill-amber-300 dark:text-amber-300" aria-hidden />
        Preferiti
      </span>
      {lista.isLoading ? (
        <span className="h-8 w-40 shrink-0 animate-pulse rounded-md bg-muted/60" aria-hidden />
      ) : preferiti.length === 0 ? (
        <span className="shrink-0 text-xs text-muted-foreground">
          {lista.isError ? "non disponibili" : "aggiungili con la stella nella pagina di un titolo"}
        </span>
      ) : (
        preferiti.map((p) => {
          const q = perTicker.get(p.ticker);
          return (
            <Link key={p.ticker} to={`/stocks/${encodeURIComponent(p.ticker)}`} className={PASTIGLIA}>
              <span className="font-semibold">{p.ticker}</span>
              {q?.price != null && (
                <span className="tabular-nums text-foreground/80">
                  {formatMoney(q.price, p.currency ?? q.currency)}
                </span>
              )}
              <Variazione pct={q?.change_pct} />
            </Link>
          );
        })
      )}
      {altriRecenti.length > 0 && (
        <>
          <span className="mx-1 h-5 w-px shrink-0 bg-border" aria-hidden />
          <span className="inline-flex shrink-0 items-center gap-1 text-[0.6765rem] font-semibold uppercase tracking-wider text-muted-foreground">
            <History className="h-3.5 w-3.5" aria-hidden />
            Recenti
          </span>
          {altriRecenti.map((t) => (
            <Link key={t} to={`/stocks/${encodeURIComponent(t)}`} className={PASTIGLIA}>
              <span className="font-medium">{t}</span>
            </Link>
          ))}
        </>
      )}
    </nav>
  );
}
