# Finance Alert — audit e roadmap frontend/UI/UX

Data: 2026-09-09 · riconciliato con il codice il 2026-09-10  
Questo documento trasforma l'audit esplorativo in 72 interventi tracciabili. Le voci nascono come proposte: diventano lavoro eseguibile quando entrano nel backlog con criterio di accettazione e test.

## Riconciliazione (2026-09-10)

L'audit e stato scritto senza controllare cosa l'app gia facesse, quindi la colonna
**Stato** e stata aggiunta verificando ogni voce contro il codice. Il conto:

| Stato | Voci |
|---|---:|
| Presente | 38 |
| Manca | 27 |
| Parziale | 5 |
| In attesa di dati | 1 |
| Non si fa | 1 |

**Quasi meta della roadmap era gia costruita.** Pianificare le 72 voci come lavoro
nuovo avrebbe significato riscrivere il crosshair sincronizzato, l'export CSV
filtrato, le colonne persistenti, il confronto benchmark e le azioni bulk sugli
alert — tutte gia in produzione.

Quattro voci sono state chiuse dopo la riconciliazione, il 2026-09-10: UX-040 e
UX-063 con la valuta di quotazione (FA-025), UX-037 e UX-039 con il timeframe
persistente e il comando di reset sul grafico. La tabella qui sopra e
ricalcolata dalle righe, non scritta a mano.

⚠️ Due verdetti sono stati corretti durante la riconciliazione, e la causa e la
stessa: **una parola cercata al posto del codice letto**. Il crosshair
sincronizzato (UX-038) risultava assente e invece e il secondo canale di
`useChartSync`. Acknowledge/mute (UX-033) risultava presente in 130 file perche
`mute` sta dentro `text-muted-foreground`. Un grep senza confini di parola e il
falso positivo che CLAUDE.md documenta gia in altre forme; qui avrebbe prodotto
un verdetto sbagliato in entrambe le direzioni.

La colonna **Evidenza** nomina il file che regola il verdetto, cosi il prossimo
lettore puo ricontrollare invece di fidarsi di questa tabella.

**UX-061 non e un rinvio.** La watchlist e stata rimossa deliberatamente, come il
sistema letto/non letto: non va reintrodotta senza che l'utente la chieda.

## Tranche 1 — navigazione e orientamento (P0/P1)

| ID | Intervento | Risultato atteso | Stato | Evidenza |
|---|---|---|---|---|
| UX-001 | Breadcrumb su dettaglio titolo/settore/mercato | L'utente torna al contesto con un solo gesto | **Manca** |  |
| UX-002 | Stato pagina attivo nella navbar | La sezione corrente è sempre riconoscibile | **Presente** | `Layout.tsx` (NavLink/aria-current) |
| UX-003 | Command palette globale | Apertura rapida di pagine, ticker e azioni | **Manca** |  |
| UX-004 | Shortcuts documentate | Le azioni frequenti sono scopribili | **Manca** | la scorciatoia di ricerca esiste, la documentazione no |
| UX-005 | Deep link per ogni pannello principale | Un link riapre lo stesso contesto | **Presente** | `useSearchParams` su 6 pagine |
| UX-006 | Persistenza filtri per sezione | Cambio pagina non azzera il lavoro | **Presente** | `screenerFilterAreas` + preset in localStorage |
| UX-007 | 404 con suggerimenti contestuali | Un URL errato porta a una destinazione utile | **Presente** | `NotFoundPage.tsx` (FA-013) |
| UX-008 | Stati loading uniformi | Nessun salto di layout tra caricamento e dati | **Presente** | `Skeleton` + `first-paint-gate.tsx` |
| UX-009 | Stati vuoti con azione primaria | L'utente sa come ottenere il primo risultato | **Parziale** | gli stati vuoti esistono, l'azione primaria no |
| UX-010 | Error boundary per route | Un widget rotto non oscura tutta l'app | **Presente** | `ErrorBoundary` in `Layout.tsx`, con key sul pathname |
| UX-011 | Toast con link alla risorsa | Un errore recuperabile diventa azione | **Parziale** | toast con dettaglio API (FA-010), senza link alla risorsa |
| UX-012 | Indicatore dati aggiornati | Età e fonte dei dati sono leggibili | **Presente** | `CardUpdatedAt.tsx` |

## Tranche 2 — ricerca, filtri e tabelle (P1)

