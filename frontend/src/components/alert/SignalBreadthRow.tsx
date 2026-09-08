import { Users } from "lucide-react";

/* Quanta compagnia aveva questo segnale il giorno in cui è scattato.
 *
 * Misurato sul magazzino alert, la differenza fra detector è enorme:
 * `trend_pullback` scatta in media insieme a 43 altri titoli (max 127),
 * `gap_and_go` insieme a 2,7 (max 8). Il primo quasi mai riguarda il titolo:
 * è una condizione di mercato che quel giorno lo ha toccato. Il secondo sì.
 *
 * La piattaforma lo ha sempre saputo e non lo ha mai detto, quindi ogni alert
 * si legge uguale che si sia mosso un titolo o cento.
 *
 * ⚠️ È CONTESTO, MAI CONFERMA. Due studi indipendenti (CLAUDE.md) trovano la
 * concurrence NULLA a 1/2/3/5 giorni: sapere che quaranta nomi hanno fatto la
 * stessa cosa non rende il segnale migliore. Cambia cosa deve concludere CHI
 * LEGGE — se il movimento è di settore, il titolo non sta dicendo niente di
 * suo. Il testo lo dice esplicitamente, perché una riga che mostra "38 altri
 * titoli" accanto a Forza e Probabilità verrebbe letta come un rinforzo se non
 * lo negasse. */
export function SignalBreadthRow({
  others,
  sameSector,
}: {
  others: number | null | undefined;
  sameSector: number | null | undefined;
}) {
  // Gli alert legacy non hanno signal_date, quindi non hanno un "quel giorno"
  // con cui confrontarsi. Niente è meglio di uno zero, che si leggerebbe come
  // "era solo".
  if (others == null) return null;

  const alone = others === 0;
  const inSector = sameSector ?? 0;

  return (
    <div className="flex items-start gap-2 rounded-lg border border-border/60 px-3 py-2">
      <Users className="h-3.5 w-3.5 shrink-0 mt-0.5 text-muted-foreground" aria-hidden />
      <div className="min-w-0">
        <div className="text-sm">
          {alone ? (
            <>
              <span className="font-semibold">Solo questo titolo</span> ha fatto
              scattare questo segnale quel giorno.
            </>
          ) : (
            <>
              Scattato anche su{" "}
              <span className="font-semibold tabular-nums">{others}</span>{" "}
              {others === 1 ? "altro titolo" : "altri titoli"}
              {/* Il settore non viene nominato: chi legge e' sulla pagina del
                  titolo, dove il settore sta nell'intestazione. Un campo in
                  piu' sull'API per ripetere una parola gia' a schermo. */}
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
        </div>
        <div className="text-xs text-muted-foreground italic mt-0.5">
          {alone
            ? "Movimento del titolo, non una condizione di mercato."
            : "Non è una conferma — la coincidenza di segnali non ha mostrato vantaggio. Serve a distinguere un fatto del titolo da una condizione di mercato."}
        </div>
      </div>
    </div>
  );
}
