/* ─── Il prezzo che rappresenta l'INGRESSO di un alert ───────────────────── *
 *
 * ⚠️ Non è `trigger_price`, che sembra questo e non lo è.
 *
 * Un alert è una riga VIVA: finché il segnale persiste, ogni scansione lo
 * rivede e riscrive `trigger_price` con la chiusura corrente. Misurato in
 * produzione il 2026-09-18 su 8.736 alert: 80% ne ha almeno una revisione, e
 * nel 18% dei casi il prezzo mostrato dista oltre il 2% dalla chiusura della
 * barra del segnale. Su FICO il box diceva 985,39 — la chiusura dell'11
 * settembre — accanto a una data segnale del 4, la cui chiusura era 932,26.
 *
 * `snapshot.first_price` è il prezzo fissato alla PRIMA emissione, che non si
 * muove più. È l'ingresso che il magazzino dei piani misura, quindi è anche
 * quello su cui il piano a schermo deve poggiare: altrimenti si mostrerebbe
 * una geometria e se ne misurerebbe un'altra.
 *
 * Un proprietario solo perché il prezzo serve in due posti — il box e il piano
 * — e due letture diverse dello stesso concetto divergono al primo ritocco.
 */
type AlertConPrezzi = {
  trigger_price: number;
  snapshot?: Record<string, unknown> | null;
};

/** Il prezzo alla prima emissione, col ripiego su `trigger_price` per gli
 *  alert che precedono il campo (il meglio disponibile, non una stima). */
export function entryPrice(alert: AlertConPrezzi): number {
  const grezzo = alert.snapshot?.["first_price"];
  return typeof grezzo === "number" && Number.isFinite(grezzo) && grezzo > 0
    ? grezzo
    : alert.trigger_price;
}

/** True quando il prezzo del segnale VIVO si è mosso rispetto a quello della
 *  rilevazione: sono due fatti diversi, entrambi giusti, e vanno mostrati come
 *  due invece di lasciarne vedere uno solo. */
export function priceHasMoved(alert: AlertConPrezzi, soglia = 0.005): boolean {
  const ingresso = entryPrice(alert);
  if (!Number.isFinite(alert.trigger_price) || alert.trigger_price <= 0) return false;
  return Math.abs(alert.trigger_price - ingresso) / ingresso > soglia;
}
