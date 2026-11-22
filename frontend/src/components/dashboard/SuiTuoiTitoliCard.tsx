import { useQuery } from "@tanstack/react-query";
import { Briefcase, CalendarClock, Gavel, Newspaper, Star } from "lucide-react";
import { Children, cloneElement, isValidElement, type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { dashboard, type AnalistaMio, type NotiziaMia, type TrimestraleMia } from "@/api/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { quandoTrimestrale, tempoFa } from "@/lib/suiTuoiTitoli";
import { cn } from "@/lib/utils";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";

/* ─── Sui tuoi titoli (FA-149) ────────────────────────────────────────────
 *
 * Che cosa succede ai titoli in posizione e fra i preferiti: trimestrali
 * vicine, cambi di rating, notizie. I movimenti di oggi stanno gia' nel conto
 * eToro e nella striscia dei preferiti, quindi qui non si ripetono.
 *
 * ⚠️ Altezza FISSA per sezione, a ogni larghezza: la scheda sta in cima al
 * cruscotto, e crescere quando arrivano i dati spingerebbe giu' tutta la
 * pagina (tetto CLS del gate UI). Le liste scorrono dentro. */

const CHIAVE_TITOLI = "dashboard.suituoititoli.pieni";

/** Senza ricordo si assume che i titoli ci siano: e' il caso di chi usa la
 *  pagina (posizioni e preferiti), e il gate, col seme che ha posizioni,
 *  lo misura cosi'. Solo un «0» ricordato accorcia lo scheletro. */
function leggiAveaTitoli(): boolean {
  try {
    return localStorage.getItem(CHIAVE_TITOLI) !== "0";
  } catch {
    return true;
  }
}

function ricordaAveaTitoli(v: boolean): void {
  try {
    localStorage.setItem(CHIAVE_TITOLI, v ? "1" : "0");
  } catch {
    /* nessun ricordo: lo scheletro alla prossima apertura e' quello corto */
  }
}

/** ⚠️ Altezza fissa SOLO da lg (regola «One scroll context below lg» in
 *  index.css): sotto i 1024px lo scorrimento interno delle schede e'
 *  spento, e con un'altezza fissa il contenuto usciva dal riquadro e si
 *  sovrapponeva alle sezioni sotto (segnalato da telefono il 2026-11-22).
 *  Su telefono le sezioni crescono, ma mostrano le prime cinque voci. */
const SEZIONE = "lg:h-[188px] overflow-y-auto";
const PRIME_SU_TELEFONO = 5;

function Segno({ r }: { r: string }) {
  return (
    <span className="shrink-0">
      {r === "posizione" ? (
        <Briefcase className="h-3 w-3 text-muted-foreground" aria-hidden />
      ) : (
        <Star className="h-3 w-3 fill-amber-400 text-amber-700 dark:fill-amber-300 dark:text-amber-300" aria-hidden />
      )}
      <span className="sr-only">{r === "posizione" ? "in posizione" : "preferito"}</span>
    </span>
  );
}

function Ticker({ t }: { t: string }) {
  return (
    <Link to={`/stocks/${encodeURIComponent(t)}`} className="shrink-0 font-semibold hover:underline">
      {t}
    </Link>
  );
}

function Sezione({ icona, titolo, vuoto, children, n }: {
  icona: ReactNode; titolo: string; vuoto: string; children: ReactNode; n: number;
}) {
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {icona}
        {titolo}
      </div>
      <div className={SEZIONE}>
        {n === 0 ? <p className="py-2 text-xs text-muted-foreground">{vuoto}</p> : (
          <>
            {/* Oltre la quinta voce le righe spariscono sotto lg. In JS e non
                con una variante arbitraria di Tailwind, che il purger non ha
                generato (verificato sul CSS prodotto). */}
            <ul className="space-y-1">
              {Children.map(children, (c, i) =>
                i >= PRIME_SU_TELEFONO && isValidElement<{ className?: string }>(c)
                  ? cloneElement(c, { className: cn(c.props.className, "max-lg:hidden") })
                  : c)}
            </ul>
            {n > PRIME_SU_TELEFONO && (
              <p className="pt-1 text-xs text-muted-foreground lg:hidden">+{n - PRIME_SU_TELEFONO} altre</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function RigaTrimestrale({ t }: { t: TrimestraleMia }) {
  return (
    <li className="flex items-center gap-1.5 text-sm">
      <Segno r={t.rilevanza} />
      <Ticker t={t.ticker} />
      <span className="min-w-0 truncate text-xs text-muted-foreground">{t.nome}</span>
      <span className="ml-auto shrink-0 text-xs tabular-nums">{quandoTrimestrale(t)}</span>
    </li>
  );
}

function RigaAnalista({ a }: { a: AnalistaMio }) {
  const su = a.azione === "up";
  const giu = a.azione === "down";
  return (
    <li className="flex items-center gap-1.5 text-sm">
      <Segno r={a.rilevanza} />
      <Ticker t={a.ticker} />
      <span className={cn("shrink-0 text-xs font-medium",
        su && TESTO_SU, giu && TESTO_GIU)}>
        {su ? "↑" : giu ? "↓" : "•"} {a.a}
      </span>
      <span className="min-w-0 truncate text-xs text-muted-foreground">
        {a.da ? `da ${a.da} · ` : ""}{a.societa}
      </span>
    </li>
  );
}

function RigaNotizia({ n, adesso }: { n: NotiziaMia; adesso: number }) {
  return (
    <li className="text-sm">
      <div className="flex items-center gap-1.5">
        <Segno r={n.rilevanza} />
        <Ticker t={n.ticker} />
        <span className="min-w-0 truncate text-xs text-muted-foreground">
          {n.fonte} · {tempoFa(n.pubblicata, adesso)}
        </span>
      </div>
      {n.link ? (
        <a href={n.link} target="_blank" rel="noopener noreferrer" className="line-clamp-1 text-xs hover:underline">
          {n.titolo}
        </a>
      ) : (
        <span className="line-clamp-1 text-xs">{n.titolo}</span>
      )}
    </li>
  );
}

export function SuiTuoiTitoliCard() {
  const q = useQuery({
    queryKey: ["dashboard", "sui-tuoi-titoli"],
    queryFn: ({ signal }) => dashboard.suiTuoiTitoli(signal),
    staleTime: 5 * 60_000,
  });
  const d = q.data;
  // Fissato al montaggio: «3 h fa» non deve cambiare a ogni render.
  const [adesso] = useState(() => Date.now());
  // Lo scheletro prende l'altezza che la scheda aveva l'ultima volta. Su
  // telefono le tre sezioni si impilano (~470px) e il messaggio «nessun
  // titolo» ne occupa 148: uno scheletro sempre a tre sezioni faceva risalire
  // tutta la pagina sotto quando arrivava la risposta (CLS 0,15 nel gate).
  const [aveaTitoli] = useState(leggiAveaTitoli);
  const titoliNoti = d?.titoli;
  useEffect(() => {
    if (titoliNoti != null) ricordaAveaTitoli(titoliNoti > 0);
  }, [titoliNoti]);

  return (
    <Card>
      <CardContent className="space-y-2 p-3">
        <SectionTitle icon={Briefcase} label="Sui tuoi titoli" />
        {q.isError ? (
          <div className="flex h-[148px] md:h-[188px] items-center">
            <QueryError message="dei tuoi titoli" errore={q.error} onRetry={q.refetch} isRetrying={q.isFetching} />
          </div>
        ) : !d && !aveaTitoli ? (
          <div className="h-[148px] md:h-[188px] animate-pulse rounded-md bg-muted/40" aria-hidden />
        ) : !d ? (
          <div className="grid gap-3 md:grid-cols-3" aria-hidden>
            {[0, 1, 2].map((i) => (
              <div key={i} className={cn(SEZIONE, "animate-pulse rounded-md bg-muted/40")} />
            ))}
          </div>
        ) : d.titoli === 0 ? (
          <p className="flex h-[148px] md:h-[188px] items-center text-sm text-muted-foreground">
            Nessun titolo in posizione o fra i preferiti: segnane uno con la stella dal suo dettaglio.
          </p>
        ) : (
          <div className="grid gap-3 md:grid-cols-3">
            <Sezione icona={<CalendarClock className="h-3.5 w-3.5" aria-hidden />} titolo="Trimestrali"
              vuoto="Nessuna trimestrale nei prossimi 14 giorni." n={d.trimestrali.length}>
              {d.trimestrali.map((t) => <RigaTrimestrale key={t.ticker} t={t} />)}
            </Sezione>
            <Sezione icona={<Gavel className="h-3.5 w-3.5" aria-hidden />} titolo="Analisti"
              vuoto="Nessun cambio di rating negli ultimi 30 giorni." n={d.analisti.length}>
              {d.analisti.map((a, i) => <RigaAnalista key={`${a.ticker}-${a.data}-${a.societa}-${i}`} a={a} />)}
            </Sezione>
            <Sezione icona={<Newspaper className="h-3.5 w-3.5" aria-hidden />} titolo="Notizie"
              vuoto="Nessuna notizia negli ultimi 3 giorni." n={d.notizie.length}>
              {d.notizie.map((n, i) => <RigaNotizia key={`${n.ticker}-${i}`} n={n} adesso={adesso} />)}
            </Sezione>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
