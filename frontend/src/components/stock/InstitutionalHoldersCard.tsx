import { Building2, ChevronDown, ChevronUp } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { TickerHolder } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useTickerInstitutionalHolders } from "@/hooks/useInstitutionals";
import { type Ordine, ordina, riepilogo, variazione } from "@/lib/fondiDetentori";
import { fmtBig } from "@/lib/format";
import { cn } from "@/lib/utils";
import { TONO_VARIAZIONE } from "@/lib/variazioneMacro";

/* ─── Chi detiene il titolo (riassetto del 2026-10-12) ─────────────────────
 *
 * Prima: una tabella dell'ULTIMA operazione (Add / Reduce / Nuovo, con la
 * data) e sotto un grafico delle posizioni coi nomi tagliati a dieci lettere
 * e le barre che partivano a x diverse, perche' la variazione stava in una
 * colonna di larghezza variabile prima della barra.
 *
 * Ora una vista sola che risponde a cio' che si chiede aprendo la scheda:
 *   - in testa quanti fondi, quanto valgono in tutto le loro posizioni, chi
 *     ha aumentato e chi ridotto, a che trimestre si riferisce;
 *   - una riga per fondo: il nome intero e il VALORE della posizione sopra, il
 *     PESO nel portafoglio del fondo sotto, con la barra che parte sempre alla
 *     stessa x e sulla stessa scala, e il movimento del trimestre come
 *     contorno a destra;
 *   - i fondi usciti in un elenco a parte, chiuso: sono storia, non posizioni.
 */

const PRIME = 10;

function dataBreve(s: string | null): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  return y && m && d ? `${d}/${m}/${y.slice(2)}` : s;
}

function Riga({ h, maxPeso }: { h: TickerHolder; maxPeso: number }) {
  const v = variazione(h);
  const peso = h.portfolio_pct;
  const larghezza = peso != null && maxPeso > 0 ? Math.max(2, (peso / maxPeso) * 100) : 0;
  return (
    <li className="border-t border-border/40 py-1.5">
      <div className="flex min-w-0 items-baseline justify-between gap-2">
        <Link
          to={`/institutionals/${h.institutional_slug}`}
          className="min-w-0 truncate text-sm font-semibold hover:underline"
          title={h.institutional_name}
        >
          {h.institutional_name}
        </Link>
        <span className="shrink-0 text-sm font-semibold tabular-nums">{fmtBig(h.value_usd)}</span>
      </div>
      {/* Una griglia sola per tutte le righe: barra, peso e movimento stanno in
          colonna per costruzione, e la barra ha sempre la stessa scala. */}
      <div className="mt-1 grid grid-cols-[minmax(0,1fr)_3rem_3.75rem] items-center gap-2">
        <span className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
          <span className="block h-full rounded-full bg-primary/80" style={{ width: `${larghezza}%` }} />
        </span>
        <span className="text-right text-xs font-semibold tabular-nums">
          {peso == null ? "—" : `${peso.toFixed(1)}%`}
        </span>
        <span
          className={cn("text-right text-[0.7059rem] tabular-nums",
            v?.tono === "su" ? TONO_VARIAZIONE.su : v?.tono === "giu" ? TONO_VARIAZIONE.giu : TONO_VARIAZIONE.fermo)}
          title={v?.spiegazione}
        >
          {v?.testo ?? ""}
        </span>
      </div>
    </li>
  );
}

function Riepilogo({ fondi }: { fondi: TickerHolder[] }) {
  const r = riepilogo(fondi);
  return (
    <div className="mb-2 grid grid-cols-3 gap-2">
      <div className="min-w-0 rounded-md bg-muted/30 px-2 py-1.5">
        <div className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">Fondi</div>
        <div className="text-lg font-bold leading-tight tabular-nums">{r.fondi}</div>
      </div>
      <div className="min-w-0 rounded-md bg-muted/30 px-2 py-1.5">
        <div className="truncate text-[0.6471rem] uppercase tracking-wider text-muted-foreground">Valore detenuto</div>
        <div className="text-lg font-bold leading-tight tabular-nums">{fmtBig(r.valoreTotale)}</div>
      </div>
      <div className="min-w-0 rounded-md bg-muted/30 px-2 py-1.5">
        <div className="truncate text-[0.6471rem] uppercase tracking-wider text-muted-foreground">Nel trimestre</div>
        <div className="flex flex-wrap items-baseline gap-x-1.5 text-xs font-semibold leading-tight tabular-nums">
          <span className={TONO_VARIAZIONE.su}>▲ {r.aumentano + r.nuovi}</span>
          <span className={TONO_VARIAZIONE.giu}>▼ {r.riducono}</span>
        </div>
        {r.nuovi > 0 && <div className="text-[0.6471rem] text-muted-foreground">{r.nuovi} nuovi</div>}
      </div>
    </div>
  );
}

