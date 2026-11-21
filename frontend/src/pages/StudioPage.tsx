import { useQuery } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { type DopoMovimento, type Evento, type Misura, type Stagionalita, studio } from "@/api/studio";
import { Card, CardContent } from "@/components/ui/card";
import { GraficoSvg } from "@/components/ui/grafico-svg";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { intervallo, MODELLI, type Modello, parametriDaUrl, pct } from "@/lib/studio";
import { cn } from "@/lib/utils";
import { GIU, SU } from "@/lib/coloriGrafico";

/* ─── Studio: statistica storica di un simbolo (FA-157) ───────────────────
 *
 * Tre domande sul passato. Ogni risposta mette accanto al numero il caso base
 * (la stessa misura su tutte le finestre) e le finestre indipendenti, perche'
 * «dopo un calo del 10% ha fatto +3%» non dice niente se in un mese qualunque
 * ha fatto +2,5%. Lo stato vive nell'URL: un link riapre lo stesso studio. */

const DOPO_MAX = 10;
const CAMPO = "h-9 rounded-md border border-input bg-background px-2 text-sm";

function RigaMisura({ nome, m }: { nome: string; m: Misura }) {
  return (
    <tr className="border-b last:border-0">
      <td className="py-1.5 pr-3 font-medium">{nome}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums">{m.casi}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums">{m.finestre}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums">{pct(m.media, 2)}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums">{pct(m.mediana, 2)}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums">{m.quota_positivi == null ? "—" : `${Math.round(m.quota_positivi * 100)}%`}</td>
      <td className="py-1.5 text-xs text-muted-foreground">{intervallo(m)}</td>
    </tr>
  );
}

