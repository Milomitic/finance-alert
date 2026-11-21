import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Una scelta esclusiva fra poche opzioni, a pulsanti affiancati (B-43).
 *
 *  Era ricostruita a mano in una dozzina di posti, con quattro colori diversi
 *  per l'opzione scelta e altezze da 24 a 36px. Bottoni con `aria-pressed`
 *  dentro un `role="group"`, NON `role="tab"`: non c'e' un pannello da
 *  promettere, e un `aria-controls` verso un id che non esiste fa annunciare
 *  agli assistivi una relazione inventata (CLAUDE.md, il caso «Recenti /
 *  Storico»).
 *
 *  ⚠️ Classi LETTERALI per taglia: il purger di Tailwind vede solo quelle. */

export interface VoceSegmentata<T> {
  id: T;
  label: ReactNode;
  /** Spiegazione breve dell'opzione. */
  titolo?: string;
  /** Il nome per i lettori di schermo, quando l'etichetta e' solo un'icona. */
  nome?: string;
}

const TAGLIA = {
  piccola: "min-h-6 px-2 text-[0.7059rem]",
  media: "min-h-8 px-2.5 text-xs",
} as const;

export function Segmentato<T extends string | number | null>({
  voci,
  valore,
  onCambia,
  etichetta,
  taglia = "piccola",
  className,
}: {
  voci: readonly VoceSegmentata<T>[];
  valore: T;
  onCambia: (v: T) => void;
  /** Il nome del gruppo per i lettori di schermo. */
  etichetta: string;
  taglia?: keyof typeof TAGLIA;
  className?: string;
}) {
  return (
    <div role="group" aria-label={etichetta} className={cn("inline-flex items-center rounded-md border p-0.5", className)}>
      {voci.map((v) => (
        <button
          key={String(v.id)}
          type="button"
          aria-pressed={valore === v.id}
          title={v.titolo}
          aria-label={v.nome}
          onClick={() => onCambia(v.id)}
          className={cn(
            "whitespace-nowrap rounded font-semibold transition-colors coarse:min-h-11",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            TAGLIA[taglia],
            valore === v.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}
