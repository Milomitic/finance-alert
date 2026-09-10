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
| FA-027 | P1 | UX/dettaglio | Il dettaglio titolo perde titoli e valori a 1440px | **OPEN** | Rilevato sugli screenshot del 2026-09-10, con la causa misurata: `StockDetailPage.tsx:281` divide in `[2fr_1fr]` e spezza poi la colonna destra in due, lasciando **~133px di contenuto utile** per scheda — e i valori vengono disegnati SOPRA le etichette (`Sostenib45lità`, `Valore71`), non troncati accanto. La riga bassa (`:344`, `[1.5fr_1fr_1fr_1fr]` con `lg:h-[520px]` fisso) riduce tre schede a 244px, da cui titoli `F`, `VALUATION…`, `ANAL…`. **Il layout corretto esiste gia su mobile**, dove la stessa scheda rende i cinque pilastri come barre etichettate: il rimedio e dare alla colonna destra la larghezza che il mobile ha gia, non progettare qualcosa di nuovo. Vedi [frontend-audit-2026-09-10.md](frontend-audit-2026-09-10.md) §4.1. |
| FA-028 | P2 | UX/dashboard | La barra indici e vuota su desktop e viva su tablet e mobile | **OPEN** | Sei indici, dodici `n/d`, nella striscia piu in alto della pagina piu aperta. Nella **stessa sessione di acquisizione** tablet e mobile mostrano `FUT S&P 500 7649 ↓ -0.44%`: il componente sa ricadere sui futures a mercati chiusi e su due viewport su tre lo fa. Due su tre funzionanti escludono un'indisponibilita della sorgente. Da riprodurre prima di ipotizzare la causa. §4.4. |
| FA-029 | P2 | UX/correlazioni | Una posizione non sa da quale segnale e nata | **OPEN** | `Position.alert_id` esiste nel tipo e arriva al frontend; la pagina Posizioni non lo usa, mentre il suo sottotitolo promette "trade tracciati dal piano operativo dei segnali". Costo: un link. Insieme va resa la geometria: entry, stop, target e prezzo sono quattro colonne dove una barra risponde a colpo d'occhio alla sola domanda che conta su una posizione aperta. §7.1 e §7.2. |
| FA-030 | P1 | Dati | La finestra 52 settimane e l'intera storia su 5 timeframe su 6 | **OPEN** | `market_detail_service.py:198` sceglie il ramo con `range_key in ("1m","3m","6m")`, cioe il vocabolario **precedente** a `2faee27`, mai aggiornato. Il selettore offre 5m/30m/1h/1d/1w/1m: il default `1d` mappa su `period="max"`, quindi il 52W low di ^GSPC e 4.40, il minimo del 1932. Il ramo `else` assegna letteralmente `high_52w = high_window`, percio 52W high/low stampa gli **stessi numeri** di Range high/low accanto. Calcolato solo sulle chiusure, e l'etichetta non lo dice (`KpiCell` non ha slot per tooltip); la scheda titolo invece lo dichiara. **Nessun test copre il blocco.** La meta pericolosa non e il 4.40 che si autodenuncia, sono i 60 giorni su 5m/30m: plausibili, quindi creduti. Audit §3.1. |
| FA-031 | P1 | Dati | Il macro sbaglia la scala di mille volte | **OPEN** | La scheda dice `Total Non-Farm Payrolls (thousands)` e il formatter stampa `159.1K` su un numero gia in migliaia: **l'unita e nel payload e il formatter la ignora**. Il grafico Storico release disegna il **livello** come barre da zero, quindi 60 barre identiche: la domanda che si fa a NFP e la variazione, ~150K contro un livello di 159.100K, un millesimo dell'altezza. E `release_date` e costruita da `MacroObservation.date`, cioe il periodo osservato: 1 ago 26 per un dato pubblicato a settembre. Periodo, pubblicazione e acquisizione sono tre campi. Audit §3.2. |
| FA-032 | P1 | Dati | Variazione di quote stampata con l'unita del peso | **OPEN** | `institutional_service` calcola la variazione percentuale delle **quote**; `InstitutionalHoldersCard` la passa ad `AllocationBars.deltaPct`, definita e formattata come variazione del **peso in punti percentuali**. A schermo: Balyasny +7663.7PP, Citadel +462.6PP, Millennium +107.6PP. **L'argomento non richiede il codice**: un peso vive fra 0 e 100%, quindi il valore assoluto di un delta in punti non puo superare 100, e ce ne sono tre sopra la soglia sullo stesso schermo. Separare `shares_change_pct` e `portfolio_weight_delta_pp`; l'invariante va in un test. Audit §3.3. |
| FA-033 | P1 | Dati | Quattro prezzi base per lo stesso titolo, nessuno dichiarato | **OPEN** | Lo stesso target analisti rende **+11.5%** in una scheda e **+4.3%** in un'altra sulla pagina di DG; l'aritmetica lo conferma da sola (138,93/124,57 e 138,93/133,21). Le basi sono quattro: header = prezzo live; pannello analisti = `pt.current` di yfinance, vecchio quanto la cache fondamentali (aggiornato 4g fa); scheda punteggio = ultima `OhlcvDaily.close` via `quality_extras`; piu una quarta in `pillars.py`. Nessuna dichiara quale prezzo usa ne a che ora. Audit §3.4. |
| FA-034 | P2 | Dati/UX | Le holdings di un fondo non hanno limite a nessuno dei tre strati | **OPEN** | `visibleHoldings.map` sull'intero array senza slice ne virtualizzazione ne `max-h`; `get_detail` non ha `limit`/`offset`, a differenza di `get_ticker_holders` subito sotto che ha `limit: int = 25`; la query non ha `.limit()`. Uno screenshot interno supera i **302.900 pixel** di altezza. Il divario header 4.295 / tabella 5.252 ha un meccanismo esatto e non e sporcizia nei dati: `compute_qoq_deltas` **inserisce righe sintetiche** per le uscite (`shares=0`, `action="sold_out"`) e non aggiorna mai `total_positions`. 5.252 meno 4.295 = 957 uscite. Entrambi i numeri sono corretti per cio che contano: manca l'etichetta. Audit §4.2. |
| FA-035 | P2 | Dati | La classificazione degli strumenti e ferma a una fotografia di luglio | **OPEN** | Il filtro che esclude gli ETF dalle aggregazioni settoriali **e capillare e corretto**: ogni query in `api/sectors.py` porta `.where(instrument_type == "equity")`. Il problema e il flag: scritto **una sola volta** da una migration con lista hard-coded di 24 ticker raccolti come exactly the NYSE Arca listings il 2026-07-04. QQQ e quotato NASDAQ e non c'e, mentre SQQQ e TQQQ si. E **nessun percorso di ingestione lo valorizza**: ne `seed_service` ne `catalog_refresh_service`, quindi ogni riga nuova nasce `equity`. Sul DB: 975 equity / 24 etf, mai cresciuti. Il rilievo non e QQQ nel settore sbagliato, e che ogni ETF aggiunto dopo luglio e invisibile a sette query. Audit §3.6. |
| FA-036 | P2 | UX/calendario | Le pastiglie del calendario non lasciano leggere il ticker | **OPEN** | Ogni pastiglia mostra il logo e una lettera. Su un calendario earnings il ticker **e** l'informazione. La causa e la disposizione: cella larga ~140px con **due pastiglie affiancate**, ~65px ciascuna; una per riga ne avrebbe ~130. La cella ha altezza abbondante e larghezza scarsa, e il contenuto e disposto nel verso sbagliato. Audit §4.3. |
| FA-037 | P2 | Struttura | Due pagine di diagnostica, una delle quali si chiama Impostazioni | **OPEN** | `/settings` e 62 righe e monta otto pannelli tutti diagnostici; il file lo dice di se, Admin / diagnostic surface. Gli unici controlli sono filtri **effimeri** su uno studio: nessuno persiste. Le preferenze vere esistono sparse — tema e sidebar in `Layout`, `chart-timeframe` in `chartPrefs`, viste salvate nel filtro screener, colonne in `useColumnVisibility` — e il toggle del tema sta **accanto** al link Impostazioni, non dentro. Proposta: una Diagnostica con schede Piattaforma e Motore, che separa disponibilita del sistema da capacita predittiva, e l'ingranaggio libero per le preferenze. Audit §5.1. |
| FA-038 | P3 | UX/navigazione | Il ritorno manca sulle due pagine di dettaglio piu visitate | **OPEN** | Tre pagine su cinque hanno gia un ritorno esplicito: `SectorDetail`, `MacroDetail` con Indietro, `InstitutionalDetail` con Tutti i portafogli. Mancano in **`StockDetailPage`** e **`MarketDetailPage`**. E l'occhiello sopra il titolo che assolve la funzione di breadcrumb esiste gia su Calendario e Impostazioni: **il modello e applicato a due pagine su diciassette**, estenderlo costa meno che progettarne uno nuovo. Audit §5.3. |
| FA-039 | P3 | Frontend | L'AbortSignal e supportato dal client e quasi mai propagato | **OPEN** | `api/client.ts` inoltra davvero `signal` a fetch: il supporto e reale. Ma nel frontend esistono **due sole** occorrenze di `Abort` in tutto il sorgente e **nessun** `AbortController`. Su 58 `queryFn` in produzione **una** destruttura il `signal` di React Query, `useStockSearch`; nei moduli `api/`, su 54 wrapper uno solo espone il parametro, quindi un hook non potrebbe inoltrarlo nemmeno volendo. Completare qui prima di valutare un secondo client. Audit §9. |
| FA-018 | P2 | Accessibilita | Aggiungere descrizione accessibile al dialog degli alert prezzo | **DONE / PROD** | `PriceAlertDialog` espone `DialogDescription` screen-reader-only; warning Radix corretto, codice deployato e suite frontend verde. |
| FA-019 | P0 | Release | Push e sincronizzazione cloud dei commit locali | **DONE / PROD** | Push verificato; CI 34366785799 completata con tutti i job verdi, Argo `Synced/Healthy`, StatefulSet sull’immagine `42693fb1b09195be96065cfdc1bda0be176c014a`, health esterno 200 e `/metrics` esterno 403. |
| FA-021 | P2 | GitOps | Eliminare lo stato Argo `OutOfSync` del Cluster CNPG quando il diff effettivo è vuoto | **DONE / PROD** | Verificato live 2026-09-09: `postgres-cluster` torna `Synced/Healthy` e tutte e cinque le Application sono sincronizzate; il cluster resta sano 1/1 e nessun pod si e riavviato. Causa isolata: l'operatore aggiunge `enabled: true` alla voce di `spec.plugins`, e il CRD non dichiara `x-kubernetes-list-type`, quindi la lista è ATOMICA e una chiave in più rende diversa tutta la lista. `postgresql.parameters` non causa drift benché l'operatore vi inietti 23 chiavi: è una mappa e ArgoCD possiede solo le sue sette. Rimedio: dichiarare il campo nel manifest, **non** un `ignoreDifferences` su `/spec/plugins`, che silenzierebbe anche una modifica vera all'archiviatore. |

