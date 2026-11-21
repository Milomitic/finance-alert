import { NotebookPen } from "lucide-react";
import { useState } from "react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useNota } from "@/hooks/useTitoloConfronti";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

/** La nota personale sul titolo (FA-156), accanto alla stella.
 *
 *  Un appunto: perche' lo segui, dove avresti lo stop, cosa aspetti. Si
 *  scrive solo dall'app: il token MCP e' in sola lettura per costruzione.
 *  L'icona si riempie quando una nota c'e', cosi' si vede senza aprirla. */
export function NotaTitolo({ ticker }: { ticker: string }) {
  const { q, salva } = useNota(ticker);
  const testo = q.data?.testo ?? "";
  const [aperta, setAperta] = useState(false);
  const [bozza, setBozza] = useState("");
  const presente = testo.length > 0;

  return (
    <Popover
      open={aperta}
      onOpenChange={(o) => {
        if (o) setBozza(testo);
        setAperta(o);
      }}
    >
      <PopoverTrigger asChild>
        <Button
          type="button"
          disabled={q.isLoading}
          aria-label={`Nota su ${ticker}`}
          variant="ghost" size="icon" className="shrink-0"
        >
          <NotebookPen
            className={cn("h-5 w-5", presente ? "text-foreground" : "text-muted-foreground")}
            strokeWidth={presente ? 2.5 : 1.75}
            aria-hidden
          />
          {presente && <span className="sr-only"> (c'è una nota)</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 max-w-[calc(100vw-2rem)] space-y-2 p-3" collisionPadding={16}>
        <label htmlFor={`nota-${ticker}`} className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          La tua nota
        </label>
        <textarea
          id={`nota-${ticker}`}
          value={bozza}
          onChange={(e) => setBozza(e.target.value)}
          maxLength={4000}
          rows={5}
          className="w-full resize-y rounded-md border border-input bg-background p-2 text-sm"
          placeholder="Perché lo segui, dove avresti lo stop, cosa aspetti…"
        />
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            {salva.isError ? "Non salvata, riprova." : q.data?.aggiornata_il
              ? `Aggiornata il ${new Date(q.data.aggiornata_il).toLocaleDateString("it-IT")}` : ""}
          </span>
          <button
            type="button"
            disabled={salva.isPending || bozza.trim() === testo}
            onClick={() => salva.mutate(bozza, { onSuccess: () => setAperta(false) })}
            className="min-h-8 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {bozza.trim() === "" && presente ? "Togli" : "Salva"}
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
