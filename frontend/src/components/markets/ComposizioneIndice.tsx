import { Link } from "react-router-dom";

import type { Composizione, Costituente } from "@/hooks/useMercati";
import { numero, percentuale } from "@/lib/numeri";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";
import { cn } from "@/lib/utils";

/* ─── La composizione di un indice (FA-186) ───────────────────────────────
 *
 * Sette indici del paniere hanno i costituenti nel catalogo, con l'ampiezza
 * gia' calcolata a ogni scansione. Qui la pagina dell'indice la mostra:
 * quanti salgono e quanti scendono, quanti stanno sopra le medie, i settori,
 * chi tira e chi frena. Ogni numero porta il suo denominatore. ⚠️ Le
 * variazioni dei costituenti sono in PUNTI percentuali (dal server). */

function tono(v: number | null | undefined): string {
  return v == null || v === 0 ? "text-muted-foreground" : v > 0 ? TESTO_SU : TESTO_GIU;
}

function data(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("it-IT", { day: "numeric", month: "numeric", year: "numeric" });
}

function Tessera({ nome, valore, su }: { nome: string; valore: string; su?: string }) {
  return (
    <div className="min-w-0 rounded-md bg-muted/30 px-2.5 py-2">
      <dt className="text-[0.7059rem] uppercase leading-tight tracking-wider text-muted-foreground">{nome}</dt>
      <dd className="text-lg font-bold tabular-nums leading-tight">{valore}</dd>
      {su && <dd className="text-[0.7059rem] text-muted-foreground">{su}</dd>}
    </div>
  );
}

function Elenco({ titolo, righe, conContributo }: { titolo: string; righe: Costituente[]; conContributo: boolean }) {
  return (
    <div className="min-w-0">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{titolo}</h3>
      <ul className="divide-y divide-border/40">
        {righe.map((t) => (
          <li key={t.ticker}>
            <Link to={`/stocks/${encodeURIComponent(t.ticker)}`} className="flex items-center gap-2 py-1 text-sm hover:underline">
              <span className="w-16 shrink-0 font-semibold">{t.ticker}</span>
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{t.nome}</span>
              <span className={cn("shrink-0 font-semibold tabular-nums", tono(t.var_pct))}>{percentuale(t.var_pct)}</span>
              {conContributo && (
                <span className="hidden w-20 shrink-0 text-right text-xs tabular-nums text-muted-foreground sm:block"
                  title="Contributo stimato: peso di capitalizzazione nel catalogo per la variazione">
                  {/* Sotto lo 0,01% non si scrive: accanto ai migliori di oggi
                      sarebbe una colonna di zeri (un titolo piccolo pesa poco). */}
                  {t.contributo_pp == null || Math.abs(t.contributo_pp) < 0.005 ? "" : percentuale(t.contributo_pp, 2)}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ComposizioneIndice({ c }: { c: Composizione }) {
  const a = c.ampiezza;
  const tot = a.avanzano + a.scendono;
  const quotaSu = tot > 0 ? (a.avanzano / tot) * 100 : 50;
  const n = c.indice.titoli_nel_catalogo;
  const conContributo = !c.indice.pesato_sul_prezzo;
  const maxPeso = Math.max(1, ...c.settori.map((s) => s.peso_pct ?? s.titoli));
  return (
    <section className="space-y-4" aria-label={`Composizione di ${c.indice.nome}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">Composizione · {c.indice.nome}</h2>
          <p className="text-xs text-muted-foreground">
            {n} titoli nel catalogo{c.alla_scansione_del ? `, alla scansione del ${data(c.alla_scansione_del)}` : ""}.
            {c.indice.nota ? ` ${c.indice.nota}` : ""}
          </p>
        </div>
        <Link to={`/stocks?index=${encodeURIComponent(c.indice.code)}`}
          className="text-sm font-medium text-primary hover:underline">
          Apri i {n} titoli nello screener →
        </Link>
      </div>

      <div className="space-y-1">
        <div className="flex h-2.5 overflow-hidden rounded-full bg-muted" role="img"
          aria-label={`${a.avanzano} titoli in rialzo e ${a.scendono} in ribasso`}>
          <div className="bg-emerald-500" style={{ width: `${quotaSu}%` }} />
          <div className="flex-1 bg-rose-500" />
        </div>
        <p className="flex justify-between text-xs tabular-nums">
          <span className={TESTO_SU}>{a.avanzano} in rialzo</span>
          <span className="text-muted-foreground">variazione media {percentuale(a.var_media_pct)}</span>
          <span className={TESTO_GIU}>{a.scendono} in ribasso</span>
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Tessera nome="Sopra la media a 50" valore={a.sopra_ema50_pct == null ? "—" : `${numero(a.sopra_ema50_pct, 0)}%`} su={`su ${n}`} />
        <Tessera nome="Sopra la media a 200" valore={a.sopra_ema200_pct == null ? "—" : `${numero(a.sopra_ema200_pct, 0)}%`} su={`su ${n}`} />
        <Tessera nome="Nuovi massimi a 52 sett." valore={String(a.nuovi_massimi_52s)} su={`su ${n}`} />
        <Tessera nome="Nuovi minimi a 52 sett." valore={String(a.nuovi_minimi_52s)} su={`su ${n}`} />
      </dl>

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr] [&>*]:min-w-0">
        <div className="min-w-0">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Settori {conContributo ? "per peso" : "per numero di titoli"}
          </h3>
          <ul className="space-y-1">
            {c.settori.slice(0, 8).map((s) => {
              const misura = s.peso_pct ?? s.titoli;
              return (
                <li key={s.settore} className="text-xs">
                  <div className="flex justify-between gap-2">
                    <span className="truncate">{s.settore}</span>
                    <span className="shrink-0 tabular-nums">
                      {s.peso_pct != null ? `${numero(s.peso_pct, 0)}%` : `${s.titoli} titoli`}
                      <span className={cn("ml-2", tono(s.var_media_pct))}>{percentuale(s.var_media_pct, 1)}</span>
                    </span>
                  </div>
                  <div className="mt-0.5 h-1.5 rounded bg-muted">
                    <div className="h-1.5 rounded bg-primary/60" style={{ width: `${(misura / maxPeso) * 100}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
        <Elenco titolo="I migliori di oggi" righe={c.migliori} conContributo={conContributo} />
        <Elenco titolo="I peggiori di oggi" righe={c.peggiori} conContributo={conContributo} />
      </div>
      {conContributo ? (
        <p className="text-xs text-muted-foreground">
          Il contributo è stimato sulla capitalizzazione del catalogo, non sui pesi ufficiali dell&apos;indice.
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Indice pesato sul prezzo: i pesi di capitalizzazione non lo descrivono, quindi niente contributi.
        </p>
      )}
    </section>
  );
}
