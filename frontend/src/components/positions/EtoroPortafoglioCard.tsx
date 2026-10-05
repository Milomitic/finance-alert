import { ChevronDown, RefreshCw, Wallet } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { EtoroConto, EtoroPortafoglio, EtoroPosizione } from "@/api/etoro";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { EtoroDaAbbinare } from "@/components/positions/EtoroDaAbbinare";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useSincronizzaEtoro } from "@/hooks/useEtoro";
import { etichettaLato, fmtPct, raggruppaPerStrumento, type GruppoStrumento } from "@/lib/etoroPortafoglio";
import { formatMoney, formatMoneySigned } from "@/lib/money";
import { cn } from "@/lib/utils";

/* ─── Il portafoglio eToro (FA-124) ───────────────────────────────────────
 *
 * Una riga per STRUMENTO, il dettaglio delle singole posizioni a un tocco:
 * vedi `lib/etoroPortafoglio`. Tutti i numeri in dollari sono di eToro, nella
 * valuta del conto; i prezzi sono nella valuta dello strumento.
 *
 * Su un CFD a leva ×5 le due grandezze che contano non sono il prezzo: sono
 * il P/L in % del MARGINE e quanto del margine si perde se scatta lo stop.
 * Sono a schermo per questo, e per la stessa ragione una posizione senza stop
 * si dice esplicitamente.
 */

function tono(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-muted-foreground";
  return v > 0 ? "text-emerald-800 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
}

function ora(iso: string): string {
  return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

function giorno(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

function Cifra({ etichetta, children, className }: { etichetta: string; children: React.ReactNode; className?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[0.6471rem] font-semibold uppercase tracking-wider text-muted-foreground">{etichetta}</div>
      <div className={cn("text-sm font-semibold tabular-nums", className)}>{children}</div>
    </div>
  );
}

function Conto({ conto }: { conto: EtoroConto }) {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-md border bg-muted/20 px-3 py-2">
      <Cifra etichetta="Valore del conto">{formatMoney(conto.valore_totale, "USD")}</Cifra>
      <Cifra etichetta="Oggi" className={tono(conto.guadagno_giorno)}>
        {formatMoneySigned(conto.guadagno_giorno, "USD")}{" "}
        <span className="text-xs">({fmtPct(conto.guadagno_giorno_pct, 2)})</span>
      </Cifra>
      <Cifra etichetta="P/L aperto" className={tono(conto.pnl_aperto)}>
        {formatMoneySigned(conto.pnl_aperto, "USD")}
      </Cifra>
      <Cifra etichetta="Cassa disponibile">{formatMoney(conto.credito_usd, "USD")}</Cifra>
    </div>
  );
}

function Identita({ g }: { g: GruppoStrumento }) {
  const nome = g.ticker ?? g.simbolo ?? `#${g.instrumentId}`;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <StockLogo ticker={g.ticker ?? g.simbolo} size="xs" />
      <div className="min-w-0">
        <div className="flex min-w-0 items-baseline gap-1.5">
          {g.ticker ? (
            <Link to={`/stocks/${encodeURIComponent(g.ticker)}`} className="shrink-0 text-sm font-bold hover:underline">
              {nome}
            </Link>
          ) : (
            <span className="shrink-0 text-sm font-bold">{nome}</span>
          )}
          {g.nome && <span className="min-w-0 truncate text-xs text-muted-foreground" title={g.nome}>{g.nome}</span>}
        </div>
        <div className="text-xs text-muted-foreground">
          {etichettaLato(g)} · {g.posizioni.length} {g.posizioni.length === 1 ? "posizione" : "posizioni"}
          {!g.ticker && " · non abbinato al catalogo"}
        </div>
      </div>
    </div>
  );
}

