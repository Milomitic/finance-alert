# Studio e Mercati: analisi ed evolutive pronte da implementare (2026-11-27)

Le due sezioni più povere dell'app, guardate insieme perché condividono dati
(le serie complete di indici, materie prime e cripto), componenti (grafici,
calendari dei rendimenti) e regole (descrivere, non prevedere).

Ogni proposta è una **scheda eseguibile**: problema misurato, cosa costruire
(file, endpoint, forma dei dati), interfaccia su computer e telefono, test
(con il controllo negativo), criteri di verifica in produzione, sforzo. Le
schede hanno già un numero di backlog (FA-183 … FA-204) e sono ordinate in
ondate: la sezione 6 dice da dove partire.

Fonti: codice al commit `83bf5103`; produzione interrogata dal pod il
2026-11-27; interfaccia guardata in locale (stesso bundle, database di
sviluppo al 16/11) a 1440 px e a 375 px.

---

## 1. Stato di oggi, misurato

### 1.1 Mercati

| Cosa | Oggi |
|---|---|
| `/markets` | 98 righe: tre schede (Indici 9, Materie prime 4, Cripto 2) con nome, mini-linea, prezzo, variazione del giorno. Gli stessi dati del paniere della home |
| `/markets/:simbolo` | testata, grafico a candele con indicatori (buono), KPI tecnici per timeframe, KPI di prezzo, un riquadro «Meta», notizie |
| Dati già calcolati e **non usati** dalla sezione | ampiezza per 9 indici (`market-summary.by_index`), settori, distribuzione RSI, movers; serie complete dal 1927 (`market_detail_service`, in cache e scaldate ogni 5 minuti da FA-181); tassi e banche centrali da FRED (osservazioni dal 2023) |
| Costituenti nel catalogo | S&P 500 503, Nasdaq-100 101, FTSE 100 99, EuroStoxx 50 50, Hang Seng 50, FTSE MIB 40, Nikkei 40, Dow 30, KOSPI 20 |
| Tempi (dopo FA-181/182) | dettaglio indice 0,2-0,8 s, 172 KB compressi |

**Difetti visti a schermo:**

- **M-D1. Nomi illeggibili.** `MarketsPage.Riga` stampa `a.flag` come testo:
  si legge «us Nasdaq…», e nella colonna stretta il nome si riduce a «us…»,
  «Or…», «Bit…» su computer e a «u..», «j..» su telefono. Altrove la bandiera
  è un SVG (`/flags/us.svg`).
- **M-D2. Il link porta al future.** `to={quote_symbol ?? symbol}`: fuori
  orario apre la pagina di NQ=F invece di quella di ^IXIC, il contrario della
  correzione di FA-180 (la pagina dell'indice segue già il future da sola).
- **M-D3. Spazio sprecato.** Tre colonne di altezza molto diversa (9, 4, 2
  righe); metà schermo vuota; nessuna intestazione né contesto.
- **M-D4. Numeri all'inglese nel dettaglio.** `formatMarketPrice` usa
  `toFixed` (punto decimale) sotto 1.000 e toglie i decimali sopra: «7297»
  per 7.297,49, «47.59» per 47,59; «+1.60%», «PREV CLOSE». FA-177 non è
  arrivata qui.
- **M-D5. Testata accavallata su telefono.** «^GSPC» e «7297» si toccano, il
  nome diventa «S&P …».
- **M-D6. Il riquadro «Meta»** mostra «Bar nel chart 2514», «Range attivo 1d»,
  «Stato mercato OPEN», «Categoria Index»: informazioni da sviluppatore, in
  inglese.
- **M-D7. Etichette che non dicono cosa misurano.** «Range low 2191» è il
  minimo di dieci anni; «bull/bear» nella tabella dei KPI.
- **M-D8. Niente di ciò che si chiede a un indice:** rendimenti per periodo,
  distanza dal massimo, volatilità, composizione, confronto con altri
  mercati, stagionalità, legame con lo Studio.

### 1.2 Studio

Dopo l'ondata 1 (FA-178) lo Studio è **onesto**: verdetto in testa (non
concludente / compatibile con zero / instabile / diversa dalla base),
differenza con intervallo, stabilità nelle due metà, correzione di
Benjamini-Hochberg sulla stagionalità, distribuzione con percentili.

| Studio in produzione | Tempo | Esito |
|---|---|---|
| NVDA attorno alle trimestrali, 5 sedute | 287 ms | 20 eventi, 19 finestre: non concludente |
| Stagionalità ^IXIC | 157 ms | 4 su 17 sopravvivono alla correzione |
| Stagionalità GC=F | 179 ms | 3 su 17 |
| ^GSPC dopo −5% in 5 sedute, 21 dopo | 211 ms | 683 casi, 178 finestre: compatibile con zero |
| ^GSPC attorno al CPI | 110 ms | **19 rilasci** (date di rilascio solo dal 2025) |

**Difetti visti a schermo:**

- **S-D1. Colonna «Mediana» vuota nella stagionalità.** `stagionalita.gruppo`
  non calcola la mediana; la tabella stampa «—» su tutte le 17 righe.
- **S-D2. I modelli escono dal bordo su telefono** («Attorno a un ev…»), e il
  modulo occupa tutto il primo schermo: il risultato comincia sotto.
- **S-D3. L'istogramma non ha assi**: solo gli estremi, nessuna linea dello
  zero, nessuna mediana segnata.
- **S-D4. La stagionalità mostra barre senza intervallo**: l'intervallo di
  ogni mese sta solo in tabella, quindi il grafico dice «aprile +1,36%» senza
  dire «da +0,1 a +2,6».
- **S-D5. Nessun grafico per «dopo un movimento»** e il percorso attorno
  all'evento è una media senza banda né numero di eventi per punto (D-86).
- **S-D6. I casi non si vedono.** Lo Studio dice «22 casi» ma non QUALI: non
  si può controllare che il 2020 non pesi da solo, che è il primo dubbio
  sensato davanti a un risultato.
- **S-D7. Il simbolo si scrive a mano** e le serie macro si scelgono dall'ID
  FRED (D-83).
- **S-D8. Coperture corte**: date di rilascio macro 18-21 per serie (dal
  2025), trimestrali ~20 per titolo.

### 1.3 Cosa resta dell'analisi del 22/11

