import { type ReactNode, useLayoutEffect, useMemo, useRef, useState } from "react";

import { LARGHEZZA_DI_RIPIEGO, tacche } from "@/lib/graficoSvg";
import { cn } from "@/lib/utils";

/* ─── Un grafico in SVG scritto a mano (FA-137) ───────────────────────────
 *
 * Al posto di recharts, che portava ~330 kB per cinque grafici semplici:
 * linee e barre su un asse di CATEGORIE (bin, trimestri, date), uno o due
 * assi Y, linee di riferimento, griglia e un tooltip al passaggio. Il grafico
 * a candele della pagina titolo resta lightweight-charts.
 *
 * ⚠️ Cosa non fa, di proposito: zoom, animazioni, assi temporali continui.
 * Un grafico che ne ha bisogno usa lightweight-charts.
 *
 * La larghezza segue il contenitore (ResizeObserver); in jsdom, dove non c'e',
 * resta `LARGHEZZA_DI_RIPIEGO`. L'altezza e' quella del contenitore se
 * `altezza` manca: il chiamante la fissa con le classi, come faceva con
 * `ResponsiveContainer`. */

export type SerieGrafico<T> = {
  chiave: string;
  nome?: string;
  valore: (riga: T) => number | null | undefined;
  colore: string;
  tipo?: "linea" | "barre";
  spessore?: number;
  tratteggio?: string;
  /** Punti sui vertici della linea. */
  punti?: boolean;
  asse?: "sx" | "dx";
  /** Colore della singola barra (es. per esito). */
  coloreBarra?: (riga: T, i: number) => string;
  opacita?: number;
  /** Salta i buchi invece di spezzare la linea (il `connectNulls` di prima). */
  connetti?: boolean;
};

export type RiferimentoGrafico = { y: number; asse?: "sx" | "dx"; tratteggio?: string; colore?: string };

/** FA-194: un'area fra due valori per riga (la banda 10°-90° di un percorso). */
export type BandaGrafico<T> = {
  chiave: string;
  da: (riga: T) => number | null | undefined;
  a: (riga: T) => number | null | undefined;
  colore: string;
  opacita?: number;
  asse?: "sx" | "dx";
};

type Props<T> = {
  dati: T[];
  x: (riga: T) => string;
  serie: SerieGrafico<T>[];
  altezza?: number;
  formatoY?: (v: number) => string;
  formatoYDx?: (v: number) => string;
  formatoX?: (etichetta: string) => string;
  /** Mostra un'etichetta dell'asse X ogni N (0 = automatico). */
  ogniX?: number;
  riferimenti?: RiferimentoGrafico[];
  /** Aree fra due valori, sotto le linee (FA-194). */
  bande?: BandaGrafico<T>[];
  /** Linee verticali sugli indici dati (il giorno di un evento, FA-194). */
  verticali?: number[];
  /** Includi lo zero nella scala di sinistra (sempre vero con le barre). */
  zero?: boolean;
  tooltip?: (riga: T) => ReactNode;
  etichetta: string;
  className?: string;
};


const M = { alto: 8, basso: 20, sx: 40, dx: 8, dxAsse: 44 };

function estremi(valori: number[], conZero: boolean): [number, number] {
  let lo = Math.min(...valori);
  let hi = Math.max(...valori);
  if (conZero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.05;
  return [conZero && lo === 0 ? 0 : lo - pad, conZero && hi === 0 ? 0 : hi + pad];
}

function useLarghezza() {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(LARGHEZZA_DI_RIPIEGO);
  const [h, setH] = useState(0);
  // ⚠️ La misura si prende PRIMA del disegno (A-40). Con il solo osservatore
  // la prima larghezza era il ripiego da 600px, e se la sua callback tardava
  // (scheda in background, misurato una volta a 375px) il grafico restava
  // largo 600 in un contenitore da 289 e perdeva i mesi di destra. In un
  // layout effect lo stato aggiornato si disegna nello stesso fotogramma.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const misura = (larghezza: number, altezza: number) => {
      setW(Math.max(120, Math.round(larghezza)));
      setH(Math.round(altezza));
    };
    if (el.clientWidth > 0) misura(el.clientWidth, el.clientHeight);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => misura(e.contentRect.width, e.contentRect.height));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, w, h };
}

