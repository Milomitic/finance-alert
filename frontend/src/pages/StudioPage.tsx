import { useQuery } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { type Confronto, type DopoMovimento, type Evento, type Fascia, type Misura, type Stagionalita, studio } from "@/api/studio";
import { ApiError } from "@/api/client";
import { useIsPhone } from "@/hooks/useMediaQuery";
import { Card, CardContent } from "@/components/ui/card";
import { GraficoSvg } from "@/components/ui/grafico-svg";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { intervallo, MODELLI, type Modello, parametriDaUrl, pct, posizioneSulleFasce, sogliaInFrase } from "@/lib/studio";
import { cn } from "@/lib/utils";
import { GIU, NEUTRO, SU } from "@/lib/coloriGrafico";
import { Segmentato } from "@/components/ui/segmentato";
import { Button } from "@/components/ui/button";
import { ElencoCasi } from "@/components/studio/ElencoCasi";
import { FraseEscursioni, GraficoPercorso, LegendaPercorso } from "@/components/studio/GraficoPercorso";

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
  const isPhone = useIsPhone();
  if (isPhone) {
    // D-87: a 375px la tabella era larga 560 e scorreva di lato, con il nome
    // della riga che usciva per primo. Su telefono una scheda per riga.
    return (
      <ul className="space-y-2">
        {righe.map(([n, m]) => (
          <li key={n} className="rounded-md border p-2 text-sm">
            <div className="font-medium">{n}</div>
            <dl className="mt-1 grid grid-cols-3 gap-x-2 gap-y-1 text-xs">
              <div><dt className="text-muted-foreground">Media</dt><dd className="font-semibold tabular-nums">{pct(m.media, 2)}</dd></div>
              <div><dt className="text-muted-foreground">Mediana</dt><dd className="tabular-nums">{pct(m.mediana, 2)}</dd></div>
              <div><dt className="text-muted-foreground">Positivi</dt><dd className="tabular-nums">{m.quota_positivi == null ? "—" : `${Math.round(m.quota_positivi * 100)}%`}</dd></div>
              <div><dt className="text-muted-foreground">Casi</dt><dd className="tabular-nums">{m.casi}</dd></div>
              <div className="col-span-2"><dt className="text-muted-foreground">Finestre indip.</dt><dd className="tabular-nums">{m.finestre}</dd></div>
              <div className="col-span-3"><dt className="text-muted-foreground">Intervallo della media (95%)</dt><dd>{intervallo(m)}</dd></div>
            </dl>
          </li>
        ))}
      </ul>
    );
  }
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

/** Il verdetto sopra i numeri (D-84): tre stati, mai «conviene». */
const TESTO_VERDETTO: Record<Confronto["verdetto"], { titolo: string; tono: string }> = {
  non_concludente: { titolo: "Non concludente", tono: "border-amber-500/50 bg-amber-50 dark:bg-amber-950/30" },
  compatibile_con_zero: { titolo: "Compatibile con zero", tono: "border-border bg-muted/40" },
  instabile: { titolo: "Non regge nelle due metà", tono: "border-amber-500/50 bg-amber-50 dark:bg-amber-950/30" },
  diversa_dalla_base: { titolo: "Diversa dalla base", tono: "border-sky-500/50 bg-sky-50 dark:bg-sky-950/30" },
};

function RigaVerdetto({ c, finestre }: { c: Confronto; finestre: number }) {
  const v = TESTO_VERDETTO[c.verdetto];
  const iv = c.intervallo_differenza;
  const perche =
    c.verdetto === "non_concludente"
      ? finestre < 20
        ? `${finestre} finestre indipendenti: ne servono almeno 20 per dire qualcosa.`
        : "l'intervallo non è stimabile."
      : c.verdetto === "compatibile_con_zero"
        ? "l'intervallo della differenza contiene lo zero: potrebbe essere caso."
        : c.verdetto === "instabile"
          ? "nel complesso esclude lo zero, ma nelle due metà della storia la differenza cambia segno."
          : "l'intervallo della differenza esclude lo zero e regge nelle due metà. Descrive il passato, non lo prevede.";
  const st = c.stabilita;
  return (
    <div className={cn("rounded-md border px-3 py-2 text-sm", v.tono)}>
      <strong>{v.titolo}</strong> — {perche}
      {c.differenza != null && (
        <div className="mt-0.5 text-xs text-muted-foreground">
          Differenza dalla base{" "}
          <span className={cn("tabular-nums", c.verdetto === "diversa_dalla_base" && "font-semibold text-foreground")}>
            {pct(c.differenza, 2)}
          </span>
          {iv && <span className="tabular-nums"> (da {pct(iv[0], 2)} a {pct(iv[1], 2)}, 95%)</span>}
        </div>
      )}
      {st && (st.prima != null || st.seconda != null) && (
        <div className="text-xs text-muted-foreground tabular-nums">
          {/* F4: la stessa differenza sulla prima e sulla seconda metà della storia. */}
          Prima metà {pct(st.prima, 2)} · seconda metà {pct(st.seconda, 2)}
        </div>
      )}
    </div>
  );
}

