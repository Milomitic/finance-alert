# Finance Alert — revisione UI/UX su acquisizione completa

Data: 2026-09-10
Fonte: 426 screenshot, 17 route × 3 viewport (desktop 1440×1000, tablet 768×1024,
mobile 390×844), acquisizione autenticata del 10 settembre 2026.

Questa revisione parte dalle immagini e risale al codice per ogni difetto, così
ogni voce nomina la causa e non solo il sintomo. Dove una cosa funziona già, è
detto: metà del valore di un audit è non far riscrivere ciò che è a posto.

---

## 1. Il risultato in una riga

**Il desktop è il viewport peggiore dell'app.** Non è un'impressione: è
misurabile su tre assi indipendenti, e su due pagine su tre il layout mobile
mostra più informazione leggibile di quello desktop.

| Misura | Desktop | Tablet | Mobile |
|---|---:|---:|---:|
| Contenitori con scorrimento interno, dashboard | **35** | 9 | 9 |
| Contenitori con scorrimento interno, dettaglio titolo | **29** | 3 | 5 |
| Barra indici in alto | `n/d` ×6 | quotazioni FUT | quotazioni FUT |

Il numero di contenitori interni è la metrica che conta perché descrive una
scelta di progetto: quando lo spazio manca, l'app **rimpicciolisce il
contenitore** invece di far scorrere la pagina. Su desktop, dove lo spazio
verticale è abbondante, questa scelta produce 35 riquadri che scorrono dentro
una pagina che a sua volta scorre.

---

## 2. Quello che funziona, e va preso a modello

### Esplora è già la pagina che il resto dell'app dovrebbe imitare

`/sectors` fa esattamente ciò che questa revisione avrebbe altrimenti proposto
come novità:

- **tre ordinamenti dello stesso universo affiancati** — Analisti, Qualità ×
  Tecnico, Segnali — così la domanda "dove guardare" ha tre risposte
  confrontabili invece di una classifica sola che pretende di essere la verità;
- **una didascalia che dichiara i limiti**: *"Non sono previsioni di rendimento:
  gli studi condotti sul motore non mostrano capacità predittiva sui ritorni
  futuri"*;
- **una nota su ciò che manca**: *"47 stock senza settore assegnato: contano nel
  totale ma non compaiono qui"*;
- **una correlazione vera resa come grafico**: lo scatter Qualità × Tecnico con
  la bolla dimensionata sul numero di titoli e colorata sul saldo segnali;
- **una colonna derivata**, `Divario` = Qualità − Tecnico, che è l'unica
  metrica in tutta l'app a mettere due lenti in relazione invece di affiancarle.

Le sezioni 4 e 5 di questo documento sono, in gran parte, "porta il metodo di
Esplora sulle altre pagine".

### Le altre cose che non vanno toccate

- **Salute** (`/health`): banner di stato, 19 sorgenti con quote e ultimo
  errore testuale (`X HTTP 402 — quota/rate-limit; breaker aperto`), semaforo
  rosso/verde usato per "rotto" e non per direzione. Corretto.
- **Posizioni**: valute native (`830,80 €`), totali dichiarati come convertiti
  (*"Somme convertite in USD ai cambi correnti"*). È la pagina che FA-009 ha
  sistemato e si vede.
- **In formazione**: quattro tessere su otto mostrano un trattino con la
  motivazione accanto — *"troppo pochi per un tasso (servono 20)"*, *"serve
  almeno un esito maturo"*. È scomodo da guardare ed è la cosa giusta.
- **Segnali**: il marcatore di calibrazione per detector è già sulla cella
  Probabilità (`AlertsTable.calibrationTag`). Non va reinventato.

---

## 3. Struttura dell'app

### 3.1 Due pagine di diagnostica, una delle quali si chiama "Impostazioni"

| Route | Etichetta nel menu | Contenuto reale |
|---|---|---|
| `/health` | Salute | sorgenti dati, scheduler, scan, log |
| `/settings` | Impostazioni | efficacia dei segnali, calibrazione, refresh catalogo |