export function GraficoSvg<T>({
  dati, x, serie, altezza, formatoY = (v) => String(v), formatoYDx, formatoX = (s) => s,
  ogniX = 0, riferimenti = [], bande = [], verticali = [], zero = false, tooltip, etichetta, className,
}: Props<T>) {
  const { ref, w, h: hContenitore } = useLarghezza();
  const [attivo, setAttivo] = useState<number | null>(null);
  const H = altezza ?? (hContenitore > 40 ? hContenitore : 200);
  const conDx = serie.some((s) => s.asse === "dx");
  const ml = M.sx;
  const mr = conDx ? M.dxAsse : M.dx;
  const larg = Math.max(10, w - ml - mr);
  const alt = Math.max(10, H - M.alto - M.basso);
  const n = dati.length;

  const scale = useMemo(() => {
    const per = (asse: "sx" | "dx") => {
      const s = serie.filter((x) => (x.asse ?? "sx") === asse);
      const v = s.flatMap((x) => dati.map((r) => x.valore(r))).filter(
        (v): v is number => v != null && Number.isFinite(v));
      riferimenti.filter((r) => (r.asse ?? "sx") === asse).forEach((r) => v.push(r.y));
      bande.filter((b) => (b.asse ?? "sx") === asse).forEach((b) => dati.forEach((r) => {
        for (const x of [b.da(r), b.a(r)]) if (x != null && Number.isFinite(x)) v.push(x);
      }));
      if (v.length === 0) return null;
      const barre = s.some((x) => x.tipo === "barre");
      const [lo, hi] = estremi(v, barre || (asse === "sx" && zero));
      return { lo, hi, y: (val: number) => M.alto + alt - ((val - lo) / (hi - lo)) * alt };
    };
    return { sx: per("sx"), dx: per("dx") };
  }, [dati, serie, riferimenti, bande, zero, alt]);

  const banda = n > 0 ? larg / n : larg;
  const cx = (i: number) => ml + banda * (i + 0.5);
  const barre = serie.filter((s) => s.tipo === "barre");
  const passoX = ogniX > 0 ? ogniX : Math.max(1, Math.ceil(n / Math.max(1, Math.floor(larg / 56))));

  const percorso = (s: SerieGrafico<T>) => {
    const sc = scale[s.asse ?? "sx"];
    if (!sc) return "";
    let d = "";
    let aperto = false;
    dati.forEach((r, i) => {
      const v = s.valore(r);
      if (v == null || !Number.isFinite(v)) { if (!s.connetti) aperto = false; return; }
      d += `${aperto ? "L" : "M"}${cx(i).toFixed(1)},${sc.y(v).toFixed(1)}`;
      aperto = true;
    });
    return d;
  };

  const sx = scale.sx;
  return (
    <div ref={ref} className={cn("relative h-full w-full", className)}>
      <svg
        width={w}
        height={H}
        style={{ maxWidth: "100%" }}
        viewBox={`0 0 ${w} ${H}`}
        role="img"
        aria-label={etichetta}
        // Da tastiera come col mouse (B-61): il grafico si raggiunge col Tab
        // e le frecce spostano il punto attivo, con lo stesso riquadro dei
        // valori. Fuori fuoco il punto torna libero.
        tabIndex={0}
        className="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onKeyDown={(e) => {
          if (n === 0) return;
          if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
            e.preventDefault();
            const passo = e.key === "ArrowRight" ? 1 : -1;
            setAttivo((a) => Math.min(n - 1, Math.max(0, (a ?? (passo > 0 ? -1 : n)) + passo)));
          } else if (e.key === "Home") {
            e.preventDefault();
            setAttivo(0);
          } else if (e.key === "End") {
            e.preventDefault();
            setAttivo(n - 1);
          } else if (e.key === "Escape") {
            setAttivo(null);
          }
        }}
        onBlur={() => setAttivo(null)}
        onMouseLeave={() => setAttivo(null)}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const px = e.clientX - box.left - ml;
          const i = Math.floor(px / banda);
          setAttivo(i >= 0 && i < n ? i : null);
        }}
      >
        {sx && tacche(sx.lo, sx.hi).map((t) => (
          <g key={`g${t}`}>
            <line x1={ml} x2={ml + larg} y1={sx.y(t)} y2={sx.y(t)} stroke="hsl(var(--border))" strokeDasharray="3 3" />
            <text x={ml - 4} y={sx.y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="hsl(var(--muted-foreground))">
              {formatoY(t)}
            </text>
          </g>
        ))}
        {scale.dx && tacche(scale.dx.lo, scale.dx.hi).map((t) => (
          <text key={`d${t}`} x={ml + larg + 4} y={scale.dx!.y(t)} dy="0.32em" fontSize={11}
            fill="hsl(var(--muted-foreground))">
            {(formatoYDx ?? formatoY)(t)}
          </text>
        ))}
        {dati.map((r, i) => (i % passoX === 0 ? (
          <text key={`x${i}`} x={cx(i)} y={H - 4} textAnchor="middle" fontSize={11} fill="hsl(var(--muted-foreground))">
            {formatoX(x(r))}
          </text>
        ) : null))}
        {riferimenti.map((rf, k) => {
          const sc = scale[rf.asse ?? "sx"];
          return sc ? (
            <line key={`r${k}`} x1={ml} x2={ml + larg} y1={sc.y(rf.y)} y2={sc.y(rf.y)}
              stroke={rf.colore ?? "hsl(var(--muted-foreground))"} strokeOpacity={0.6}
              strokeDasharray={rf.tratteggio} />
          ) : null;
        })}
        {bande.map((b) => {
          const sc = scale[b.asse ?? "sx"];
          if (!sc) return null;
          const sopra: string[] = [];
          const sotto: string[] = [];
          dati.forEach((r, i) => {
            const da = b.da(r);
            const a = b.a(r);
            if (da == null || a == null || !Number.isFinite(da) || !Number.isFinite(a)) return;
            sopra.push(`${cx(i).toFixed(1)},${sc.y(a).toFixed(1)}`);
            sotto.unshift(`${cx(i).toFixed(1)},${sc.y(da).toFixed(1)}`);
          });
          return sopra.length > 1 ? (
            <polygon key={b.chiave} points={[...sopra, ...sotto].join(" ")} fill={b.colore}
              fillOpacity={b.opacita ?? 0.18} stroke="none" />
          ) : null;
        })}
        {verticali.filter((i) => i >= 0 && i < n).map((i) => (
          <line key={`v${i}`} x1={cx(i)} x2={cx(i)} y1={M.alto} y2={M.alto + alt}
            stroke="hsl(var(--muted-foreground))" strokeOpacity={0.7} strokeDasharray="4 3" />
        ))}
        {barre.map((s, b) => {
          const sc = scale[s.asse ?? "sx"];
          if (!sc) return null;
          const lb = (banda * 0.7) / barre.length;
          return (
            <g key={s.chiave}>
              {dati.map((r, i) => {
                const v = s.valore(r);
                if (v == null || !Number.isFinite(v)) return null;
                const y0 = sc.y(Math.max(Math.min(0, sc.hi), sc.lo));
                const y1 = sc.y(v);
                return (
                  <rect key={i} x={ml + banda * i + banda * 0.15 + lb * b} width={Math.max(1, lb - 1)}
                    y={Math.min(y0, y1)} height={Math.max(1, Math.abs(y1 - y0))}
                    fill={s.coloreBarra ? s.coloreBarra(r, i) : s.colore} fillOpacity={s.opacita ?? 1} rx={1.5} />
                );
              })}
            </g>
          );
        })}
        {serie.filter((s) => s.tipo !== "barre").map((s) => {
          const sc = scale[s.asse ?? "sx"];
          return (
            <g key={s.chiave}>
              <path d={percorso(s)} fill="none" stroke={s.colore} strokeWidth={s.spessore ?? 1.5}
                strokeDasharray={s.tratteggio} strokeLinejoin="round" strokeLinecap="round" />
              {sc && (s.punti || attivo != null) && dati.map((r, i) => {
                const v = s.valore(r);
                if (v == null || !Number.isFinite(v) || (!s.punti && i !== attivo)) return null;
                return <circle key={i} cx={cx(i)} cy={sc.y(v)} r={i === attivo ? 4 : 2.5} fill={s.colore} />;
              })}
            </g>
          );
        })}
        {attivo != null && (
          <line x1={cx(attivo)} x2={cx(attivo)} y1={M.alto} y2={M.alto + alt}
            stroke="hsl(var(--muted-foreground))" strokeOpacity={0.4} />
        )}
      </svg>
      {/* I dati come tabella per i lettori di schermo (B-61): l'etichetta del
          grafico diceva che cosa misura, non i numeri. */}
      <table className="sr-only">
        <caption>{etichetta}</caption>
        <thead>
          <tr>
            <th scope="col">Periodo</th>
            {serie.map((s) => <th key={s.chiave} scope="col">{s.nome ?? s.chiave}</th>)}
          </tr>
        </thead>
        <tbody>
          {dati.map((r, i) => (
            <tr key={i}>
              <th scope="row">{formatoX(x(r))}</th>
              {serie.map((s) => {
                const v = s.valore(r);
                return (
                  <td key={s.chiave}>
                    {v == null || !Number.isFinite(v) ? "—" : (s.asse === "dx" && formatoYDx ? formatoYDx : formatoY)(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {attivo != null && dati[attivo] != null && (
        // Annunciato quando il punto cambia da tastiera.
        <div aria-live="polite" className="sr-only">
          {formatoX(x(dati[attivo]))}
        </div>
      )}
      {attivo != null && dati[attivo] != null && (
        <div
          className="pointer-events-none absolute top-1 z-10 rounded-md border border-border bg-background px-2 py-1 text-xs shadow-sm"
          style={cx(attivo) > w / 2 ? { right: w - cx(attivo) + 8 } : { left: cx(attivo) + 8 }}
        >
          {tooltip ? tooltip(dati[attivo]) : (
            <>
              <div className="font-medium">{formatoX(x(dati[attivo]))}</div>
              {serie.map((s) => {
                const v = s.valore(dati[attivo]);
                return v == null ? null : (
                  <div key={s.chiave} className="flex items-center gap-1.5 tabular-nums">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.colore }} />
                    {s.nome ?? s.chiave}: {(s.asse === "dx" && formatoYDx ? formatoYDx : formatoY)(v)}
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}
    </div>
  );
}
