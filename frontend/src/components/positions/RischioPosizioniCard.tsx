import { ShieldAlert } from "lucide-react";
import { useState } from "react";

import type {
  EtoroPrimoPassaggio,
  EtoroRischio,
  EtoroRischioPosizione,
} from "@/api/etoro";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { Button } from "@/components/ui/button";
import { HintLabel } from "@/components/ui/info-hint";
import { formatMoney, formatMoneySigned } from "@/lib/money";
import { cn } from "@/lib/utils";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";

/* ─── Il rischio delle posizioni aperte (FA-143, FA-144, FA-145) ──────────
 *
 * Tutto descrittivo: quanto manca allo stop, come si e' comportato lo
 * strumento nelle finestre passate con stop e target alle distanze di oggi,
 * quanta esposizione c'e' su ciascun sottostante, una stima lineare sotto
 * scenario e il costo di tenere aperto. Niente qui dice che cosa fare, e la
 * frase in testa lo dichiara.
 *
 * ⚠️ Altezza riservata mentre carica (`min-h`): la scheda sta fra il conto e
 * le posizioni manuali, e comparire dopo spingerebbe giu' la pagina (il tetto
 * CLS del gate UI e' 0,1). */

const MIN_H = "min-h-[18rem]";

function pct(v: number | null | undefined, cifre = 1): string {
  return v == null ? "—" : `${v.toFixed(cifre)}%`;
}

function num(v: number | null | undefined, cifre = 1): string {
  return v == null ? "—" : v.toFixed(cifre).replace(".", ",");
}

function anno(iso: string): string {
  return iso.slice(0, 4);
}

function PrimoPassaggio({ g }: { g: EtoroPrimoPassaggio | null }) {
  if (!g) {
    return (
      <p className="text-xs text-muted-foreground">
        Storia insufficiente per la frequenza passata (servono almeno 252 sedute), o stop non impostato.
      </p>
    );
  }
  const q = (n: number) => (n / g.finestre) * 100;
  return (
    <div className="space-y-1">
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={`Su ${g.finestre} finestre: stop prima ${g.stop}, target prima ${g.target}, nessuno dei due ${g.nessuno}`}
      >
        <span className="bg-rose-500" style={{ width: `${q(g.stop)}%` }} />
        <span className="bg-emerald-500" style={{ width: `${q(g.target)}%` }} />
      </div>
      <p className="text-xs text-muted-foreground">
        Su {g.finestre} finestre da {g.orizzonte} sedute dal {anno(g.dal)}:{" "}
        <span className={TESTO_GIU}>stop prima {g.stop}</span>
        {" · "}
        <span className={TESTO_SU}>target prima {g.target}</span>
        {" · "}nessuno {g.nessuno}. Quota stop {pct(q(g.stop), 0)} (intervallo {g.stop_pct_ci[0].toFixed(0)}–
        {g.stop_pct_ci[1].toFixed(0)}%).
      </p>
    </div>
  );
}

function Posizione({ p }: { p: EtoroRischioPosizione }) {
  const c = p.costo_tenuta;
  return (
    <div className="space-y-1.5 border-t border-border/50 pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="text-sm font-bold">{p.ticker}</span>
        <span className="text-xs text-muted-foreground">
          {p.lato === "long" ? "Long" : "Short"} ×{p.leva} · esposizione {formatMoney(p.esposizione_usd, "USD")}
        </span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs">
        <span>
          <span className="text-muted-foreground">Allo stop </span>
          <span className={cn("font-semibold tabular-nums",
            p.distanza_stop_pct != null && p.distanza_stop_pct <= 0 && TESTO_GIU)}>
            {pct(p.distanza_stop_pct)}
          </span>
          {p.distanza_stop_atr != null && (
            <span className="text-muted-foreground"> · {num(p.distanza_stop_atr)} ATR</span>
          )}
          {p.distanza_stop_sedute != null && (
            <span className="text-muted-foreground"> · ~{num(p.distanza_stop_sedute)} sedute tipiche</span>
          )}
        </span>
        {p.distanza_target_pct != null && (
          <span>
            <span className="text-muted-foreground">Al target </span>
            <span className="font-semibold tabular-nums">{pct(p.distanza_target_pct)}</span>
          </span>
        )}
      </div>
      <PrimoPassaggio g={p.primo_passaggio} />
      {c && (
        <p className="text-xs text-muted-foreground">
          Costo di tenuta: pagato finora {c.pagate_usd != null ? formatMoney(c.pagate_usd, "USD") : "—"}
          {c.settimana_usd != null && (
            <>
              {" · "}previsto {formatMoney(c.settimana_usd, "USD")} a settimana,{" "}
              {formatMoney(c.settimane_4_usd ?? 0, "USD")} in 4 settimane,{" "}
              {formatMoney(c.settimane_12_usd ?? 0, "USD")} in 12
            </>
          )}
        </p>
      )}
    </div>
  );
}

