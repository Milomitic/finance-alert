import { Card, CardContent } from "@/components/ui/card";
import { InfoHint } from "@/components/ui/info-hint";
import { cn } from "@/lib/utils";

/* ─── Una metrica a schermo, in evidenza o compatta ─────────────────────────
 *
 * Due livelli e non uno: sopra una tabella lunga, otto tessere tutte uguali
 * si leggono come un muro, e la metrica che risponde alla domanda della
 * pagina («funziona?») pesa quanto un conteggio di servizio. La variante
 * `primary` ha numero grande e bordo colorato; le altre stanno in una riga
 * compatta sotto.
 *
 * ⚠️ Il colore segue il TONO dichiarato dal chiamante, mai il valore: un
 * «54%» verde su un campione non concludente affermerebbe un risultato che il
 * dato non regge. Le classi sono letterali (CLAUDE.md, purger di Tailwind).
 */
export interface MetricTileProps {
  label: string;
  value: string;
  /** Cifra o intervallo che accompagna il valore: resta SEMPRE a schermo. */
  hint?: string;
  /** Spiegazione in prosa, dietro un tocco. */
  note?: string;
  tone?: "ok" | "bad" | null;
  primary?: boolean;
}

export function MetricTile({ label, value, hint, note, tone, primary = false }: MetricTileProps) {
  return (
    <Card
      data-metrica={primary ? "principale" : "secondaria"}
      className={cn(primary && "border-primary/40 bg-primary/[0.04] shadow-sm")}
    >
      <CardContent className={primary ? "p-3.5" : "px-3 py-2"}>
        {/* ⚠️ A capo, non troncata. Su un telefono due tessere affiancate
            riducevano «Efficacia dei convertiti» a «EFFICACIA DEI …»: il nome
            e' l'identita' della metrica, e quando lo spazio manca cede la
            decorazione, non l'etichetta (CLAUDE.md). Trovato nel collaudo in
            browser del 2026-09-16. */}
        <div className="flex items-start gap-1 text-[0.6765rem] uppercase tracking-wider text-muted-foreground font-mono">
          <span className="min-w-0 break-words leading-snug">{label}</span>
          {note && <InfoHint label={label} text={note} />}
        </div>
        <div
          className={cn(
            "tabular-nums leading-tight",
            primary ? "text-3xl font-bold mt-1" : "text-lg font-semibold",
            tone === "ok" && "text-emerald-800 dark:text-emerald-400",
            tone === "bad" && "text-rose-700 dark:text-rose-400",
          )}
        >
          {value}
        </div>
        {hint && (
          <div className={cn("text-muted-foreground", primary ? "text-xs mt-1" : "text-[0.7059rem]")}>
            {hint}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Le principali in una riga larga, le altre compatte sotto. */
export function MetricStrip({ tiles }: { tiles: MetricTileProps[] }) {
  const principali = tiles.filter((t) => t.primary);
  const altre = tiles.filter((t) => !t.primary);
  return (
    <div className="space-y-2">
      {principali.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 [&>*]:min-w-0">
          {principali.map((t) => (
            <MetricTile key={t.label} {...t} />
          ))}
        </div>
      )}
      {altre.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 [&>*]:min-w-0">
          {altre.map((t) => (
            <MetricTile key={t.label} {...t} />
          ))}
        </div>
      )}
    </div>
  );
}
