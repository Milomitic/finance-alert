# Studio: analisi completa ed evoluzione (2026-11-22)

Analisi della pagina `/studio` (FA-157): cosa fa oggi, cosa misura male o non
misura, quali capacità nuove i dati dell'app già permettono, e come
ridisegnarla. Misure prese in produzione il 2026-11-22 sull'immagine
`510b5807`.

---

## 1. Lo stato di oggi

Tre modelli fissi su un simbolo (titolo del catalogo o mercato), con lo
stato nell'URL:

| Modello | Domanda | Server |
|---|---|---|
| Dopo un movimento | cosa succede H sedute dopo una variazione ≥ X% in N sedute | `studio_service.dopo_movimento` |
| Stagionalità | rendimento per mese e per giorno della settimana | `studio_service.stagionalita` |
| Attorno a un evento | percorso medio da −6 a +10 sedute attorno a trimestrali o rilasci macro | `studio_service.evento` |

Ogni misura porta occorrenze, finestre indipendenti, intervallo al 95% e caso
base. È la parte solida: le regole di onestà del motore applicate a una
domanda libera.

**Misurato in produzione:**

| Studio | Tempo | Risultato |
|---|---|---|
| AAPL, −10% in 5 sedute, 21 dopo | 79 ms | 22 occorrenze in **9 finestre**; differenza dalla base +0,57%, intervallo della condizione da −3,6% a +9,6% |
| Stagionalità ^GSPC | **3.461 ms** (a freddo) | 99 anni; 4 mesi su 12 con l'intervallo che esclude lo zero |
| NVDA attorno alle trimestrali, 5 sedute | 73 ms | 20 eventi; **media +0,6%, mediana −3,6%** |
| ^GSPC attorno al CPI | 120 ms | **19 rilasci** |
| Simbolo inesistente | 785 ms | 404 «Nessuna storia per XYZQ» |

Ingressi alla pagina: il menu Analisi e un solo link, dalla scheda «Titoli
simili» (modello evento). Strumento MCP `studio` con le stesse tre domande.

---

## 2. Cosa misura male o non misura

In ordine d'impatto. Ognuno è un caso della regola del progetto «un numero non
deve affermare più di quanto misura».

**M1. Confronti multipli senza correzione.** La stagionalità fa 17 confronti
(12 mesi + 5 giorni), e su ^GSPC quattro mesi «escludono lo zero». Col 95% per
confronto ci si aspetta circa un falso positivo per pura combinatoria. Lo
schermo non lo dice e il lettore porta via «aprile è un mese forte». Serve la
correzione per famiglia (Benjamini-Hochberg, già in `conditional_screen_grid`)
e il colore solo per ciò che la supera.

**M2. Solo la media, mai la forma.** NVDA attorno alle trimestrali: media
+0,6%, mediana −3,6%, positivi il 42%. La media dice «sale un po'», la seduta
tipica dice «scende»: due code grandi a destra trascinano la media. Con
venti eventi la distribuzione è l'informazione, e oggi non si vede.

**M3. La differenza dalla base non ha un intervallo suo** (D-84, aperto). È il
numero in grassetto, e due intervalli che si sovrappongono non dicono se la
differenza è diversa da zero.

**M4. Campioni piccoli che sembrano normali.** AAPL dopo un −10%: 9 finestre
indipendenti, eppure la tabella ha lo stesso aspetto di una con 126. Sotto una
soglia (20, come altrove nel progetto) il risultato va dichiarato non
concludente prima dei numeri, non dopo.

**M5. Copertura degli eventi corta.** Il CPI ha 19 rilasci perché
`macro_release_dates` copre il calendario a tre anni; le trimestrali 20 perché
la cache dei fondamentali tiene circa cinque anni. Le date di rilascio FRED
hanno storia lunga (ALFRED, le «vintage»): il CPI dal 1990 sono oltre 400
rilasci. Lo stesso per le trimestrali, ricostruibili dagli archivi SEC già
usati dallo studio score-IC.