export function InstitutionalHoldersCard({ ticker }: { ticker: string }) {
  // Tutti i detentori, non i primi 25: il riepilogo somma i valori, e una
  // somma sulla prima pagina sarebbe un totale falso.
  const q = useTickerInstitutionalHolders(ticker, 200, true);
  const [ordine, setOrdine] = useState<Ordine>("peso");
  const [tutti, setTutti] = useState(false);
  const [usciti, setUsciti] = useState(false);

  const fondi = useMemo(() => q.data?.holders ?? [], [q.data]);
  const ordinati = useMemo(() => ordina(fondi, ordine), [fondi, ordine]);
  const attuali = new Set(fondi.map((h) => h.institutional_id));
  const storici = (q.data?.historical ?? []).filter((h) => !attuali.has(h.institutional_id));
  const visibili = tutti ? ordinati : ordinati.slice(0, PRIME);
  const maxPeso = Math.max(0, ...fondi.map((h) => h.portfolio_pct ?? 0));
  const r = riepilogo(fondi);

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-3">
          <SectionTitle icon={Building2} label="Fondi che lo detengono" className="mb-2" />
          <div className="h-24 animate-pulse rounded bg-muted/40" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle icon={Building2} label="Fondi che lo detengono" className="mb-2" />
        {fondi.length === 0 ? (
          <div className="py-3 text-center text-sm text-muted-foreground">
            Nessun fondo tracciato detiene questo titolo.
          </div>
        ) : (
          <>
            <Riepilogo fondi={fondi} />
            <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[0.7059rem] text-muted-foreground">
                Barra = peso nel portafoglio del fondo · 13F al {dataBreve(r.periodo)}
              </span>
              <div className="flex rounded-md border p-0.5" role="group" aria-label="Ordina i fondi">
                {(["peso", "valore"] as const).map((o) => (
                  <button
                    key={o}
                    type="button"
                    onClick={() => setOrdine(o)}
                    aria-pressed={ordine === o}
                    className={cn(
                      "min-h-[28px] rounded px-2 text-xs font-semibold capitalize transition-colors",
                      ordine === o ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {o}
                  </button>
                ))}
              </div>
            </div>
            <ul>
              {visibili.map((h) => (
                <Riga key={`${h.institutional_id}-${h.period_end_date}`} h={h} maxPeso={maxPeso} />
              ))}
            </ul>
            {fondi.length > PRIME && (
              <button
                type="button"
                onClick={() => setTutti((t) => !t)}
                className="mt-1 inline-flex min-h-[32px] items-center gap-1 text-xs font-medium text-primary hover:underline"
                aria-expanded={tutti}
              >
                {tutti ? <ChevronUp className="h-3.5 w-3.5" aria-hidden /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
                {tutti ? "Mostra i primi 10" : `Mostra tutti i ${fondi.length}`}
              </button>
            )}
          </>
        )}
        {storici.length > 0 && (
          <div className="mt-2 border-t border-border/40 pt-1">
            <button
              type="button"
              onClick={() => setUsciti((u) => !u)}
              className="inline-flex min-h-[32px] items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
              aria-expanded={usciti}
            >
              {usciti ? <ChevronUp className="h-3.5 w-3.5" aria-hidden /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
              Usciti di recente ({storici.length})
            </button>
            {usciti && (
              <ul className="mt-1 space-y-1">
                {storici.map((h) => (
                  <li key={`${h.institutional_id}-${h.period_end_date}`}
                    className="flex min-w-0 items-baseline justify-between gap-2 text-xs text-muted-foreground">
                    <Link to={`/institutionals/${h.institutional_slug}`} className="min-w-0 truncate hover:underline"
                      title={h.institutional_name}>
                      {h.institutional_name}
                    </Link>
                    <span className="shrink-0 tabular-nums">
                      {h.portfolio_pct == null ? "—" : `${h.portfolio_pct.toFixed(1)}%`} · {fmtBig(h.value_usd)} · {dataBreve(h.period_end_date)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
