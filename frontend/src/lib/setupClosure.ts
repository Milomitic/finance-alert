/* ─── Perché un setup si è chiuso senza convertire ─────────────────────────
 *
 * FA-061. La distinzione era già CALCOLATA dentro `expire_stale_setups` — le
 * contava separatamente nel log, col commento che spiega perché dicono cose
 * diverse — e poi scriveva entrambe come `expired` senza conservare quale. Ora
 * la colonna esiste; questo file è la metà che la mostra.
 *
 * ⚠️ Il caso DOMINANTE è «non lo so», e il progetto parte da lì. Misurato in
 * produzione il 2026-09-14: 322 setup scaduti senza ragione registrata contro
 * **UNO** con la ragione, perché la colonna è nata quel giorno. Inventare una
 * ragione per i 322 sarebbe la forma esatta del difetto che questa voce
 * chiude: una spiegazione credibile che nessuno può controllare.
 */

export type SetupClosure = "stale" | "aged" | "decayed" | "no_data" | "unknown";

export function setupClosure(raw: string | null | undefined): SetupClosure {
  return raw === "stale" || raw === "aged" || raw === "decayed" || raw === "no_data"
    ? raw
    : "unknown";
}

/** L'etichetta della pastiglia di stato. ⚠️ «Ritirato» è separato da
 *  «Scaduto» perché i due contano diversamente: vedi `COUNTS_AS_FAILURE`. */
export const CLOSURE_BADGE: Record<SetupClosure, string> = {
  stale: "Scaduto",
  aged: "Scaduto",
  decayed: "Ritirato",
  // ⚠️ «Scaduto» e non una pastiglia propria: conta come gli altri due nel
  // denominatore del tasso: l'occasione di convertire c'era davvero,
  // gliel'ha tolta il titolo smettendo di quotare. La differenza sta nel
  // PERCHÉ, che va nella riga sotto, non nello stato.
  no_data: "Scaduto",
  unknown: "Scaduto",
};

/** Il FATTO, sotto il titolo. Mai una conclusione: dice cosa è successo. */
export const CLOSURE_DETAIL: Record<SetupClosure, string> = {
  stale: "le condizioni si sono sfaldate",
  aged: "ha toccato il tetto d'attesa restando valido",
  decayed: "sceso sotto la soglia di attenzione",
  // Il FATTO, non la conclusione: il titolo ha smesso di produrre barre,
  // quindi nessuna poteva più farlo scattare né decadere.
  no_data: "la serie prezzi del titolo si è fermata",
  // ⚠️ Non «scaduto e basta»: l'assenza va DETTA. Un'etichetta muta sui 322
  // episodi chiusi prima che la colonna esistesse li farebbe sembrare tutti
  // dello stesso tipo, che è precisamente ciò che non si sa.
  unknown: "ragione non registrata",
};

/**
 * Se questa chiusura entra nel denominatore del tasso di conversione.
 *
 * ⚠️ `decayed` NON ci entra, e il backend lo esclude già: un setup ritirato
 * dalla shortlist non ha mai avuto l'occasione di convertire, quindi contarlo
 * come fallimento misurerebbe il ricambio della lista invece dell'efficacia.
 * Senza questa distinzione a schermo, chi conta le righe a occhio ottiene un
 * rapporto diverso da quello che l'app riporta — e non ha modo di sapere
 * perché.
 */
export const COUNTS_AS_FAILURE: Record<SetupClosure, boolean> = {
  stale: true,
  aged: true,
  decayed: false,
  no_data: true,
  unknown: true,
};

export const DECAYED_WHY =
  "Ritirato dalla shortlist prima di potersi risolvere: resta fuori dal tasso di conversione, perché non ha mai avuto l'occasione di convertire.";
