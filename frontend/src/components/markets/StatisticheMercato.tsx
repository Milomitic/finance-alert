import type { Calo, Statistiche } from "@/hooks/useMercati";
import { percentuale } from "@/lib/numeri";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";
import { cn } from "@/lib/utils";

/* ─── Statistiche di un mercato (FA-185) ──────────────────────────────────
 *
 * Al posto del riquadro «Meta» (bar nel chart, range attivo): cio' che si
 * chiede a un indice. Tutto alla chiusura giornaliera che dichiara; la
 * variazione di oggi sta nella testata. Altezza fissa per il gate CLS. */

function pp(v: number | null | undefined, decimali = 1): string {
  return v == null ? "—" : percentuale(v * 100, decimali);
}

function data(iso: string | null | undefined): string {
  if (!iso) return "";
  const [a, m, g] = iso.split("-");
  return `${Number(g)}/${Number(m)}/${a}`;
}

function Tessera({ nome, valore, sotto, tono }: { nome: string; valore: string; sotto?: string; tono?: "su" | "giu" }) {
  return (
    <div className="min-w-0 rounded-md bg-muted/30 px-2.5 py-2">
      <dt className="text-[0.7059rem] uppercase leading-tight tracking-wider text-muted-foreground">{nome}</dt>
      <dd className={cn("text-lg font-bold tabular-nums leading-tight", tono === "su" && TESTO_SU, tono === "giu" && TESTO_GIU)}>
        {valore}
      </dd>
      {sotto && <dd className="text-[0.7059rem] leading-tight text-muted-foreground">{sotto}</dd>}
    </div>
  );
}

function tono(v: number | null | undefined): "su" | "giu" | undefined {
  return v == null || v === 0 ? undefined : v > 0 ? "su" : "giu";
}

function frasCalo(c: Calo | null): string | undefined {
  if (!c || !c.picco) return undefined;
  return c.recupero ? `${data(c.picco)} → ${data(c.minimo)}, recuperato` : `${data(c.picco)} → ${data(c.minimo)}, non recuperato`;
}

export function StatisticheMercato({ s }: { s: Statistiche }) {
  const r = s.rendimenti;
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-[0.7059rem] font-semibold uppercase tracking-wider text-muted-foreground">Statistiche</h2>
        <span className="text-[0.7059rem] text-muted-foreground">alla chiusura del {data(s.data_chiusura)} · storia dal {data(s.dal)}</span>
      </div>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-2 2xl:grid-cols-3">
        <Tessera nome="Da inizio anno" valore={pp(r.ytd)} tono={tono(r.ytd)} />
        <Tessera nome="Un anno" valore={pp(r["1a"])} tono={tono(r["1a"])} />
        <Tessera nome="5 anni, annuo" valore={pp(r["5a_ann"])} tono={tono(r["5a_ann"])} />
        <Tessera nome="Dal massimo storico" valore={pp(s.dal_massimo_storico?.distanza)}
          sotto={s.dal_massimo_storico ? `massimo il ${data(s.dal_massimo_storico.data)}` : undefined} />
        <Tessera nome="Dal massimo a 52 sett." valore={pp(s.massimo_52s?.distanza)}
          sotto={s.massimo_52s ? `il ${data(s.massimo_52s.data)}` : undefined} />
        <Tessera nome="Volatilità annua" valore={pp(s.vol_20g, 0)} sotto={`20 sedute · un anno ${pp(s.vol_1a, 0)}`} />
        <Tessera nome="Peggior calo in 5 anni" valore={pp(s.calo_massimo_5a?.profondita)} sotto={frasCalo(s.calo_massimo_5a)} />
        <Tessera nome="Peggior calo storico" valore={pp(s.calo_massimo_storico?.profondita)}
          sotto={frasCalo(s.calo_massimo_storico)} />
        <Tessera nome="Dal minimo a 52 sett." valore={pp(s.minimo_52s?.distanza)}
          sotto={s.minimo_52s ? `il ${data(s.minimo_52s.data)}` : undefined} />
      </dl>
    </div>
  );
}