/** Domande d'esempio per chi apre la pagina vuota (D-81). */
const ESEMPI: { testo: string; parametri: Record<string, string> }[] = [
  { testo: "Cosa ha fatto AAPL nelle 21 sedute dopo un calo del 10% in 5 sedute?",
    parametri: { simbolo: "AAPL", modello: "dopo_movimento", soglia: "-10", sedute: "5", orizzonte: "21" } },
  { testo: "Quali mesi sono andati meglio per l'S&P 500?",
    parametri: { simbolo: "^GSPC", modello: "stagionalita" } },
  { testo: "Cosa fa NVDA nelle 5 sedute attorno alle trimestrali?",
    parametri: { simbolo: "NVDA", modello: "evento", tipo: "trimestrali", orizzonte: "5" } },
];

function Esempi({ onScegli }: { onScegli: (p: Record<string, string>) => void }) {
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">Scegli un simbolo, oppure parti da una di queste domande:</p>
      <div className="grid gap-2 md:grid-cols-3">
        {ESEMPI.map((e) => (
          <button
            key={e.testo}
            type="button"
            onClick={() => onScegli(e.parametri)}
            className="rounded-md border bg-muted/30 p-3 text-left text-sm hover:bg-accent"
          >
            {e.testo}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Il colore di una barra: il verso solo se l'intervallo esclude lo zero (D-85). */
function coloreSeEsce(m: Misura): string {
  // F5: il verso solo per cio' che sopravvive alla correzione per famiglia;
  // senza il campo (risposte vecchie) vale l'intervallo che esclude lo zero.
  if (m.significativo === false) return NEUTRO;
  const iv = m.intervallo;
  if (!iv || (iv[0] <= 0 && iv[1] >= 0)) return NEUTRO;
  return (m.media ?? 0) >= 0 ? SU : GIU;
}

/** La forma della distribuzione (F1): percentili e un istogramma della
 *  condizione sopra quello della base, sulla stessa griglia. */
function Distribuzione({ cond, base, fasce }: { cond: Misura; base: Misura; fasce?: Fascia[] }) {
  if (cond.casi === 0) return null;
  const max = Math.max(0.0001, ...(fasce ?? []).flatMap((f) => [f.condizione, f.base]));
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold">Distribuzione</h2>
      <dl className="grid grid-cols-3 gap-2 text-sm sm:grid-cols-5">
        {([["Peggiore", cond.peggiore], ["10° perc.", cond.p10], ["Mediana", cond.mediana], ["90° perc.", cond.p90], ["Migliore", cond.migliore]] as const).map(([n, v]) => (
          <div key={n} className="rounded-md bg-muted/30 px-2 py-1">
            <dt className="text-xs text-muted-foreground">{n}</dt>
            <dd className="font-semibold tabular-nums">{pct(v ?? null, 1)}</dd>
          </div>
        ))}
      </dl>
      {fasce && fasce.length > 0 && <Istogramma fasce={fasce} max={max} cond={cond} base={base} />}
      <p className="sr-only">
        Peggiore {pct(cond.peggiore ?? null, 1)}, mediana {pct(cond.mediana ?? null, 1)}, migliore {pct(cond.migliore ?? null, 1)};
        nella base la mediana è {pct(base.mediana ?? null, 1)}.
      </p>
    </div>
  );
}

/** FA-192: l'istogramma con la linea dello zero, le due mediane segnate e
 *  l'asse in percentuale. Prima c'erano solo i due estremi, e la mediana —
 *  il numero che l'ondata 1 ha messo accanto alla media — non si vedeva. */
function Istogramma({ fasce, max, cond, base }: { fasce: Fascia[]; max: number; cond: Misura; base: Misura }) {
  const L = fasce.length * 20;
  const zero = posizioneSulleFasce(0, fasce);
  const medCond = posizioneSulleFasce(cond.mediana, fasce);
  const medBase = posizioneSulleFasce(base.mediana, fasce);
  return (
    <figure>
      <svg viewBox={`0 0 ${L} 72`} className="h-20 w-full" preserveAspectRatio="none" role="img"
        aria-label="Quota dei casi per fascia di rendimento: dopo la condizione e in tutte le finestre">
        {fasce.map((f, i) => (
          <g key={i}>
            <rect x={i * 20 + 2} y={68 - (f.base / max) * 60} width={7} height={(f.base / max) * 60} fill={NEUTRO} opacity={0.5} />
            <rect x={i * 20 + 10} y={68 - (f.condizione / max) * 60} width={7} height={(f.condizione / max) * 60} fill="hsl(var(--primary))" />
          </g>
        ))}
        <line x1={0} x2={L} y1={68.5} y2={68.5} stroke="currentColor" className="text-border" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        {zero != null && (
          <line x1={zero * L} x2={zero * L} y1={0} y2={68} stroke="currentColor" className="text-muted-foreground"
            strokeWidth={1} strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
        )}
        {medBase != null && (
          <line x1={medBase * L} x2={medBase * L} y1={4} y2={68} stroke={NEUTRO} strokeWidth={2} vectorEffect="non-scaling-stroke" />
        )}
        {medCond != null && (
          <line x1={medCond * L} x2={medCond * L} y1={4} y2={68} stroke="hsl(var(--primary))" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      <div className="relative mt-1 h-4 text-xs text-muted-foreground tabular-nums">
        <span className="absolute left-0">{pct(fasce[0].da, 1)}</span>
        {zero != null && zero > 0.12 && zero < 0.88 && (
          <span className="absolute -translate-x-1/2" style={{ left: `${zero * 100}%` }}>0</span>
        )}
        <span className="absolute right-0">{pct(fasce[fasce.length - 1].a, 1)}</span>
      </div>
      <figcaption className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
        <span><span className="text-primary">■</span> dopo la condizione (linea: mediana {pct(cond.mediana ?? null, 1)})</span>
        <span><span style={{ color: NEUTRO }}>■</span> base (mediana {pct(base.mediana ?? null, 1)})</span>
        {zero != null && <span>tratteggio: zero</span>}
      </figcaption>
    </figure>
  );
}

function Risultato({ p, onEsempio }: {
  p: ReturnType<typeof parametriDaUrl>;
  onEsempio: (p: Record<string, string>) => void;
}) {
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
  if (p.simbolo === "") return <Esempi onScegli={onEsempio} />;
  if (q.isError && q.error instanceof ApiError && q.error.status === 404) {
    // D-82: un simbolo sconosciuto non e' un guasto del server.
    return <p className="text-sm text-muted-foreground">«{p.simbolo}» non è né nel catalogo né fra i mercati.</p>;
  }
  if (q.isError) return <QueryError message="dello studio" errore={q.error} onRetry={q.refetch} isRetrying={q.isFetching} />;
  if (!q.data) return <div className="h-64 animate-pulse rounded-md bg-muted/40" aria-hidden />;

  if (p.modello === "dopo_movimento") {
    const r = q.data as DopoMovimento;
    return (
      <div className="space-y-2">
        <p className="text-sm">
          {p.orizzonte} sedute dopo ogni giorno in cui {p.simbolo} si era mosso di {sogliaInFrase(p.soglia)}
          {p.soglia < 0 ? " o peggio" : " o più"} in {p.sedute} sedute.
        </p>
        <RigaVerdetto c={r} finestre={r.condizione.finestre} />
        {r.percorso && r.percorso.length > 1 && r.condizione.casi > 0 && (
          <div className="space-y-1">
            {/* FA-194: il percorso, non solo il punto d'arrivo. */}
            <GraficoPercorso percorso={r.percorso}
              etichetta={`Rendimento cumulato di ${p.simbolo} nelle ${p.orizzonte} sedute dopo il movimento`} />
            <LegendaPercorso conSingoli={false} />
            {r.escursioni && <FraseEscursioni e={r.escursioni} orizzonte={p.orizzonte} />}
          </div>
        )}
        <TabellaMisure righe={[["Dopo il movimento", r.condizione], ["Base: tutte le finestre", r.base]]} />
        <Distribuzione cond={r.condizione} base={r.base} fasce={r.istogramma} />
        {r.elenco_casi && (
          <ElencoCasi casi={r.elenco_casi} totale={r.condizione.casi} episodi={r.condizione.finestre}
            simbolo={p.simbolo} modello={p.modello} etichettaMossa="Mossa" />
        )}
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
              coloreBarra: coloreSeEsce }]} />
        </div>
        <p className="text-xs text-muted-foreground">
          Colorati solo i mesi che reggono alla correzione per {r.confronti ?? 17} confronti (12 mesi e 5 giorni,
          Benjamini-Hochberg): {r.sopravvissuti ?? 0} su {r.confronti ?? 17}. Senza correzione uno ogni venti uscirebbe per caso.
        </p>
        <h2 className="text-sm font-semibold">Per mese</h2>
        <TabellaMisure righe={[...r.mesi.map((m) => [m.mese, m] as [string, Misura]), ["Tutti i mesi", r.base_mesi]]} />
        <h2 className="text-sm font-semibold">Per giorno della settimana</h2>
        <TabellaMisure righe={[...r.giorni.map((g) => [g.giorno, g] as [string, Misura]), ["Tutte le sedute", r.base_giorni]]} />
      </div>
    );
  }
  const r = q.data as Evento;
  if (r.eventi === 0 || r.a_orizzonte.casi === 0) {
    // FA-192: un messaggio solo. Prima un verdetto «0 finestre indipendenti»
    // e una tabella di trattini ripetevano tre volte la stessa assenza.
    return (
      <p className="text-sm text-muted-foreground">
        {r.tipo === "macro"
          ? `Nessun rilascio di ${p.serie} nella storia di ${p.simbolo}.`
          : `Nessuna trimestrale nota per ${p.simbolo}: lo studio sulle trimestrali vale per i titoli del catalogo con i fondamentali in cache.`}
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-sm">
        {r.eventi} {p.tipo === "macro" ? `rilasci di ${p.serie}` : "trimestrali passate"}; percorso medio di {p.simbolo}
        {" "}dalla chiusura della seduta precedente.
      </p>
      {r.percorso.length > 1 && (
        <div className="space-y-1">
          {/* FA-194 (D-86): banda, mediana e i singoli eventi, non solo la media. */}
          <GraficoPercorso percorso={r.percorso} singoli={r.singoli} conBase={false}
            giornoEvento={r.percorso.findIndex((s) => s.seduta === 0)}
            etichetta={`Rendimento di ${p.simbolo} attorno all'evento, per seduta, dalla chiusura precedente`} />
          <LegendaPercorso conSingoli={(r.singoli?.length ?? 0) > 0} conBase={false} />
          <p className="text-xs text-muted-foreground">
            {r.percorso[0].n ?? r.eventi} eventi in ogni seduta; la linea verticale è il giorno dell&apos;evento.
          </p>
        </div>
      )}
      <RigaVerdetto c={r} finestre={r.a_orizzonte.finestre} />
      <TabellaMisure righe={[[`A ${r.orizzonte} sedute dall'evento`, r.a_orizzonte], ["Base: tutte le finestre", r.base]]} />
      <Distribuzione cond={r.a_orizzonte} base={r.base} fasce={r.istogramma} />
      {r.elenco_casi && (
        <ElencoCasi casi={r.elenco_casi} totale={r.a_orizzonte.casi} episodi={r.a_orizzonte.finestre}
          simbolo={p.simbolo} modello={p.modello} />
      )}
    </div>
  );
}

/** La domanda in una riga, per il modulo chiuso su telefono. */
function riassunto(p: ReturnType<typeof parametriDaUrl>): string {
  if (p.modello === "stagionalita") return `${p.simbolo} · stagionalità`;
  if (p.modello === "evento") {
    return `${p.simbolo} · ${p.tipo === "macro" ? `rilasci ${p.serie}` : "trimestrali"} · ${Math.min(p.orizzonte, DOPO_MAX)} sedute`;
  }
  return `${p.simbolo} · ${sogliaInFrase(p.soglia)} in ${p.sedute} · ${p.orizzonte} sedute`;
}

export default function StudioPage() {
  const [sp, setSp] = useSearchParams();
  const p = parametriDaUrl(sp);
  const [bozza, setBozza] = useState(p);
  const isPhone = useIsPhone();
  // FA-192: su telefono, a studio calcolato, il modulo si chiude in una riga
  // e il risultato sale nel primo schermo (D-87). Si riapre con «Modifica».
  const [moduloAperto, setModuloAperto] = useState(false);
  const chiuso = isPhone && p.simbolo !== "" && !moduloAperto;
  // D-82: il modulo segue l'URL. «Indietro» del browser cambiava il risultato
  // e lasciava il modulo sulla domanda di prima. Aggiornato in render, non in
  // un effetto (la regola dei hook gatta set-state-in-effect).
  const chiaveUrl = sp.toString();
  const [urlPrec, setUrlPrec] = useState(chiaveUrl);
  if (chiaveUrl !== urlPrec) {
    setUrlPrec(chiaveUrl);
    setBozza(parametriDaUrl(sp));
  }

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
    setModuloAperto(false);
  };

  const scegliModello = (id: Modello) => setBozza({
    ...bozza,
    modello: id,
    // D-82: gli eventi arrivano a 10 sedute; il campo restava a 21
    // e il browser bloccava l'invio con una bolla nativa.
    orizzonte: id === "evento" ? Math.min(bozza.orizzonte, DOPO_MAX) : bozza.orizzonte,
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-3 sm:p-6">
      <h1 className="sr-only">Studio</h1>
      <Card>
        <CardContent className="space-y-3 p-4">
          <SectionTitle icon={FlaskConical} label="Studio" />
          {/* Su telefono la descrizione lascia spazio ai dati (richiesta del 2026-11-22). */}
          <p className="hidden sm:block text-xs text-muted-foreground">
            Statistica storica: che cosa è successo, non che cosa succederà. Ogni numero ha accanto il caso base e
            le finestre indipendenti.
          </p>
          {chiuso ? (
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="min-w-0 truncate font-medium">{riassunto(p)}</span>
              <Button type="button" variant="outline" size="sm" onClick={() => setModuloAperto(true)}>Modifica</Button>
            </div>
          ) : (
          <form onSubmit={imposta} className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Simbolo
              <input className={cn(CAMPO, "w-28 uppercase")} value={bozza.simbolo}
                onChange={(e) => setBozza({ ...bozza, simbolo: e.target.value })} placeholder="AAPL, ^GSPC" />
            </label>
            {isPhone ? (
              // FA-192: i tre modelli uscivano dal bordo a 375 px («Attorno a un ev…»).
              <label className="flex w-full flex-col gap-1 text-xs text-muted-foreground">
                Domanda
                <select className={CAMPO} value={bozza.modello} onChange={(e) => scegliModello(e.target.value as Modello)}>
                  {MODELLI.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
              </label>
            ) : (
              <Segmentato etichetta="Modello" taglia="media" valore={bozza.modello}
                onCambia={(id) => scegliModello(id as Modello)}
                voci={MODELLI.map((m) => ({ id: m.id as Modello, label: m.label }))} />
            )}
            {bozza.modello === "dopo_movimento" && (
              <>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  Variazione %
                  <input type="number" min={-90} max={500} className={cn(CAMPO, "w-20")} value={bozza.soglia}
                    onChange={(e) => setBozza({ ...bozza, soglia: Number(e.target.value) })} />
                  <span className="text-[0.6765rem]">−90…+500, negativa = calo</span>
                </label>
                <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                  in sedute
                  <input type="number" min={1} max={63} className={cn(CAMPO, "w-16")} value={bozza.sedute}
                    onChange={(e) => setBozza({ ...bozza, sedute: Number(e.target.value) })} />
                  <span className="text-[0.6765rem]">1–63</span>
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
                <span className="text-[0.6765rem]">{bozza.modello === "evento" ? `1–${DOPO_MAX} attorno a un evento` : "1–252"}</span>
              </label>
            )}
            <Button type="submit" variant="default">
              Calcola
            </Button>
          </form>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-3 p-4">
          {/* D-87: il risultato ripete la domanda, cosi' un link condiviso non
              apre tabelle senza il titolo che le ha prodotte. */}
          {p.simbolo !== "" && (
            <h2 className="text-base font-semibold">
              {p.simbolo} · {MODELLI.find((m) => m.id === p.modello)?.label}
            </h2>
          )}
          <Risultato
            p={p}
            onEsempio={(q) => {
              const n = new URLSearchParams(q);
              setSp(n);
              setBozza(parametriDaUrl(n));
            }}
          />
        </CardContent>
      </Card>
    </div>
  );
}
