# Analisi completa dell'app — 2026-09-26

Che cosa migliorare e che cosa aggiungere, deciso sui dati della produzione e
non sull'impressione. Ogni rilievo porta la misura da cui viene; dove la misura
è debole lo dice.

## 1. Da dove vengono i numeri

| Fonte | Cosa ha dato | Limite |
|---|---|---|
| Log di accesso dell'app (Loki, 7 giorni) | aperture reali di ogni pagina ed endpoint | 7 giorni, non 30: vedi §3.5 |
| Prometheus (7 e 30 giorni) | latenze, errori, Web Vitals, allarmi, riavvii, memoria | `increase()` sottostima le rotte poco usate (CLAUDE.md) |
| Database di produzione | copertura dei dati, scansioni, volumi di segnali, uso delle funzioni | — |
| Nodo | disco, immagini, memoria | — |
| Log su disco dell'app | invii del digest Telegram | 7 giorni di rotazione |
| Codice e linee di base | dimensioni, codice mai eseguito, mutazione, accessibilità, dipendenze | — |
| Backlog e audit precedenti | ciò che è già noto o chiuso | — |

## 2. Il quadro

**L'app è in buona salute.** In 30 giorni: zero riavvii del pod, zero 5xx
salvo 3 sui fondamentali di un titolo, backup giornalieri completati, drill di
ripristino passato, notturne verdi dal 17 settembre, CI verde. Le intestazioni
di sicurezza sono complete (CSP, HSTS, frame, nosniff, referrer, permissions) e
le API rispondono 401 senza sessione. Il percorso lento storico,
`/api/stocks/quotes`, ha oggi una media di **0,16 s** e **nessuna** richiesta
oltre i 5 s su 7 giorni: FA-006 è risolta nei fatti.

**L'uso si concentra su due pagine.** Aperture degli ultimi 7 giorni, dai log:

| Pagina | Aperture | Al giorno |
|---|---:|---:|
| Cruscotto | 120 | ~17 |
| Dettaglio titolo | 116 | ~16 |
| Calendario | 69 | ~10 |
| Screener | 68 | ~10 |
| Superinvestor | 48 | ~7 |
| Segnali (lista) | 43 | ~6 |
| Dettaglio mercato | 16 | ~2 |
| Posizioni | 11 | ~1,5 |
| Setup | 8 | ~1 |
| Settori | 7 | ~1 |
| Diagnostica | 5 | <1 |
| Serie macro | 0 | 0 |

Il dettaglio di un segnale è stato aperto 9 volte in una settimana. Nel
database: **0 disegni** sul grafico, **2 prezzi-obiettivo**, **2 posizioni**.
Ne segue una regola di priorità semplice: un miglioramento sul cruscotto o sul
dettaglio titolo vale dieci volte uno sulle pagine secondarie.

## 3. Rilievi, con la misura

### 3.1 ⚠️ I conteggi dei segnali usano la data dell'ultima revisione — P1

La regola dei due orari (CLAUDE.md, «Un alert è una riga VIVA») è stata
applicata alle date mostrate e agli esiti, **non agli aggregati del backend**.
Una dozzina di interrogazioni filtra o ordina su `Alert.triggered_at`, che ogni
scansione riscrive finché il segnale persiste.

| Dove | Cosa dice | Cosa è vero |
|---|---|---|
| Digest Telegram del 24/09 | «723 alert nelle ultime 24h» | 87 nati nella finestra |
| Digest Telegram del 25/09 | «568 alert» | 66 nati |
| KPI del cruscotto, ultime 24h (oggi) | 555 | 71 |

Il digest elenca poi i «top per timestamp», cioè gli alert **appena rivisti**,
e stampa `trigger_price`, che è l'ultima chiusura e non il prezzo d'ingresso.
È il messaggio che arriva ogni mattina fuori dall'app, gonfiato di otto volte.

I punti coinvolti: `notifier_service._fetch_alerts_last_24h` (digest),
`stats_service` (KPI 24h e confronto col giorno prima, istogramma per giorno e
segnale, alert per indice a 30 giorni, titoli più attivi, titolo più attivo
della settimana), `alert_service` (filtro «dal / al» della lista, che ordina
invece per giorno di nascita), `leaderboard_service` (classifiche di settore),
`technical_score_service` (segnali recenti nella lente Tecnico),
`platform_health` (alert di una scansione).

