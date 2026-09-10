# Piano di implementazione — dall'audit del 10 settembre 2026

Fonte: [frontend-audit-2026-09-10.md](frontend-audit-2026-09-10.md)
Backlog: [PROJECT-BACKLOG.md](PROJECT-BACKLOG.md), venti voci aperte
Branch: `cloud`

---

## Come è ordinato, e perché

L'ordine non segue la gravità apparente. Segue cinque principi, e ognuno viene
da un errore che questo progetto ha già pagato.

**1. Per i difetti di unità, il test viene prima della correzione.** FA-030 è la
dimostrazione: il blocco 52W non ha una sola asserzione, e il difetto è
sopravvissuto a un rename del vocabolario timeframe restando invisibile da
`2faee27` in poi. Una correzione senza test è una correzione che torna.

**2. Le invarianti prima delle istanze.** Tre controlli valgono per tutta
l'applicazione, costano poche righe e avrebbero intercettato tre difetti su
quattro. Vanno scritti una volta, all'inizio, non dedotti quattro volte.

**3. Quando il contratto è giusto, si corregge il chiamante.** `AllocationBars`
documenta la sua prop come *«variazione del peso in portafoglio, in punti
percentuali»* e la formatta di conseguenza: è corretta. Sbaglia
`InstitutionalHoldersCard`, che le passa una variazione di quote. «Sistemare
AllocationBars» sarebbe l'istruzione sbagliata.

**4. Un commit chiude un difetto verificabile.** Niente tranche in un colpo
solo: ogni voce deve poter fallire da sola in CI e poter essere verificata da
sola a schermo. Il CD rilascia a ogni push, quindi il costo di commit separati
è tempo di attesa, non rischio.

**5. Le decisioni non si mescolano al lavoro.** Una sola voce richiede una
scelta che cambia i numeri a schermo, ed è isolata in Tranche 0 perché non
blocchi il resto.

**Divisione del lavoro.** Io faccio progetto, implementazione, test e CI/CD.
La verifica su browser e dispositivo reale resta tua: jsdom non calcola gli
stili, quindi contrasto, focus visibile e target touch non sono misurabili dai
test. Sotto ogni voce c'è il controllo che ti chiedo.

---

## Tranche 0 — la decisione, prima di tutto

### D-1 · Il market cap: convertire o etichettare (FA-026)

**Non è lavoro, è una scelta**, e cambia numeri che sei abituato a leggere.

Oggi la colonna «Mkt cap» stampa `$` su un valore che è nella valuta di
quotazione. HSBC legge `$2.86T` accanto a un prezzo `HK$165.60`. **E la colonna
si ordina**, quindi non è un'etichetta sbagliata, è una classifica sbagliata.

| Opzione | Effetto | Costo |
|---|---|---|
| A. Convertire in USD | l'ordinamento torna sensato; HSBC passa da `$2.86T` a circa `$367B` | dipendenza FX nello screener |
| B. Etichettare per valuta | onesto; `HK$2.86T` | l'ordinamento diventa privo di senso |
| **C. Ordinare in USD, mostrare in valuta nativa** | entrambe le cose giuste | una colonna in più nel payload |

**Raccomando C.** La colonna esiste per ordinare, quindi l'ordinamento non può
rompersi; e mostrare `HK$2.86T` accanto a `HK$165.60` è coerente con la riga.
Il valore convertito serve solo alla chiave di ordinamento e al confronto, e può
comparire come suggerimento al passaggio.

⚠️ `risk.py` ha già fatto questa scelta e ha scelto la conversione, con
`to_usd`: 158 nomi superavano la soglia mega-cap in valuta nativa contro 83 in
dollari, cioè **75 titoli classificati mega-cap senza esserlo**. La funzione
esiste già, non va scritta.

**Dimmi quale preferisci.** Nel frattempo tutto il resto procede: nessun'altra
voce dipende da questa.

---

## Tranche 1 — le unità

Quattro difetti che fanno leggere numeri sbagliati. È la tranche con il rapporto
danno/costo più alto e va per prima.

### 1.0 · Le tre invarianti condivise

Prima delle quattro correzioni, tre controlli che valgono ovunque. Sono la
generalizzazione dei difetti trovati, non un'astrazione speculativa: ognuno
nasce da un caso reale visto a schermo.

| Invariante | Da chi nasce | Dove vive |
|---|---|---|
| Una percentuale di un intero non varia di più di 100 punti | +7663.7PP | test su `AllocationBars` |
| Due riquadri con etichette diverse non stampano lo stesso numero | `52W high` = `Range high` | test su `market_detail_service` |
| Un suffisso compatto consuma la scala dichiarata | `159.1K` su migliaia | test sul formatter macro |

