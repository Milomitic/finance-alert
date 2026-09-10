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
| FA-018 | P2 | Accessibilita | Aggiungere descrizione accessibile al dialog degli alert prezzo | **DONE / PROD** | `PriceAlertDialog` espone `DialogDescription` screen-reader-only; warning Radix corretto, codice deployato e suite frontend verde. |
| FA-019 | P0 | Release | Push e sincronizzazione cloud dei commit locali | **DONE / PROD** | Push verificato; CI 34366785799 completata con tutti i job verdi, Argo `Synced/Healthy`, StatefulSet sull’immagine `42693fb1b09195be96065cfdc1bda0be176c014a`, health esterno 200 e `/metrics` esterno 403. |
| FA-021 | P2 | GitOps | Eliminare lo stato Argo `OutOfSync` del Cluster CNPG quando il diff effettivo è vuoto | **DONE / PROD** | Verificato live 2026-09-09: `postgres-cluster` torna `Synced/Healthy` e tutte e cinque le Application sono sincronizzate; il cluster resta sano 1/1 e nessun pod si e riavviato. Causa isolata: l'operatore aggiunge `enabled: true` alla voce di `spec.plugins`, e il CRD non dichiara `x-kubernetes-list-type`, quindi la lista è ATOMICA e una chiave in più rende diversa tutta la lista. `postgresql.parameters` non causa drift benché l'operatore vi inietti 23 chiavi: è una mappa e ArgoCD possiede solo le sue sette. Rimedio: dichiarare il campo nel manifest, **non** un `ignoreDifferences` su `/spec/plugins`, che silenzierebbe anche una modifica vera all'archiviatore. |

## Cosa resta aperto (2026-09-10)

Nessuna attivita e bloccata e nessuna e in corso di rilascio. Le sette voci qui
sotto sono tutto quello che il backlog tiene aperto: due in attesa di dati, due
in attesa di un collaudo su dispositivo reale, due aperte, una che aspetta una
decisione.

| ID | Cosa serve per chiuderla | Chi puo sbloccarla |
|---|---|---|
| FA-006 | 7+ giorni di traffico reale, poi p50/p95/p99 per handler | il tempo |
| FA-007 | sessioni browser reali che popolino i percentili RUM | il tempo |
| FA-011 | verifica su browser/dispositivo reale di focus trap, ESC, scroll lock, restore | l'utente |
| FA-013 | verifica browser di back/forward e serializzazione date locali | l'utente |
| FA-008 | classificare e correggere 47 finding ESLint non gated | lavoro |
| FA-015 | il kubelet local-path non espone `volume_stats` per Loki: la regola PVC non ha dati | una sorgente diversa |
| FA-026 | decidere se il market cap si converte in USD o si etichetta per valuta | l'utente |

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