| ID | Intervento | Risultato atteso | Stato | Evidenza |
|---|---|---|---|---|
| UX-013 | Ricerca con debounce configurabile | Meno richieste e risposta più stabile | **Presente** | `useStockSearch.ts` |
| UX-014 | Evidenziazione match nei risultati | Il motivo del risultato è immediato | **Presente** | `NavbarSearch.tsx` |
| UX-015 | Recenti e preferiti nella ricerca | Ritorno rapido ai titoli usati | **Presente** | `NavbarSearch.tsx` (recenti in localStorage) |
| UX-016 | Filtri salvabili come viste | Un set di filtri è riutilizzabile | **Presente** | FA-022, `screenerViews.ts` |
| UX-017 | Preset “apertura”, “rischio”, “liquidità” | Accesso a casi d'uso frequenti | **Manca** | i preset sono solo quelli che salva l'utente |
| UX-018 | Conteggio risultati per filtro | L'utente capisce l'impatto di una scelta | **Presente** | `total` in `StocksBrowserPage.tsx` |
| UX-019 | Rimozione filtri con chip | Reset granulare senza riaprire pannelli | **Presente** | `StockFiltersCard.tsx` |
| UX-020 | Tabelle con colonne persistenti | La configurazione sopravvive alla sessione | **Presente** | `useColumnVisibility.ts` |
| UX-021 | Ordinamento multi-colonna | Confronti più precisi | **Manca** |  |
| UX-022 | Paginazione o virtualizzazione | Liste grandi restano fluide | **Manca** |  |
| UX-023 | Export CSV con filtri applicati | L'export corrisponde alla vista | **Presente** | `ExportCsvButton.tsx` |
| UX-024 | Copia link riga/titolo | Condivisione del contesto senza spiegazioni | **Manca** |  |

## Tranche 3 — dashboard e segnali (P1)

| ID | Intervento | Risultato atteso | Stato | Evidenza |
|---|---|---|---|---|
| UX-025 | Layout dashboard personalizzabile | Ogni utente mette in primo piano i KPI | **Manca** |  |
| UX-026 | Riordino card con drag and drop accessibile | Personalizzazione anche da tastiera | **Manca** |  |
| UX-027 | Preset dashboard salvabili | Passaggio rapido tra analisi diverse | **Manca** |  |
| UX-028 | Drill-down KPI | Dal numero si arriva al dettaglio filtrato | **Manca** |  |
| UX-029 | Spiegazione del punteggio | Il segnale è interpretabile | **Presente** | `lib/alertMeta.ts` + `SignalSnapshotView.tsx` |
| UX-030 | Confronto segnale vs storico | La decisione ha un riferimento temporale | **Presente** | `DetectorPerformancePanel` + esiti in `AlertsTable` |
| UX-031 | Timeline eventi con raggruppamento | Meno rumore nelle giornate affollate | **Presente** | `setupGrouping.ts`, raggruppamento nel calendario |
| UX-032 | Badge severità coerenti | Priorità leggibile a colpo d'occhio | **Presente** | `lib/alertMeta.ts` |
| UX-033 | Acknowledge/mute alert | Gli alert già valutati non disturbano | **Manca** | grep `mute` restituisce solo `text-muted-foreground` |
| UX-034 | Azioni bulk sugli alert | Gestione rapida di più risultati | **Presente** | `useBulkAlerts` in `AlertsPage.tsx` |
| UX-035 | Stato “dati parziali” esplicito | Nessuna falsa certezza quando manca una fonte | **Presente** | `MarketStateBadge` STALE, `TopMoversCard` |
| UX-036 | Glossario inline | Termini finanziari comprensibili senza uscire | **Manca** |  |

## Tranche 4 — grafici e analisi (P1/P2)

| ID | Intervento | Risultato atteso | Stato | Evidenza |
|---|---|---|---|---|
| UX-037 | Preset timeframe persistenti | Il grafico riapre nell'orizzonte scelto | **Presente** | `lib/chartPrefs.ts`; l'URL ha sempre la precedenza sulla preferenza |
| UX-038 | Crosshair sincronizzato tra pannelli | Una data è confrontabile su tutti i grafici | **Presente** | `useChartSync.ts`, canale `crosshairMove` |
| UX-039 | Zoom/reset sempre visibili | Recupero rapido dopo esplorazione | **Presente** | comando nella toolbar, usa `defaultVisibleRange` come l'effetto di caricamento |
| UX-040 | Legenda con unità e valuta | Nessuna ambiguità sui numeri | **Presente** | valuta dichiarata una volta in testa alla riga |
| UX-041 | Tooltip accessibile da tastiera | I dati non dipendono solo dal puntatore | **Manca** |  |
| UX-042 | Download immagine/CSV del grafico | Risultati riutilizzabili fuori dall'app | **Presente** | `lib/chartExport.ts` |
| UX-043 | Overlays per earnings/dividendi | Il contesto fondamentale è sul prezzo | **Presente** | `lib/signalMarkers.ts` |
| UX-044 | Confronto benchmark | Performance relativa più immediata | **Presente** | `ChartOptionsToolbar.tsx` |
| UX-045 | Soglie configurabili per indicatori | Analisi adattabile al metodo dell'utente | **Manca** |  |
| UX-046 | Preset indicatori per strategia | Setup ripetibili con meno clic | **Manca** |  |
| UX-047 | Messaggio dati insufficienti | Il grafico non appare “vuoto” senza spiegazione | **Presente** | `StockDetailPage.tsx`, `MicroDataCard.tsx` |
| UX-048 | Riduzione animazioni rispettosa di prefers-reduced-motion | Comfort e prevedibilità migliorati | **Presente** | `index.css` + `MarketTickerTape.tsx` |