function Dettaglio({ p, valuta }: { p: EtoroPosizione; valuta: string | null }) {
  return (
    <li className="grid grid-cols-2 gap-x-4 gap-y-1 py-2 text-xs sm:grid-cols-4">
      <div>
        <span className="text-muted-foreground">Aperta il </span>
        <span className="tabular-nums">{giorno(p.aperta_il)}</span>
      </div>
      <div className="tabular-nums">
        {formatMoney(p.prezzo_apertura, valuta)} → {formatMoney(p.prezzo_corrente, valuta)}
      </div>
      <div className="tabular-nums">
        <span className="text-muted-foreground">Margine </span>
        {formatMoney(p.margine_usd ?? p.importo_usd, "USD")}
      </div>
      <div className={cn("tabular-nums font-semibold", tono(p.pnl_usd))}>
        {formatMoneySigned(p.pnl_usd, "USD")} ({fmtPct(p.pnl_pct_margine)})
      </div>
      <div className="col-span-2 tabular-nums sm:col-span-4">
        <span className="text-muted-foreground">Stop </span>
        {p.stop != null ? (
          <>
            {formatMoney(p.stop, valuta)}{" "}
            <span className="text-rose-600 dark:text-rose-400">({fmtPct(p.stop_pct_margine)} del margine)</span>
          </>
        ) : (
          <span className="font-semibold text-rose-600 dark:text-rose-400">nessuno</span>
        )}
        <span className="text-muted-foreground"> · Target </span>
        {p.target != null ? formatMoney(p.target, valuta) : "nessuno"}
        {p.commissioni_usd != null && p.commissioni_usd !== 0 && (
          <>
            <span className="text-muted-foreground"> · Overnight e dividendi </span>
            {formatMoneySigned(-p.commissioni_usd, "USD")}
          </>
        )}
        {p.copia && <span className="text-muted-foreground"> · da copy trading</span>}
      </div>
    </li>
  );
}

function RigaStrumento({ g }: { g: GruppoStrumento }) {
  const [aperto, setAperto] = useState(false);
  const idDettaglio = `etoro-dettaglio-${g.instrumentId}`;
  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Identita g={g} />
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <Cifra etichetta="Margine">{formatMoney(g.margineUsd, "USD")}</Cifra>
          <Cifra etichetta="Esposizione">{formatMoney(g.esposizioneUsd, "USD")}</Cifra>
          <Cifra etichetta="P/L" className={tono(g.pnlUsd)}>
            {formatMoneySigned(g.pnlUsd, "USD")} <span className="text-xs">({fmtPct(g.pnlPctMargine)})</span>
          </Cifra>
          <Cifra etichetta="Stop peggiore" className="text-rose-600 dark:text-rose-400">
            {g.senzaStop > 0 ? `${g.senzaStop} senza stop` : fmtPct(g.stopPeggiorePct)}
          </Cifra>
          <button
            type="button"
            onClick={() => setAperto(!aperto)}
            aria-expanded={aperto}
            aria-controls={aperto ? idDettaglio : undefined}
            aria-label={`${aperto ? "Nascondi" : "Mostra"} le posizioni su ${g.ticker ?? g.simbolo ?? g.instrumentId}`}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border/60 text-muted-foreground hover:bg-muted"
          >
            <ChevronDown className={cn("h-4 w-4 transition-transform", aperto && "rotate-180")} aria-hidden />
          </button>
        </div>
      </div>
      {aperto && (
        <ul id={idDettaglio} className="mt-1 divide-y divide-border/40 rounded-md bg-muted/20 px-3">
          {g.posizioni.map((p) => <Dettaglio key={p.position_id} p={p} valuta={g.valuta} />)}
        </ul>
      )}
    </li>
  );
}

const MOTIVO: Record<string, string> = {
  stop: "a stop", target: "a target", chiusa: "chiusa", non_trovata: "non trovata nello storico",
};