`/settings` non contiene nessuna impostazione. Il suo sottotitolo lo dice:
*"Statistiche di efficacia dei segnali e stato dei refresh catalogo per
indice"*. È una seconda pagina di diagnostica, staccata dalla prima, raggiunta
da un ingranaggio in fondo alla barra laterale — cioè nel posto dove ogni
applicazione mette le preferenze.

Chi cerca "perché il motore dice questo" deve sapere che la risposta sta sotto
un ingranaggio; chi cerca una preferenza la cerca lì e non la trova.

**Proposta.** Una sola destinazione `Diagnostica` con due schede, *Piattaforma*
e *Motore*. Libera una voce di menu e mette le due metà della stessa domanda
nello stesso posto. L'ingranaggio resta libero per le preferenze vere, che oggi
non esistono e che l'audit precedente chiede in tre voci separate (canali di
notifica UX-064, quiet hours UX-066, import/export UX-068).

### 3.2 L'URL e l'etichetta non si parlano

| Route | Etichetta |
|---|---|
| `/sectors` | Esplora |
| `/stocks` | Screener |
| `/institutionals` | Superinvestor |
| `/settings` | Impostazioni |

Quattro destinazioni su dieci hanno un indirizzo che non nomina la pagina. I
link sono condivisibili — `useSearchParams` è usato su sei pagine, il deep link
funziona — ma non sono **leggibili**: ricevere `/sectors` e trovarsi su
"Esplora" costringe ad aprirlo per sapere cos'è.

Non è urgente e cambiare le route rompe i segnalibri. Va però messo agli atti,
perché ogni nuova voce peggiora la mappa se non se ne tiene conto.

### 3.3 Sei pagine di dettaglio senza una via di ritorno

`/stocks/:ticker`, `/sectors/:name`, `/markets/:symbol`, `/macro/:seriesId`,
`/institutionals/:slug` più la 404: nessuna compare nel menu, nessuna ha un
breadcrumb, e il menu laterale evidenzia la sezione padre ma non dice a che
punto si è dentro di essa.

Due pagine hanno un occhiello sopra il titolo che assolve la funzione —
Calendario mostra `PIANIFICAZIONE · EVENTI DI MERCATO`, Impostazioni mostra
`AMMINISTRAZIONE · DIAGNOSTICA` — e le altre quindici no. **Il modello esiste
già ed è applicato a due pagine su diciassette.** Estenderlo alle sei di
dettaglio è più economico che progettare un breadcrumb nuovo, ed è
esattamente UX-001, che l'audit di ieri segna ancora come mancante.

---

## 4. Difetti con una causa nominata

### 4.1 Il dettaglio titolo perde titoli e valori a 1440px — misurato

È la pagina più importante dell'app ed è quella messa peggio. Su desktop:

- `Profittabilità Sostenib**45**lità` — **il valore è disegnato sopra la
  parola**, non troncato accanto;
- `Crescita Valore**71**` — stesso difetto;
- schede intitolate `F`, `VALUATION…`, `ANAL…`, e una il cui titolo visibile è
  `10) yfinance · cache 1h`, cioè un frammento;
- `CONSERVA…`, `Segna… recent… confid… 98%`, `aggiorna… 18m fa`.

**La causa è aritmetica, non estetica.** A 1440px la colonna contenuto è
1136px (1440 − 256 di barra laterale − 48 di padding).

`StockDetailPage.tsx:281` divide la riga in `[2fr_1fr]`, e il `1fr` di destra
viene poi spezzato in due da `sm:grid-cols-2`:

```
1136 − 12 (gap)  = 1124  →  2fr = 749px   |   1fr = 375px
375 − 12 (gap)   = 363   →  due schede da ~181px
181 − 48 (padding della Card)              →  ~133px di contenuto utile
```

Centotrentatré pixel non contengono "Sostenibilità" più un numero allineato a
destra. Da lì la sovrapposizione.