**Fatto quando** i tre test esistono e sono ROSSI sul codice attuale. È la
condizione di ingresso alle quattro voci sotto: se un test non diventa rosso,
non sta misurando il difetto.

---

### 1.1 · FA-030 · La finestra 52 settimane

**Il difetto.** `market_detail_service.py:198` sceglie il ramo con
`range_key in ("1m", "3m", "6m")`, il vocabolario precedente a `2faee27`. Il
commento sopra dichiara *«52w window always — independent of `range_key`»* e il
codice fa l'opposto. Il commento del ramo `else` — *«1y / 5y / all — the
in-range high/low IS already ≥ 52w»* — era **vero** nel vecchio vocabolario e
oggi è falso in entrambe le direzioni:

| Timeframe | Finestra reale | Errore |
|---|---|---|
| 5m, 30m | 60 giorni | sottostima |
| 1h | 730 giorni | sovrastima |
| **1d** (default) | intera storia | sovrastima grave |
| 1w | intera storia | sovrastima grave |
| 1m | 1 anno | corretto per caso |

**Cosa cambia.**

1. Togliere la condizione sul `range_key`. La finestra 52W si deriva dalle barre
   **già scaricate** quando coprono almeno un anno, e solo quando non lo fanno
   si paga la seconda richiesta a yfinance. Oggi il ramo `1m` fa sempre una
   chiamata in più; così ne fa una solo su 5m/30m/1h.
2. Dichiarare la base nell'etichetta. Entrambi i rami usano solo le chiusure e
   `KpiCell` non ha slot per un tooltip: o si aggiunge lo slot, o l'etichetta
   diventa «52W high (chiusure)». La scheda titolo lo dichiara già —
   `MicroDataCard`: *«basato sulle chiusure giornaliere»* — quindi la
   convenzione esiste e va solo resa visibile qui.

**Il test.** Sei casi, uno per timeframe, con una serie sintetica in cui il
minimo assoluto sta **fuori** dalla finestra annuale. Su `1d` il test deve
fallire oggi.

**Verifica tua.** Apri `/markets/^GSPC` sul default: «52W low» e «Range low»
devono mostrare numeri **diversi**. Poi prova ogni timeframe: nessuno deve dare
4.40.

---

### 1.2 · FA-032 · Variazione di quote contro variazione di peso

**Il difetto.** `InstitutionalHoldersCard.tsx:178` passa `h.qoq_change_pct` —
la variazione percentuale delle **quote** — alla prop `deltaPct` di
`AllocationBars`, documentata come *«change in the fund's portfolio weight, in
percentage POINTS»* e con il tooltip *«Variazione del peso in portafoglio»*.

**Il componente è corretto. Sbaglia il chiamante.**

**Cosa cambia.**

1. Nello schema, due campi distinti: `shares_change_pct` e
   `portfolio_weight_delta_pp`. Sono due misure e non possono condividere una
   colonna.
2. Il backend calcola il secondo dai pesi dei due filing consecutivi. Se il peso
   precedente non è disponibile, il campo è `null` e la cella mostra `—`:
   assenza, non zero.
3. La card mostra quella disponibile, con l'unità giusta accanto.

**Il test.** Quote da 100 a 120 danno `+20%` di quote e `null` o il vero delta
di peso, mai `+20PP`. Più l'invariante: `|Δpp| ≤ 100`.

**Verifica tua.** Sul dettaglio di DG, pannello «Posizioni per istituzione»:
nessun valore in PP sopra 100.

---

### 1.3 · FA-031 · Il macro

Tre difetti sullo stesso schermo, uno per volta.

**a) La scala.** La scheda rende `Total Non-Farm Payrolls (thousands)` e il
formatter stampa `159.1K` su un numero già in migliaia. **L'unità è nel payload
e il formatter la ignora.** Il formatter deve accettare la scala della serie e
rifiutarsi di compattare senza. Reso corretto: `159,1 mln` oppure
`159.100 mila`, mai un `K` sopra un `(thousands)`.

**b) Il grafico.** «Storico release» disegna il **livello** come barre da zero:
sessanta barre identiche. Per NFP la domanda è la **variazione** mensile, ~150K
contro un livello di 159.100K, cioè un millesimo dell'altezza. Serve una scelta
esplicita fra livello e variazione, con linea per i livelli e barre per le
variazioni.

⚠️ Il valore mensile di NFP che si legge sui giornali è la variazione, non il
livello. Ma la serie FRED conserva l'unità originale: la trasformazione è
un'operazione **nostra** e va dichiarata, non sottintesa.

