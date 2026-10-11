import { ArrowDown, ArrowUp, ArrowUpDown, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import type { SectorPerformanceRow, SectorsPerformance } from "@/hooks/useSectorDetail";
import { formatRendimento, quota, tonoRendimento } from "@/lib/sectorPerformance";
import { cn } from "@/lib/utils";

/* ─── I rendimenti di tutti i settori (2026-10-11) ─────────────────────────
 *
 * La pagina Esplora confrontava i settori per punteggio, e nessun numero
 * diceva quale fosse SALITO. Una riga per settore, sei finestre, la quota
 * sopra la media a 200 sedute, e l'S&P 500 in testa come riferimento.
 *
 * ⚠️ Il blocco arriva da un endpoint lento (qualche secondo a freddo) e la
 * pagina e' sotto il cancello CLS. Tre cose lo tengono fermo: righe di
 * altezza fissa, gia' disegnate coi nomi dall'overview mentre carica; colonne
 * a larghezza fissa (`table-fixed`), perche' «…» e «+12.3%» non sono larghi
 * uguale; e righe segnaposto con chiavi PROPRIE, perche' all'arrivo dei dati
 * le righe si riordinano per rendimento e React, con le stesse chiavi,
 * SPOSTEREBBE i nodi — uno spostamento che il cancello conta. Nodi nuovi al
 * posto dei vecchi non spostano niente. */

const FINESTRE = ["1s", "1m", "3m", "ytd", "1a"] as const;
const ETICHETTE: Record<(typeof FINESTRE)[number], string> = {
  "1s": "1 sett.", "1m": "1 mese", "3m": "3 mesi", ytd: "YTD", "1a": "1 anno",
};
type Chiave = "ultimo" | (typeof FINESTRE)[number] | "ema200";

function valore(r: SectorPerformanceRow, k: Chiave): number | null {
  if (k === "ultimo") return r.ultimo_giorno ?? null;
  if (k === "ema200") return quota(r.sopra_ema200);
  return r.rendimenti.find((x) => x.finestra === k)?.settore ?? null;
}

export function SectorReturnsTable({ dati, settori, isLoading }: {
  dati: SectorsPerformance | undefined;
  /** I nomi dall'overview: le righe esistono prima che arrivino i numeri. */
  settori: string[];
  isLoading: boolean;
}) {
  const [chiave, setChiave] = useState<Chiave>("1m");
  const [verso, setVerso] = useState<"desc" | "asc">("desc");
  const perNome = useMemo(() => new Map((dati?.settori ?? []).map((r) => [r.name, r])), [dati]);
  const ordinati = useMemo(() => {
    const nomi = [...settori];
    if (!dati) return nomi;
    return nomi.sort((a, b) => {
      const va = perNome.get(a) ? valore(perNome.get(a)!, chiave) : null;
      const vb = perNome.get(b) ? valore(perNome.get(b)!, chiave) : null;
      if (va == null && vb == null) return a.localeCompare(b);
      if (va == null) return 1;
      if (vb == null) return -1;
      return verso === "desc" ? vb - va : va - vb;
    });
  }, [settori, dati, perNome, chiave, verso]);
  const spy = (k: string) => dati?.spy.find((x) => x.finestra === k)?.settore ?? null;

  function ordina(k: Chiave) {
    if (k === chiave) setVerso((v) => (v === "desc" ? "asc" : "desc"));
    else {
      setChiave(k);
      setVerso("desc");
    }
  }

  const colonne: { k: Chiave; label: string }[] = [
    { k: "ultimo", label: "Oggi" },
    ...FINESTRE.map((f) => ({ k: f as Chiave, label: ETICHETTE[f] })),
    { k: "ema200", label: "Sopra EMA200" },
  ];

  return (
    <Card className="min-w-0">
      <CardContent className="p-4">
        <SectionTitle
          icon={TrendingUp}
          label="Rendimenti dei settori"
          className="mb-1"
        />
        <p className="mb-3 text-xs text-muted-foreground">
          Indici a pesi uguali dei titoli di ciascun settore, l'S&P 500 come riferimento. Clicca una colonna per ordinare.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] table-fixed text-sm tabular-nums">
            <colgroup>
              <col className="w-[26%]" />
              {colonne.map((c) => (
                <col key={c.k} className={c.k === "ema200" ? "w-[16%]" : "w-[9.66%]"} />
              ))}
            </colgroup>
            <thead>
              <tr className="text-[0.6765rem] uppercase tracking-wider text-muted-foreground">
                <th className="py-1.5 text-left font-semibold">Settore</th>
                {colonne.map((c) => {
                  const attiva = c.k === chiave;
                  const Freccia = attiva ? (verso === "desc" ? ArrowDown : ArrowUp) : ArrowUpDown;
                  return (
                    <th key={c.k} className="py-1.5 text-right font-semibold" aria-sort={attiva ? (verso === "desc" ? "descending" : "ascending") : "none"}>
                      <button
                        type="button"
                        onClick={() => ordina(c.k)}
                        className={cn("inline-flex min-h-[28px] items-center gap-1 uppercase tracking-wider hover:text-foreground", attiva && "text-foreground")}
                      >
                        {c.label}
                        <Freccia className={cn("h-3 w-3", !attiva && "opacity-40")} aria-hidden />
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {/* Niente sfondo: rose-600 su un grigio scende sotto 4,5:1 (CLAUDE.md). */}
              <tr className="h-9 border-t border-border/60">
                <td className="pr-2 font-semibold whitespace-nowrap">S&P 500</td>
                <td className="text-right text-muted-foreground">—</td>
                {FINESTRE.map((f) => (
                  <td key={f} className={cn("text-right font-semibold", isLoading ? "text-muted-foreground" : tonoRendimento(spy(f)))}>
                    {isLoading ? "…" : formatRendimento(spy(f))}
                  </td>
                ))}
                <td className="text-right text-muted-foreground">—</td>
              </tr>
              {ordinati.map((nome, i) => {
                const r = perNome.get(nome);
                return (
                  <tr key={dati ? nome : `attesa-${i}`} className="h-9 border-t border-border/40 hover:bg-muted/30">
                    <td className="max-w-[14rem] truncate pr-2 whitespace-nowrap">
                      <Link to={`/sectors/${encodeURIComponent(nome)}`} className="font-medium hover:underline">
                        {nome}
                      </Link>
                    </td>
                    {colonne.slice(0, -1).map((c) => {
                      const v = r ? valore(r, c.k) : null;
                      return (
                        <td key={c.k} className={cn("text-right", c.k === chiave ? "font-bold" : "font-medium",
                          r ? tonoRendimento(v) : "text-muted-foreground")}>
                          {r ? formatRendimento(v) : isLoading ? "…" : "—"}
                        </td>
                      );
                    })}
                    <td className="text-right">
                      <Ema200 r={r} isLoading={isLoading} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function Ema200({ r, isLoading }: { r: SectorPerformanceRow | undefined; isLoading: boolean }) {
  const pct = r ? quota(r.sopra_ema200) : null;
  if (pct == null) return <span className="text-muted-foreground">{isLoading ? "…" : "—"}</span>;
  return (
    <span className="inline-flex items-center justify-end gap-2">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-muted" aria-hidden>
        <span className="block h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </span>
      <span className="w-9 font-semibold">{pct}%</span>
    </span>
  );
}