function coppie(d: EtoroRischio): { a: string; b: string; r: number }[] {
  const { titoli, matrice } = d.correlazione;
  if (!matrice) return [];
  const out = [];
  for (let i = 0; i < titoli.length; i++) {
    for (let j = i + 1; j < titoli.length; j++) out.push({ a: titoli[i], b: titoli[j], r: matrice[i][j] });
  }
  return out.sort((x, y) => Math.abs(y.r) - Math.abs(x.r)).slice(0, 5);
}

const PRIME_POSIZIONI = 4;

function ElencoPosizioni({ posizioni }: { posizioni: EtoroRischioPosizione[] }) {
  const [tutte, setTutte] = useState(false);
  const visibili = tutte ? posizioni : posizioni.slice(0, PRIME_POSIZIONI);
  return (
    <div className="space-y-3">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Per posizione</div>
      {visibili.map((p) => <Posizione key={p.position_id} p={p} />)}
      {posizioni.length > PRIME_POSIZIONI && (
        <Button type="button" variant="link" size="testo" className="text-xs" aria-expanded={tutte} onClick={() => setTutte((t) => !t)}>
          {tutte ? "Mostra meno" : `Mostra tutte le ${posizioni.length} posizioni`}
        </Button>
      )}
    </div>
  );
}

export function RischioPosizioniCard({
  d, caricamento, errore,
}: { d: EtoroRischio | undefined; caricamento: boolean; errore: boolean }) {
  if (!caricamento && !errore && (!d || d.posizioni.length === 0)) return null;
  return (
    <Card className={MIN_H}>
      <CardContent className="space-y-4 p-4">
        <div>
          <SectionTitle icon={ShieldAlert} label="Rischio delle posizioni" className="mb-1" />
          <p className="text-xs text-muted-foreground">
            Statistica storica degli strumenti, non una previsione né un consiglio.
          </p>
        </div>
        {caricamento ? (
          <div className="h-48 animate-pulse rounded-md bg-muted/50" aria-hidden />
        ) : errore || !d ? (
          <p className="text-sm text-muted-foreground">Rischio non disponibile in questo momento.</p>
        ) : (
          <>
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
              <span>
                <span className="text-muted-foreground">Esposizione </span>
                <span className="font-semibold">{formatMoney(d.esposizione_totale, "USD")}</span>
              </span>
              {d.leva_effettiva != null && (
                <span>
                  <span className="text-muted-foreground">Leva effettiva sul conto </span>
                  <span className="font-semibold">{num(d.leva_effettiva)}×</span>
                </span>
              )}
              {d.posizioni_effettive != null && (
                <span>
                  {/* La spiegazione al tocco, non in title (D-39b). */}
                  <HintLabel text="Quante posizioni indipendenti valgono, data la correlazione dei rendimenti a 60 sedute: 1 vuol dire una scommessa sola." className="text-muted-foreground">Posizioni indipendenti</HintLabel>{" "}
                  <span className="font-semibold">{num(d.posizioni_effettive)}</span>
                </span>
              )}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Esposizione per sottostante
                </div>
                <ul className="space-y-0.5 text-sm">
                  {d.per_sottostante.map((v) => (
                    <li key={v.nome} className="flex justify-between gap-3">
                      <span className="min-w-0 truncate">{v.nome}</span>
                      <span className="tabular-nums">{formatMoneySigned(v.usd, "USD")}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-xs text-muted-foreground">
                  Un fondo a leva conta per il suo multiplo: 1.000 su SOXL sono 3.000 sui semiconduttori.
                </p>
              </div>
              <div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Se l&apos;indice si muove in un giorno
                </div>
                <ul className="space-y-0.5 text-sm">
                  {d.scenario.map((s) => (
                    <li key={`${s.indice}${s.shock_pct}`} className="flex justify-between gap-3">
                      <span className="min-w-0 truncate">{s.indice} {s.shock_pct > 0 ? "+" : s.shock_pct < 0 ? "−" : ""}{Math.abs(s.shock_pct).toFixed(0)}%</span>
                      <span className={cn("tabular-nums",
                        s.pnl_usd < 0 ? TESTO_GIU : TESTO_SU)}>
                        {formatMoneySigned(s.pnl_usd, "USD")}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-xs text-muted-foreground">
                  Stima lineare dal beta a un anno. Un ETF a leva su più giorni non è lineare: si allontana da
                  questa cifra quanto più il mercato oscilla.
                </p>
              </div>
            </div>

            {/* ⚠️ Dopo gli aggregati (D-39): un blocco per posizione eToro
                erano ~1.500px prima di esposizione e scenario, le uniche
                letture d'insieme. Le prime quattro, le altre a richiesta. */}
            <ElencoPosizioni posizioni={d.posizioni} />

            {coppie(d).length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Correlazione a {d.correlazione.sedute} sedute
                </div>
                <ul className="space-y-0.5 text-sm">
                  {coppie(d).map((c) => (
                    <li key={`${c.a}-${c.b}`} className="flex justify-between gap-3">
                      <span>{c.a} · {c.b}</span>
                      <span className="tabular-nums">{num(c.r, 2)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