**c) Le date.** `release_date` è costruita da `MacroObservation.date`, cioè il
periodo osservato: da qui «1 ago 26» per un dato pubblicato a settembre.
Periodo osservato, data di pubblicazione e data di acquisizione sono tre campi.
Se la pubblicazione non è nota, **non va ricostruita**: si mostra il periodo e
si dice che la pubblicazione non è disponibile.

**Il test.** Una serie con unità `thousands` non produce mai un output con
suffisso `K`. Una osservazione senza data di pubblicazione nota non ne inventa
una.

**Verifica tua.** `/macro/3`: il numero grande deve essere leggibile come
«centocinquantanove milioni», e il grafico deve mostrare qualcosa che varia.

---

### 1.4 · FA-033 · Le quattro basi prezzo

**Il difetto.** Lo stesso target analisti rende `+11.5%` e `+4.3%` sulla pagina
di DG. Le basi sono quattro e nessuna è dichiarata:

| Scheda | Base | Età |
|---|---|---|
| Header | prezzo live | secondi |
| Pannello analisti | `pt.current` di yfinance | quanto la cache fondamentali |
| Scheda punteggio | ultima `OhlcvDaily.close` | fine giornata |
| Fattore valutazione | una quarta ancora | — |

**Cosa cambia.** Due strade, e raccomando la seconda.

- *Una base sola.* Elegante e fragile: obbliga ogni consumatore a dipendere dal
  prezzo live, che ha un breaker e può essere `STALE`.
- **Ogni confronto dichiara la propria base.** Un confronto che non può
  dichiararla non si mostra. È coerente con la regola che questo repo applica ai
  tassi: un numero senza il suo denominatore non si pubblica.

In pratica: il tipo che porta un `upside` porta anche `base_price` e
`base_as_of`, e la scheda li rende come contesto sotto la percentuale.

**Il test.** Due confronti con basi diverse non possono comparire senza
dichiararle. Un `upside` senza `base_price` non si serializza.

**Verifica tua.** Sulla pagina di DG le percentuali verso il target devono o
coincidere, o dire su quale prezzo sono calcolate.

---

## Tranche 2 — leggibilità

Tutta frontend, verificabile a occhio, nessuna dipendenza dalla Tranche 1.

### 2.1 · FA-027 · Il dettaglio titolo a 1440px

**Il difetto.** I valori sono disegnati **sopra** le etichette:
`Profittabilità Sostenib`**`45`**`lità`. Quattro schede in basso perdono il
titolo fino a `F` e `ANAL…`.

**La causa è aritmetica.** `StockDetailPage.tsx:281` divide in `[2fr_1fr]` e
spezza il `1fr` destro in due: restano ~133px di contenuto utile per scheda.
La riga `:344` fa lo stesso in basso con `[1.5fr_1fr_1fr_1fr]` più
`lg:h-[520px]`, un'altezza **fissa** che impone scorrimento interno comunque.

**Cosa cambia.** Non si progetta niente di nuovo: **il layout corretto esiste
già su mobile**, dove la stessa scheda rende i cinque pilastri come barre
etichettate col valore. Basta impilare le due schede a `lg` invece di
affiancarle — da 181px a 375px — e togliere l'altezza fissa alla riga in basso.

**Il test.** Un test che monta la scheda a larghezza ridotta e asserisce che
l'etichetta del pilastro e il suo valore siano due nodi distinti e non
sovrapposti. ⚠️ jsdom non calcola gli stili, quindi la sovrapposizione **non**
è verificabile da test: il test può solo pinnare la struttura, la
sovrapposizione la vedi tu.

**Verifica tua.** `/stocks/DG` a 1440: nessun numero sopra una parola, nessun
titolo di scheda ridotto a una lettera.

### 2.2 · FA-036 · Le pastiglie del calendario

Ogni pastiglia mostra logo e una lettera perché la cella larga ~140px ne ospita
**due affiancate**. Una per riga ne avrebbe ~130 e il ticker entrerebbe. La
cella ha altezza abbondante e larghezza scarsa: il contenuto è disposto nel
verso sbagliato.

**Verifica tua.** `/calendar?view=month`: si legge il ticker senza aprire il
giorno.

### 2.3 · FA-038 · Il ritorno

Tre pagine di dettaglio su cinque hanno già un ritorno. Mancano in
`StockDetailPage` e `MarketDetailPage`. E l'occhiello sopra il titolo esiste già
su Calendario e Impostazioni: **il modello è applicato a due pagine su
diciassette**. Estenderlo alle cinque di dettaglio costa meno che progettarne
uno nuovo.

### 2.4 · Igiene