`StockDetailPage.tsx:344` fa lo stesso alla riga in basso con
`[1.5fr_1fr_1fr_1fr]`: tre schede da **244px**, ~196px di contenuto, che è la
ragione di `F` e `ANAL…`. La stessa riga porta `lg:h-[520px]`, un'altezza
**fissa**, che impone scorrimento interno a tutte e quattro
indipendentemente da quanto contengano.

**Che la soluzione non sia da inventare lo dimostra il mobile.** A 390px la
stessa scheda Qualità rende `CONSERVATIVE` per intero e i cinque pilastri come
barre etichettate con il valore — Profittabilità 43, Sostenibilità 67, Crescita
71, Valore 70, Sentiment 61 — con Profittabilità in ambra perché è la più
bassa. È una lettura migliore di quella desktop sotto ogni aspetto.

Il rimedio è dare alla colonna destra la larghezza che il mobile ha già:
impilare le due schede invece di affiancarle (togliere `sm:grid-cols-2` alle
larghezze `lg`), che le porta da 181px a 375px. E togliere l'altezza fissa
alla riga in basso.

### 4.2 Il market cap mescola valute su una colonna ORDINABILE

Già a backlog come FA-026, ma gli screenshot lo rendono più grave di come lo
avevo descritto: **le due valute stanno sulla stessa riga**.

| Titolo | Prezzo | Mkt cap mostrato |
|---|---|---|
| 0001.HK CK Hutchison | HK$70.20 | **$267.5B** |
| 0005.HK HSBC | HK$165.60 | **$2.86T** |

Il prezzo dichiara i dollari di Hong Kong, il market cap accanto dichiara i
dollari americani, e il numero è lo stesso dato nella stessa valuta. Con quella
cifra HSBC sarebbe la società più capitalizzata al mondo — e la colonna si
ordina, quindi non è un'etichetta sbagliata, è una **classifica sbagliata**.

`risk.py` ha già pagato questo difetto: il suo test registra 158 nomi sopra la
soglia mega-cap in valuta nativa contro 83 in dollari, cioè 75 titoli
classificati come mega-cap stabili senza esserlo.

Resta una decisione, non una rietichettatura: convertire tiene l'ordinamento
sensato e cambia i numeri a schermo; etichettare ogni cap con la sua valuta è
onesto e rende l'ordinamento privo di senso. La prima è quasi certamente
quella giusta perché la colonna esiste **per** ordinare.

### 4.3 La barra indici è morta su desktop e viva sugli altri due viewport

Desktop: `S&P 500 n/d n/d`, `Nasdaq Composite n/d n/d`, `Dow Jones n/d n/d`,
`Nikkei 225 n/d n/d`, `Euro Stoxx 50 n/d n/d`, `FTSE MIB n/d n/d`. Sei indici,
dodici `n/d`, nella striscia più in alto della pagina più visitata.

Tablet e mobile, **stessa sessione di acquisizione**: `FUT S&P 500 7649 ↓
-0.44%`, `FUT Nasdaq Composite 29.450 ↓ -0.39%`. Il componente sa ricadere sui
futures a mercati chiusi, e su due viewport su tre lo fa.

Due su tre funzionanti escludono un'indisponibilità della sorgente e indicano
qualcosa di specifico al percorso desktop. Va riprodotto prima di ipotizzare la
causa; quello che si può dire dagli screenshot è che **non è un problema di
dati**.

Vale anche la pena notare che, tre righe più sotto, la striscia di ampiezza
dice `USA 54% -0.93% · Europa 58% -1.63% · Asia 54% -0.11%`. Due componenti
parlano degli stessi mercati nello stesso schermo, uno vuoto e uno pieno.

### 4.4 Il calendario non lascia leggere chi pubblica

Le pastiglie degli eventi mostrano il logo e una lettera: `D ▲`, `P. ▲`, `C ▲`,
`N ▲`, `A…`, `O…`, `S…`, `K…`. Su un calendario earnings il ticker è
l'informazione, e non c'è.

La causa è la disposizione: ogni cella è larga ~140px e ne ospita **due
affiancate**, quindi ciascuna ha ~65px. Una per riga ne avrebbe ~130 e il
ticker entrerebbe. La cella ha altezza abbondante e larghezza scarsa, e il
contenuto è disposto nel verso sbagliato.

