import { ChevronDown, Loader2, Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useAlertPeers } from "@/hooks/useAlerts";

/* Quanta compagnia aveva questo segnale il giorno in cui è scattato.
 *
 * Misurato sul magazzino alert, la differenza fra detector è enorme:
 * `trend_pullback` scatta in media insieme a 43 altri titoli (max 127),
 * `gap_and_go` insieme a 2,7 (max 8). Il primo quasi mai riguarda il titolo:
 * è una condizione di mercato che quel giorno lo ha toccato. Il secondo sì.
 *
 * ⚠️ È CONTESTO, MAI CONFERMA. Due studi indipendenti (CLAUDE.md) trovano la
 * concurrence NULLA a 1/2/3/5 giorni: sapere che quaranta nomi hanno fatto la
 * stessa cosa non rende il segnale migliore. Cambia cosa deve concludere CHI
 * LEGGE — se il movimento è di settore, il titolo non sta dicendo niente di
 * suo. Il testo lo dice esplicitamente, perché una riga che mostra "38 altri
 * titoli" accanto a Forza e Probabilità verrebbe letta come un rinforzo se non
 * lo negasse.
 *
 * ⚠️ FA-064 — IL CONTEGGIO È PER DIREZIONE. Sommava i titoli scattati al rialzo
 * e al ribasso sullo stesso detector: in produzione il numero di 7.088 alert su
 * 8.397 conteneva titoli della direzione opposta, con mediana 6 e punte di 93.
 * Un detector scattato in entrambi i versi la stessa mattina è il contrario di
 * una condizione di mercato in una direzione, e la riga diceva il contrario.
 * Il conteggio opposto non viene buttato: che lo stesso detector sia scattato
 * al contrario su N titoli è un'informazione, e si dice.
 *
 * I titoli contati si possono vedere. Non con un link a `/alerts` filtrato —
 * quel filtro sulle date legge `triggered_at`, l'ampiezza `signal_date`, e il
 * numero e la lista descriverebbero due popolazioni — ma con un endpoint che
 * applica lo stesso predicato. Caricati solo quando si apre il pannello. */
export function SignalBreadthRow({
  alertId,
  sameTone,
  sameToneSector,
  oppositeTone,
}: {
  alertId: number;
  sameTone: number | null | undefined;
  sameToneSector: number | null | undefined;
  oppositeTone: number | null | undefined;
}) {
  const [aperto, setAperto] = useState(false);
  const compagni = useAlertPeers(alertId, aperto);

  // Senza signal_date o senza direzione non c'è un "quel giorno nello stesso
  // verso" con cui confrontarsi. Niente è meglio di uno zero, che si
  // leggerebbe come "era solo". Vale anche per un bundle vecchio in cache,
  // che conosceva i nomi di campo precedenti.
  if (sameTone == null) return null;

  const alone = sameTone === 0;
  const inSector = sameToneSector ?? 0;
  const opposti = oppositeTone ?? 0;

  return (
    <div className="flex items-start gap-2 rounded-lg border border-border/60 px-3 py-2">
      <Users className="h-3.5 w-3.5 shrink-0 mt-0.5 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="text-sm">
          {alone ? (
            <>
              <span className="font-semibold">Solo questo titolo</span> ha fatto
              scattare questo segnale in questa direzione quel giorno.
            </>
          ) : (
            <>
              Scattato anche su{" "}
              <span className="font-semibold tabular-nums">{sameTone}</span>{" "}
              {sameTone === 1 ? "altro titolo" : "altri titoli"} nella stessa direzione
              {/* Il settore non viene nominato: chi legge e' sulla pagina del
                  titolo, dove il settore sta nell'intestazione. */}
              {inSector > 0 && (
                <>
                  , di cui{" "}
                  <span className="font-semibold tabular-nums">{inSector}</span> nello
                  stesso settore
                </>
              )}
              .
            </>
          )}
          {opposti > 0 && (
            <>
              {" "}
              Nella direzione opposta è scattato su{" "}
              <span className="font-semibold tabular-nums">{opposti}</span>{" "}
              {opposti === 1 ? "titolo" : "titoli"}.
            </>
          )}
        </div>
        <div className="text-xs text-muted-foreground italic mt-0.5">
          {/* ⚠️ Diceva «Movimento del titolo, non una condizione di mercato»:
              affermava una CAUSA dall'assenza di altri match (FA-059). Il
              perimetro non e' il mercato, e' il catalogo scansionato quel
              giorno. */}
          {alone
            ? "Nessun altro titolo del catalogo scansionato ha mostrato questa condizione nella stessa direzione quel giorno."
            : "Non è una conferma — la coincidenza di segnali non ha mostrato vantaggio. Serve a distinguere un fatto del titolo da una condizione di mercato."}
        </div>

        {!alone && (
          <div className="mt-1.5">
            <button
              type="button"
              onClick={() => setAperto((v) => !v)}
              aria-expanded={aperto}
              className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronDown
                className={aperto ? "h-3 w-3 rotate-180 transition-transform" : "h-3 w-3 transition-transform"}
                aria-hidden
              />
              {aperto ? "Nascondi i titoli" : "Mostra i titoli"}
            </button>
            {aperto && (
              <div className="mt-1.5">
                {compagni.isLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-label="Caricamento" />
                ) : compagni.isError ? (
                  <p className="text-xs text-muted-foreground">
                    Impossibile caricare i titoli.
                  </p>
                ) : (
                  <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
                    {(compagni.data ?? []).map((p) => (
                      <li key={p.stock_id} className="min-w-0">
                        <Link
                          to={`/stocks/${encodeURIComponent(p.ticker)}`}
                          className="font-medium tabular-nums hover:underline underline-offset-2"
                        >
                          {p.ticker}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
