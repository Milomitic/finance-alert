import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import { coloreDirezione } from "@/lib/coloriGrafico";
import { numero, percentuale } from "@/lib/numeri";

/* ─── Il contesto di mercato (FA-188) ─────────────────────────────────────
 *
 * VIX, curva dei tassi, Fed e BCE, ampiezza dell'universo, dollaro. Ogni
 * tessera dice il valore, da dove veniva un mese fa e, quando la storia lo
 * permette, a quale percentile sta col suo periodo scritto. Nessun colore
 * «buono/cattivo»: un percentile e' un'etichetta. Descrive, non prevede. */

export interface TesseraContesto {
  chiave: string;
  nome: string;
  valore: number;
  unita: string;
  prima: number | null;
  variazione_relativa: number | null;
  percentile: number | null;
  percentile_dal: string | null;
  serie: number[];
  data: string | null;
  nota: string | null;
  simbolo: string | null;
}

export interface Contesto {
  tessere: TesseraContesto[];
}

function livello(v: number, unita: string): string {
  return `${numero(v, 2, true)}${unita}`;
}

function anno(iso: string | null): string {
  return iso ? iso.slice(0, 4) : "";
}

function Linea({ serie }: { serie: number[] }) {
  if (serie.length < 2) return null;
  const min = Math.min(...serie);
  const max = Math.max(...serie);
  const span = max - min || 1;
  const punti = serie.map((v, i) => `${(i / (serie.length - 1)) * 100},${22 - ((v - min) / span) * 20}`).join(" ");
  return (
    <svg viewBox="0 0 100 24" preserveAspectRatio="none" className="h-6 w-full" aria-hidden>
      <polyline points={punti} fill="none" stroke={coloreDirezione(serie[serie.length - 1] - serie[0])}
        strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Tessera({ t }: { t: TesseraContesto }) {
  const corpo = (
    <>
      <dt className="text-[0.7059rem] uppercase leading-tight tracking-wider text-muted-foreground">{t.nome}</dt>
      <dd className="text-xl font-bold tabular-nums leading-tight">{livello(t.valore, t.unita)}</dd>
      <dd className="text-[0.7059rem] leading-tight text-muted-foreground">
        {t.prima != null && (t.variazione_relativa != null
          ? `in un mese ${percentuale(t.variazione_relativa * 100, 1)}`
          : `un mese fa ${livello(t.prima, t.unita)}`)}
      </dd>
      <dd><Linea serie={t.serie} /></dd>
      <dd className="text-[0.7059rem] leading-tight text-muted-foreground">
        {t.percentile != null
          ? `al ${Math.round(t.percentile)}° percentile dal ${anno(t.percentile_dal)}`
          : t.nota ?? ""}
      </dd>
      {t.percentile != null && t.nota && <dd className="text-[0.7059rem] leading-tight text-muted-foreground">{t.nota}</dd>}
    </>
  );
  return t.simbolo ? (
    <Link to={`/markets/${encodeURIComponent(t.simbolo)}`} className="min-w-0 rounded-md bg-muted/30 px-2.5 py-2 hover:bg-muted/50">
      <dl>{corpo}</dl>
    </Link>
  ) : (
    <dl className="min-w-0 rounded-md bg-muted/30 px-2.5 py-2">{corpo}</dl>
  );
}

export function ContestoMercato() {
  const q = useQuery({
    queryKey: ["markets", "contesto"],
    queryFn: ({ signal }) => api<Contesto>("/api/markets/contesto", { signal }),
    staleTime: 10 * 60_000,
  });
  if (q.isLoading) return <div className="h-[150px] animate-pulse rounded bg-muted/30" aria-hidden />;
  if (!q.data || q.data.tessere.length === 0) return null;
  return (
    <section aria-label="Contesto di mercato" className="space-y-1">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        {q.data.tessere.map((t) => <Tessera key={t.chiave} t={t} />)}
      </div>
      <p className="text-[0.7059rem] text-muted-foreground">
        Descrive la situazione, non la prevede. Un percentile alto o basso non è un segnale.
      </p>
    </section>
  );
}
