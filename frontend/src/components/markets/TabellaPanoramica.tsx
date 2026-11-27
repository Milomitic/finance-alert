import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Segmentato } from "@/components/ui/segmentato";
import { useIsPhone } from "@/hooks/useMediaQuery";
import { percentuale } from "@/lib/numeri";
import { ordinaPer, type RigaUnita, valoreColonna as valore } from "@/lib/panoramica";
import { prezzoMercato } from "@/lib/prezzoMercato";
import { type PeriodoTinta, tintaRendimento } from "@/lib/tintaRendimento";
import { cn } from "@/lib/utils";

/* ─── Panoramica dei rendimenti (FA-184) ──────────────────────────────────
 *
 * La domanda che la home non copre: come stanno andando i mercati su
 * settimane e mesi. Prezzo e «Oggi» sono quelli vivi del paniere; i periodi
 * sono alla chiusura giornaliera che la pagina dichiara. Computer: tabella
 * ordinabile con la prima colonna ferma. Telefono: un periodo alla volta,
 * nessuno scorrimento laterale. */

const CATEGORIE: { id: string; titolo: string }[] = [
  { id: "index", titolo: "Indici" },
  { id: "commodity", titolo: "Materie prime" },
  { id: "crypto", titolo: "Cripto" },
];

type Colonna = { id: string; titolo: string; periodo: PeriodoTinta };
const PERIODI: Colonna[] = [
  { id: "oggi", titolo: "Oggi", periodo: "oggi" },
  { id: "1s", titolo: "1S", periodo: "1s" },
  { id: "1m", titolo: "1M", periodo: "1m" },
  { id: "3m", titolo: "3M", periodo: "3m" },
  { id: "ytd", titolo: "YTD", periodo: "ytd" },
  { id: "1a", titolo: "1A", periodo: "1a" },
];

function pp(v: number | null | undefined, decimali = 1): string {
  return v == null ? "—" : percentuale(v * 100, decimali);
}

function Bandiera({ flag }: { flag: string | null }) {
  return flag ? (
    <img src={`/flags/${flag}.svg`} alt="" width={18} height={12} className="h-3 w-[18px] shrink-0 rounded-sm object-cover" />
  ) : null;
}

/** La posizione fra minimo e massimo delle 52 settimane, come un punto su una linea. */
function Barra52({ r }: { r: RigaUnita }) {
  if (r.posizione_52s == null) return <span className="text-muted-foreground">—</span>;
  const x = Math.max(0, Math.min(1, r.posizione_52s)) * 100;
  return (
    <span className="relative inline-block h-3 w-20 align-middle"
      title={`Minimo ${prezzoMercato(r.minimo_52s?.valore, r.category)} · massimo ${prezzoMercato(r.massimo_52s?.valore, r.category)}`}>
      <span className="absolute left-0 right-0 top-1/2 h-px bg-border" />
      <span className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary" style={{ left: `${x}%` }} />
      <span className="sr-only">{Math.round(x)}% della distanza fra minimo e massimo a 52 settimane</span>
    </span>
  );
}

type Ordine = { col: string; giu: boolean } | null;

/** Un'intestazione ordinabile: primo clic decrescente, secondo crescente,
 *  terzo torna all'ordine del server. Fuori dal componente (static-components). */
function Intestazione({ id, titolo, ordine, onOrdina }: {
  id: string; titolo: string; ordine: Ordine; onOrdina: (o: Ordine) => void;
}) {
  const attivo = ordine?.col === id;
  return (
    <th scope="col" className="px-2 py-1.5 text-right font-medium"
      aria-sort={attivo ? (ordine!.giu ? "descending" : "ascending") : "none"}>
      <button type="button" className="hover:text-foreground"
        onClick={() => onOrdina(attivo && ordine!.giu ? { col: id, giu: false } : attivo ? null : { col: id, giu: true })}>
        {titolo}{attivo ? (ordine!.giu ? " ↓" : " ↑") : ""}
      </button>
    </th>
  );
}

