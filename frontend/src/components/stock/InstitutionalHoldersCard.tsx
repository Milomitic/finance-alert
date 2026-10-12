import { Building2, ChevronDown, ChevronUp } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { TickerHolder } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useTickerInstitutionalHolders } from "@/hooks/useInstitutionals";
import { type Ordine, ordina, ordinaPerData, riepilogo, variazione } from "@/lib/fondiDetentori";
import { fmtBig } from "@/lib/format";
import { cn } from "@/lib/utils";
import { TONO_VARIAZIONE } from "@/lib/variazioneMacro";

/* ─── Superinvestor e fondi: chi detiene il titolo, e cosa ha fatto ────────
 *
 * Due viste sulla stessa scheda, e rispondono a domande diverse:
 *   - «Detentori»: chi lo detiene ORA, quanto pesa nel suo portafoglio e
 *     quanto vale la posizione. Una riga per fondo, su una linea sola: nome,
 *     barra del peso (stessa scala per tutti), peso, movimento del trimestre,
 *     valore. Le colonne stanno in un'unica griglia, quindi allineate per
 *     costruzione anche fra righe diverse.
 *   - «Ultime operazioni»: il verbo del 13F (Nuovo / Add / Reduce / Sold out)
 *     con la data, dal piu' recente. I fondi usciti stanno qui, perche' sono
 *     un'operazione, non una posizione.
 *
 * Il titolo della scheda NON cambia con la vista: e' la sua identita' (il gate
 * e2e e il link «N fondi» dell'intestazione la trovano per quello).
 */

const PRIME = 15;

type Vista = "detentori" | "operazioni";