### 4.5 Colonne vuote per il 100% delle righe

Su *In formazione*, `LIVELLO D'INNESCO` e `DISTANZA` mostrano un trattino su
ogni riga visibile. Due colonne che occupano larghezza per non dire nulla, su
una tabella che ha già dovuto tagliare `ATTESA` a destra.

Una colonna vuota per tutte le righe del risultato corrente non va renderizzata.
La regola generale, coerente con quella che questo repo applica ai tassi senza
denominatore: **lo spazio va a ciò che porta un'informazione**.

### 4.6 Righe tagliate a metà altezza

Nella scheda SEGNALI della dashboard desktop la riga `IFX.DE` è tagliata
orizzontalmente a metà. È il segno di un contenitore ad altezza fissa che non
si allinea al passo delle righe: una riga mozzata dice al lettore che c'è
dell'altro, ma nel modo peggiore, perché sembra un errore di disegno.

---

## 5. Correlazioni che i dati contengono e lo schermo non mostra

Questa è la parte richiesta esplicitamente: informazioni nuove ottenute
mettendo in relazione oggetti che oggi vivono su pagine diverse. Sono ordinate
per rapporto fra valore e costo.

### 5.1 Una posizione non sa da quale segnale è nata — e il dato c'è

`Position.alert_id` esiste nel tipo, arriva al frontend, e la pagina Posizioni
**non lo usa**. Nel frattempo l'intestazione della pagina dichiara *"Trade
tracciati dal piano operativo dei segnali"*, quindi promette il collegamento e
non lo offre.

Costo: un link. Valore: da una posizione aperta si torna alla regola, alla
catena di conferme e alla Forza che l'hanno prodotta, cioè si può giudicare
**perché** si è in quel trade e non solo come sta andando.

### 5.2 Entry, stop, target e prezzo sono quattro numeri dove servirebbe una geometria

La riga di ARGX.BR dice: entry 830,80 €, stop 625,52 €, target 1036,08 €,
prezzo 865,20 €, P&L +4.14%. Per sapere quanto manca allo stop bisogna fare la
sottrazione a mente, su quattro colonne.

Gli stessi quattro numeri disegnati come una barra — stop a sinistra, target a
destra, entry marcato, prezzo come cursore — rispondono a colpo d'occhio alla
sola domanda che conta su una posizione aperta: **quanto sono vicino a
uscire, e da che parte**. È l'unica parte del playbook che ha un backtest OOS
alle spalle (la geometria stop/target), quindi è anche l'unica che merita di
essere resa graficamente senza pretese predittive.

### 5.3 Il Divario Qualità − Tecnico esiste solo per i settori

Esplora calcola e mostra `Divario` per gli undici settori: Energy +8.4,
Consumer Discretionary −25.6. È la metrica più informativa della pagina perché
è l'unica che **mette in relazione due lenti** invece di affiancarle.

Lo screener ha `composite` e `tech_composite` come colonne separate sulla
stessa riga e non ne fa la differenza. Un titolo con Qualità 81 e Tecnico 40 è
un oggetto diverso da uno con 81 e 80 — società solida che il mercato sta
vendendo contro società solida che il mercato compra — e oggi l'app conosce
entrambi i numeri e non dice mai in cosa differiscono.

⚠️ Va introdotto come **descrittore, non come segnale**: lo studio score-IC dice
che il composito Qualità non prevede i rendimenti, quindi un Divario alto non è
un'occasione, è una discrepanza da guardare. La formulazione conta quanto il
numero.

### 5.4 Il calendario e i setup parlano dello stesso futuro su pagine diverse

*In formazione* dice `ATTESA 13g` su ogni setup. Il calendario sa che quel
ticker pubblica fra 5 giorni. Sono due fatti datati sullo stesso titolo, e
messi vicini rispondono a una domanda che nessuna delle due pagine può porre da
sola: **il setup si risolve prima o dopo la trimestrale?**