## Cosa resta aperto (2026-09-10)

Nessuna attivita e bloccata e nessuna e in corso di rilascio. Le venti voci qui
sotto sono tutto quello che il backlog tiene aperto: due in attesa di dati, due
in attesa di un collaudo su dispositivo reale, quindici aperte, una che aspetta
una decisione.

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
| FA-027 | togliere una griglia al dettaglio titolo | lavoro |
| FA-028 | riprodurre la barra indici vuota su desktop | lavoro |
| FA-029 | collegare posizione e segnale, e rendere la geometria | lavoro |
| FA-030 | finestra 52W indipendente dal timeframe, piu un test | lavoro |
| FA-031 | separare livello, variazione, unita e date del macro | lavoro |
| FA-032 | separare variazione quote e variazione peso | lavoro |
| FA-033 | una base prezzo comune, o dichiarata per ogni confronto | lavoro |
| FA-034 | paginare le holdings ed etichettare i due conteggi | lavoro |
| FA-035 | valorizzare instrument_type all'ingestione | lavoro |
| FA-036 | una pastiglia per riga nel calendario | lavoro |
| FA-037 | unire le due diagnostiche, liberare l'ingranaggio | lavoro |
| FA-038 | ritorno su dettaglio titolo e dettaglio mercato | lavoro |
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