function dataBreve(s: string | null): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  return y && m && d ? `${d}/${m}/${y.slice(2)}` : s;
}

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${v.toFixed(1)}%`;
}

function toneDi(tono: "su" | "giu" | "fermo" | undefined): string {
  return tono === "su" ? TONO_VARIAZIONE.su : tono === "giu" ? TONO_VARIAZIONE.giu : TONO_VARIAZIONE.fermo;
}

/* Due forme scritte per intero: il purger di Tailwind vede solo letterali.
 * Sul telefono la barra cede il posto al nome, che e' l'identita' della riga. */
const GRIGLIA_FONDI =
  "grid grid-cols-[minmax(0,1fr)_2.75rem_3.5rem_4rem] sm:grid-cols-[minmax(0,1fr)_4.5rem_2.75rem_3.5rem_4rem] items-center gap-x-2";

function TestataFondi() {
  return (
    <li className={cn(GRIGLIA_FONDI, "pb-0.5 text-[0.6471rem] font-semibold uppercase tracking-wider text-muted-foreground")}>
      <span>Fondo</span>
      <span className="hidden sm:block" aria-hidden />
      <span className="text-right">Peso</span>
      <span className="text-right">Trim.</span>
      <span className="text-right">Valore</span>
    </li>
  );
}

function RigaFondo({ h, maxPeso }: { h: TickerHolder; maxPeso: number }) {
  const v = variazione(h);
  const peso = h.portfolio_pct;
  const larghezza = peso != null && maxPeso > 0 ? Math.max(2, (peso / maxPeso) * 100) : 0;
  return (
    <li className={cn(GRIGLIA_FONDI, "border-t border-border/40 py-1 leading-[1.125rem]")}>
      <Link
        to={`/institutionals/${h.institutional_slug}`}
        className="min-w-0 truncate text-xs font-medium hover:underline"
        title={h.institutional_name}
      >
        {h.institutional_name}
      </Link>
      <span className="hidden h-1.5 overflow-hidden rounded-full bg-muted sm:block" aria-hidden>
        <span className="block h-full rounded-full bg-primary/80" style={{ width: `${larghezza}%` }} />
      </span>
      <span className="text-right text-[0.7059rem] font-semibold tabular-nums">{pct(peso)}</span>
      <span className={cn("text-right text-[0.6471rem] tabular-nums", toneDi(v?.tono))} title={v?.spiegazione}>
        {v?.testo ?? ""}
      </span>
      <span className="text-right text-[0.7059rem] tabular-nums">{fmtBig(h.value_usd)}</span>
    </li>
  );
}

/** Il verbo del 13F, col vocabolario di Dataroma. */
function verbo(action: string | null): { label: string; tone: string } {
  switch (action) {
    case "new":
      return { label: "Nuovo", tone: "text-emerald-800 dark:text-emerald-300" };
    case "add":
      return { label: "Add", tone: "text-emerald-800 dark:text-emerald-300" };
    case "reduce":
      return { label: "Reduce", tone: "text-amber-700 dark:text-amber-300" };
    case "sold_out":
      return { label: "Sold out", tone: "text-rose-700 dark:text-rose-300" };
    case "hold":
      return { label: "Hold", tone: "text-muted-foreground" };
    default:
      return { label: action ?? "—", tone: "text-muted-foreground" };
  }
}

/* Testata e righe usano la STESSA stringa: le colonne si allineano per
 * costruzione. `minmax(0,1fr)` e' cio' che lascia troncare il nome. */
const GRIGLIA_OPERAZIONI =
  "grid grid-cols-[minmax(0,1fr)_3.75rem_2.75rem_4rem_3.25rem] items-center gap-x-2 min-w-[320px] md:min-w-0";

function TestataOperazioni() {
  return (
    <li className={cn(GRIGLIA_OPERAZIONI, "pb-0.5 text-[0.6471rem] font-semibold uppercase tracking-wider text-muted-foreground")}>
      <span>Fondo</span>
      <span>Azione</span>
      <span className="text-right">%</span>
      <span className="text-right">Valore</span>
      <span className="text-right">Data</span>
    </li>
  );
}

function RigaOperazione({ h }: { h: TickerHolder }) {
  const a = verbo(h.action);
  return (
    <li className={cn(GRIGLIA_OPERAZIONI, "border-t border-border/40 py-1 leading-[1.125rem]")}>
      <Link
        to={`/institutionals/${h.institutional_slug}`}
        className="min-w-0 truncate text-xs font-medium hover:underline"
        title={h.institutional_name}
      >
        {h.institutional_name}
      </Link>
      <span className={cn("truncate text-[0.7059rem] font-semibold", a.tone)}>{a.label}</span>
      <span className="text-right text-[0.7059rem] tabular-nums text-muted-foreground">{pct(h.portfolio_pct)}</span>
      <span className="text-right text-[0.7059rem] tabular-nums text-muted-foreground">{fmtBig(h.value_usd)}</span>
      <span className="text-right text-[0.7059rem] tabular-nums text-muted-foreground">{dataBreve(h.period_end_date)}</span>
    </li>
  );
}

function Riepilogo({ fondi }: { fondi: TickerHolder[] }) {
  const r = riepilogo(fondi);
  return (
    <div className="mb-2 grid grid-cols-3 gap-2">
      <div className="min-w-0 rounded-md bg-muted/30 px-2 py-1">
        <div className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">Fondi</div>
        <div className="text-base font-bold leading-tight tabular-nums">{r.fondi}</div>
      </div>
      <div className="min-w-0 rounded-md bg-muted/30 px-2 py-1">
        <div className="truncate text-[0.6471rem] uppercase tracking-wider text-muted-foreground">Valore detenuto</div>
        <div className="text-base font-bold leading-tight tabular-nums">{fmtBig(r.valoreTotale)}</div>
      </div>
      <div className="min-w-0 rounded-md bg-muted/30 px-2 py-1">
        <div className="truncate text-[0.6471rem] uppercase tracking-wider text-muted-foreground">Nel trimestre</div>
        <div className="flex flex-wrap items-baseline gap-x-1.5 text-xs font-semibold leading-tight tabular-nums">
          <span className={TONO_VARIAZIONE.su}>▲ {r.aumentano + r.nuovi}</span>
          <span className={TONO_VARIAZIONE.giu}>▼ {r.riducono}</span>
          {r.nuovi > 0 && <span className="text-[0.6471rem] font-normal text-muted-foreground">{r.nuovi} nuovi</span>}
        </div>
      </div>
    </div>
  );
}

function Segmenti<T extends string>({ voci, valore, onChange, etichetta }: {
  voci: readonly { id: T; label: string }[];
  valore: T;
  onChange: (v: T) => void;
  etichetta: string;
}) {
  return (
    <div className="flex rounded-md border p-0.5" role="group" aria-label={etichetta}>
      {voci.map((v) => (
        <button
          key={v.id}
          type="button"
          onClick={() => onChange(v.id)}
          aria-pressed={valore === v.id}
          className={cn(
            "min-h-[26px] rounded px-2 text-[0.7059rem] font-semibold transition-colors",
            valore === v.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}

function AltriBottone({ aperto, totale, onClick }: { aperto: boolean; totale: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-1 inline-flex min-h-[28px] items-center gap-1 text-xs font-medium text-primary hover:underline"
      aria-expanded={aperto}
    >
      {aperto ? <ChevronUp className="h-3.5 w-3.5" aria-hidden /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
      {aperto ? `Mostra i primi ${PRIME}` : `Mostra tutti i ${totale}`}
    </button>
  );
}

export function InstitutionalHoldersCard({ ticker }: { ticker: string }) {
  // Tutti i detentori, non i primi 25: il riepilogo somma i valori, e una
  // somma sulla prima pagina sarebbe un totale falso.
  const q = useTickerInstitutionalHolders(ticker, 200, true);
  const [vista, setVista] = useState<Vista>("detentori");
  const [ordine, setOrdine] = useState<Ordine>("peso");
  const [tutti, setTutti] = useState(false);

  const fondi = useMemo(() => q.data?.holders ?? [], [q.data]);
  const ordinati = useMemo(() => ordina(fondi, ordine), [fondi, ordine]);
  const operazioni = useMemo(() => {
    const attuali = new Set(fondi.map((h) => h.institutional_id));
    const usciti = (q.data?.historical ?? []).filter((h) => !attuali.has(h.institutional_id));
    return ordinaPerData([...fondi, ...usciti]);
  }, [fondi, q.data]);
  const maxPeso = Math.max(0, ...fondi.map((h) => h.portfolio_pct ?? 0));
  const r = riepilogo(fondi);

  const vistaSelettore = fondi.length > 0 || operazioni.length > 0 ? (
    <Segmenti
      etichetta="Vista dei fondi"
      valore={vista}
      onChange={(v) => { setVista(v); setTutti(false); }}
      voci={[{ id: "detentori", label: "Detentori" }, { id: "operazioni", label: "Ultime operazioni" }] as const}
    />
  ) : undefined;

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-3">
          <SectionTitle icon={Building2} label="Superinvestor / fondi" className="mb-2" />
          <div className="h-24 animate-pulse rounded bg-muted/40" />
        </CardContent>
      </Card>
    );
  }

  const elenco = vista === "detentori" ? ordinati : operazioni;
  const visibili = tutti ? elenco : elenco.slice(0, PRIME);

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle icon={Building2} label="Superinvestor / fondi" className="mb-2" right={vistaSelettore} />
        {fondi.length === 0 && operazioni.length === 0 ? (
          <div className="py-3 text-center text-sm text-muted-foreground">
            Nessun fondo tracciato detiene questo titolo.
          </div>
        ) : vista === "detentori" ? (
          <>
            <Riepilogo fondi={fondi} />
            <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[0.6471rem] text-muted-foreground">
                Barra = peso nel portafoglio del fondo · 13F al {dataBreve(r.periodo)}
              </span>
              <Segmenti
                etichetta="Ordina i fondi"
                valore={ordine}
                onChange={setOrdine}
                voci={[{ id: "peso", label: "Peso" }, { id: "valore", label: "Valore" }] as const}
              />
            </div>
            {fondi.length === 0 ? (
              <div className="py-2 text-center text-xs text-muted-foreground">
                Nessun fondo lo detiene ora: le uscite sono fra le ultime operazioni.
              </div>
            ) : (
              <ul data-vista="detentori">
                <TestataFondi />
                {visibili.map((h) => (
                  <RigaFondo key={`${h.institutional_id}-${h.period_end_date}`} h={h} maxPeso={maxPeso} />
                ))}
              </ul>
            )}
          </>
        ) : (
          /* Le colonne fisse sono piu' larghe di un telefono: scorre la lista,
             invece di schiacciare il nome a zero. */
          <div className="overflow-x-auto md:overflow-visible">
            <ul data-vista="operazioni">
              <TestataOperazioni />
              {visibili.map((h) => (
                <RigaOperazione key={`${h.institutional_id}-${h.period_end_date}`} h={h} />
              ))}
            </ul>
          </div>
        )}
        {elenco.length > PRIME && (
          <AltriBottone aperto={tutti} totale={elenco.length} onClick={() => setTutti((t) => !t)} />
        )}
      </CardContent>
    </Card>
  );
}