Nella stessa tranche, perché sono righe di CSS o di condizione:

- Colonne vuote per il 100% delle righe (`LIVELLO D'INNESCO`, `DISTANZA` su *In
  formazione*) non si renderizzano. ⚠️ Ma un `—` sulla distanza può significare
  **trigger non basato sul prezzo**: in quel caso la cella dice «condizione di
  volatilità», non resta vuota.
- Righe tagliate a metà altezza: il contenitore ad altezza fissa deve allinearsi
  al passo delle righe.
- Su mobile l'identità non si comprime a zero mentre la misura resta. Nessuna
  colonna del nome comprimibile.

---

## Tranche 3 — i dati che crescono

### 3.1 · FA-034 · Le holdings

**Nessun limite a nessuno dei tre strati**: il frontend mappa l'intero array,
`get_detail` non ha `limit`/`offset` — a differenza di `get_ticker_holders`
subito sotto, che ha `limit: int = 25` — e la query non ha `.limit()`. Uno
screenshot interno supera i **302.900 pixel**.

**Cosa cambia.** Paginazione **lato server**, ricerca per ticker o nome, filtro
sulle variazioni. ⚠️ Virtualizzare il DOM ridurrebbe il rendering e non il
payload né il lavoro del backend: non è la stessa cosa e non basta.

**E i due conteggi vanno etichettati.** 4.295 e 5.252 sono entrambi corretti:
il primo è `total_positions`, scritto all'ingest come le posizioni riportate nel
filing; il secondo conta anche le **957 righe sintetiche** che
`compute_qoq_deltas` inserisce per le uscite senza aggiornare il primo. Manca
solo che ognuno dica cosa conta.

### 3.2 · FA-035 · La classificazione degli strumenti

Il filtro che esclude gli ETF dai settori **è capillare e corretto**. È il flag
a essere congelato: `instrument_type` è scritto una sola volta da una migration
con lista hard-coded di 24 ticker raccolti come *«exactly the NYSE Arca
listings»* il 2026-07-04, e **nessun percorso di ingestione lo valorizza**.
975 equity / 24 etf, mai cresciuti.

**Cosa cambia.** `seed_service` e `catalog_refresh_service` lo valorizzano al
confine, come già fanno con `canonical_country` e — da oggi —
`major_unit_currency`. Più una migration che riclassifica il catalogo esistente.

⚠️ Il criterio non può essere la lista dei ticker né l'exchange: QQQ è sfuggito
proprio perché la lista raccoglieva NYSE Arca ed è quotato NASDAQ. Serve un
segnale della fonte, e se la fonte non lo dà, il campo resta `null` e il filtro
lo tratta come «non classificato», non come `equity`.

---

## Tranche 4 — le connessioni

Le prime due partono da campi già nel payload: sono le più economiche
dell'intero piano.

### 4.1 · FA-029 · Posizione, segnale, geometria

`Position.alert_id` esiste, arriva al frontend e **non viene usato**, mentre
l'intestazione della pagina promette *«trade tracciati dal piano operativo dei
segnali»*. Costa un link. Simmetricamente `converted_alert_id` collega setup e
segnale: il percorso **setup → segnale → posizione** è già nei dati e non è mai
reso.

Insieme, la geometria: entry, stop, target e prezzo sono quattro colonne dove
una barra risponde a colpo d'occhio a **quanto sono vicino a uscire, e da che
parte**. ⚠️ «Rischio allo stop» è una misura geometrica con limiti di
esecuzione, non una perdita massima garantita, e va detto.

### 4.2 · Il Divario nello screener

Esplora calcola Qualità − Tecnico per gli undici settori. Lo screener ha
`composite` e `tech_composite` sulla **stessa riga** e non ne fa la differenza.

⚠️ Va introdotto come **descrittore, non come segnale**: lo studio score-IC dice
che il composito Qualità non prevede i rendimenti, quindi un Divario alto è una
discrepanza da guardare, non un'occasione. Ed è una differenza fra indicatori su
scale distinte, non uno sconto economico.

### 4.3 · Il calendario dentro i setup

*In formazione* dice `ATTESA 13g`; il calendario sa che quel ticker pubblica fra
5. Un'icona sulla riga del setup quando esiste un evento dentro la finestra di
attesa risponde a: **il setup si risolve prima o dopo la trimestrale?**

### 4.4 · La sorgente degradata dove il dato si consuma

Salute sa che Marketaux è fuori servizio; la scheda News mostra solo meno
articoli. Una riga sulla scheda trasforma un'assenza inspiegata in una
spiegata. ⚠️ Attribuire l'impatto **solo dove è tracciabile**: fonte → tipo di
dato → scheda, mai un impatto ticker-specifico che il contratto non supporta.