Ondata 2 (mai iniziata): F2 percorso con MAE/MFE, F6 primo passaggio, F7 al
netto del mercato, F9 drawdown, F15 ingressi contestuali, F16 galleria
(parziale: tre esempi), D-81, D-83, D-86. Ondata 3: F8, F10, F11, F12, F14,
F17, F19. Le schede della sezione 4 le riprendono tutte, con il disegno
concreto, più le nuove nate da questa passata.

---

## 2. Principi per entrambe le sezioni

1. **Descrivere, non prevedere.** Correlazioni, regimi, stagionalità e
   percentili sono fotografie del passato. Nessun colore o verbo che suggerisca
   un'azione («forte», «conviene»). È la regola del progetto
   (`trade playbook`, FA-057).
2. **Ogni numero col suo campione.** Un percentile dice su quale periodo; una
   correlazione su quante sedute; un rendimento a quale chiusura.
3. **La tavolozza ha un significato solo.** Rosa/smeraldo = direzione di un
   prezzo. Una correlazione o un percentile non sono una direzione: usano una
   scala neutra (sezione 5.4), col contrasto calcolato sui token come in
   `scoreMeta.contrasto.test.ts`.
4. **Un proprietario per ogni calcolo condiviso.** Rendimenti per periodo,
   calendario mensile, drawdown e volatilità servono sia a Mercati sia allo
   Studio: vivono in `app/stats/` e le due sezioni li chiamano.
5. **I tentativi si contano.** Ogni domanda nuova dello Studio moltiplica le
   occasioni di trovare rumore. Le domande di ondata 3 arrivano solo dopo il
   contatore delle varianti (FA-200).
6. **Altezze fisse e niente scorrimento laterale.** Il gate CLS (0,1) e il
   gate mobile (375 px) valgono per ogni scheda nuova.

---

## 3. Mercati: le schede

### FA-183 — Mercati, correzioni visibili · S (½ giorno)

**Problema:** M-D1 … M-D7.

**Cosa fare:**

- `MarketsPage.Riga`: bandiera come `<img src="/flags/{flag}.svg">` 18×12
  (il componente esiste nel dettaglio), nome intero su due righe (nome sopra,
  simbolo sotto), `min-w-0` + `truncate` solo sul nome; link sempre a
  `a.symbol` (M-D2).
- Formato: `formatMarketPrice` → `lib/money.ts`/`lib/numeri.ts`
  (`numero(v, decimali)` all'italiano, 2 decimali per indici e materie prime,
  0 sopra 10.000 solo per le cripto); variazioni con `percentuale()` e il
  `MENO`. Una funzione, testata.
- Testata del dettaglio: simbolo e nome su una riga, prezzo **sotto** su
  telefono (`flex-col sm:flex-row`); «PREV CLOSE» → «Chiusura prec.»; stati
  «LIVE» → «In seduta», «Ultima chiusura», «Future NQ=F» (FA-180).
- Il riquadro «Meta» sparisce: la categoria e la valuta vanno in testata, il
  resto è sostituito dalle Statistiche (FA-185).
- `TechnicalKpiCard`: «bull/bear» → «rialzo/ribasso» (è condivisa col
  titolo: cambia anche lì, va bene).
- KPI di prezzo: «Range high/low» → «Massimo/minimo del grafico (10 anni)»,
  o meglio la finestra effettiva calcolata dalle barre.

**Test:** `MarketsPage.test.tsx` — la bandiera è un `img` con `alt`, il nome
completo è nel DOM, il link punta al simbolo cash anche con `using_futures`.
Formato: tabella di casi (7.297,49 · 47,59 · 63.570 per BTC · −1,92%).
Controllo negativo: rimettere `quote_symbol` nel link e pretendere il rosso.

**Verifica:** a 375 px nessun nome sotto i 6 caratteri visibili (misura con
`read_page`), gate mobile verde.

---

### FA-184 — Panoramica dei rendimenti · M (1,5 giorni)

**Problema:** M-D3, M-D8. La pagina ripete la home; la domanda che la home non
copre è «come stanno andando i mercati su settimane e mesi».

**Backend:** `app/stats/rendimenti.py` (nuovo, puro, senza dipendenze dal
database):

```python
def rendimenti_per_periodo(date: list[date], chiusure: list[float], oggi: date) -> dict
# {"1s","1m","3m","6m","ytd","1a","3a","5a"} → rendimento semplice dall'ultima
# chiusura disponibile ALLA data di inizio del periodo (la prima seduta >= ),
# None se la storia non arriva. "3a" e "5a" anche annualizzati ("3a_ann").
def volatilita_annua(chiusure, sedute=20, giorni_anno=252) -> float | None
# deviazione standard dei rendimenti logaritmici * sqrt(giorni_anno);
# le cripto usano 365 (scambiano tutti i giorni) e lo DICHIARANO.
def distanza_dal_massimo(chiusure, finestra: int | None) -> dict
# {"valore", "data", "distanza_pct", "sedute_da"}; finestra None = storico.
```

Endpoint `GET /api/markets/panoramica` (in `api/market.py`), servito da una
`CacheFresca` di 5 minuti e scaldato dal job `riscalda_dettagli` di FA-181:

```json
{"alla_chiusura_del": "2026-11-26",
 "strumenti": [{"symbol": "^GSPC", "name": "S&P 500", "category": "index",
   "flag": "us", "ultima_chiusura": 7297.49,
   "rendimenti": {"1s": 0.012, "1m": -0.021, "3m": 0.04, "ytd": 0.18, "1a": 0.21,
                  "3a_ann": 0.15, "5a_ann": 0.13},
   "massimo_52s": {"distanza_pct": -0.063, "data": "2026-10-02"},
   "minimo_52s": {"distanza_pct": 0.15, "data": "2026-04-08"},
   "posizione_52s": 0.62, "vol_20g": 0.14, "vol_1a": 0.16,
   "sopra_ema200": true, "distanza_ema200": 0.031}]}
```

Fonte: `market_detail_service.get_detail(simbolo, "1d")` (storia completa, in
cache). La variazione di OGGI resta quella viva del paniere: la tabella dei
periodi è dichiaratamente «alla chiusura del …».

**Frontend:** `pages/MarketsPage.tsx` diventa a sezioni; componente
`components/markets/TabellaPanoramica.tsx`:

- Computer: tabella a larghezza piena, raggruppata per categoria (righe di
  intestazione), colonne Strumento · Ultimo · Oggi · 1S · 1M · 3M · YTD · 1A ·
  52 settimane (una barretta orizzontale col punto del prezzo fra minimo e
  massimo) · Dal massimo · Vol. 20g. Ordinabile per colonna (lato client: le
  righe sono ~15, tutte presenti). Prima colonna ferma.
- Celle dei rendimenti: testo nel colore di direzione e **fondo tenue
  proporzionale** (3 intensità, soglie per periodo: un 3% in un giorno non è
  un 3% in un anno — soglie `{1s: 1/3/6, 1m: 2/5/10, …}` in un solo file).
- Telefono: niente tabella. Un `Segmentato` sceglie il periodo (Oggi · 1S · 1M
  · YTD · 1A), ogni strumento è una riga a due livelli (nome intero + simbolo;
  prezzo + rendimento del periodo scelto) e la barretta delle 52 settimane
  sotto. Categoria come intestazione appiccicosa.

**Test:** `test_rendimenti.py` — anno bisestile, YTD il 2 gennaio (la prima
seduta dell'anno), storia più corta del periodo → None, cripto con 365. Un
test pretende che `api/market.py` e lo Studio chiamino la STESSA funzione
(censimento sulla sorgente, come `test_periodi_indicatori.py`).
`TabellaPanoramica.test.tsx`: ordinamento, cella None → «—» e non 0.

**Verifica:** in produzione ^GSPC 1A confrontato a mano con le due chiusure
lette dal dettaglio; tempo dell'endpoint < 100 ms a caldo.

---

### FA-185 — Dettaglio: Statistiche e calendario dei rendimenti · M (1,5 giorni)

**Problema:** M-D6, M-D8. Il dettaglio di un indice non dice di quanto è
salito quest'anno, quanto è lontano dal massimo, come si è comportato mese
per mese.

**Backend:** `app/stats/calendario.py` (nuovo, condiviso con FA-195):

```python
def calendario_mensile(date, chiusure) -> dict
# {"anni": [{"anno": 2026, "mesi": [r_gen | None, …12], "anno_totale": r}],
#  "media_mesi": [...12], "positivi_mesi": [...12]}
# rendimento da fine mese a fine mese, come la stagionalità dello Studio:
# la stagionalità diventa una VISTA di questa tabella (un proprietario solo).
```

e `app/stats/drawdown.py` (condiviso con FA-198):

```python
def drawdown(date, chiusure, soglia=0.10) -> dict
# {"corrente": {"pct", "dal_picco", "sedute"},
#  "massimo": {"pct", "picco", "minimo", "recupero" | None},
#  "episodi": [{"picco","minimo","recupero","pct","sedute_discesa","sedute_recupero"}]}
```

Endpoint `GET /api/markets/{simbolo}/statistiche` → rendimenti per periodo
(FA-184), volatilità 20g e 1a, distanza dal massimo storico e da quello a 52
settimane, drawdown massimo in 1, 5 anni e storico con le date, calendario
mensile. In cache per (simbolo, giorno).

**Frontend:** al posto di «Meta», nella colonna destra:

- **Statistiche** (`components/markets/StatisticheMercato.tsx`): griglia di
  tessere — YTD, 1A, 5A annualizzato, Dal massimo (con la data), Vol. 20g e
  1a, Peggior calo in 5 anni (con le date). Altezza fissa.
- **Calendario dei rendimenti** (`components/stats/CalendarioRendimenti.tsx`,
  condiviso con lo Studio): anni in riga (ultimi 12, «Mostra tutti» per la
  storia completa), mesi in colonna, ultima colonna l'anno. Cella colorata col
  fondo tenue di direzione; in fondo la riga «Media» e la riga «Positivi»
  (quota). Su telefono: una riga per anno con 12 quadratini senza numeri
  (tocca per il valore) e il totale dell'anno a destra.
- Sotto il calendario un rimando: «Questi mesi sono diversi dagli altri? →
  Stagionalità nello Studio» (link con i parametri: la domanda giusta per un
  calendario è la correzione per famiglia, che sta là).

**Test:** calendario su una serie sintetica con salti di mese e un mese senza
sedute; drawdown con recupero, senza recupero, e con due episodi annidati.
Controllo negativo sul drawdown: una serie monotona crescente ha `massimo.pct
== 0`.

**Verifica:** ^GSPC 2008 nel calendario (−38,5% d'anno, controllabile a mano);
peggior calo storico ~−86% (1929-32) sulla storia completa.

---

### FA-186 — Composizione dell'indice · M (2 giorni)

**Problema:** sette dei nove indici del paniere hanno i costituenti nel
catalogo, con ampiezza già calcolata a ogni scansione, e la pagina
dell'indice non lo sa. È la capacità più distintiva che la sezione può avere:
nessun sito generico lega un indice ai segnali e ai punteggi dei suoi titoli.

**Mappa** (in `api/market.py`, accanto a `LIVE_ASSET_DEFINITIONS`):

| Simbolo | Indice del catalogo | Nota da dichiarare |
|---|---|---|
| ^GSPC | S&P 500 (503) | — |
| ^DJI | Dow Jones (30) | **pesato sul prezzo**: niente «contributo» da capitalizzazione |
| ^IXIC | Nasdaq-100 (101) | «i 101 titoli del Nasdaq-100, non i ~3.000 del Composite» |
| ^STOXX50E | EuroStoxx 50 (50) | — |
| FTSEMIB.MI | FTSE MIB (40) | — |
| ^HSI | Hang Seng top 50 | — |
| ^N225 | Nikkei 225 (40 principali) | «40 su 225» |

**Backend:** `GET /api/markets/{simbolo}/composizione`:

```json
{"indice": {"code": "SP500", "nome": "S&P 500", "titoli_nel_catalogo": 503,
            "nota": null},
 "ampiezza": {"avanzano": 402, "scendono": 98, "sopra_ema50_pct": 61.2,
              "sopra_ema200_pct": 55.0, "vicini_massimi_52s": 41,
              "vicini_minimi_52s": 6, "rsi_sopra_70": 22, "rsi_sotto_30": 4},
 "settori": [{"settore": "Technology", "titoli": 68, "var_media_pct": 1.4,
              "peso_cap_pct": 31.0}],
 "migliori": [{"ticker", "nome", "var_pct", "contributo_stimato_pp"}],
 "peggiori": [...],
 "segnali_oggi": {"rialzo": 12, "ribasso": 7},
 "alla_scansione_del": "2026-11-26T23:32:00Z"}
```

Ampiezza da `market_stats_service` (`by_index`, già nel riepilogo); migliori e
peggiori dalle ultime due barre dei costituenti (una query su ~500 id);
contributo stimato = peso di capitalizzazione nel catalogo × variazione,
**solo** per gli indici pesati sulla capitalizzazione, etichettato «stimato
sulla capitalizzazione del catalogo, non sui pesi ufficiali». Cache 5 minuti.

**Frontend:** `components/markets/ComposizioneIndice.tsx`, sotto il grafico,
a tutta larghezza:

- Riga di ampiezza: una barra divisa avanzano/scendono, e quattro tessere
  (sopra EMA50, sopra EMA200, vicini ai massimi, vicini ai minimi). Ogni
  tessera porta il suo denominatore («su 503»).
- Settori: barre orizzontali ordinate per peso, colore di direzione sulla
  variazione media.
- Migliori/peggiori: due liste da 5 con logo, ticker, variazione e link al
  titolo.
- Pulsante «Apri i 503 titoli nello screener» → `/stocks?index=<code>`
  (il filtro esiste: `StocksBrowserPage` legge `index`).

Telefono: le stesse sezioni impilate, settori ridotti ai primi 6 con «Tutti».

**Test:** la mappa copre ogni indice con costituenti (test che legge
`stock_indices` dal seme); il Dow non ha `contributo_stimato_pp`; un indice
senza costituenti (^VIX, ^HSI se il catalogo ne fosse privo) rende 404 e il
frontend non monta la sezione (altezza riservata solo se c'è).

**Verifica:** su ^GSPC avanzano + scendono + invariati = titoli con dati;
confronto con la riga S&P 500 della matrice d'ampiezza della home.

---

### FA-187 — Confronto normalizzato · M (1,5 giorni)

**Problema:** «l'oro ha fatto meglio del Nasdaq quest'anno?» oggi non ha
risposta nell'app.

**Backend:** `GET /api/markets/confronto?simboli=^GSPC,GC=F,BTC-USD&dal=2026-01-01`
→ date comuni e serie in base 100. Accetta **anche titoli del catalogo**
(riusa `studio_service.serie_di`, che sa leggere entrambi), al massimo 6
simboli. Allineamento sulle date in comune per ogni coppia di sedute
consecutive (le cripto scambiano il sabato: si tiene l'ultima chiusura nota,
dichiarato). Risposta piccola: solo chiusure, niente indicatori.

```json
{"date": ["2026-01-02", ...],
 "serie": {"^GSPC": [100, 100.4, ...], "GC=F": [...]},
 "riepilogo": {"^GSPC": {"rendimento": 0.18, "peggior_calo": -0.11,
                          "vol_ann": 0.15}}}
```

**Frontend:** `components/markets/ConfrontoNormalizzato.tsx` con
lightweight-charts (serie a linea, una per simbolo), periodo con `Segmentato`
(1M · 3M · 6M · YTD · 1A · 3A · 5A · 10A), aggiunta di un simbolo con la
ricerca (FA-199 la generalizza), stato nell'URL (`?confronta=^GSPC,GC=F&periodo=ytd`).
Legenda sotto il grafico: colore, nome, rendimento del periodo, peggior calo.
Palette **categoriale** da 6 colori, distinta da rosa/smeraldo (sezione 5.4).
Default: S&P 500, Euro Stoxx 50, FTSE MIB, Oro, Bitcoin.

Ingresso anche dal dettaglio: «Confronta con…» accanto al titolo del grafico
apre la pagina Mercati col confronto pronto.

**Test:** allineamento con un calendario a 7 giorni contro uno a 5; un simbolo
sconosciuto rende 404 col suo nome; più di 6 → 422.

**Verifica:** Oro YTD letto sul grafico = Oro YTD della panoramica (FA-184):
due viste, un numero.

---

### FA-188 — Contesto di mercato · M (1,5 giorni)

**Problema:** la pagina non dice in che situazione sono i mercati: tassi,
volatilità attesa, ampiezza.

**Backend:** `GET /api/markets/contesto`, cache 15 minuti. Cinque misure, ognuna
con valore, variazione a 1 mese, mini-serie di un anno e **percentile nel
periodo disponibile, col periodo scritto**:

| Tessera | Fonte | Periodo del percentile |
|---|---|---|
| VIX | ^VIX dal dettaglio mercati | dal 1990 |
| Tassi USA 10a e 2a, e la loro differenza | FRED `DGS10`, `DGS2` (osservazioni dal 2023) | **dal 2023**: va detto, è corto |
| Fed e BCE | `DFEDTARU`, `ECBDFR` | — (livello e data dell'ultima variazione) |
| Ampiezza dell'universo | `market-summary.global.pct_above_ema200` | ⚠️ **nessuno oggi**: `market_snapshot` tiene solo l'ultima riga (verificato il 27/11). Serve un archivio giornaliero (tabella `ampiezza_giornaliera`, una riga per scansione notturna: data, % sopra EMA50/200, avanzano, scendono, per l'universo e per indice); il percentile compare quando la storia ha almeno un anno, prima si mostra solo il valore |
| Dollaro | DX-Y.NYB (dopo FA-190) | dal 2000 |

**Frontend:** `components/markets/ContestoMercato.tsx`, fascia di tessere in
cima a `/markets` (5 su computer, 2 per riga su telefono), altezza fissa.
Nessun colore «buono/cattivo»: il percentile è un'etichetta («al 78° percentile
dal 1990»), la variazione segue la direzione. Fra parentesi la frase fissa:
«Descrive la situazione, non la prevede».

**Test:** percentile con valori ripetuti; serie FRED vuota → tessera assente,
non a zero; tessera dell'ampiezza senza percentile finché l'archivio ha meno
di un anno.

**Sforzo con l'archivio dell'ampiezza:** +½ giorno (tabella, migrazione,
scrittura a fine scansione). Conviene accenderlo **subito**, anche prima del
resto della scheda: la storia comincia solo da quando si archivia.

**Verifica:** VIX della tessera = VIX del paniere; percentile ricalcolato a
mano su un campione.

---

### FA-189 — Correlazioni fra mercati · S-M (1 giorno)

**Problema:** «l'oro si muove ancora contro le azioni?» — una domanda da
mercati che l'app sa già calcolare: `rischio_posizioni_service.correlazioni`
lavora su mappe data→rendimento e regge calendari diversi.

**Backend:** `GET /api/markets/correlazioni?sedute=60` (60 o 250) sul paniere:
matrice, più per ogni coppia la stessa correlazione un anno fa (per dire se
è cambiata). Rendimenti giornalieri sulle date comuni; le coppie con meno di
40 date comuni restano vuote.

**Frontend:** `components/markets/MatriceCorrelazioni.tsx`: triangolo
inferiore, celle con scala **divergente neutra** (sezione 5.4), valore a due
decimali al passaggio e in `sr-only`; selettore 60 sedute · 1 anno. Toccando
una cella si apre il confronto normalizzato della coppia (FA-187). Su
telefono: elenco delle 8 coppie più e meno correlate invece della matrice.

**Test:** correlazione di una serie con sé stessa = 1; serie costante → vuoto
(non NaN); simmetria.

---

### FA-190 — Paniere esteso: valute, tassi, altri indici · S-M (1 giorno)

**Problema:** il paniere è quello della home, pensato per il nastro dei
prezzi. Per una pagina Mercati mancano il dollaro, l'euro-dollaro, i tassi e
indici principali (Russell 2000, DAX, CAC 40, FTSE 100, KOSPI), il rame.

**Backend:** `MERCATI_ESTESI` in `api/market.py`, **separata** da
`LIVE_ASSET_DEFINITIONS` così la home non cambia: ^RUT, ^GDAXI, ^FCHI, ^FTSE,
^KS11, DX-Y.NYB, EURUSD=X, USDJPY=X, ^TNX (rendimento a 10 anni, già in
percentuale), HG=F. Categorie nuove `fx` e `tassi`. `_LIVE_META` le include,
così il dettaglio le apre. `GET /api/markets/estesi` con `CacheFresca` da 30 s
(le quotazioni) e lo stesso `quotazione_da_mostrare` per gli indici con
future (^RUT ↔ RTY=F).

⚠️ Il rendimento di ^TNX è un **livello**, non un prezzo: le variazioni si
dicono in punti base, non in percentuale. Va nel formato della categoria.

**Frontend:** le categorie nuove in `/markets` (panoramica e schede);
`NavbarSearch` sezione Mercati estesa.

**Test:** ogni simbolo esteso ha meta; ^TNX formattato in punti base;
il paniere della home è invariato (conteggio).

**Verifica:** dopo il rilascio, un giro completo di `estesi` sotto 1,5 s a
freddo, nessun simbolo con `error`. Sondati dal pod il 27/11, rispondono
tutti: RTY=F 2.754, DX-Y.NYB 104,05, ^TNX 4,93, ^KS11 4.916, HG=F 5,60,
EURUSD=X 1,0936.

---

### FA-191 — Orari delle borse · S (½ giorno)

Una fascia sottile in cima a `/markets`: Tokyo · Hong Kong · Europa · Londra ·
New York (pre-market, seduta, after-hours), ciascuna con stato e «apre fra
2 h 10'» / «chiude fra 35'». Fonte: `live_quote_service._MARKET_HOURS_LOCAL`
e `_is_premarket` (fuso con l'ora legale). ⚠️ **Nell'app non esiste un
calendario delle festività** (verificato il 27/11: `live_quote_service` lo
dichiara, «only weekday + time-of-day»). Due strade: dichiarare «festività non
considerate» sotto la fascia, oppure una tabella delle chiusure NYSE ed
europee scritta per l'anno (una ventina di date, aggiornata a gennaio) che
servirebbe anche al pre-market e allo stato LIVE — il Ringraziamento del
26/11 è passato come seduta normale per l'interfaccia. Componente puro con
l'orologio iniettato (`useNowTick`), test su un giorno di cambio dell'ora.

---

### FA-205 — Calendario delle chiusure di borsa · S (½ giorno)

**Problema:** nell'app nessun pezzo sa che una borsa è chiusa per festa. Il
26/11 (Ringraziamento) l'interfaccia ha trattato New York come in seduta, e
il giorno dopo il pre-market ha letto una seduta inesistente come «ieri».

**Cosa fare:** `app/core/chiusure_borsa.py` con le date di chiusura intera e
di chiusura anticipata per NYSE, Xetra/Borsa Italiana, LSE, Tokyo e Hong Kong,
per l'anno in corso e il successivo (una ventina di righe per borsa, dalle
pagine ufficiali), più un test che fallisce a dicembre se manca l'anno dopo —
così l'elenco non scade in silenzio (la lezione dell'elenco macro scritto a
mano che finiva il 31 agosto). Lo usano `_is_market_open`, `_is_premarket`,
FA-191 e lo stato «in seduta» del paniere. Mezze giornate (il 27/11 New York
chiude alle 13:00) incluse.

---

## 4. Studio: le schede

### FA-192 — Studio, correzioni visibili · S (½ giorno)

- **S-D1** `stagionalita.gruppo`: `mediana` (e `intervallo` già c'è). Test
  che la pretende non nulla su ogni gruppo con casi.
- **S-D2** modelli in un `Segmentato` che va a capo (o `select` sotto `sm`);
  dopo il calcolo, su telefono, il modulo si chiude in una riga
  «AAPL · −10% in 5 · 21 sedute · Modifica» (D-87, la parte non fatta).
- **S-D3** istogramma: tacche sull'asse X in percentuale, linea dello zero,
  mediana della condizione e della base segnate; passare a `GraficoSvg`
  (barre + riferimenti verticali: serve `riferimentiX`, piccola estensione).
- Il segno meno tipografico nella frase («−10%», non «-10%»), come FA-177.
- Evento con zero eventi: un solo messaggio («Nessuna trimestrale nota per
  NVDA: lo studio sulle trimestrali vale per i titoli del catalogo con la
  cache dei fondamentali») e niente verdetto a «0 finestre».

---

### FA-193 — Vedere i casi, ed esportarli · S-M (1 giorno)

**Problema:** S-D6. Il primo controllo di chiunque davanti a «22 casi» è
guardare quali.

**Backend:** `_misura` riceve le date e i valori e rende anche `casi`
(al massimo 500, i più recenti prima):

```json
"casi": [{"data": "2025-04-04", "esito": 0.081, "episodio": 7, "primo": true,
          "mossa": -0.142}]
```

`episodio` = numero della finestra indipendente (lo stesso raggruppamento di
`independent_blocks`, esposto), `primo` = primo giorno dell'episodio. Per
l'evento: la data dell'evento e il suo esito; per la stagionalità i casi sono
il calendario (FA-195).

**Frontend:** sotto la distribuzione, «I 22 casi (9 episodi)» richiudibile:
tabella data · mossa · esito, con gli episodi raggruppati (solo il primo
giorno in evidenza, gli altri rientrati). Toggle «Solo il primo giorno di ogni
episodio». Pulsante **Esporta CSV** (lato client, `Blob`, separatore `;` e
virgola decimale per Excel italiano). Su telefono: schede da tre righe.

**Test:** casi ed episodi coerenti con `finestre`; CSV con BOM UTF-8 e
virgola decimale; un caso con esito None non rompe l'esportazione.

---

### FA-194 — Il percorso, con la banda e il «quanto bisognava sopportare» · M (2 giorni)

**Problema:** S-D5, e la F2 dell'analisi precedente.

**Backend** (`studio_service`):

- `dopo_movimento` rende `percorso`: per k = 0…H, media, mediana, 10° e 90°
  percentile del rendimento cumulato dei casi, e la media della base; più
  `escursioni`: per ogni caso il minimo (MAE) e il massimo (MFE) lungo il
  percorso, riassunti in mediana e 90° percentile.
- `evento` rende anche mediana e 10°/90° percentile per seduta, il numero di
  eventi per seduta, e (se ≤ 40) i percorsi dei singoli eventi con la data.

**Frontend:** `components/studio/GraficoPercorso.tsx` su `GraficoSvg`
(serve un tipo `banda`: area fra due serie — estensione piccola e riusabile):
banda 10-90 tenue, mediana piena, media tratteggiata, base grigia
tratteggiata, linea dello zero; per l'evento una linea verticale sul giorno
dell'evento e, se ci sono, i percorsi singoli in grigio sottile con la data al
passaggio. Sotto, una frase sola:

> Lungo le 21 sedute, nel caso tipico la discesa massima è stata −4,1%; in un
> caso su dieci ha superato −11,2%.

Altezza fissa 240 px (180 su telefono).

**Test:** percorso su una serie a gradino nota; MAE di una serie monotona
crescente = 0; numero di eventi per seduta decrescente ai bordi.

---

### FA-195 — Stagionalità: intervalli a schermo e calendario anni × mesi · S (1 giorno)

**Problema:** S-D4.

- Il grafico dei mesi diventa un **forest plot**: un punto per mese con la
  sua barra d'intervallo, linea dello zero, colore solo per i mesi che
  superano la correzione (come oggi), etichetta «4 su 17 dopo la correzione».
  Lo stesso per i giorni della settimana (oggi solo in tabella).
- Sotto, il **calendario dei rendimenti** di FA-185 (stesso componente, stessa
  funzione `calendario_mensile`): permette di vedere se un mese «forte» lo è
  per tre anni eccezionali o con regolarità. È la prova di stabilità della
  stagionalità, a occhio.
- La stagionalità del server passa da `calendario_mensile`: un proprietario.

**Test:** il forest plot riceve gli intervalli dal payload (nessun ricalcolo
nel client); censimento: `stagionalita` chiama `calendario_mensile`.

---

### FA-196 — Toccare prima il target o lo stop · S (1 giorno)

F6. Modello nuovo «Toccare prima»: «Se compro AAPL oggi, con un target a +8%
e uno stop a −5%, cosa è successo prima, storicamente, entro 21 sedute?»

**Backend:** `GET /api/studio/primo_passaggio?simbolo&lato&target_pct&stop_pct&orizzonte`
che riusa `rischio_posizioni_service.primo_passaggio` (finestre disgiunte,
Wilson, stop e target nella stessa barra = stop). Serve `serie_di` con
massimi e minimi: `Serie` guadagna `alti`/`bassi` opzionali (il catalogo e il
dettaglio mercati li hanno).

**Frontend:** barra divisa target prima / stop prima / nessuno dei due, con
gli intervalli di Wilson; verdetto «non concludente» sotto 20 finestre. Colori
di direzione (qui sono davvero rialzo e ribasso). Frase fissa: «È la storia
del titolo con queste distanze, non una probabilità per domani».

**Test:** stessa barra = stop; serie che sale soltanto = tutti target.

---

### FA-197 — Al netto del mercato · S (1 giorno)

F7. Opzione «al netto di» (S&P 500 di default, o un altro indice del
paniere) per «dopo un movimento», «evento» e stagionalità: il rendimento in
eccesso sullo stesso intervallo di date. Per un titolo non USA il default è il
suo indice locale (FTSE MIB per `.MI`, ecc., dalla mappa di FA-186).

**Backend:** `app/stats/eccesso.py`: allinea due serie per data e rende la
serie dei rapporti; i modelli lavorano sulla serie dei rapporti senza sapere
nulla. Parametro `netto=^GSPC`.

**Frontend:** casella «al netto di [S&P 500 ▾]» nel modulo; il titolo del
risultato lo dice («… in eccesso sull'S&P 500»).

**Test:** una serie identica al riferimento → eccesso zero ovunque; date non
allineate.

---

### FA-198 — Cali e recuperi · S-M (1 giorno)

F9. Modello «Cali e recuperi» (riusa `app/stats/drawdown.py` di FA-185):
elenco dei cali oltre X% con picco, minimo, profondità, sedute di discesa e di
recupero; grafico «sott'acqua» (distanza dal massimo nel tempo, area);
mediana della profondità e dei tempi di recupero; dove sta il calo di oggi fra
quelli storici («il calo attuale, −12%, è più profondo di 31 dei 44 cali oltre
il 10% dal 1990»).

---

### FA-199 — Il modulo come frase, a due colonne, con la ricerca · M (1,5 giorni)

S-D2, S-D7, D-81, D-83 e il ridisegno 5.1-5.2 dell'analisi del 22/11, mai
fatto:

- da `lg` due colonne: domanda a sinistra (320 px, ferma), risultato a destra;
- il modulo scritto come frase («Se **AAPL** è **sceso** del **10%** in **5**
  sedute, cosa è successo nelle **21** dopo?»), con i campi dentro la frase;
- simbolo con **ricerca** (riusa la ricerca della barra in alto: titoli e
  mercati), serie macro scelta **per nome** da un elenco (endpoint che rende
  `macro_series` con etichetta);
- galleria di partenza da 6 domande (oggi 3), una per modello;
- **ingressi contestuali** (F15): «Studia» nella testata del titolo, nel
  dettaglio mercato (sezione «Domande pronte» di FA-185), sulla riga di una
  posizione, nel dialogo di un segnale (porta a FA-202).

---

### FA-200 — Studi salvati e contatore delle varianti · M (2 giorni) — prerequisito dell'ondata 3

F17. Il presidio contro la ricerca del rumore, prima di dare domande nuove.

**Backend:** tabelle `studi_salvati` (id, nome, simbolo, modello, parametri
JSON, creato_il) e `studi_tentativi` (simbolo, modello, impronta dei
parametri, quando), migrazione alembic. Ogni calcolo registra un tentativo
(scrittura leggera, fuori dalla risposta). `GET /api/studio/tentativi?simbolo&modello`
→ varianti distinte negli ultimi 30 giorni. CRUD degli studi salvati.

**Frontend:** sotto il verdetto, quando le varianti sono più di una:

> Hai provato 7 varianti di questa domanda su AAPL in 30 giorni. Con 7
> tentativi, la probabilità che almeno uno esca «diverso dalla base» per puro
> caso è circa 30%.

(1 − 0,95ⁿ, dichiarato come approssimazione per prove indipendenti.)
Elenco degli studi salvati nella colonna della domanda; «Salva» accanto a
«Calcola».

**Test:** la stessa domanda ripetuta non conta come variante; la frase
appare da 2 in su; il calcolo non fallisce se la scrittura del tentativo
fallisce.

---

### FA-201 — Dopo una condizione tecnica o di regime · M (2 giorni) — dopo FA-200

F12. Modello «Dopo una condizione» con un menu chiuso, per non diventare un
generatore di ipotesi: RSI(14) sotto 30 / sopra 70; chiusura sotto/sopra
l'EMA200; nuovo massimo / minimo a 52 settimane; VIX sopra X (serie ^VIX
allineata). L'evento è il **primo giorno** in cui la condizione diventa vera
(non ogni giorno in cui resta vera), con il raggruppamento in episodi di
sempre. Periodi da `app.indicators.periods` (fonte unica).

---

### FA-202 — Dopo i segnali del motore · M (1,5 giorni) — dopo FA-200

F10. «Cosa è successo dopo i segnali `trend_pullback` su AAPL, sul suo
settore, su tutto l'universo», agli orizzonti 1/5/21/63 contro il controllo
abbinato. Dati già maturati in `esiti_orizzonti` (`cella`,
`celle_per_detector`): serve un filtro per simbolo e settore. Ingresso dal
dialogo di un segnale. Su un titolo solo sarà quasi sempre «non concludente»,
ed è giusto che lo dica.

---

### FA-203 — Due simboli: rapporto e piccoli multipli · M (2 giorni) — dopo FA-200

F11. (a) «Simbolo B» facoltativo: lo studio gira sul **rapporto** A/B (oro
contro S&P 500, un titolo contro il suo settore), riusando la serie dei
rapporti di FA-197. (b) La stessa domanda su fino a 4 simboli, in piccoli
multipli con lo stesso asse. Il contatore di FA-200 conta ogni simbolo come
una variante.

---

### FA-204 — Eventi con storia lunga e sorprese · L (3-4 giorni)

F8 + F19.

- **Date di rilascio macro storiche**: l'API FRED `series/vintagedates` rende
  le date in cui una serie è cambiata, cioè i rilasci, dal 1990 circa. Uno
  script di riempimento (`app.scripts.backfill_date_rilascio`) le scrive in
  `macro_release_dates`; il CPI passa da 19 a ~400 rilasci. ⚠️ Verificare su un
  rilascio noto prima di riempire la storia (la lezione di Nasdaq, che data al
  giorno dopo).
- **Trimestrali con la sorpresa**: `yfinance.Ticker.get_earnings_dates(limit=100)`
  rende data, stima, EPS riportato e sorpresa per ~25 anni. Tabella
  `trimestrali_storiche` (ticker, data, stima, riportato, sorpresa_pct),
  riempita una volta e aggiornata dal job delle trimestrali.
- Condizione «battute / mancate» nel modello evento; per le macro «sopra /
  sotto il consenso» dove `macro_consenso` ha il previsto.

---

## 5. Disegno

### 5.1 `/markets`, computer

```
┌ Mercati ─────────────────────────────────────────────── alla chiusura del 26/11 ┐
│ Tokyo ● chiusa · apre fra 9 h │ Europa ● aperta · chiude fra 2 h │ NY ◐ pre-market │  FA-191
├──────────────┬──────────────┬──────────────┬──────────────┬──────────────────────┤
│ VIX 23,8     │ 10a−2a +0,42 │ Fed 4,25%    │ Sopra EMA200 │ Dollaro 104,2         │  FA-188
│ 78° pct ▁▃▅▇ │ dal 2023 ▃▅▆ │ BCE 2,00%    │ 49,5% univ.  │ −1,2% in un mese      │
├──────────────┴──────────────┴──────────────┴──────────────┴──────────────────────┤
│ Strumento        Ultimo   Oggi    1S     1M     3M    YTD    1A   52 sett.  Dal max│  FA-184
│ INDICI                                                                              │
│ 🇺🇸 S&P 500       7.297,49 +1,60% +1,2%  −2,1%  +4,0% +18%  +21%  ──●───   −6,3%  │
│ 🇺🇸 Nasdaq Comp. 24.129,5  +2,33% …                                                │
│ MATERIE PRIME · CRIPTO · VALUTE · TASSI …                                           │
├────────────────────────────────────────────┬────────────────────────────────────────┤
│ Confronto  [1M 3M 6M YTD 1A 3A 5A 10A]     │ Correlazioni  [60 sedute | 1 anno]     │  FA-187
│  ╱‾‾╲__╱‾‾  S&P  +18%                       │   ■ □ ▪ …   (triangolo)                │  FA-189
│ ╱       Oro +31%   BTC −8%                  │                                        │
└────────────────────────────────────────────┴────────────────────────────────────────┘
```

### 5.2 `/markets`, telefono (375 px)

```
Mercati                         alla chiusura del 26/11
[Tokyo ● · Europa ● · NY ◐ →]      (scorre da sola, una riga)
┌ VIX 23,8 ┐┌ 10a−2a ┐            (2 per riga, 3 righe)
[ Oggi | 1S | 1M | YTD | 1A ]      (Segmentato)
INDICI
🇺🇸 S&P 500                7.297,49
   ^GSPC  ──●──            +18,0%
🇺🇸 Nasdaq Composite      24.129,5
…
Confronto (grafico a tutta larghezza, 200 px)
Coppie più e meno correlate (elenco)
```

### 5.3 `/markets/:simbolo`

```
← Mercati
┌ 🇺🇸 S&P 500  ^GSPC · Indice · USD        In seduta  7.297,49  +1,60% ┐
│                                          Chiusura prec. 7.182,6          │
├───────────────────────────────────────────┬─────────────────────────────┤
│ Grafico (com'è)                            │ Statistiche   FA-185         │
│                                            │ YTD +18% · 1A +21% · Dal max │
│                                            │ −6,3% (2 ott) · Vol 20g 14%  │
│                                            │ KPI tecnici (com'è)          │
├───────────────────────────────────────────┴─────────────────────────────┤
│ Composizione · S&P 500 (503 titoli)                         FA-186       │
│ ▓▓▓▓▓▓▓▓▓░░ 402 su · 98 giù   Sopra EMA200 55% · Massimi 41 · Minimi 6   │
│ Settori ▬▬▬▬ Tech 31%  …        Migliori · Peggiori          [Screener →]│
├──────────────────────────────────────┬──────────────────────────────────┤
│ Calendario dei rendimenti  FA-185    │ Domande pronte per lo Studio     │
│ 2026 ■■□■■■□■■■■  +18%               │ · Dopo un calo del 5% in 5 sedute│
│ 2025 ■□■■■■■□■■■■ +24%               │ · Stagionalità · Attorno al CPI  │
├──────────────────────────────────────┴──────────────────────────────────┤
│ Notizie (com'è)                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 5.4 Colori

| Uso | Token | Regola |
|---|---|---|
| Direzione di un prezzo | rosa/smeraldo esistenti (`TESTO_SU`, `TESTO_GIU`, `coloreDirezione`) | invariata |
| Fondo tenue delle celle di rendimento | 3 intensità per verso (`bg-emerald-500/10,/20,/30`, idem rosa) | testo sempre sopra AA, calcolato |
| Scala divergente neutra (correlazioni, percentili) | da sky (−1) a grigio (0) ad ambra (+1), **5 classi letterali** | non è una direzione; contrasto calcolato sui token |
| Palette categoriale (confronto) | 6 colori distinti dai due di direzione | con il validatore della skill dataviz |

⚠️ Classi **letterali** in mappe `Record<…, string>`: il purger di Tailwind non
vede quelle composte a runtime (regola del progetto).

### 5.5 Studio a due colonne

È il disegno 5.1-5.3 dell'analisi del 22/11, confermato; si aggiungono il
grafico del percorso (FA-194) come vista principale di «dopo un movimento» e
«evento», il forest plot e il calendario (FA-195) per la stagionalità, e «I
casi» (FA-193) sotto ogni risultato.

---

## 6. Ordine consigliato

| Ondata | Schede | Giorni | Perché in quest'ordine |
|---|---|---|---|
| **A — correggere** | FA-183, FA-192, l'archivio dell'ampiezza di FA-188 | ~1,5 | difetti a schermo oggi, nessun rischio, sbloccano il resto (formati, layout); l'archivio subito perché la storia parte solo da lì |
| **B — il primo valore** | FA-184, FA-185, FA-193, FA-194 | ~6 | le due pagine diventano utili; i calcoli condivisi (`app/stats/rendimenti`, `calendario`, `drawdown`) nascono qui |
| **C — la parte distintiva** | FA-186, FA-187, FA-195, FA-199 | ~6 | composizione degli indici e confronto; lo Studio a due colonne con la ricerca |
| **D — contesto e domande sicure** | FA-188, FA-189, FA-190, FA-205, FA-191, FA-196, FA-197, FA-198 | ~8 | domande nuove che non moltiplicano i tentativi; FA-205 prima di FA-191 |
| **E — prima il presidio** | FA-200 | ~2 | il contatore delle varianti, prima delle domande aperte |
| **F — domande aperte** | FA-201, FA-202, FA-203, FA-204 | ~9 | solo dopo FA-200 |

**Raccomandazione:** partire da A (mezza giornata a testa, chiudibili oggi
stesso) e poi da B. FA-186 (composizione) è la scheda col miglior rapporto
fra valore e sforzo dopo B: tutti i dati esistono già e nessun sito generico
lega un indice ai titoli, ai segnali e ai punteggi di chi lo guarda.

### 6.1 Cosa vale per ogni scheda (lista di controllo)

- `app/core/rotte.py` e `lib/rotteUso.ts` se nasce una rotta (nessuna,
  in questo piano: tutto sta in `/markets`, `/markets/:simbolo`, `/studio`).
- Tipi: `app.scripts.genera_tipi_frontend` dopo ogni modello Pydantic nuovo.
- Gate: CLS (altezze riservate per ogni sezione caricata in ritardo), mobile
  375 (nessun trabocco in `<main>`), axe chiaro e scuro (linee di base da
  generare in CI se cambiano).
- Codice mai eseguito: ogni job o thread nuovo ha il suo test che lo esegue.
- Server MCP: se uno strumento nuovo serve anche alle domande in chat
  (panoramica, statistiche, primo passaggio), si aggiunge a `mcp/` in sola
  lettura.
- Verifica in produzione: immagine del pod, `GIT_SHA` nel container, una
  stringa nuova nel bundle, e un numero controllato a mano.
