# Finance Alert — backlog unico

Ultimo aggiornamento: 2026-09-10  
Repository: `finance-alert-cloud`  
Branch di lavoro: `cloud` (l'unico che CI costruisce e che il CD rilascia)

Questo file è il backlog operativo canonico. Ogni nuova attività deve avere un ID qui; un’attività si chiude solo quando il codice è stato pushato, sincronizzato dal CD e verificato nell’ambiente target.

## Stati

- **DONE / PROD**: implementata, pushata e verificata in produzione.
- **READY / LOCAL**: implementata e committata localmente, ma non ancora presente in produzione.
- **IN PROGRESS**: implementazione o verifica in corso.
- **OPEN**: analizzata, da implementare.
- **WAITING DATA**: strumentazione presente; servono dati reali prima di decidere.
- **BLOCKED**: il prossimo passo richiede un’azione esterna o un’autorizzazione non disponibile.

## Stato corrente

| ID | Priorità | Area | Attività | Stato | Evidenza / criterio di chiusura |
|---|---:|---|---|---|---|
| FA-001 | P0 | Sicurezza | Proteggere `/metrics` dall’ingress pubblico con allowlist loopback | **DONE / PROD** | Commit `cb524d5` pushato; probe esterno 403, health 200, Prometheus interno `up=1`. |
| FA-002 | P1 | Backup | Portare la retention PostgreSQL da 7 a 30 giorni | **DONE / PROD** | ObjectStore pg-backups: retentionPolicy=30d verificata il 2026-09-09. La storia preesistente inizia il 2 settembre: 30d e la policy, non 30 giorni di backup retroattivi. |
| FA-003 | P1 | Backup | Migrare dal Barman integrato CNPG al Barman Cloud Plugin prima di CNPG 1.31 | **DONE / PROD** | Plugin chart 0.8.0/v0.15.0 installato, `pg-1` 2/2 Ready, WAL archiviati, `ScheduledBackup pg-daily` con `method=plugin` e backup `pg-plugin-verify-20260909` **completed** in 3m34s. Restore separato riuscito: cluster sano, dati verificati (stocks/alerts identici al live, ohlcv 2.476.821 contro 2.476.822 perche il live ha acquisito una barra dopo il backup; 28 tabelle, alembic `a3f71c9d2e40`, `fa_app` non superuser). Le risorse temporanee di restore e backup sono state eliminate e verificate come `NotFound`. |
| FA-004 | P1 | Osservabilità | Aggiornare gli alert ai metric name del plugin | **DONE / PROD** | PrometheusRule applicata, plugin scrape `up=1`, e la verifica che conta e fatta (2026-09-09): le tre serie `barman_cloud_cloudnative_pg_io_*` **esistono** in Prometheus, entrambe le regole sui backup le interrogano, tutte le 14 regole del gruppo valutano `ok/inactive` e l'ultimo backup disponibile risulta di 12,7 ore fa. Una regola che punta a un nome inesistente resta verde per assenza di serie, non per salute: e il guasto gia documentato in CLAUDE.md. |
| FA-005 | P2 | Kubernetes | Rimuovere `spec.monitoring.enablePodMonitor` deprecato | **DONE / PROD** | PodMonitor finance-alert-postgres presente in monitoring, scrape up=1; enablePodMonitor=false restituito dal default del server. |
| FA-006 | P2 | Performance | Analizzare i percorsi lenti sui percentili reali | **WAITING DATA** | Bucket/latenze già strumentati; attendere almeno 7 giorni e misurare p50/p95/p99 prima/dopo. |
| FA-007 | P2 | Frontend | Introdurre RUM per Web Vitals LCP/INP/CLS | **WAITING DATA** | `web-vitals` ufficiale per CLS/INP/LCP e route a cardinalita finita sono in produzione sull’immagine `42693fb`. Servono sessioni browser reali per popolare i percentili e validare il payload. |
| FA-008 | P2 | Frontend | Ridurre e presidiare i finding ESLint React Hooks | **OPEN** | Riconteggiato il 2026-09-10: **39 errori e 8 warning**, tutti in quattro regole — `react-refresh/only-export-components` 21, `react-hooks/set-state-in-effect` 13, `react-hooks/exhaustive-deps` 8, `react-hooks/refs` 5. Le categorie `purity` e `immutability` che CLAUDE.md elencava sono ora a zero. Nessuna e gated: `eslint.hooks.config.js` richiede che una violazione rompa qualcosa che l'utente sente, ed e la barra da rispettare prima di aggiungere una regola al gate. |
| FA-009 | P1 | UX | Correggere etichette valuta/prezzo nelle posizioni | **DONE / PROD** | Prezzi e P&L usano la valuta nativa con fallback USD; codice incluso nell’immagine `42693fb`, build e suite frontend verdi. |
| FA-010 | P1 | UX | Rendere visibili e recuperabili gli errori delle mutazioni | **DONE / PROD** | Hook posizioni con toast successo/errore e dettaglio API; form trade mantiene errore inline; codice incluso nell’immagine `42693fb`, build e suite frontend verdi. |
| FA-011 | P1 | UX mobile | Focus trap, ESC, scroll lock e restore del drawer | **IN PROGRESS** | Comportamento dialog deployato; manca la verifica manuale su browser/dispositivo reale per focus trap, ESC, scroll lock e restore. |
| FA-012 | P1 | UX/search | Stati errore e semantica combobox | **DONE / PROD** | Stato errore con retry e ruoli `combobox`/`listbox`/`option` implementati e inclusi nell’immagine `42693fb`; build e suite frontend verdi. |
| FA-013 | P2 | UX/navigation | Preservare filtri/calendar/search nell’URL e migliorare il 404 | **IN PROGRESS** | 404 e stato calendar/search serializzato in URL sono deployati; resta verifica browser di back/forward e serializzazione date locali. |
| FA-014 | P2 | Sessioni | Revoca server-side e logout tra schede | **DONE / PROD** | Tabella `revoked_sessions` (migrazione `50c3faa68285`) piu idratazione in `lifespan`. La lista viveva in un dizionario di processo: un riavvio riportava in vita ogni token di cui qualcuno aveva fatto logout, per i **sette giorni** di `session_max_age_days`, e ogni deploy e un riavvio. Solo il digest SHA-256 finisce a tabella, mai il token. **Le letture restano in memoria di proposito**: `read_session_token` gira a ogni richiesta autenticata e `/api/health` da solo e 18k delle ~20k giornaliere, quindi una SELECT per richiesta pagherebbe una domanda la cui risposta e quasi sempre no. ⚠️ Questo NON risolve piu repliche: la revoca raggiunge subito il database ma la memoria dell'altra replica lo impara al proprio riavvio. Oggi la replica e una; per due servirebbe una rilettura a TTL o un pub/sub. 22 test. |
| FA-015 | P3 | Logging/storage | Guardrail dimensione Loki e monitoraggio disco nodo | **OPEN** | Regole pubblicate; guardia filesystem root disponibile. Il kubelet local-path non espone volume_stats per Loki: la regola PVC non ha dati e non puo essere dichiarata operativa. |
| FA-016 | P2 | Prodotto | Decomporre le 72 proposte dell’audit UI/UX | **DONE** | Riconciliazione completata il 2026-09-10: tutte e 72 le voci hanno ora **Stato** ed **Evidenza** in [frontend-ux-audit-2026-09-09.md](frontend-ux-audit-2026-09-09.md). Esito: 34 gia presenti, 31 mancanti, 5 parziali, 1 in attesa di dati, 1 rifiutata (UX-061 watchlist, rimossa deliberatamente). **Quasi meta della roadmap era gia costruita**, quindi pianificarla come lavoro nuovo avrebbe riscritto codice in produzione. Due verdetti sono stati corretti in corsa da un grep senza confini di parola: `mute` sta dentro `text-muted-foreground`. Le 31 mancanti sono candidate, non lavoro impegnato: entrano qui con un ID quando l'utente le chiede. |
| FA-017 | P2 | Sicurezza | Triage dei finding Bandit e hardening dei casi confermati | **DONE / PROD** | Validazione URL HTTP(S) aggiunta; classificazione in [docs/security-bandit-triage.md](security-bandit-triage.md). Nessun high; audit npm/pip e CI 34366785799 verdi; codice deployato nell’immagine `42693fb`. |
| FA-020 | P1 | Accessibilita | Lingua del documento, link di salto, nome del logout e titolo per rotta | **DONE / PROD** | `lang="it"`, link "Salta al contenuto" primo elemento focalizzabile, label logout `sr-only` e `document.title` derivato da `NAV`; 7 test dedicati, suite frontend 290 pass; immagine `42693fb` verificata in produzione. |
| FA-022 | P2 | UX/screener | Viste salvate: filtri, ordinamento e colonne insieme | **DONE / PROD** | Estende i preset esistenti invece di affiancarli. Formato versionato con migrazione in LETTURA: i preset gia nel browser sono oggetti di soli filtri senza marcatore e continuano a funzionare, applicandosi con l'ordinamento PREDEFINITO della tabella e non con quello corrente. 16 test fra `screenerViews.test.ts` e `StockFiltersCard.views.test.tsx`; suite frontend 314 pass. Commit `f88a8d5`, CI verde, immagine rilasciata. |
| FA-025 | P1 | UX/valuta | La valuta di quotazione sul dettaglio titolo | **DONE / PROD** | 312 titoli su 1010 non sono in dollari e la pagina cablava `$` su ogni prezzo: per un terzo dell'universo il simbolo non era ambiguo, era **sbagliato**. `lib/money.ts` unifica i TRE formatter che esistevano (lo screener aveva una mappa e faceva bene, PositionsPage un helper `Intl`, il dettaglio niente). 26 punti convertiti: prezzo, variazione, chiusura precedente, legenda del grafico, price alert, range 52w, holding ETF, target analisti, EPS, grafico trimestrale. Migrazione `8fc285de13e2` per sei righe LSE con etichetta `GBp` stantia (i PREZZI erano corretti: tutte e 99 le `.L` hanno `ohlcv_in_pounds`), e `seed_service` normalizza al confine perche il prossimo import non le rimetta. 11 test backend, 42 frontend. |
| FA-023 | P2 | UX/grafici | Marker dei segnali leggibili e pan che si ferma invece di resettare | **DONE / PROD** | Commit `9363ed9`. I marker passano alla palette direzionale rosa/emerald imposta da CLAUDE.md (rosso/verde significa "rotto"), guadagnano un gradino di dimensione e **portano il conteggio** quando piu segnali cadono sulla stessa barra: prima tre segnali e uno disegnavano lo stesso glifo, quindi i giorni piu affollati sembravano i piu tranquilli. La dimensione NON dipende dalla Forza, ed e fissato da un test: sarebbe la stessa affermazione della rampa di rischio rimossa dal playbook, dove la banda 90-99 ha realizzato 42,3% contro 52-53%. Il clamp e riscritto per **far scorrere la finestra senza mai cambiarne la larghezza** — la vecchia versione tappava i due bordi in modo indipendente, allargava la finestra all'intera serie e lo zoom si azzerava. 11 test in `chartClamp.test.ts`, che prima non ne aveva pur governando tre pannelli. |
| FA-024 | P2 | Prodotto | Statistiche su rendimenti ed efficacia nelle pagine setup ed esiti | **DONE / PROD** | Commit `3a6ee82`, immagine `3a6ee82d` verificata in produzione con le cinque Application `Synced/Healthy`. `conversion_stats` guadagna rendimento **market-neutral e assoluto in coppia** (pubblicarne uno solo lascia che un setup rialzista si intesti la deriva del mercato), mediana in testa e media accanto, tasso di efficacia con intervallo di Wilson dimensionato su `independent_blocks` e non sulle righe, piu `by_detector`. Il pannello per famiglia rende **il tasso con la sua banda contro il 50%**, non una barra del tasso: una banda che attraversa il 50 diventa grigia e legge "non concludente". 13 test backend, 11 frontend. |
| FA-026 | P1 | Dati | Il market cap e nella valuta di quotazione e lo screener ci ordina | **OPEN** | Trovato mentre si sistemava la valuta (2026-09-10). `stock.market_cap` NON e in dollari: `risk.py` ha gia pagato questo difetto, e il suo test lo quantifica — 158 nomi superavano la soglia mega-cap in valuta nativa contro 83 in USD, quindi **75 titoli erano classificati mega-cap stabili senza esserlo**. La colonna market cap dello screener stampa `$` sul numero grezzo ed e **ordinabile**, quindi un cap da 19.812 miliardi di won supera uno da 3.500 miliardi di dollari. Non e una rietichettatura: convertire in USD tiene l'ordinamento sensato e cambia i numeri a schermo, etichettare ogni cap con la sua valuta e onesto e rende l'ordinamento privo di senso. Serve una decisione prima del codice. |
| FA-027 | P1 | UX/dettaglio | Il dettaglio titolo perde titoli e valori a 1440px | **DONE / PROD** | Commit `66aa10c`, incluso nel run verde di `328e264` (sette job). Due difetti con la stessa forma: quando lo spazio manca, cede l'informazione che dice COSA stai guardando. (a) `[2fr_1fr]` lasciava 375px alla colonna destra, spezzata in due schede: ~133px di contenuto utile, da cui i valori disegnati SOPRA le etichette. ⚠️ **Il commento sopra quella griglia descriveva gia il difetto** — «side by side these two got ~170px each... the Qualità gauge collided with its risk badge» — e lo risolveva solo sotto `sm`, mentre la colonna e stretta da `lg` in su. Una correzione parziale che avvalorava l'idea che il caso fosse chiuso. `lg:grid-cols-1` porta da 133px a 375px, piu di quanto abbia il mobile, dove la stessa scheda e sempre stata leggibile. (b) `SectionTitle` aveva lo slot destro `shrink-0` e l'etichetta `truncate`: cedeva sempre e solo il titolo, da cui `F` per `FUNDAMENTALS` mentre il timestamp accanto restava intero. `flex-wrap` manda sotto la chrome e tiene il nome. Il componente e canonico, 47 schede lo usano, quindi la modifica e scelta per non cambiare nulla quando lo spazio basta. ⚠️ jsdom non calcola gli stili: i quattro test fissano la struttura, non il risultato a schermo, e lo dicono. Confermati rossi. Resta la verifica a schermo su `/stocks/DG` a 1440. |
| FA-028 | P2 | UX/dashboard | La barra indici e vuota su desktop e viva su tablet e mobile | **OPEN** | Sei indici, dodici `n/d`, nella striscia piu in alto della pagina piu aperta. Nella **stessa sessione di acquisizione** tablet e mobile mostrano `FUT S&P 500 7649 ↓ -0.44%`: il componente sa ricadere sui futures a mercati chiusi e su due viewport su tre lo fa. Due su tre funzionanti escludono un'indisponibilita della sorgente. Da riprodurre prima di ipotizzare la causa. §4.4. |
| FA-029 | P2 | UX/correlazioni | Una posizione non sa da quale segnale e nata | **OPEN** | `Position.alert_id` esiste nel tipo e arriva al frontend; la pagina Posizioni non lo usa, mentre il suo sottotitolo promette "trade tracciati dal piano operativo dei segnali". Costo: un link. Insieme va resa la geometria: entry, stop, target e prezzo sono quattro colonne dove una barra risponde a colpo d'occhio alla sola domanda che conta su una posizione aperta. §7.1 e §7.2. |
| FA-030 | P1 | Dati | La finestra 52 settimane e l'intera storia su 5 timeframe su 6 | **DONE / PROD** | Commit `633ebc2`, sette job CI verdi, pod Ready sull'immagine corrispondente. La finestra usa le chiusure delle ultime 52 settimane indipendentemente dal timeframe; il test parametrico sui sei timeframe e stato **verificato rosso prima e verde dopo**, e prima non esisteva alcuna asserzione sul blocco — per questo il difetto e sopravvissuto al rename del vocabolario da `2faee27` in poi. ⚠️ La meta pericolosa non era il 4.40 su ^GSPC, che si autodenuncia, ma i 60 giorni etichettati «52 settimane» su 5m/30m: plausibili, quindi creduti. Resta la verifica a schermo: su `/markets/^GSPC` il 52W low deve differire dal Range low e non valere 4.40 in nessuno dei sei timeframe. |
| FA-031 | P1 | Dati | Il macro sbaglia la scala di mille volte | **DONE / PROD** | Commit `44ce2ef`, sette job CI verdi, pod Ready sull'immagine `c2eb5b95`. **Verificato sui dati veri**: migrazione `c6b2f93a1d47` applicata, PAYEMS `thousands`, GDPC1 `billions`, RSAFS `millions`, e l'ultimo PAYEMS memorizzato e 159.075 migliaia, cioe 159,1 milioni di occupati — la pagina rende ora `159.1M` invece di `159.1K`. Tre difetti, una causa comune: **l'unita era nel payload e nessuno la leggeva**, perche l'API esponeva `unit="level"` sia per una serie in migliaia sia per una in miliardi. Ora `value_kind` e `source_scale` sono due campi. ⚠️ Una scala ignota non viene indovinata: si mostra il numero memorizzato senza trasformazione, come `lib/money.ts` fa senza valuta. Il grafico distingue livello e variazione — linea contro barre, asse che non forza lo zero — e dichiara che la variazione e una trasformazione NOSTRA. E `release_date`, costruita dal periodo osservato, e diventata tre campi con la pubblicazione a `null` finche' non arriva dal calendario. Otto test, confermati rossi; fra questi che i nomi vecchi NON esistano piu, perche un frontend che leggesse `unit` otterrebbe `undefined` e il difetto tornerebbe in silenzio. Resta la verifica a schermo su `/macro/3`. |
| FA-032 | P1 | Dati | Variazione di quote stampata con l'unita del peso | **DONE / PROD** | Commit `225b11d`, sette job CI verdi. Contratti distinti `shares_change_pct` e `portfolio_weight_delta_pp`. ⚠️ Il componente `AllocationBars` era **corretto**: documentava la sua prop come peso in punti percentuali e la formattava cosi. Sbagliava il chiamante, che le passava `qoq_change_pct`, cioe quote — quindi "sistemare AllocationBars" sarebbe stata l'istruzione sbagliata. Il peso si confronta solo col filing immediatamente precedente; senza peso comparabile resta `null`, senza saltare un trimestre. L'invariante e in un test: un delta di peso oltre 100pp viene rifiutato, perche una percentuale di un intero non puo variare di piu di 100 punti e a schermo ce n'erano tre. Test verificati rossi prima e verdi dopo. |
| FA-033 | P1 | Dati | Quattro prezzi base per lo stesso titolo, nessuno dichiarato | **DONE / PROD** | Commit `9406b54` pushato. Lo stesso target rendeva +11.5% e +4.3% sulla stessa pagina; le basi erano quattro e nessuna diceva quale fosse, quindi la contraddizione non era leggibile — sembravano due misure diverse invece che la stessa misura su due basi. ⚠️ La correzione **non** e imporre una base sola: obbligherebbe ogni consumatore a dipendere dal prezzo live, che ha un breaker e puo essere STALE. Ogni confronto dichiara la propria, come i tassi dichiarano il denominatore. `target_upside_pct` viaggia con `upside_base_price` e `upside_base_as_of`, e la base compare accanto alla percentuale, non solo nel tooltip. Il test che conta e che la coppia non si separi mai: `("target_upside_pct" in an) == ("upside_base_price" in an)`. Quattro test su sei confermati rossi togliendo la base. 2040 backend, 412 frontend. Sette job CI verdi. Resta la verifica a schermo su DG. |
| FA-034 | P2 | Dati/UX | Le holdings di un fondo non hanno limite a nessuno dei tre strati | **OPEN** | `visibleHoldings.map` sull'intero array senza slice ne virtualizzazione ne `max-h`; `get_detail` non ha `limit`/`offset`, a differenza di `get_ticker_holders` subito sotto che ha `limit: int = 25`; la query non ha `.limit()`. Uno screenshot interno supera i **302.900 pixel** di altezza. Il divario header 4.295 / tabella 5.252 ha un meccanismo esatto e non e sporcizia nei dati: `compute_qoq_deltas` **inserisce righe sintetiche** per le uscite (`shares=0`, `action="sold_out"`) e non aggiorna mai `total_positions`. 5.252 meno 4.295 = 957 uscite. Entrambi i numeri sono corretti per cio che contano: manca l'etichetta. Audit §4.2. |
| FA-035 | P2 | Dati | La classificazione degli strumenti e ferma a una fotografia di luglio | **OPEN** | Il filtro che esclude gli ETF dalle aggregazioni settoriali **e capillare e corretto**: ogni query in `api/sectors.py` porta `.where(instrument_type == "equity")`. Il problema e il flag: scritto **una sola volta** da una migration con lista hard-coded di 24 ticker raccolti come exactly the NYSE Arca listings il 2026-07-04. QQQ e quotato NASDAQ e non c'e, mentre SQQQ e TQQQ si. E **nessun percorso di ingestione lo valorizza**: ne `seed_service` ne `catalog_refresh_service`, quindi ogni riga nuova nasce `equity`. Sul DB: 975 equity / 24 etf, mai cresciuti. Il rilievo non e QQQ nel settore sbagliato, e che ogni ETF aggiunto dopo luglio e invisibile a sette query. Audit §3.6. |
| FA-036 | P2 | UX/calendario | Le pastiglie del calendario non lasciano leggere il ticker | **DONE / PROD** | Commit `328e264`, sette job CI verdi. ⚠️ **Il difetto era gia stato trovato e gia corretto, con la soglia sbagliata.** Il commento in `DayCell` lo racconta: due colonne «made the tickers vanish», trentuno etichette invisibili, rimedio a `dense-3` (1400px) sul calcolo «due chip da 85px». Ma 85px non contengono un ticker, e lo screenshot che ha riaperto il caso e a **1440px**, dentro il ramo a due colonne. Seconda volta oggi con questa forma, dopo FA-027. Rifatto il conto, due colonne leggibili vorrebbero un viewport oltre i 1480px: invece di rincorrere la soglia, **una colonna sempre**. Il «+N» esiste gia ed e onesto — lo dice quello stesso commento — mentre una fila di pastiglie senza nome no. |
| FA-037 | P2 | Struttura | Due pagine di diagnostica, una delle quali si chiama Impostazioni | **OPEN** | `/settings` e 62 righe e monta otto pannelli tutti diagnostici; il file lo dice di se, Admin / diagnostic surface. Gli unici controlli sono filtri **effimeri** su uno studio: nessuno persiste. Le preferenze vere esistono sparse — tema e sidebar in `Layout`, `chart-timeframe` in `chartPrefs`, viste salvate nel filtro screener, colonne in `useColumnVisibility` — e il toggle del tema sta **accanto** al link Impostazioni, non dentro. Proposta: una Diagnostica con schede Piattaforma e Motore, che separa disponibilita del sistema da capacita predittiva, e l'ingranaggio libero per le preferenze. Audit §5.1. |
| FA-038 | P3 | UX/navigazione | Il ritorno manca sulle due pagine di dettaglio piu visitate | **DONE / PROD** | Commit `66aa10c`. Il modello non e stato inventato: `SectorDetail` e `InstitutionalDetail` lo avevano gia, un `<Link>` verso la pagina padre col suo nome. Aggiunto a `/stocks/:ticker` (Screener) e `/markets/:symbol` (Dashboard). ⚠️ E `MacroDetail` passa da `navigate(-1)` a un `<Link>`: un ritorno alla storia del browser non porta da nessuna parte quando la pagina si apre da un link ricevuto, cioe esattamente quando serve. Il test legge il SORGENTE delle cinque pagine e cerca la destinazione: montarle vorrebbe react-query, il router e i grafici, cioe testare l'infrastruttura invece del ritorno. **Un primo tentativo costruiva un finto componente dentro il test** e avrebbe asserito che il TEST rende un'ancora: buttato, era vero di niente. |
| FA-039 | P3 | Frontend | L'AbortSignal e supportato dal client e quasi mai propagato | **OPEN** | `api/client.ts` inoltra davvero `signal` a fetch: il supporto e reale. Ma nel frontend esistono **due sole** occorrenze di `Abort` in tutto il sorgente e **nessun** `AbortController`. Su 58 `queryFn` in produzione **una** destruttura il `signal` di React Query, `useStockSearch`; nei moduli `api/`, su 54 wrapper uno solo espone il parametro, quindi un hook non potrebbe inoltrarlo nemmeno volendo. Completare qui prima di valutare un secondo client. Audit §9. |
| FA-018 | P2 | Accessibilita | Aggiungere descrizione accessibile al dialog degli alert prezzo | **DONE / PROD** | `PriceAlertDialog` espone `DialogDescription` screen-reader-only; warning Radix corretto, codice deployato e suite frontend verde. |
| FA-019 | P0 | Release | Push e sincronizzazione cloud dei commit locali | **DONE / PROD** | Push verificato; CI 34366785799 completata con tutti i job verdi, Argo `Synced/Healthy`, StatefulSet sull’immagine `42693fb1b09195be96065cfdc1bda0be176c014a`, health esterno 200 e `/metrics` esterno 403. |
| FA-021 | P2 | GitOps | Eliminare lo stato Argo `OutOfSync` del Cluster CNPG quando il diff effettivo è vuoto | **DONE / PROD** | Verificato live 2026-09-09: `postgres-cluster` torna `Synced/Healthy` e tutte e cinque le Application sono sincronizzate; il cluster resta sano 1/1 e nessun pod si e riavviato. Causa isolata: l'operatore aggiunge `enabled: true` alla voce di `spec.plugins`, e il CRD non dichiara `x-kubernetes-list-type`, quindi la lista è ATOMICA e una chiave in più rende diversa tutta la lista. `postgresql.parameters` non causa drift benché l'operatore vi inietti 23 chiavi: è una mappa e ArgoCD possiede solo le sue sette. Rimedio: dichiarare il campo nel manifest, **non** un `ignoreDifferences` su `/spec/plugins`, che silenzierebbe anche una modifica vera all'archiviatore. |

## Cosa resta aperto (2026-09-10)

**La Tranche 1 del piano e chiusa.** I quattro difetti di significato dei numeri
sono corretti: FA-030 (la finestra 52 settimane era l'intera storia su cinque
timeframe su sei), FA-031 (il macro sbagliava la scala di mille volte),
FA-032 (una variazione di quote stampata con l'unita del peso, con tre valori
sopra il massimo aritmeticamente possibile) e FA-033 (quattro prezzi base per
lo stesso titolo). Le prime tre sono in produzione e verificate; FA-033 e verde su
tutti e sette i job e in attesa del solo rollout.

Ognuna ha portato un test che e stato **confermato rosso** togliendo la
correzione, che era la condizione d'ingresso posta dal piano — e non era una
formalita: il blocco 52W non aveva alcuna asserzione, ed e per questo che il
difetto e sopravvissuto a un rename restando invisibile per mesi.

**La Tranche 2 e quasi chiusa.** FA-027 (il dettaglio titolo che disegnava i
valori sopra le etichette), FA-036 (le pastiglie del calendario senza ticker) e
FA-038 (il ritorno mancante) sono in produzione. Resta la voce 2.4 del piano,
l'igiene: colonne vuote per il 100% delle righe, righe tagliate a meta altezza,
e l'identita che si comprime a zero su mobile mentre la misura resta.

⚠️ **Due dei tre difetti erano gia stati trovati e gia corretti, con la soglia
sbagliata.** FA-027 risolveva sotto `sm` una colonna che e stretta da `lg` in
su; FA-036 spostava a 1400px un calcolo che ne vuole 1480. In entrambi i casi
il commento accanto al codice descriveva il difetto e dichiarava di averlo
chiuso, il che e' precisamente cio che lo ha tenuto nascosto: una correzione
parziale avvalora la convinzione che il caso sia risolto. **Quando un commento
dice di aver sistemato qualcosa, rifare il conto costa meno che fidarsi.**

Le tredici voci qui sotto sono quello che resta: due in attesa di dati, due in
attesa di un collaudo su dispositivo reale, otto aperte, una che aspetta una
decisione.

**Le prime da fare sono FA-030 fino a FA-033**, i quattro difetti di significato
dei numeri. Un titolo troncato si riconosce; un numero sbagliato con l'unita
sbagliata accanto no.

Sequenza, criteri di chiusura e verifiche richieste all'utente:
[implementation-plan-2026-09-10.md](implementation-plan-2026-09-10.md).
⚠️ Una sola voce e bloccata da una scelta e non da lavoro: **FA-026**, dove
convertire il market cap in USD, etichettarlo per valuta o fare entrambe le
cose cambia numeri gia visibili a schermo. Il piano raccomanda la terza.

Le voci da FA-027 in poi vengono dall'audit unificato
([frontend-audit-2026-09-10.md](frontend-audit-2026-09-10.md)), che fonde la
revisione Claude e quella GPT Astra 6 sulla stessa acquisizione di 426
screenshot.

⚠️ **Correzione.** La revisione Claude apriva con "il desktop e il viewport
peggiore dell'app", sostenuta da "35 contenitori con scorrimento interno sulla
dashboard desktop". Erano **scatti**, non contenitori: la cattura campiona
inizio/centro/fondo di ogni contenitore. Contati correttamente sono 9 su
desktop e 4 su mobile, e il totale su 16 pagine e desktop 35 / tablet 31 /
**mobile 39**. La tesi generale e falsa: il desktop e il peggiore su 2 pagine,
il mobile su 4. Sopravvive solo il rilievo stretto, che resta utile — sulle due
pagine piu dense il desktop annida da due a sette volte piu del mobile.

**Il risultato dell'audit unificato e un altro:** i difetti gravi non sono di
layout ma di **significato dei numeri**. Sei valori a schermo sono sbagliati o
ambigui in modo che orienta una decisione, e tre lo sono di molto — un fattore
1000, un fattore 100 e un minimo del 1932 etichettato come minimo annuale.

| ID | Cosa serve per chiuderla | Chi puo sbloccarla |
|---|---|---|
| FA-006 | 7+ giorni di traffico reale, poi p50/p95/p99 per handler | il tempo |
| FA-007 | sessioni browser reali che popolino i percentili RUM | il tempo |
| FA-011 | verifica su browser/dispositivo reale di focus trap, ESC, scroll lock, restore | l'utente |
| FA-013 | verifica browser di back/forward e serializzazione date locali | l'utente |
| FA-008 | classificare e correggere 47 finding ESLint non gated | lavoro |
| FA-015 | il kubelet local-path non espone `volume_stats` per Loki: la regola PVC non ha dati | una sorgente diversa |
| FA-026 | decidere se il market cap si converte in USD o si etichetta per valuta | l'utente |
| FA-028 | riprodurre la barra indici vuota su desktop | lavoro |
| FA-029 | collegare posizione e segnale, e rendere la geometria | lavoro |
| FA-034 | paginare le holdings ed etichettare i due conteggi | lavoro |
| FA-035 | valorizzare instrument_type all'ingestione | lavoro |
| FA-037 | unire le due diagnostiche, liberare l'ingranaggio | lavoro |
| FA-039 | propagare l'AbortSignal negli hook | lavoro |

⚠️ **FA-006 e FA-007 non sono lavoro rimandato, sono misure che maturano.**
Trattarle come task da spingere significa concludere su campioni che non hanno
ancora senso — lo stesso errore che il magazzino esiti rende esplicito sullo
schermo con "non concludente".

FA-011 e FA-013 sono le uniche due che aspettano l'utente: il codice e in
produzione, manca il collaudo su un dispositivo vero, che jsdom non puo fare
(CLAUDE.md: senza stili calcolati axe non vede focus visibile ne target touch).

Le 31 voci mancanti dell'audit UI/UX **non sono in questa lista di proposito**.
Sono candidate riconciliate, non lavoro impegnato: prendono un ID qui quando
l'utente ne chiede una.

## Evidenze e limiti

- Il 2026-09-09 il cluster e stato verificato via SSH: CNPG 1.30.0, plugin Barman installato; nessun aggiornamento dell'operatore eseguito.
- La pipeline CI 34366785799 e verde; produzione verificata sull'immagine `42693fb` con Argo `Synced/Healthy`. Gli aggiornamenti successivi richiedono la propria verifica CI/CD.
- La revoca sessioni e attualmente in memoria; non resiste a riavvii. FA-014 resta aperto.
- I valori RUM raccolti dal precedente reporter non vanno usati come Core Web Vitals validati; attendere la versione corretta e campioni reali.
- Il Python globale non contiene le dipendenze backend: usare uv run --project backend pytest.