function Chiuse({ chiuse }: { chiuse: EtoroPosizione[] }) {
  if (chiuse.length === 0) return null;
  return (
    <div>
      <div className="mb-1 text-[0.6471rem] font-semibold uppercase tracking-wider text-muted-foreground">
        Chiuse negli ultimi 30 giorni
      </div>
      <ul className="divide-y divide-border/40">
        {chiuse.map((p) => (
          <li key={p.position_id} className="flex flex-wrap items-baseline gap-x-3 py-1.5 text-xs">
            <span className="font-semibold">{p.ticker ?? p.simbolo ?? `#${p.instrument_id}`}</span>
            <span className="text-muted-foreground">
              {p.lato === "long" ? "Long" : "Short"} ×{p.leva} · {MOTIVO[p.motivo_chiusura ?? "chiusa"]} il{" "}
              {p.chiusa_il ? giorno(p.chiusa_il) : "—"}
            </span>
            <span className={cn("ml-auto font-semibold tabular-nums", tono(p.profitto_netto_usd))}>
              {formatMoneySigned(p.profitto_netto_usd, "USD")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** I dati arrivano dalla PAGINA, che aspetta sia le posizioni manuali sia
 *  questo portafoglio prima di disegnare: una scheda che cambia altezza a dati
 *  arrivati sposterebbe tutto cio' che sta sotto (FA-106, gate CLS 0,1). */
export function EtoroPortafoglioCard({ d, errore }: { d: EtoroPortafoglio | undefined; errore: boolean }) {
  const sync = useSincronizzaEtoro();
  if (errore || !d) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-red-600 dark:text-red-400">
          Portafoglio eToro non disponibile.
        </CardContent>
      </Card>
    );
  }
  if (!d.configurato) {
    return (
      <Card>
        <CardContent className="space-y-1 p-4">
          <SectionTitle icon={Wallet} label="Portafoglio eToro" />
          <p className="text-sm text-muted-foreground">
            Non collegato. Servono la chiave pubblica e una chiave utente in sola lettura, da eToro →
            Impostazioni → Trading → API Key Management, in <code>ETORO_API_KEY</code> e{" "}
            <code>ETORO_USER_KEY</code>.
          </p>
        </CardContent>
      </Card>
    );
  }
  const gruppi = raggruppaPerStrumento(d.aperte);
  const doppioni = gruppi.filter((g) => g.ancheManuale).map((g) => g.ticker);
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <SectionTitle
          icon={Wallet}
          label="Portafoglio eToro"
          right={
            <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
              {d.conto && <span>aggiornato alle {ora(d.conto.aggiornato_il)}</span>}
              <button
                type="button"
                onClick={() => sync.mutate()}
                disabled={sync.isPending}
                aria-label="Sincronizza adesso con eToro"
                className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border/60 hover:bg-muted disabled:opacity-50"
              >
                <RefreshCw className={cn("h-3.5 w-3.5", sync.isPending && "animate-spin")} aria-hidden />
              </button>
            </span>
          }
        />
        {sync.isError && (
          <p className="text-xs text-red-600 dark:text-red-400">
            Sincronizzazione non riuscita: {sync.error instanceof Error ? sync.error.message : "errore"}
          </p>
        )}
        {d.conto && <Conto conto={d.conto} />}
        {doppioni.length > 0 && (
          <p className="text-xs text-muted-foreground">
            {doppioni.join(", ")} {doppioni.length === 1 ? "è" : "sono"} anche fra le posizioni inserite a
            mano qui sotto: quella manuale ora è un doppione e si può chiudere.
          </p>
        )}
        <EtoroDaAbbinare lista={d.da_decidere} />
        {gruppi.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">Nessuna posizione aperta su eToro.</p>
        ) : (
          <ul className="divide-y divide-border/40">
            {gruppi.map((g) => <RigaStrumento key={g.instrumentId} g={g} />)}
          </ul>
        )}
        <Chiuse chiuse={d.chiuse} />
        {(d.preferiti_da_etoro > 0 || d.watchlist_fuori_catalogo > 0) && (
          <p className="text-xs text-muted-foreground">
            Dalle tue watchlist eToro: <span className="font-semibold text-foreground">{d.preferiti_da_etoro}</span>{" "}
            {d.preferiti_da_etoro === 1 ? "preferito" : "preferiti"}
            {d.watchlist_fuori_catalogo > 0 &&
              ` · ${d.watchlist_fuori_catalogo} strumenti non sono nel catalogo (crypto, materie prime o titoli non coperti)`}
            . «Recently Invested» resta fuori.
          </p>
        )}
        <EtoroDaAbbinare
          lista={d.watchlist_da_confermare}
          titolo="Dalle watchlist, da confermare"
          spiegazione="Il simbolo c'è nel catalogo ma il nome è diverso: confermalo e diventa un preferito."
        />
      </CardContent>
    </Card>
  );
}