**M6. Rendimenti assoluti.** «Dopo un calo del 10% AAPL ha fatto +3%» contiene
il mercato di quei giorni. Il caso base corregge la media di lungo periodo, non
il regime: dopo i cali del 2020 è salito tutto. Manca l'opzione «al netto
dell'S&P 500» (o della mediana dell'universo, la scelta del motore).

**M7. Nessuna prova di stabilità.** Il progetto si fida di un effetto solo se
regge su campioni disgiunti (la lezione dello studio di settembre: t 3,5 sciolto
sui due gruppi). Lo Studio non mostra se il risultato regge nella prima e nella
seconda metà della storia.

**M8. Prestazioni a freddo.** La stagionalità di un indice impiega 3,5 s alla
prima richiesta (storia scaricata e calcolata ogni volta). Per i titoli è
sotto i 100 ms. Una cache per (simbolo, giorno) la porta allo stesso livello.

**M9. Nessun conto dei tentativi.** Chi prova venti soglie finché una «funziona»
ha trovato rumore. È la regola B dello studio condizionale (FDR per famiglia)
applicata all'utente: oggi lo schermo non sa quanti studi sono stati fatti.

---

## 3. UX e UI di oggi

Dai rilievi del 2026-11-17 restano aperti **D-81, D-82, D-83, D-84, D-85,
D-86, D-87** (nella fase 5, FA-176). In sintesi:

- **Nessun punto di partenza**: modulo vuoto e «Scegli un simbolo», nessun
  esempio, nomi dei modelli astratti, un solo ingresso dalle altre pagine (D-81).
- **Il modulo corregge in silenzio** i valori, l'orizzonte degli eventi resta
  a 21 con un massimo di 10, il 404 diventa un errore generico (D-82).
- **Serie FRED da sapere a memoria** (`CPIAUCSL`), quando l'app conosce già
  nomi e ID (D-83).
- **Stagionalità**: due tabelle senza titolo, barre verdi e rosse su misure che
  includono lo zero (D-85).
- **Eventi**: percorso senza banda né numero di eventi per punto (D-86).
- **Telefono**: tabelle da 560 px che scorrono di lato, risultato senza
  intestazione della domanda, scheletro fisso da 256 px (D-87).

Rilievi nuovi di questa passata:

- **«Dopo un movimento» non ha grafico**: una frase e una tabella di due righe.
  È il modello più usato e il meno leggibile.
- **Il modulo occupa tre righe su telefono** (simbolo, modello, parametri) e
  resta in cima anche dopo il calcolo: il risultato comincia a metà schermo.
- **Doppio margine**: `p-3 sm:p-6` dentro il margine del layout.
- **Il risultato non si rilegge da solo**: un link condiviso apre tabelle senza
  la domanda che le ha prodotte.

---

## 4. Capacità nuove

Tutte su dati che l'app ha già, salvo dove scritto. Sforzo: S (≤ 1 giorno),
M (2-4), L (> 4).

### 4.1 Leggere meglio la stessa domanda

| # | Capacità | Perché | Sforzo |
|---|---|---|---|
| F1 | **Distribuzione**: istogramma della condizione sovrapposto alla base, percentili 10/50/90, peggiore e migliore | M2: la media da sola inganna proprio sui casi interessanti | S |
| F2 | **Percorso cumulato** anche per «dopo un movimento», da 0 a H sedute, con banda; **massima discesa e massima salita lungo il percorso** (MAE/MFE) | dice quanto bisognava sopportare per avere quel risultato, cioè la geometria di uno stop | M |
| F3 | **Differenza con intervallo e verdetto**: «compatibile con zero» o «diversa da zero», e «non concludente» sotto le 20 finestre | M3, M4 | S |
| F4 | **Regge nelle due metà?** La stessa misura sulla prima e sulla seconda metà della storia, e per anno | M7: è la prova di replica del progetto, a schermo | S |
| F5 | **Correzione per famiglia** in stagionalità e in ogni modello che produce più confronti | M1 | S |

### 4.2 Domande nuove

