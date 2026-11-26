import { HintLabel } from "@/components/ui/info-hint";
import { cn } from "@/lib/utils";

/** Una metrica delle schede Infrastruttura e Dati & deploy (D-51). Erano due
 *  copie identiche con la spiegazione in `title=`, che su un telefono non si
 *  apre: testi come «weekend e festivi giustificano 3-4 giorni» erano
 *  invisibili a meta' degli schermi. Ora la spiegazione si apre al tocco. */
export function Metrica({ label, value, tono, hint }: { label: string; value: string; tono: string; hint?: string }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
        {hint ? <HintLabel text={hint}>{label}</HintLabel> : label}
      </div>
      <div className={cn("text-[0.8235rem] font-semibold tabular-nums", tono)}>{value}</div>
    </div>
  );
}