function TabellaMisure({ righe }: { righe: [string, Misura][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="py-1.5 pr-3 font-medium" />
            <th className="py-1.5 pr-3 text-right font-medium">Casi</th>
            <th className="py-1.5 pr-3 text-right font-medium">Finestre indip.</th>
            <th className="py-1.5 pr-3 text-right font-medium">Media</th>
            <th className="py-1.5 pr-3 text-right font-medium">Mediana</th>
            <th className="py-1.5 pr-3 text-right font-medium">Positivi</th>
            <th className="py-1.5 font-medium">Intervallo della media (95%)</th>
          </tr>
        </thead>
        <tbody>{righe.map(([n, m]) => <RigaMisura key={n} nome={n} m={m} />)}</tbody>
      </table>
    </div>
  );
}

function Risultato({ p }: { p: ReturnType<typeof parametriDaUrl> }) {
  const orizzonteEvento = Math.min(p.orizzonte, DOPO_MAX);
  const q = useQuery<DopoMovimento | Stagionalita | Evento>({
    queryKey: ["studio", p.modello, p.simbolo, p.sedute, p.soglia, p.orizzonte, p.tipo, p.serie],
    queryFn: ({ signal }) => {
      if (p.modello === "stagionalita") return studio.stagionalita(p.simbolo, signal);
      if (p.modello === "evento") {
        return studio.evento({ simbolo: p.simbolo, tipo: p.tipo, serie_macro: p.serie || undefined,
          orizzonte: orizzonteEvento }, signal);
      }
      return studio.dopoMovimento({ simbolo: p.simbolo, sedute: p.sedute, soglia_pct: p.soglia,
        orizzonte: p.orizzonte }, signal);
    },
    enabled: p.simbolo !== "" && (p.modello !== "evento" || p.tipo !== "macro" || p.serie !== ""),
    staleTime: 10 * 60_000,
  });
  if (p.simbolo === "") return <p className="text-sm text-muted-foreground">Scegli un simbolo per cominciare.</p>;
  if (q.isError) return <QueryError message="dello studio" onRetry={q.refetch} isRetrying={q.isFetching} />;
  if (!q.data) return <div className="h-64 animate-pulse rounded-md bg-muted/40" aria-hidden />;

  if (p.modello === "dopo_movimento") {
    const r = q.data as DopoMovimento;
    return (
      <div className="space-y-2">
        <p className="text-sm">
          {p.orizzonte} sedute dopo ogni giorno in cui {p.simbolo} si era mosso
          {p.soglia < 0 ? ` di ${p.soglia}% o peggio` : ` di +${p.soglia}% o più`} in {p.sedute} sedute.
          {" "}Differenza dalla base: <strong>{pct(r.differenza, 2)}</strong>.
        </p>
        <TabellaMisure righe={[["Dopo il movimento", r.condizione], ["Base: tutte le finestre", r.base]]} />
      </div>
    );
  }
  if (p.modello === "stagionalita") {
    const r = q.data as Stagionalita;
    return (
      <div className="space-y-4">
        <div className="h-[220px]">
          <GraficoSvg dati={r.mesi} x={(m) => m.mese} formatoY={(v) => pct(v, 1)}
            etichetta={`Rendimento medio per mese di ${p.simbolo}`}
            serie={[{ chiave: "media", nome: "Media", valore: (m) => m.media, colore: "hsl(var(--primary))", tipo: "barre",
              coloreBarra: (m) => ((m.media ?? 0) >= 0 ? SU : GIU) }]} />
        </div>
        <TabellaMisure righe={[...r.mesi.map((m) => [m.mese, m] as [string, Misura]), ["Tutti i mesi", r.base_mesi]]} />
        <TabellaMisure righe={[...r.giorni.map((g) => [g.giorno, g] as [string, Misura]), ["Tutte le sedute", r.base_giorni]]} />
      </div>
    );
  }
  const r = q.data as Evento;
  return (
    <div className="space-y-3">
      <p className="text-sm">
        {r.eventi} {p.tipo === "macro" ? `rilasci di ${p.serie}` : "trimestrali passate"}; percorso medio di {p.simbolo}
        {" "}dalla chiusura della seduta precedente.
      </p>
      {r.percorso.length > 0 && (
        <div className="h-[220px]">
          <GraficoSvg dati={r.percorso} x={(s) => (s.seduta > 0 ? `+${s.seduta}` : String(s.seduta))}
            formatoY={(v) => pct(v, 1)} riferimenti={[{ y: 0 }]}
            etichetta="Rendimento medio attorno all'evento, per seduta"
            serie={[{ chiave: "media", nome: "Media", valore: (s) => s.media, colore: "hsl(var(--primary))", spessore: 2, punti: true }]} />
        </div>
      )}
      <TabellaMisure righe={[[`A ${r.orizzonte} sedute dall'evento`, r.a_orizzonte], ["Base: tutte le finestre", r.base]]} />
      {r.tipo === "trimestrali" && r.eventi === 0 && (
        <p className="text-xs text-muted-foreground">Nessuna trimestrale passata nota: lo studio vale per i titoli del catalogo.</p>
      )}
    </div>
  );
}

export default function StudioPage() {
  const [sp, setSp] = useSearchParams();
  const p = parametriDaUrl(sp);
  const [bozza, setBozza] = useState(p);

  const imposta = (e: FormEvent) => {
    e.preventDefault();
    const n = new URLSearchParams();
    n.set("simbolo", bozza.simbolo.trim().toUpperCase());
    n.set("modello", bozza.modello);
    if (bozza.modello === "dopo_movimento") {
      n.set("sedute", String(bozza.sedute));
      n.set("soglia", String(bozza.soglia));
      n.set("orizzonte", String(bozza.orizzonte));
    }
    if (bozza.modello === "evento") {
      n.set("tipo", bozza.tipo);
      n.set("orizzonte", String(Math.min(bozza.orizzonte, DOPO_MAX)));
      if (bozza.tipo === "macro") n.set("serie", bozza.serie.trim().toUpperCase());
    }
    setSp(n);
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-3 sm:p-6">
      <h1 className="sr-only">Studio</h1>
      <Card>
        <CardContent className="space-y-3 p-4">
          <SectionTitle icon={FlaskConical} label="Studio" />
          <p className="text-xs text-muted-foreground">
            Statistica storica: che cosa è successo, non che cosa succederà. Ogni numero ha accanto il caso base e
            le finestre indipendenti.
          </p>
          <form onSubmit={imposta} className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Simbolo
              <input className={cn(CAMPO, "w-28 uppercase")} value={bozza.simbolo}
                onChange={(e) => setBozza({ ...bozza, simbolo: e.target.value })} placeholder="AAPL, ^GSPC" />
            </label>
            <div className="flex rounded-md border p-0.5" role="group" aria-label="Modello">
              {MODELLI.map((m) => (
                <button key={m.id} type="button" aria-pressed={bozza.modello === m.id}
                  onClick={() => setBozza({ ...bozza, modello: m.id as Modello })}
                  className={cn("min-h-8 rounded px-2 text-xs font-semibold",
                    bozza.modello === m.id ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>
                  {m.label}
                </button>
              ))}
            </div>
            {bozza.modello === "dopo_movimento" && (
              <>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Variazione %
                  <input type="number" className={cn(CAMPO, "w-20")} value={bozza.soglia}
                    onChange={(e) => setBozza({ ...bozza, soglia: Number(e.target.value) })} />
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  in sedute
                  <input type="number" min={1} max={63} className={cn(CAMPO, "w-16")} value={bozza.sedute}
                    onChange={(e) => setBozza({ ...bozza, sedute: Number(e.target.value) })} />
                </label>
              </>
            )}
            {bozza.modello === "evento" && (
              <>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Evento
                  <select className={CAMPO} value={bozza.tipo}
                    onChange={(e) => setBozza({ ...bozza, tipo: e.target.value as "trimestrali" | "macro" })}>
                    <option value="trimestrali">Trimestrali del titolo</option>
                    <option value="macro">Rilasci macro</option>
                  </select>
                </label>
                {bozza.tipo === "macro" && (
                  <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                    Serie FRED
                    <input className={cn(CAMPO, "w-28 uppercase")} value={bozza.serie}
                      onChange={(e) => setBozza({ ...bozza, serie: e.target.value })} placeholder="CPIAUCSL" />
                  </label>
                )}
              </>
            )}
            {bozza.modello !== "stagionalita" && (
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                Orizzonte (sedute)
                <input type="number" min={1} max={bozza.modello === "evento" ? DOPO_MAX : 252}
                  className={cn(CAMPO, "w-20")} value={bozza.orizzonte}
                  onChange={(e) => setBozza({ ...bozza, orizzonte: Number(e.target.value) })} />
              </label>
            )}
            <button type="submit" className="h-9 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground">
              Calcola
            </button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <Risultato p={p} />
        </CardContent>
      </Card>
    </div>
  );
}