| # | Capacità | Dati | Sforzo |
|---|---|---|---|
| F6 | **Primo passaggio**: probabilità di toccare +X% prima di −Y% entro H sedute | `primo_passaggio` esiste già (endpoint e strumento MCP), su finestre disgiunte con Wilson | S |
| F7 | **Al netto del mercato**: rendimento in eccesso sull'S&P 500 o sulla mediana dell'universo | serie di mercato già lette dallo Studio | S |
| F8 | **Eventi condizionati alla sorpresa**: trimestrali battute o mancate (sorpresa EPS in cache), dati macro sopra o sotto il consenso | `macro_consenso` + esiti, sorpresa EPS nei fondamentali | M |
| F9 | **Drawdown e recupero**: profondità, durata e tempo di recupero dei cali oltre X% | sola serie dei prezzi | S |
| F10 | **Dopo i segnali del motore**: cosa è successo dopo i segnali di un detector su questo titolo, settore o universo, contro il controllo abbinato | `esiti_orizzonti` con controllo a cinque titoli, già maturato | M |
| F11 | **Confronto fra simboli**: la stessa domanda su fino a cinque simboli (un titolo, il suo settore, l'S&P 500) in piccoli multipli | stesse funzioni, più chiamate | M |
| F12 | **Condizioni di regime**: aggiungere «sopra/sotto la media a 200», «VIX nel terzile alto», «volatilità alta» | serie macro di stato già in `backfill_macro_history` | M |
| F13 | **Correlazione e beta mobili** fra due simboli, con i regimi in cui cambiano | sola serie dei prezzi | M |
| F14 | **Studio sull'universo o su un settore**: la condizione su tutti i titoli, con le finestre contate per blocchi di tempo (regola A) | OHLCV del catalogo; va calcolato in un job, non nella richiesta | L |

⚠️ **F12 e F14 moltiplicano i tentativi.** Vanno con F5 e con il contatore di
F17, altrimenti lo Studio diventa una macchina per trovare effetti che non
esistono — il difetto che sei studi del motore hanno passato mesi a evitare.

### 4.3 Lavorare con gli studi

| # | Capacità | Sforzo |
|---|---|---|
| F15 | **Ingressi contestuali**: «Studia» nella scheda titolo, nel dettaglio mercato, su una posizione e su un segnale, col simbolo e una domanda pronta | S |
| F16 | **Galleria di partenza**: sei domande d'esempio cliccabili | S |
| F17 | **Studi salvati e cronologia**, con il **numero di varianti provate** sullo stesso simbolo e modello a schermo («7 soglie provate: uno su 20 esce per caso») | M (tabella sul database, non nel browser) |
| F18 | **Esporta** CSV dei casi e PNG del grafico | S |
| F19 | **Copertura lunga degli eventi**: date di rilascio FRED storiche e trimestrali da SEC | M (M5) |
| F20 | **Cache** del calcolo per (simbolo, modello, parametri, giorno) | S (M8) |

---

## 5. Il ridisegno

### 5.1 Struttura

**Computer** (da `lg`): due colonne.

```
┌ Domanda (320px, ferma) ─────┐ ┌ Risultato ──────────────────────────────┐
│ [Simbolo ▾ ricerca]          │ │ AAPL · dopo −10% in 5 sedute · 21 dopo   │
│ ( ) Dopo un movimento        │ │ ⚑ Non concludente: 9 finestre su 20       │
│ ( ) Stagionalità             │ │ ┌Occorrenze┐┌Finestre┐┌Differenza┐┌Pos.┐ │
│ ( ) Attorno a un evento      │ │ │   22     ││   9    ││ +0,6%    ││59% │ │
│ ( ) Primo passaggio          │ │ │          ││        ││−5,8/+7,0 ││    │ │
│                              │ │ └──────────┘└────────┘└──────────┘└────┘ │
│ Se è sceso del [10]% in [5]  │ │ [ Percorso | Distribuzione | Metà ]       │
│ sedute, guarda le [21] dopo  │ │ ▁▂▃▅▆▇ grafico principale con banda       │
│ □ al netto dell'S&P 500       │ │                                          │
│ [Calcola]   3 varianti provate│ │ ▸ Dettagli (tabella completa)            │
└──────────────────────────────┘ └──────────────────────────────────────────┘
```

**Telefono**: la domanda diventa una riga sola in cima («AAPL · −10% in 5 ·
21 sedute · Modifica»), che apre il modulo in un foglio dal basso. Sotto, il
verdetto, le quattro tessere in griglia 2×2, il grafico a piena larghezza
alto 200 px, e i dettagli a schede invece della tabella da 560 px. Nessuno
scorrimento laterale.

**Prima apertura**: la galleria (F16) al posto di «Scegli un simbolo».

### 5.2 Il modulo come frase

I modelli si chiedono con le parole della domanda, non con etichette:

- «Se **AAPL** è **sceso** del **10%** o più in **5** sedute, cosa è successo
  nelle **21** dopo?»
- «In quali **mesi** **^GSPC** è andato meglio?»
- «Cosa fa **NVDA** attorno alle **trimestrali**, quando le **batte**?»

Ogni campo dice i suoi limiti sotto di sé, il simbolo si cerca (riusa la
ricerca della barra in alto), la serie macro si sceglie per nome. Il 404 del
server diventa «XYZQ non è né nel catalogo né fra i mercati».

### 5.3 I grafici

| Modello | Grafico principale | Regola di colore |
|---|---|---|
| Dopo un movimento | percorso cumulato con banda al 95%, base tratteggiata | tono neutro; il verso solo se la differenza esclude lo zero |
| Stagionalità | **forest plot**: un punto e la sua barra d'intervallo per mese | colore solo per i mesi che superano la correzione per famiglia |
| Evento | percorso da −6 a +10 con banda, linea verticale sull'evento, n per punto | come sopra |
| Distribuzione | istogramma della condizione sopra quello della base | due grigi; mediana segnata |
| Primo passaggio | barra divisa: target prima / stop prima / nessuno dei due | il verso del progetto (smeraldo/rosa) |

Tutti dai componenti già condivisi (`GraficoSvg`, `lib/coloriGrafico`), con la
tabella `sr-only` per lettori di schermo che il grafico SVG porta già.

### 5.4 Il verdetto

Una riga sola, sopra i numeri, con tre stati e un solo proprietario:

- **Non concludente** — meno di 20 finestre indipendenti, o una sola metà
  della storia.
- **Compatibile con zero** — l'intervallo della differenza contiene lo zero.
- **Diversa dalla base** — esclude lo zero, regge nelle due metà, e (se ci
  sono più confronti) supera la correzione.

Mai «conviene» o «segnale»: lo Studio descrive. È la stessa frase fissa della
scheda Rischio.

---

## 6. Proposta in tre ondate

**Ondata 1 — leggere bene ciò che c'è già (≈ 4 giorni).** F3, F4, F5, F1, F20,
più D-82, D-84, D-85, D-87: verdetto, differenza con intervallo, stabilità
nelle due metà, correzione in stagionalità, distribuzione, cache, il modulo
come frase e il risultato a schede su telefono. Non aggiunge domande: rende
onesto e leggibile ciò che lo Studio già calcola.

**Ondata 2 — domande nuove a basso rischio (≈ 5 giorni).** F6 primo passaggio,
F7 al netto del mercato, F9 drawdown, F2 percorso con MAE/MFE, F15 ingressi
contestuali, F16 galleria, D-81, D-83, D-86.

**Ondata 3 — domande che moltiplicano i tentativi (≈ 8 giorni).** F17 studi
salvati col contatore delle varianti (prima, perché è il presidio delle
altre), poi F8 sorprese, F10 dopo i segnali del motore, F11 confronto fra
simboli, F12 regimi, F19 copertura lunga. F14 (universo) solo dopo, come job.

**Raccomandazione:** partire dall'ondata 1. Il rischio maggiore dello Studio
oggi non è che faccia poco, è che quello che mostra venga creduto più di
quanto regge: M1 e M2 producono a schermo, già adesso, conclusioni sbagliate
sui due esempi più ovvi (^GSPC e NVDA).