**Correzione proposta:** una colonna `emitted_at` indicizzata, scritta alla
creazione e mai più toccata, riempita dallo storico con
`coalesce(snapshot.first_emitted_at, triggered_at)`, e ogni interrogazione
rivista (qualcuna, come l'ordine delle revisioni, può legittimamente restare
su `triggered_at`: va deciso caso per caso). Una colonna e non un'estrazione JSON: è il proprietario unico che
la regola chiede, e l'unica forma che un indice può servire. Un test per ogni
aggregato con un alert nato ieri e rivisto oggi, che deve contare ieri.

### 3.2 ⚠️ Il disco si riempie di immagini, e la pulizia coincide con l'allarme critico — P1

| | 15/09, dopo l'ampliamento | 26/09 |
|---|---|---|
| Disco `/` | 31% (~25 GB) | **66% (55 GB)** |
| `containerd` | ~7-8 GB | **37 GB** |
| Immagini dell'app in cache | poche | **69** |

Dal 21 settembre ogni push costruisce e scarica un'immagine nuova (10+ al
giorno nei giorni di lavoro). kubelet cancella le immagini inutilizzate solo
oltre l'**85%** di occupazione, e `FinanceAlertNodeRootFilling` (critico) scatta
quando lo spazio libero scende sotto il 15%, cioè **alla stessa soglia**. A
questo ritmo ci si arriva in circa una settimana: l'allarme suonerà mentre
kubelet libera spazio, e un drill del lunedì (~2 GB) nello stesso momento
avrebbe poco margine.

**Correzione proposta:** `--kubelet-arg=image-maximum-gc-age=72h` (k3s
v1.36.2, disponibile), eventualmente con `image-gc-high-threshold=70`, in
`infra/terraform/cloud-init/k3s.yaml` **e** sul nodo, con un riavvio di k3s: la
stessa procedura provata il 2026-09-09 (API in ~3 s, nessun pod perso).
⚠️ Va eseguita, non solo scritta nella unit: CLAUDE.md registra già una unit
aggiornata e mai eseguita per un mese e mezzo.

### 3.3 I traceback di produzione scrivono i valori delle variabili — P1, costo minimo

`app/core/logging.py` aggiunge tre sink loguru senza `diagnose=False`, e loguru
lo accende di default. Il traceback del rinnovo catalogo di stanotte stampa i
valori di ogni variabile di ogni frame. Un'eccezione in una funzione che
maneggia un token o una chiave finirebbe in chiaro nei log su disco e in Loki.
Una parola per sink.

### 3.4 Il catalogo del Dow Jones non si aggiorna dal 22 agosto — P2

`catalog_refresh_log`: DJI **6 fallimenti su 6** dal 2026-08-22, ultimo
successo il 15/08. La fonte (tabella Wikipedia) non restituisce più componenti
validi; il blocco anti-svuotamento ha evitato danni («refusing to wipe the
index») ma nessun allarme l'ha detto per cinque settimane. Il Dow cambia
composizione di rado, quindi il danno oggi è piccolo; il difetto è che **una
fonte di catalogo può morire in silenzio**. Correggere la tabella di
provenienza, e aggiungere un allarme sui fallimenti consecutivi di rinnovo per
indice.

### 3.5 Loki regge poche ore di interrogazione — P2

Loki ha un limite di **300 MiB** ed è alla versione **2.6.1** (2022). Durante
questa analisi un'aggregazione su 7-30 giorni l'ha ucciso per memoria
(OOMKilled alle 01:24 UTC, era su da 30 giorni; tornato pronto in un minuto).
Oggi i log sono di fatto interrogabili solo su finestre brevi. Proposta: 768 MiB
(il nodo ha ~4 GB disponibili), `split_queries_by_interval` e un tetto su
`max_query_length`; poi valutare l'aggiornamento a Loki 3.x.

### 3.6 Stabilità del layout: il dettaglio titolo «salta» — P2, da confermare

Web Vitals reali (RUM), 75° percentile a 30 giorni:

| Rotta | LCP | INP | CLS |
|---|---:|---:|---:|
| `/` | 1.645 ms ✓ | 25 ms ✓ | **0,19** (da migliorare) |
| `/stocks/:ticker` | 1.750 ms ✓ | 75 ms ✓ | **0,98** (scarso) |
| `/alerts` | 875 ms ✓ | 41 ms ✓ | 0,14 |

⚠️ I campioni sono pochi (sul dettaglio titolo pochi eventi CLS), quindi il
numero va confermato prima di lavorarci. Ipotesi coerente col codice: lo
scheletro di primo caricamento imita la disposizione normale, mentre sullo
schermo dell'utente (oltre 1920 px) si monta quella larga, e l'intera pagina si
ricompone all'arrivo dei dati. Sul cruscotto, righe che compaiono solo quando la
loro interrogazione risponde (agenda, liste). Proposta: misurare il CLS dentro
il gate UI (Chromium vero, dati seminati, `PerformanceObserver`) con un tetto
per rotta, poi riservare lo spazio. Così la misura non dipende da quante volte
l'utente apre la pagina.