export function TabellaPanoramica({ righe, allaChiusuraDel }: { righe: RigaUnita[]; allaChiusuraDel: string | null }) {
  const isPhone = useIsPhone();
  const [ordine, setOrdine] = useState<Ordine>(null);
  const [periodo, setPeriodo] = useState("oggi");

  const gruppi = useMemo(() => CATEGORIE.map((c) => {
    const g = righe.filter((r) => r.category === c.id);
    return { ...c, righe: ordine ? ordinaPer(g, ordine.col, ordine.giu) : g };
  }).filter((g) => g.righe.length > 0), [righe, ordine]);

  const nota = allaChiusuraDel && (
    <p className="text-xs text-muted-foreground">
      «Oggi» e il prezzo sono in tempo reale; i periodi alla chiusura del {allaChiusuraDel.split("-").reverse().join("/")}.
    </p>
  );

  if (isPhone) {
    const col = PERIODI.find((p) => p.id === periodo) ?? PERIODI[0];
    return (
      <div className="space-y-3">
        <Segmentato etichetta="Periodo" valore={periodo} onCambia={setPeriodo}
          voci={PERIODI.filter((p) => p.id !== "3m").map((p) => ({ id: p.id, label: p.titolo }))} />
        {gruppi.map((g) => (
          <section key={g.id} aria-label={g.titolo}>
            <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{g.titolo}</h2>
            <ul className="divide-y divide-border/40">
              {g.righe.map((r) => {
                const v = valore(r, col.id);
                return (
                  <li key={r.symbol}>
                    <Link to={`/markets/${encodeURIComponent(r.symbol)}`} className="flex items-center gap-3 py-2">
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5 text-sm font-semibold"><Bandiera flag={r.flag} /><span className="truncate">{r.name}</span></span>
                        <span className="text-xs text-muted-foreground">{r.symbol}</span>
                      </span>
                      <span className="flex shrink-0 flex-col items-end tabular-nums">
                        <span className="text-sm">{prezzoMercato(r.prezzo, r.category)}</span>
                        <span className={cn("rounded px-1 text-xs font-semibold", tintaRendimento(v, col.periodo))}>{pp(v, col.id === "oggi" ? 2 : 1)}</span>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
        {nota}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-sm tabular-nums">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th scope="col" className="sticky left-0 z-10 bg-card px-2 py-1.5 text-left font-medium">Strumento</th>
              <th scope="col" className="px-2 py-1.5 text-right font-medium">Ultimo</th>
              {PERIODI.map((p) => <Intestazione key={p.id} id={p.id} titolo={p.titolo} ordine={ordine} onOrdina={setOrdine} />)}
              <th scope="col" className="px-2 py-1.5 text-center font-medium">52 settimane</th>
              <Intestazione id="max" titolo="Dal massimo" ordine={ordine} onOrdina={setOrdine} />
              <Intestazione id="vol" titolo="Vol. 20g" ordine={ordine} onOrdina={setOrdine} />
            </tr>
          </thead>
          {gruppi.map((g) => (
            <tbody key={g.id}>
              <tr><th colSpan={12} scope="colgroup" className="sticky left-0 bg-card px-2 pb-1 pt-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{g.titolo}</th></tr>
              {g.righe.map((r) => (
                <tr key={r.symbol} className="border-b border-border/40 hover:bg-muted/30">
                  <th scope="row" className="sticky left-0 z-10 bg-card px-2 py-1.5 text-left font-normal">
                    <Link to={`/markets/${encodeURIComponent(r.symbol)}`} className="flex items-center gap-1.5 hover:underline">
                      <Bandiera flag={r.flag} />
                      <span className="font-semibold">{r.name}</span>
                      <span className="text-xs text-muted-foreground">{r.symbol}</span>
                    </Link>
                  </th>
                  <td className="px-2 py-1.5 text-right">
                    {prezzoMercato(r.prezzo, r.category)}
                    {r.usaFuture && <span className="ml-1 text-[0.65rem] text-muted-foreground" title="Borsa chiusa: prezzo del future">fut.</span>}
                  </td>
                  {PERIODI.map((p) => {
                    const v = valore(r, p.id);
                    return <td key={p.id} className={cn("px-2 py-1.5 text-right", tintaRendimento(v, p.periodo))}>{pp(v, p.id === "oggi" ? 2 : 1)}</td>;
                  })}
                  <td className="px-2 py-1.5 text-center"><Barra52 r={r} /></td>
                  <td className="px-2 py-1.5 text-right">{pp(r.dal_massimo_storico?.distanza)}</td>
                  <td className="px-2 py-1.5 text-right">{pp(r.vol_20g, 0)}</td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      {nota}
    </div>
  );
}