## Tranche 5 — accessibilità, mobile e resilienza (P0/P1)

| ID | Intervento | Risultato atteso | Stato | Evidenza |
|---|---|---|---|---|
| UX-049 | Audit axe automatizzato in CI | Regressioni WCAG intercettate prima del deploy | **Presente** | `src/test/axe.ts`, gated dal job `frontend` |
| UX-050 | Focus order documentato | Navigazione tastiera coerente | **Manca** |  |
| UX-051 | Annunci aria-live per aggiornamenti | Cambi dati percepibili da screen reader | **Parziale** | un solo punto, `RunProgressToast.tsx` |
| UX-052 | Contrasto verificato per temi | Testo leggibile in ogni modalità | **Parziale** | verificato a mano; jsdom non calcola gli stili, axe non lo vede |
| UX-053 | Target touch minimo 44px | Azioni affidabili su telefono | **Manca** | un solo file dichiara 44px |
| UX-054 | Tabelle responsive con vista card | Informazioni fruibili su schermi stretti | **Presente** | vista card mobile nel browser titoli |
| UX-055 | Drawer con focus restore | Chiusura senza perdere il punto di lavoro | **Presente** | `dialog.tsx` (FA-011, verifica manuale aperta) |
| UX-056 | Offline/read-only snapshot | L'utente vede l'ultimo dato utile durante un errore rete | **Manca** |  |
| UX-057 | Retry per singolo pannello | Recupero senza ricaricare la pagina | **Presente** | `CardRefreshButton` + `CardErrorOverlay`, 14 componenti |
| UX-058 | Timeout e cancellazione richieste | Navigazione senza aggiornamenti tardivi | **Presente** | `AbortController` in `useLiveQuote`/`useMarketDetail`/`useMultiTfKpis` |
| UX-059 | Web Vitals p75 per device | Performance percepita misurabile | **In attesa di dati** | FA-007: strumentato, servono sessioni reali |
| UX-060 | Budget bundle per route | Crescita del frontend sotto controllo | **Manca** | `manualChunks` e una strategia di chunking, non un budget |

## Tranche 6 — personalizzazione e operatività (P2)

| ID | Intervento | Risultato atteso | Stato | Evidenza |
|---|---|---|---|---|
| UX-061 | Watchlist ordinabile | Monitoraggio costruito sull'ordine dell'utente | **Non si fa** | la watchlist e stata rimossa deliberatamente |
| UX-062 | Note e tag sui titoli | Memoria operativa vicino al dato | **Manca** |  |
| UX-063 | Price alert con valuta nativa | Soglie coerenti con il mercato | **Presente** | etichetta e chip nella valuta di quotazione |
| UX-064 | Canali notifica configurabili | Ogni alert raggiunge il canale scelto | **Manca** | esiste solo Telegram |
| UX-065 | Digest giornaliero | Riduzione del rumore durante la giornata | **Presente** | `digest_hour` nel notifier |
| UX-066 | Quiet hours | Nessuna notifica in finestre definite | **Manca** |  |
| UX-067 | Registro modifiche | Azioni sensibili ricostruibili | **Manca** |  |
| UX-068 | Import/export impostazioni | Trasferimento semplice tra ambienti | **Manca** |  |
| UX-069 | Pagina stato fonti dati | Diagnosi trasparente di provider degradati | **Presente** | `PlatformHealthPage.tsx` |
| UX-070 | Centro preferenze privacy | Controllo esplicito su RUM e storage | **Manca** |  |
| UX-071 | Help contestuale per errori API | Diagnosi comprensibile senza log tecnici | **Parziale** | il toast riporta il dettaglio API, non una spiegazione |
| UX-072 | Tour iniziale ignorabile e ripetibile | Le capability principali sono scopribili | **Manca** |  |

## Criteri comuni

Ogni voce deve avere: criterio di accettazione osservabile, test unit/component o browser quando serve, telemetria dell'azione critica e verifica responsive. Le voci che cambiano dati finanziari richiedono anche controllo di valuta, timestamp e fonte.
