import { useVariazionePunteggio } from "@/hooks/useTitoloConfronti";
import { CATEGORY_LABEL } from "@/lib/scoreMeta";
import { cn } from "@/lib/utils";

/** Che cosa ha mosso il punteggio Qualità a 30 e 90 giorni (FA-156).
 *
 *  Il pilastro col contributo maggiore in valore assoluto; il resto, se
 *  conta, si dichiara come «altro» invece di spalmarlo sui pilastri. Nessuna
 *  riga finche' lo storico non copre la finestra. */
export function VariazionePunteggio({ ticker }: { ticker: string }) {
  const { data } = useVariazionePunteggio(ticker);
  const finestre = data?.finestre ?? [];
  if (finestre.length === 0) return null;
  return (
    <div className="mt-2 space-y-0.5 border-t border-border/40 pt-2 text-xs">
      {finestre.map((f) => {
        const primo = f.contributi[0];
        const nome = primo ? (CATEGORY_LABEL as Record<string, string>)[primo.pilastro] ?? primo.pilastro : null;
        const fermo = Math.abs(f.delta) < 0.5;
        return (
          <p key={f.giorni} className="flex flex-wrap gap-x-1">
            <span className="text-muted-foreground">{f.giorni} g:</span>
            <span className={cn("font-semibold tabular-nums",
              !fermo && (f.delta > 0 ? "text-emerald-800 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"))}>
              {f.delta > 0 ? "+" : f.delta < 0 ? "−" : ""}{Math.abs(f.delta).toFixed(1).replace(".", ",")}
            </span>
            {!fermo && primo && Math.abs(primo.contributo) >= 0.3 && (
              <span className="text-muted-foreground">
                soprattutto {nome} ({primo.contributo > 0 ? "+" : "−"}{Math.abs(primo.contributo).toFixed(1).replace(".", ",")})
              </span>
            )}
            {!fermo && Math.abs(f.altro) >= 1 && (
              <span className="text-muted-foreground">
                · altro {f.altro > 0 ? "+" : "−"}{Math.abs(f.altro).toFixed(1).replace(".", ",")}
              </span>
            )}
          </p>
        );
      })}
    </div>
  );
}