Un setup che maturerebbe il giorno dopo gli utili non è lo stesso oggetto di
uno che matura in una settimana tranquilla, perché la trimestrale sovrascrive
la tesi tecnica. Basta un'icona sulla riga del setup quando esiste un evento
dentro la finestra di attesa.

### 5.5 Una sorgente degradata non lo dice dove il dato viene consumato

Salute sa che *"Fonte fallback non operativa: Marketaux — News"*, con
`0 / 100` di quota e `HTTP 402`. La scheda News del dettaglio titolo, che
consuma quella sorgente, mostra semplicemente meno articoli.

Il degrado è visibile solo a chi va a cercarlo su una pagina di diagnostica. Il
posto dove serve è quello dove il buco si manifesta. Una riga sottile sulla
scheda — *"una fonte news non risponde"* — trasforma un'assenza inspiegata in
un'assenza spiegata, che è la stessa distinzione fra `—` e `0` che questo repo
applica ovunque ai numeri.

### 5.6 La dashboard ha due componenti sugli stessi mercati, uno vuoto

Vedi 4.3. Al di là del difetto, la barra indici e la striscia di ampiezza sono
la stessa informazione a due granularità: livello dell'indice e salute interna
dell'indice. Fuse in una striscia sola — indice, variazione, percentuale sopra
EMA200, A/D — occuperebbero una riga invece di due e direbbero, per ogni
mercato, sia dove sta sia quanto è sostenuto.

---

## 6. Priorità

Ordinate per danno arrecato oggi, non per difficoltà.

| # | Intervento | Perché per prima |
|---|---|---|
| 1 | Larghezze del dettaglio titolo (4.1) | La pagina più importante rende valori sopra le etichette. Il rimedio è togliere una griglia, e il layout corretto esiste già su mobile. |
| 2 | Market cap in valuta mista (4.2) | Non è un'etichetta sbagliata: è una classifica sbagliata su una colonna ordinabile. |
| 3 | Barra indici su desktop (4.3) | Dodici `n/d` in cima alla pagina più aperta, con due viewport su tre funzionanti. |
| 4 | Posizione → segnale, e la barra della geometria (5.1, 5.2) | Il dato è già nel payload; la pagina promette il collegamento nel proprio sottotitolo. |
| 5 | Occhiello sulle sei pagine di dettaglio (3.3) | Il modello è già in due pagine. Chiude UX-001 senza progettare nulla. |
| 6 | Pastiglie del calendario a una per riga (4.4) | Una riga di CSS restituisce il ticker su una pagina intera. |
| 7 | Colonna Divario nello screener (5.3) | Due numeri già presenti nella riga, una sottrazione, una descrizione onesta. |
| 8 | Colonne vuote e righe mozzate (4.5, 4.6) | Igiene: lo spazio va a ciò che informa. |
| 9 | Unificare le due diagnostiche (3.1) | Riordino vero, quindi dopo le correzioni. Libera l'ingranaggio per le preferenze. |

I punti 5.4 e 5.5 sono i più interessanti e i più costosi, perché richiedono di
far parlare due sorgenti che oggi non si conoscono. Vanno affrontati quando i
primi otto sono chiusi, non prima.

---

## 7. Che cosa questa revisione NON dice

- **Non propone la watchlist.** È stata rimossa deliberatamente, come il
  sistema letto/non letto, e non torna senza una richiesta esplicita.
- **Non propone di dimensionare niente sulla Forza.** Il playbook ci ha già
  provato: la rampa di rischio è stata rimossa quando il magazzino ha mostrato
  la banda 90-99 realizzare 42,3% contro 52-53%.
- **Non propone un marcatore di calibrazione sui segnali**: esiste già.
- **Non tocca la resa di MarketChart.** Riposa senza margine destro, diversamente
  dal grafico dei titoli, ed è coerente con sé stesso.
- **Non conta i difetti di contrasto o di target touch.** jsdom non calcola gli
  stili e axe non li vede, e gli screenshot non bastano a misurarli: servirebbe
  una passata su browser reale, che resta l'oggetto di FA-011.
