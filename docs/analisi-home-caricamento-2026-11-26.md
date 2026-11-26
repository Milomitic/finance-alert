# La home mostra dati vecchi per 10-15 secondi (FA-179)

Segnalato il 2026-11-26: dalla pagina visibile ai dati aggiornati passano
10-15 s, e nel frattempo si vedono dati di giorni prima che poi cambiano.
Analisi con misure in produzione (immagine `955cd928`), poi la proposta.

---

## 1. Cosa succede davvero

Sono **due problemi diversi** che si vedono come uno.

### 1.1 Al ritorno sulla scheda (o sulla PWA) i dati restano quelli di prima

È la causa dei «dati di tre giorni fa aggiornati dopo 15 secondi», ed è
lato client.

- `lib/query-client.ts` imposta `refetchOnWindowFocus: false` per tutta
  l'app. Lo riaccendono solo il riepilogo e il mercato
  (`useDashboardSummary`, `useMarketSummary`).
- Le query vive (`useLiveAssets` ogni 15 s, `useLiveUniverseMovers` ogni
  60 s, le quotazioni, il conto eToro) hanno
  `refetchIntervalInBackground: false`: con la scheda nascosta il timer si
  ferma.
- Una scheda o una PWA ripresa dopo giorni tiene in memoria le risposte di
  allora (la cache vive finché la query è montata). Al ritorno nessuno le
  invalida: il primo aggiornamento arriva quando riparte il timer, cioè
  **dopo 15 s** per il paniere dei mercati e dopo 60 s per i titoli più mossi.
  I 15 secondi che vedi sono esattamente l'intervallo di `useLiveAssets`.

### 1.2 Al primo caricamento il server risponde lento a freddo

Misurato dentro il pod, due giri di fila sulle chiamate della home:

| Chiamata | A freddo | A caldo |
|---|---|---|
| `/api/dashboard/summary` | **6.286 ms** | 87 ms |
| `/api/dashboard/live-assets` | **1.658 ms** | 7 ms |
| `/api/etoro/vivo` | 361 ms | 6 ms |
| `/api/institutionals/aggregate` | 430 ms | 338 ms |
| `/api/etoro/andamento` | 312 ms | 307 ms |
| `/api/institutionals/operazioni` | 307 ms | 287 ms |
| le altre sette | 9-89 ms | 6-56 ms |

- `/api/dashboard/summary` non ha cache: ricalcola KPI, alert per giorno,
  titoli più segnalati, alert per indice e lista recente a ogni richiesta, e
  a freddo costa 6 s. «A freddo» capita spesso: dopo ogni rilascio (oggi
  una decina) e dopo un periodo senza traffico.
- `live-assets` a freddo va a Yahoo per tutto il paniere.
- Il cancello della home (`DashboardSkeleton`) aspetta riepilogo E mercato:
  il riepilogo a freddo decide il tempo di tutta la pagina.
- Poi le quotazioni dei titoli (`/api/stocks/quotes`, ~4,6 s di media
  misurati a settembre) completano i numeri a schermo.

---

## 2. Cosa si vuole

1. Pagina mostrata **solo coi dati già pronti**, mai con numeri di giorni
   prima.
2. Dati **subito**, perché pronti in anticipo.
3. Dati **sempre quasi aggiornati**: l'età massima è una scelta dichiarata,
   non un caso.

---

## 3. La proposta

### Fase A — al ritorno, niente dati vecchi (client, ~1 giorno)

È la parte che toglie il sintomo segnalato.

- **Ritorno in primo piano.** Un hook unico (`useRitornoInPrimoPiano`)
  ascolta `visibilitychange`. Se la scheda è rimasta nascosta oltre una
  soglia (60 s), invalida subito le query della home invece di aspettare il
  timer. Si accende anche `refetchOnWindowFocus` sulle query vive.
- **Età massima dichiarata.** Ogni query della home ha un'età oltre la quale
  il suo dato non si mostra: 2 minuti per prezzi e mercato, 15 per il
  riepilogo. Oltre quella età, al posto del numero vecchio c'è lo scheletro
  della scheda (alto uguale, quindi la pagina non salta) finché arriva il
  dato nuovo.
- Con la Fase B dietro, quell'attesa è di decine di millisecondi.

### Fase B — il server ha sempre la risposta pronta (backend, ~1-2 giorni)

- **Cache «serve-il-vecchio-e-rinfresca»** per riepilogo, mercato e
  paniere, con un'età massima per ciascuno:
  - entro l'età, la risposta esce dalla memoria;
  - oltre, esce comunque subito e un solo thread la ricalcola dietro.
  - Nessuna richiesta paga più i 6 s.
- **Un job che la tiene calda**, ogni 30-60 s in orario di mercato e più
  di rado fuori, sul modello della spazzata delle quotazioni che esiste già.
- **Riscaldamento all'avvio**, come quello dei settori: dopo un rilascio la
  prima richiesta trova la cache piena.
- ⚠️ Lavoro d'avvio in un thread: va spento sotto `PYTEST_CURRENT_TEST`, per
  il segfault di SQLite già annotato in CLAUDE.md.

### Fase C — il primo caricamento parte prima (client, ~1 giorno)

- **Le richieste della home partono insieme al codice.** Oggi partono solo
  dopo che React ha montato la pagina, cioè dopo aver scaricato ed eseguito
  il JavaScript. Con un `prefetchQuery` in `main.tsx`, eseguito prima del
  montaggio, viaggiano in parallelo al download.
- **Cache sul dispositivo**: l'ultima risposta buona in IndexedDB, con il
  suo orario. Si mostra all'apertura solo se è entro l'età massima della
  Fase A; altrimenti scheletro finché arriva la risposta fresca. È la cache
  che chiedi, con la regola che impedisce di mostrare dati di tre giorni prima.
- Il service worker resta network-first sull'HTML e fuori dalle `/api/`: la
  cache dei dati sta nell'app, che conosce l'età e la può dichiarare.

### Fase D — misurarlo (~mezza giornata)

- Una metrica nel RUM già presente (`WebVitalsReporter`): «tempo ai dati
  freschi della home», dal caricamento all'ultima query critica risolta.
- Su questa metrica si verifica la promessa: sotto 1 s al ritorno, sotto 2 s
  al primo caricamento.

---

## 4. Ordine consigliato

1. **Fase A**: toglie da sola il «vecchio per 15 s», ed è piccola.
2. **Fase B**: toglie i 6 s a freddo, e rende veloce l'attesa che la Fase A
   introduce.
3. **Fase D**: insieme alla B, per misurare prima e dopo.
4. **Fase C**: per ultima. È quella con più parti mobili (IndexedDB,
   versionamento delle forme salvate) e dà il guadagno minore, se A e B sono
   già fatte.
