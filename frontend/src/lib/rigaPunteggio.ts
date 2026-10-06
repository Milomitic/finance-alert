/** La riga di un sotto-punteggio — pilastro della Qualita' o dimensione
 *  tecnica — con la STESSA forma nelle due schede del dettaglio titolo.
 *
 *  Prima erano due grammatiche affiancate: etichetta grigia, barra colorata
 *  per fascia e valore in neretto `text-sm` nella scheda Stock Score;
 *  etichetta chiara, barra azzurra e valore minuto nella Valutazione tecnica.
 *  Due schede vicine che dicono «punteggio da 0 a 100» in due modi diversi si
 *  leggono come due scale diverse.
 *
 *  ⚠️ Classi LETTERALI: il purger di Tailwind vede solo le stringhe scritte per
 *  intero. L'etichetta a 6.5rem tiene «Profittabilità» e «Forza relativa»
 *  senza troncarle, che con gli 80px di prima capitava alla prima. */
export const RIGA_PUNTEGGIO = "grid grid-cols-[6.5rem_minmax(0,1fr)_2.25rem] items-center gap-2";
export const ETICHETTA_PUNTEGGIO = "truncate text-xs font-medium text-muted-foreground";
export const FONDO_PUNTEGGIO = "h-2 w-full overflow-hidden rounded-full bg-muted/60";
export const BARRA_PUNTEGGIO = "h-full rounded-full transition-all";
export const VALORE_PUNTEGGIO = "text-right text-sm font-bold leading-5 tabular-nums";
