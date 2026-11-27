import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useId } from "react";

import { api } from "@/api/client";
import { stocks } from "@/api/stocks";
import { Button } from "@/components/ui/button";
import { useLiveAssets } from "@/hooks/useLiveAssets";
import { useIsPhone } from "@/hooks/useMediaQuery";
import { MODELLI, type Modello, type ParametriStudio } from "@/lib/studio";
import { cn } from "@/lib/utils";

/* ─── Il modulo dello Studio, scritto come la domanda (FA-199) ────────────
 *
 * Prima: una fila di campi con le etichette dei modelli («Variazione %», «in
 * sedute») e il simbolo da sapere a memoria. Ora la domanda si legge come
 * una frase, con i campi dentro: «Se AAPL è sceso del 10% o più in 5 sedute,
 * cosa è successo nelle 21 dopo?». Il simbolo si cerca fra titoli e mercati,
 * la serie macro si sceglie per nome. */

const DOPO_MAX = 10;
const CAMPO = "h-8 rounded-md border border-input bg-background px-1.5 text-sm";

type SerieMacro = { id: string; nome: string; rilasci: number };

/** Il simbolo, con i suggerimenti da titoli del catalogo e mercati. */
export function CampoSimbolo({ valore, onCambia }: { valore: string; onCambia: (v: string) => void }) {
  const id = useId();
  const q = valore.trim();
  const mercati = useLiveAssets({ attivo: q.length > 0 });
  const titoli = useQuery({
    queryKey: ["studio", "cerca", q.toUpperCase()],
    queryFn: ({ signal }) => stocks.search({ q, limit: 8 }, signal),
    enabled: q.length >= 1,
    staleTime: 60_000,
  });
  const qq = q.toLowerCase();
  const suggeriti = [
    ...(mercati.data?.assets ?? [])
      .filter((a) => a.symbol.toLowerCase().includes(qq) || a.name.toLowerCase().includes(qq))
      .map((a) => ({ valore: a.symbol, nome: a.name })),
    ...(titoli.data?.items ?? []).map((t) => ({ valore: t.stock.ticker, nome: t.stock.name ?? "" })),
  ].slice(0, 12);
  return (
    <>
      <input aria-label="Simbolo: un titolo o un mercato" list={id} value={valore} placeholder="AAPL, ^GSPC"
        onChange={(e) => onCambia(e.target.value)}
        className={cn(CAMPO, "w-28 font-semibold uppercase")} autoComplete="off" />
      <datalist id={id}>
        {suggeriti.map((s) => <option key={s.valore} value={s.valore}>{s.nome}</option>)}
      </datalist>
    </>
  );
}

function Numero({ etichetta, valore, min, max, onCambia, largo = "w-14" }: {
  etichetta: string; valore: number; min: number; max: number; onCambia: (v: number) => void; largo?: string;
}) {
  return (
    <input type="number" aria-label={`${etichetta} (da ${min} a ${max})`} min={min} max={max} value={valore}
      onChange={(e) => onCambia(Number(e.target.value))} className={cn(CAMPO, largo, "text-center")} />
  );
}