---

## Tranche 5 — la struttura

Ultima di proposito: è riordino, e riordinare sopra difetti non corretti sposta
i difetti senza chiuderli.

### 5.1 · FA-037 · Le due diagnostiche

`/settings` monta otto pannelli diagnostici e zero preferenze; il file lo dice
di sé. Le preferenze vere esistono sparse, e il toggle del tema sta **accanto**
al link Impostazioni, non dentro.

Una destinazione `Diagnostica` con schede *Piattaforma* e *Motore*: la
separazione ha un senso preciso, perché **disponibilità del sistema** e
**capacità predittiva del motore** sono due domande diverse. L'ingranaggio resta
libero per le preferenze vere.

### 5.2 · Il raggruppamento della navigazione

Dashboard · Analisi (Mercati e settori, Screener, Calendario, Fondi) ·
Monitoraggio (In formazione, Segnali, Posizioni) · Strumenti (Stato, Metodo).
Sono **etichette di navigazione, non nuove pagine vuote**, e le pagine di
dettaglio restano oggetti trasversali.

⚠️ Da non fare nella stessa tranche: rinominare le route. `/sectors` che si
chiama «Esplora» è un difetto di leggibilità degli indirizzi, ma cambiarle rompe
i segnalibri e non risolve niente che si veda.

---

## Spike e trasversali

Non sono tranche: sono attività brevi da infilare fra una e l'altra.

| # | Cosa | Perché non è una tranche |
|---|---|---|
| S-1 | **FA-028** — riprodurre la barra indici vuota su desktop | È «Osservato». Due viewport su tre funzionano, quindi non è un problema di dati. Prima si riproduce, poi si decide se è lavoro. |
| S-2 | **FA-039** — propagare l'`AbortSignal` | Il client lo supporta; su 58 `queryFn` una lo inoltra e su 54 wrapper uno lo espone. Meccanico, va fatto quando si tocca comunque un modulo `api/`. |
| S-3 | **FA-008** — 47 finding ESLint | Non gated per scelta: la barra scritta nel repo è che una violazione rompa qualcosa che si sente. Da fare quando si tocca il file, non come campagna. |
| S-4 | **FA-015** — guardrail Loki | Bloccata da fuori: il kubelet local-path non espone `volume_stats`. Serve una sorgente diversa, non lavoro. |

**FA-006 e FA-007 non sono in questo piano.** Sono misure che maturano:
percentili di latenza e Web Vitals hanno bisogno di giorni di traffico reale.
Spingerle significa concludere su campioni che non hanno ancora senso.

**FA-011 e FA-013 aspettano te.** Il codice è in produzione e manca il collaudo
su un dispositivo vero: focus trap, ESC, scroll lock, restore del drawer, back e
forward del browser.

---

## Criteri di chiusura

Una voce è **DONE / PROD** solo quando tutte e cinque sono vere:

1. Esiste un test che diventa **rosso** togliendo la correzione. Verificato, non
   supposto: si toglie la correzione su una copia, si esegue, si ripristina.
2. La suite passa, il lint gated passa, il build passa.
3. CI verde su **tutti e sette** i job, inclusi `image` e `gitops`. Sei su sette
   verdi con `image` skipped significa che niente è stato rilasciato.
4. Il pod gira l'immagine del commit. Verde non è rilasciato: si confronta il
   tag in esecuzione con il commit.
5. La verifica a schermo indicata sotto la voce è stata fatta da te.

⚠️ **Nessun `npm install` su Windows senza la metà Linux.** È la trappola che ha
morso cinque volte: qualunque scrittura npm su Windows può togliere il ramo
Linux dal lockfile, e il difetto è invisibile in locale. Dopo ogni scrittura, il
controllo delle rimozioni: zero chiavi `node_modules/*` rimosse.

---

## Ordine consigliato in una riga

**D-1** (dimmi quale opzione) → **1.0** invarianti → **1.1** 52W → **1.2** pp →
**1.3** macro → **1.4** basi prezzo → **S-1** spike barra indici → **2.1**
dettaglio titolo → **2.2** calendario → **2.3** ritorno → **2.4** igiene →
**3.1** holdings → **3.2** instrument_type → **4.1** posizione-segnale →
**4.2** Divario → **4.3** calendario-setup → **4.4** sorgente degradata →
**5.1** diagnostica → **5.2** navigazione.

Se vuoi partire subito e saltare la decisione, il primo blocco eseguibile è
**1.0 + 1.1**: le tre invarianti e la finestra 52 settimane.
