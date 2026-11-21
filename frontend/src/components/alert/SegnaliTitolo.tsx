import { Link } from "react-router-dom";

import { direzione, type SegnaliTitolo as Conteggio } from "@/lib/segnaliPerTitolo";
import { cn } from "@/lib/utils";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";

const FRECCIA = { bull: "▲", bear: "▼", misti: "◆" } as const;
const COLORE = {
  bull: TESTO_SU,
  bear: TESTO_GIU,
  misti: "text-muted-foreground",
} as const;

function etichetta(s: Conteggio): string {
  const d = direzione(s);
  const cosa = s.n === 1 ? "1 segnale vivo" : `${s.n} segnali vivi`;
  return d === "misti" ? `${cosa}, in direzioni opposte`
    : `${cosa}, ${d === "bull" ? "rialzist" : "ribassist"}${s.n === 1 ? "a" : "i"}`;
}

/** Il segnale vivo su un titolo, accanto al suo nome (FA-136).
 *
 *  `collegamento` lo rende un link alla lista dei segnali del titolo; dentro
 *  un elemento che e' gia' un link (la pastiglia di un preferito) va senza,
 *  perche' un link dentro un link non e' HTML valido e gli assistivi lo
 *  leggono male. */
export function SegnaliTitolo({
  ticker, s, collegamento = false,
}: { ticker: string; s: Conteggio | undefined; collegamento?: boolean }) {
  if (!s || s.n === 0) return null;
  const d = direzione(s);
  const testo = etichetta(s);
  const corpo = (
    <>
      <span aria-hidden>{FRECCIA[d]}</span>
      {s.n > 1 && <span aria-hidden>{s.n}</span>}
    </>
  );
  const classi = cn("inline-flex shrink-0 items-center gap-0.5 text-[0.7rem] font-semibold tabular-nums", COLORE[d]);
  if (collegamento) {
    return (
      <Link to={`/alerts?ticker=${encodeURIComponent(ticker)}`} className={cn(classi, "hover:underline")}
            aria-label={`${ticker}: ${testo}`} title={testo}>
        {corpo}
      </Link>
    );
  }
  return (
    <span className={classi} title={testo}>
      {corpo}
      <span className="sr-only">{testo}</span>
    </span>
  );
}