export function ModuloStudio({ bozza, onBozza, onCalcola }: {
  bozza: ParametriStudio;
  onBozza: (p: ParametriStudio) => void;
  onCalcola: () => void;
}) {
  const isPhone = useIsPhone();
  const serieMacro = useQuery({
    queryKey: ["studio", "serie_macro"],
    queryFn: ({ signal }) => api<SerieMacro[]>("/api/studio/serie_macro", { signal }),
    enabled: bozza.modello === "evento" && bozza.tipo === "macro",
    staleTime: 60 * 60_000,
  });
  const imposta = (p: Partial<ParametriStudio>) => onBozza({ ...bozza, ...p });
  const scegliModello = (id: Modello) => imposta({
    modello: id,
    // D-82: gli eventi arrivano a 10 sedute.
    orizzonte: id === "evento" ? Math.min(bozza.orizzonte, DOPO_MAX) : bozza.orizzonte,
  });
  const invia = (e: FormEvent) => {
    e.preventDefault();
    onCalcola();
  };
  const sceso = bozza.soglia < 0;
  const entita = Math.abs(bozza.soglia);
  const simbolo = <CampoSimbolo valore={bozza.simbolo} onCambia={(v) => imposta({ simbolo: v })} />;

  return (
    <form onSubmit={invia} className="space-y-3">
      {isPhone ? (
        // FA-192: i tre modelli uscivano dal bordo a 375 px.
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Domanda
          <select className={CAMPO} value={bozza.modello} onChange={(e) => scegliModello(e.target.value as Modello)}>
            {MODELLI.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </label>
      ) : (
        <div role="group" aria-label="Domanda" className="flex flex-wrap gap-1">
          {MODELLI.map((m) => (
            <button key={m.id} type="button" aria-pressed={bozza.modello === m.id} onClick={() => scegliModello(m.id)}
              className={cn("rounded-md border px-2.5 py-1 text-sm",
                bozza.modello === m.id ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent")}>
              {m.label}
            </button>
          ))}
        </div>
      )}

      <p className="flex flex-wrap items-center gap-x-1.5 gap-y-2 text-sm leading-8">
        {bozza.modello === "dopo_movimento" && (
          <>
            <span>Se</span>{simbolo}<span>è</span>
            <select aria-label="Verso del movimento" className={CAMPO} value={sceso ? "giu" : "su"}
              onChange={(e) => imposta({ soglia: (e.target.value === "giu" ? -1 : 1) * Math.max(1, entita) })}>
              <option value="giu">sceso</option>
              <option value="su">salito</option>
            </select>
            <span>del</span>
            <Numero etichetta="Entità del movimento in percentuale" valore={entita} min={1} max={sceso ? 90 : 500}
              onCambia={(v) => imposta({ soglia: (sceso ? -1 : 1) * Math.max(1, v) })} />
            <span>% o più in</span>
            <Numero etichetta="Sedute del movimento" valore={bozza.sedute} min={1} max={63} onCambia={(v) => imposta({ sedute: v })} />
            <span>sedute, cosa è successo nelle</span>
            <Numero etichetta="Sedute dopo" valore={bozza.orizzonte} min={1} max={252} onCambia={(v) => imposta({ orizzonte: v })} />
            <span>dopo?</span>
          </>
        )}
        {bozza.modello === "stagionalita" && (
          <>
            <span>In quali mesi e giorni</span>{simbolo}<span>è andato meglio, e con quale regolarità?</span>
          </>
        )}
        {bozza.modello === "evento" && (
          <>
            <span>Cosa fa</span>{simbolo}<span>nelle</span>
            <Numero etichetta="Sedute attorno all'evento" valore={Math.min(bozza.orizzonte, DOPO_MAX)} min={1} max={DOPO_MAX}
              onCambia={(v) => imposta({ orizzonte: v })} />
            <span>sedute attorno</span>
            <select aria-label="Evento" className={CAMPO} value={bozza.tipo}
              onChange={(e) => imposta({ tipo: e.target.value as "trimestrali" | "macro" })}>
              <option value="trimestrali">alle sue trimestrali</option>
              <option value="macro">ai rilasci di</option>
            </select>
            {bozza.tipo === "macro" && (
              <select aria-label="Serie macro" className={cn(CAMPO, "max-w-full")} value={bozza.serie}
                onChange={(e) => imposta({ serie: e.target.value })}>
                <option value="">scegli una serie…</option>
                {(serieMacro.data ?? []).map((s) => (
                  <option key={s.id} value={s.id}>{s.nome} ({s.rilasci} rilasci)</option>
                ))}
              </select>
            )}
            <span>?</span>
          </>
        )}
      </p>

      <div className="flex items-center gap-2">
        <Button type="submit" variant="default" disabled={bozza.simbolo.trim() === "" || (bozza.modello === "evento" && bozza.tipo === "macro" && !bozza.serie)}>
          Calcola
        </Button>
        <span className="text-xs text-muted-foreground">Che cosa è successo, non che cosa succederà.</span>
      </div>
    </form>
  );
}