### 3.7 Test mancanti sui numeri a schermo — P2

355 funzioni su 1.366 non sono eseguite da nessun test; 179 sono script una
tantum, ma **127 sono servizi e 28 API**. Fra queste, quelle che producono
numeri che l'utente legge:

- `timeframe_service.compute_timeframe_kpis` — i KPI multi-timeframe di ogni
  pagina titolo;
- `premarket_service` (`_premarket_from_frame`, `_recompute`) — i movers del
  jumbotron;
- `alerts.get_confluence` — 90 chiamate a settimana;
- `institutionals.aggregate` — la pagina Superinvestor;
- i parser di `institutional_scraper` e `news_analyst_extractor` — si rompono in
  silenzio quando la pagina sorgente cambia, come ha fatto il Dow Jones.

Proposta: test su fixture salvate (HTML e frame veri) per i parser, e test di
valore per i calcoli.

### 3.8 yfinance è quattro versioni indietro — P2

yfinance **1.3.0** contro 1.7.0. È la dipendenza più esposta ai cambi di Yahoo,
e le sue versioni correggono proprio quelle rotture. Anche uvicorn (0.46 →
0.54), starlette e SQLAlchemy (2.0 → 2.1) sono indietro, ma senza urgenza. Nel
frontend 37 pacchetti indietro, 7 di versione maggiore (tailwind 4,
lightweight-charts 5, typescript 7...): migrazioni vere, da pianificare, non da
inseguire.

### 3.9 Accessibilità della pagina Segnali — P2

La linea di base conta 74 violazioni, **51 su /alerts**: 39 pulsanti senza nome
accessibile, 10 elementi interattivi annidati, 2 intestazioni di tabella vuote.
Sono tutti pulsanti-icona della tabella: lavoro meccanico, e ogni correzione
abbassa la linea di base.

### 3.10 Rilievi minori

- **CLAUDE.md dice il falso sulla capitalizzazione.** La sezione «`stock.market_cap`
  is in the LISTING currency ... NOT fixed» è superata: FA-026 è chiusa e lo
  screener ordina su `market_cap_usd`. È esattamente la nota stantia che il file
  stesso indica come pericolosa. (Corretta insieme a questo rapporto.)
- **FA-006 si può chiudere** con la misura del §2.
- **Rilasci durante le scansioni:** 5 scansioni interrotte in 10 giorni da un
  riavvio per rilascio, tutte rilanciate da sole. Costo: una scansione rifatta
  e ~10 minuti di ritardo. Si evita rimandando il bump del tag quando una
  scansione è in corso.
- **`multi-tf-kpis`** è l'endpoint più lento (media 2,3-3,2 s): gli intervalli
  intraday vanno a Yahoo. Si può mostrare subito la parte giornaliera, che sta
  nel database, e riempire l'intraday dopo.
- **12 titoli fermi da oltre 30 giorni** (gestiti da FA-071: la scansione li
  salta). Alcuni sembrano cambi di simbolo o fusioni più che uscite (BNY
  Mellon `BK` ferma dal 10 luglio): manca un rilevamento dei cambi di ticker.
  A 47 titoli manca il settore, a 27 la capitalizzazione.
- **`api/types.ts`** (1.594 righe) è scritto a mano sui modelli del backend:
  FA-055 è nato esattamente da una copia divergente. Generarlo dallo schema
  OpenAPI toglierebbe la classe di difetto.

## 4. Che cosa aggiungere

Solo proposte che l'uso misurato giustifica. Nessuna tocca il motore: sette
studi dicono che tararlo non rende, e i modelli in prova e l'archivio
non-prezzo stanno accumulando i dati che un giorno potranno dire di più.

**A. Preferiti, «recenti» e ricerca con Ctrl+K.** Il gesto più frequente
dell'app è aprire un titolo (~16 volte al giorno), e oggi si passa dalla
ricerca o dalle liste del cruscotto. Una lista di titoli seguiti con prezzo
live nel cruscotto, gli ultimi titoli aperti a portata di clic, e la ricerca da
tastiera accorciano il percorso principale.

