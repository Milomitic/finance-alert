import type { Cali, PrimoPassaggio } from "@/api/studio";
import { GraficoSvg } from "@/components/ui/grafico-svg";
import { GIU } from "@/lib/coloriGrafico";
import { pct } from "@/lib/studio";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";
import { cn } from "@/lib/utils";

/* ─── Le domande nuove dello Studio (FA-196, FA-198) ──────────────────────
 *
 * «Toccare prima»: su finestre storiche disgiunte, cosa e' stato toccato
 * prima, con gli intervalli di Wilson. «Cali e recuperi»: i cali oltre una
 * soglia, quanto ci hanno messo a rientrare, e dove sta il calo di oggi. */

function quota(k: number | undefined, n: number | undefined): string {
  if (k == null || !n) return "—";
  return `${Math.round((k / n) * 100)}%`;
}

function iv(i: [number, number] | undefined): string {
  return i ? `da ${Math.round(i[0] * 100)}% a ${Math.round(i[1] * 100)}%` : "";
}

export function RisultatoPrimoPassaggio({ r, orizzonte }: { r: PrimoPassaggio; orizzonte: number }) {
  if (!r.disponibile) return <p className="text-sm text-muted-foreground">Non calcolabile: {r.motivo}.</p>;
  const n = r.finestre ?? 0;
  const parti = [
    { nome: "prima l'obiettivo", k: r.target ?? 0, iv: r.intervallo_target, colore: "bg-emerald-500", testo: TESTO_SU },
    { nome: "prima lo stop", k: r.stop ?? 0, iv: r.intervallo_stop, colore: "bg-rose-500", testo: TESTO_GIU },
    { nome: "nessuno dei due", k: r.nessuno ?? 0, iv: r.intervallo_nessuno, colore: "bg-muted-foreground/40", testo: "" },
  ];
  return (
    <div className="space-y-3">
      {r.verdetto === "non_concludente" && (
        <div className="rounded-md border border-amber-500/50 bg-amber-50 px-3 py-2 text-sm dark:bg-amber-950/30">
          <strong>Non concludente</strong> — {n} finestre indipendenti: ne servono almeno 20 per dire qualcosa.
        </div>
      )}
      <div className="flex h-4 overflow-hidden rounded-full" role="img"
        aria-label={parti.map((p) => `${p.nome} ${quota(p.k, n)}`).join(", ")}>
        {parti.map((p) => <div key={p.nome} className={p.colore} style={{ width: `${n ? (p.k / n) * 100 : 0}%` }} />)}
      </div>
      <ul className="grid gap-2 sm:grid-cols-3">
        {parti.map((p) => (
          <li key={p.nome} className="rounded-md bg-muted/30 px-3 py-2">
            <div className="text-xs text-muted-foreground">{p.nome}</div>
            <div className={cn("text-lg font-bold tabular-nums", p.testo)}>{quota(p.k, n)}</div>
            <div className="text-xs tabular-nums text-muted-foreground">{p.k} su {n} · {iv(p.iv)}</div>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        {n} finestre di {orizzonte} sedute che non si sovrappongono, dal {r.dal} al {r.al}; obiettivo e stop nella stessa
        seduta contano come stop. È la storia del titolo con queste distanze, non una probabilità per domani.
      </p>
    </div>
  );
}

function data(iso: string | null): string {
  if (!iso) return "—";
  const [a, m, g] = iso.split("-");
  return `${Number(g)}/${Number(m)}/${a}`;
}

export function RisultatoCali({ r }: { r: Cali }) {
  return (
    <div className="space-y-3">
      {r.corrente && (
        <p className="text-sm">
          Oggi {r.simbolo} è{" "}
          <strong className="tabular-nums">{pct(r.corrente.profondita, 1)}</strong> sotto il massimo del {data(r.corrente.picco)}
          {r.numero > 0 && (
            <>; il calo di oggi è più profondo di <strong>{r.episodi_piu_profondi_del_corrente}</strong> dei {r.numero} cali oltre il{" "}
              {r.soglia_pct}% dal {data(r.dal)}</>
          )}.
        </p>
      )}
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ["Cali oltre la soglia", String(r.numero)],
          ["Profondità tipica", pct(r.profondita_mediana, 1)],
          ["Sedute di discesa tipiche", r.sedute_discesa_mediane == null ? "—" : String(Math.round(r.sedute_discesa_mediane))],
          ["Sedute per recuperare", r.sedute_recupero_mediane == null ? "—" : `${Math.round(r.sedute_recupero_mediane)} (${r.recuperati} recuperati)`],
        ].map(([n, v]) => (
          <div key={n} className="rounded-md bg-muted/30 px-2.5 py-2">
            <dt className="text-xs text-muted-foreground">{n}</dt>
            <dd className="font-semibold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="h-[180px] sm:h-[220px]">
        <GraficoSvg dati={r.sott_acqua} x={(p) => p.data} formatoX={(d) => d.slice(0, 4)} formatoY={(v) => pct(v, 0)}
          riferimenti={[{ y: -r.soglia_pct / 100, tratteggio: "4 3", colore: GIU }]}
          bande={[{ chiave: "sotto", da: (p) => p.valore, a: () => 0, colore: GIU, opacita: 0.25 }]}
          etichetta={`Distanza di ${r.simbolo} dal massimo precedente, nel tempo`}
          serie={[{ chiave: "valore", nome: "Dal massimo", valore: (p) => p.valore, colore: GIU, spessore: 1 }]} />
      </div>
      <p className="text-xs text-muted-foreground">
        Sott&apos;acqua: quanto il prezzo era sotto il massimo raggiunto fino a quel giorno. Tratteggio: la soglia del {r.soglia_pct}%.
      </p>
      {r.episodi.length > 0 && (
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm tabular-nums">
            <thead className="sticky top-0 bg-card">
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-1 pr-2 font-medium">Massimo</th>
                <th className="py-1 pr-2 font-medium">Minimo</th>
                <th className="py-1 pr-2 text-right font-medium">Calo</th>
                <th className="py-1 pr-2 text-right font-medium">Discesa</th>
                <th className="py-1 text-right font-medium">Recupero</th>
              </tr>
            </thead>
            <tbody>
              {r.episodi.map((e) => (
                <tr key={e.picco} className="border-b last:border-0">
                  <td className="py-1 pr-2">{data(e.picco)}</td>
                  <td className="py-1 pr-2">{data(e.minimo)}</td>
                  <td className={cn("py-1 pr-2 text-right font-semibold", TESTO_GIU)}>{pct(e.profondita, 1)}</td>
                  <td className="py-1 pr-2 text-right">{e.sedute_discesa} sedute</td>
                  <td className="py-1 text-right">{e.sedute_recupero == null ? "non ancora" : `${e.sedute_recupero} sedute`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted-foreground">Descrive il passato, non lo prevede.</p>
    </div>
  );
}