**B. Segnali per rilevanza, non per volume.** Nascono ~70 segnali al giorno per
un utente che apre la lista 6 volte. La Forza non ordina gli esiti (studio del
2026-09-23), quindi non può essere il criterio; la **rilevanza** sì: prima i
segnali su posizioni aperte, preferiti e setup seguiti. Vale per la lista, per
il digest (oggi «top per timestamp») e per la notifica per singolo segnale, che
oggi filtra su Forza ≥ 75.

**C. La scheda «questa settimana» (FA-088, idea dell'utente).** Eventi macro e
trimestrali dei titoli seguiti, con la distanza in giorni. I dati ci sono già
entrambi; con i preferiti di A si risolve anche il nodo aperto di FA-088
(«quali titoli entrano»).

**D. Un contatore d'uso delle pagine.** Questa analisi ha dovuto ricostruire
l'uso dai log, e ha abbattuto Loki per farlo. L'endpoint RUM riceve già la
rotta a ogni caricamento: contarla in una tabellina dà la stessa risposta in
un'interrogazione da un secondo, a schermo nella Diagnostica.

**E. Decidere su ciò che non si usa.** Disegni (0 in archivio, eppure ogni
apertura di un titolo li chiede al server), serie macro (0 aperture),
prezzi-obiettivo e posizioni (2 ciascuno), Settori (7 aperture a settimana).
Non propongo di toglierli d'ufficio: è una scelta dell'utente. Ma ogni
funzione tenuta costa manutenzione, test e richieste, e questi numeri sono la
base per decidere.

## 5. Priorità

Punteggio della skill di debito tecnico: **(Impatto + Rischio) × (6 − Sforzo)**,
ciascuno da 1 a 5.

| # | Voce | I | R | S | Punteggio |
|---:|---|:-:|:-:|:-:|---:|
| 1 | Pulizia immagini sul nodo (§3.2) | 3 | 5 | 1 | **40** |
| 2 | Conteggi dei segnali sulla data di nascita (§3.1) | 5 | 4 | 2 | **36** |
| 3 | `diagnose=False` nei log (§3.3) | 1 | 4 | 1 | **25** |
| 4 | yfinance e dipendenze Python (§3.8) | 2 | 4 | 2 | **24** |
| 5 | Nota stantia in CLAUDE.md, FA-006 chiusa (§3.10) | 1 | 3 | 1 | **20** |
| 6 | Catalogo Dow Jones + allarme sui rinnovi (§3.4) | 2 | 3 | 2 | **20** |
| 7 | Loki: memoria e limiti (§3.5) | 2 | 3 | 2 | **20** |
| 8 | Segnali per rilevanza, digest compreso (§4 B) | 4 | 2 | 3 | **18** |
| 9 | Accessibilità della pagina Segnali (§3.9) | 2 | 2 | 2 | **16** |
| 10 | Scheda «questa settimana» (§4 C) | 3 | 1 | 2 | **16** |
| 11 | Preferiti, recenti, Ctrl+K (§4 A) | 4 | 1 | 3 | **15** |
| 12 | CLS: misura nel gate, poi correzione (§3.6) | 3 | 2 | 3 | **15** |
| 13 | Test sui calcoli a schermo (§3.7) | 2 | 3 | 3 | **15** |
| 14 | Contatore d'uso delle pagine (§4 D) | 2 | 1 | 2 | **12** |
| 15 | Tipi del frontend dallo schema OpenAPI (§3.10) | 2 | 2 | 3 | **12** |
| 16 | `multi-tf-kpis` progressivo (§3.10) | 2 | 1 | 3 | **9** |
| 17 | Niente rilascio durante una scansione (§3.10) | 1 | 2 | 3 | **9** |
| — | Funzioni poco usate (§4 E) | — | — | — | decisione |

## 6. Piano in tre fasi

**Fase 1 — correttezza e rischio (1-2 giorni).** Voci 1, 2, 3, 5, 6, 7. Sono le
uniche con un difetto che l'utente vede già (il digest) o che arriverà da solo
(il disco).

**Fase 2 — solidità (circa una settimana).** Voci 4, 9, 12, 13, 17. Nessuna
cambia cosa l'app mostra; riducono la probabilità del prossimo guasto
silenzioso.

**Fase 3 — prodotto (a scelta).** Voci 8, 10, 11, 14, poi 15 e 16, e la
decisione su §4 E. L'ordine proposto segue l'uso: prima ciò che accorcia il
percorso cruscotto → titolo, poi il resto.

**Fuori dal piano, ma in calendario:** confronto dal vivo dei modelli in ombra
dopo sei mesi (marzo 2027; la selezione ne chiede sedici); FA-085 sui setup
ritirati quando la finestra si sarà chiusa su abbastanza casi; archivio
non-prezzo utile dopo dodici mesi.
