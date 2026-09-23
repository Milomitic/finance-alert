# Si può tarare il motore sulla storia? E dove serve il machine learning

**Data:** 2026-09-23 · **Strumenti:** `backend/scripts/studio_taratura/` (i dati stanno
fuori da git, in `backend/data/studio_taratura/`; come rigenerarli è scritto in
`percorsi.py`).

## In breve

1. **Sugli esiti live non si tara niente, oggi.** Quattro mesi di magazzino
   danno ±0,07 R di incertezza al detector meglio misurato; distinguere un
   miglioramento di +0,1 R richiede ~14-17 mesi sui detector a 5 giorni e anni su
   quelli a 21 e 63 (per questi ultimi c'è **un solo** blocco indipendente).
2. **Sulla storia decennale, quasi nessuna leva batte la configurazione di
   oggi fuori campione.** Soglia di Forza, cancelli, pesi dei fattori, scelta
   dei detector sul passato, geometria di medio e lungo periodo: nessuna
   differenza distinguibile dal rumore. È il **settimo risultato nullo** sulla
   direzione, dopo i sei già registrati in `CLAUDE.md`.
3. **Due eccezioni, entrambe per SOTTRAZIONE di un danno e non per scoperta di
   un vantaggio:**
   - il piano a orizzonte breve ha lo stop troppo stretto (mediana 1,7%): costa
     ~0,05 R a operazione in costi e rende peggio del caso. Uno stop più largo
     porta la skill a zero — ipotesi **pre-registrata e confermata** su 274
     titoli mai visti;
   - `candle_reversal` e `adx_confirmation` sono i soli detector con skill
     negativa che sopravvive alla correzione per test multipli. Il primo per
     colpa della geometria, il secondo per la direzione.
4. **Il machine learning trova la volatilità, e sulla direzione solo un
   effetto piccolo** (§6, §7). Il range delle 10 barre successive si prevede
   meglio dell'ATR in tutti e 7 gli anni di test. Sulla direzione, un modello
   che sceglie fra TUTTI i match prima dei cancelli porta la skill da −0,009 a
   +0,009 R a parità di volume — replicato su due gruppi di titoli disgiunti.
   Poco, ma è più di quanto faccia la soglia di Forza, che non seleziona
   affatto.
5. **Tre difetti di misura** trovati lungo la strada (§8), uno dei quali
   ribalta il segno di un detector sul pannello Prestazioni.

## 1. Materiale e metodo

**Magazzino live (produzione, sola lettura):** 9.135 alert dal 2026-05-23,
5.540 esiti di piano, 5.275 esiti a orizzonte fisso.

**Replay decennale.** 450 titoli estratti a caso (seme fisso) fra i 1.003 con
almeno 800 barre, **sulle serie di produzione** (quelle con le riparazioni di
split e barre); 2017-05 → 2026-09. Ogni barra passa dagli stessi detector
(`detect_signals_and_setups` su 261 barre, come lo scan); il cooldown di 14
giorni, la catena di 28 e i cancelli (Forza ≥ 60, allineamento al trend,
follow-through, età ≤ 7 giorni) sono **emulati** con la logica di
`signal_scan_service`. Due popolazioni:

| | righe | cosa sono |
|---|---|---|
| `ep_live` | 106.867 | gli alert che il motore di oggi avrebbe emesso |
| `ep_all` | 405.660 | i match che passano la sola età — per provare cancelli diversi |

Piano e gara con le funzioni **del magazzino live** (`costruisci_piano`,
`corri_la_gara`). Per le geometrie alternative una gara vettoriale che
riproduce quella originale su 450.340 righe con 36 discordanze (0,008%, pareggi
al bordo dello stop dovuti alla precisione float32).

**Fedeltà del replay.** Sullo stesso periodo del magazzino live la classifica
dei detector coincide (Spearman 0,68 su 11 detector) e la miscela degli esiti è
quasi identica:

| | stop | target | scaduto |
|---|---|---|---|
| replay | 57,9% | 15,2% | 26,9% |
| live | 53,0% | 14,8% | 32,1% |

Su un campione di due titoli, 22 alert su 23 e 17 su 19 coincidono con quelli
veri, a meno di 1-4 giorni di cadenza dello scan.

**Tre metriche:**

- **R** — l'attesa del piano in multipli di rischio: ciò che l'utente vede.
- **skill** — R meno un **controllo casuale**: per ogni segnale, cinque titoli
  presi a caso lo stesso giorno, con la stessa geometria in unità del *loro*
  ATR e lo stesso verso. In un universo di titoli sopravvissuti, 2017-2026,
  comprare qualunque cosa ha attesa positiva: il controllo sottrae deriva e
  geometria e lascia il solo merito dell'ingresso.
- **hit market-neutral** — il segnale batte la **mediana** dell'universo
  all'orizzonte del detector (la stessa definizione del magazzino live).

**Validazione.** Walk-forward annuale: ogni leva si sceglie sugli anni
precedenti (embargo di 100 giorni, perché gli esiti degli ultimi segnali di
train guardano dentro l'anno di test) e si misura sull'anno dopo, 2020-2026. Il
verdetto aggrega le differenze **mensili**: i segnali dello stesso mese non
sono indipendenti.

## 2. Il magazzino live non basta

Blocchi di calendario lunghi quanto l'orizzonte del detector, finestre chiuse:

| detector | orizzonte | righe | blocchi indipendenti | mesi per vedere +0,1 R |
|---|---|---|---|---|
| candle_reversal | 5 | 1.661 | 17 | ~17 |
| gap_and_go | 5 | 149 | 17 | ~14 |
| volume_breakout | 21 | 132 | 4 | ~11 |
| macd_divergence | 21 | 249 | 4 | ~28 |
| sr_flip | 21 | 936 | 4 | ~53 |
| trend_pullback, high52, structure_break | 63 | 128-675 | **1** | non stimabile |

Le stime di potenza stesse poggiano su 4-17 blocchi e sono rozze; l'ordine di
grandezza no. **Il magazzino live è la conferma fuori campione di domani, non
la base di taratura di oggi.**

## 3. Le leve, una per una

| Leva | Esito fuori campione |
|---|---|
| **Soglia di Forza** | La soglia scelta sul passato vs 60: −0,004 R al mese, t −0,20. Nessuna soglia vs 60: t 0,52. Dentro ciascun detector i quintili di Forza non ordinano gli esiti (skill −0,010 / −0,002 / −0,015 / −0,012 / −0,021); IC medio 0,008, positivo nel 57% delle celle detector×anno. **Il cancello riduce il volume, non seleziona la qualità.** |
| **Allineamento al trend** | Chi passa: skill +0,011; chi è scartato: −0,011; t 1,14. Sull'anteprima a 176 titoli il segno era opposto: instabile. |
| **Follow-through** | Scarta 516 match su 77.943 (0,7%): quasi inerte, t 0,24. |
| **Pesi dei fattori nella Forza** | 20 test (detector × fattore, IC per blocchi contro l'eccesso market-neutral): **nessuno** sopravvive a FDR 10% (q minimo 0,21). Segno concorde fra 2017-21 e 2022-26 nel 40% dei casi (il caso è 50%). I due più forti sono NEGATIVI: `expansion_strength` di squeeze e `candle_strength` di candle_reversal — più forte il fattore, peggio l'esito. |
| **Scegliere i detector sul passato** | La classifica dei detector non persiste da un anno all'altro (Spearman medio 0,13). Tenere quelli con skill > 0 in train: +0,016 al mese, t 2,44. La scelta esclude **ogni anno** i due detector del §5, più tre debolmente negativi (`chart_pattern`, `macd_divergence`, `squeeze_expansion`): stabile, ma è il §5 visto da un'altra parte, non una leva nuova. |
| **Geometria stop/target** | 73 configurazioni per orizzonte. Aggregato: netto +0,021, t 1,83; skill +0,012, t 1,87 — sotto la soglia che i test multipli impongono. Sul **medio e lungo** la geometria attuale è già sopra la mediana delle alternative (skill 0,013 contro 0,006; 0,004 contro 0,002): la taratura del 2026-05-25 regge. **Sul breve no** (§4). |

## 4. Il piano a orizzonte breve (pre-registrato)

Il piano breve (`candle_reversal`, `gap_and_go`, parte di `squeeze_expansion` e
`sr_flip`) ha il pavimento dello stop a 0,5 ATR: mediana 1,7% del prezzo. A
0,1% di costo andata e ritorno sono **0,05 R a operazione** solo di costi, e
la skill è negativa: lo stesso piano su titoli a caso rende di più.

Sull'anteprima (176 titoli) lo stop largo — pavimento 4 ATR, TP1 1,5 R — la
riportava a zero con t 2,62. Essendo stato scelto guardando i dati, è stato
scritto in `preregistrazione.json` **prima** di vedere i 274 titoli restanti,
e misurato solo su quelli:

| costo | netto attuale → largo | t | skill attuale → largo | t |
|---|---|---|---|---|
| 0% | −0,002 → −0,005 | −0,03 | −0,024 → +0,003 | **2,56** |
| 0,1% | −0,055 → −0,014 | **3,50** | idem | |
| 0,2% | −0,108 → −0,024 | 6,98 | idem | |

**Confermata.** Ma va letta per quello che è: a costo zero il netto non cambia.
Non è un vantaggio trovato, è un danno tolto. Con uno stop del 9% su un
orizzonte di 5 barre, il piano diventa in pratica «tieni 5 giorni»: la
geometria stop/target non aggiunge niente su questo orizzonte, e togliere la
parte che fa danno è l'unica cosa che i dati sostengono.

## 5. I detector che fanno peggio del caso

Skill per detector × orizzonte, t sui mesi, Benjamini-Hochberg su 22 celle:

| detector | orizzonte | righe | skill | t | q | skill con stop largo | hit mkt-neutral |
|---|---|---|---|---|---|---|---|
| candle_reversal | breve | 18.291 | −0,050 | −3,82 | **0,005** | −0,004 | 49,1% |
| adx_confirmation | lungo | 11.940 | −0,051 | −3,21 | **0,020** | −0,021 | 47,9% |
| volume_breakout | medio | 1.829 | +0,068 | 2,24 | 0,150 | +0,059 | 50,9% |
| sr_flip | lungo | 8.227 | +0,047 | 2,29 | 0,150 | +0,009 | 50,4% |
| gap_and_go | breve | 2.099 | +0,045 | 1,99 | 0,217 | +0,027 | 51,2% |

- **`candle_reversal`** — il detector più frequente in produzione. Skill
  sopra il controllo in **0 anni su 10**. Col solo stop largo torna a −0,004:
  il danno è la geometria, la direzione è una moneta (49,1%).
- **`adx_confirmation`** — resta negativo anche con lo stop largo (t −2,0) e il
  suo hit è 47,9%. È anti-skill di DIREZIONE, coerente con la calibrazione
  (`mkt_neutral_edge_pct` −0,8). Non va invertito: un −2 punti non è un segnale
  da giocare al contrario, è un detector che non merita spazio.
- I positivi **non** sopravvivono alla correzione. Tre t attorno a 2 su 22
  celle sono ciò che il caso produce.

## 6. Machine learning: meta-labeling

La domanda: dato che un detector ha sparato, un modello sa dire QUALI segnali
tenere? Gradient boosting a istogrammi e logistica L2 (scritti in numpy: il
progetto non ha scikit-learn), ~90 variabili note alla chiusura del giorno di
emissione — detector, Forza, fattori, geometria, 17 variabili del titolo con le
direzionali anche «nel verso del segnale», forza relativa al settore — più, in
una variante, 8 di mercato. Ogni colonna che guarda al futuro è bloccata da
un'asserzione. Walk-forward annuale con embargo; valore economico = skill del
30% con punteggio più alto (soglia fissata sui punteggi di TRAIN) meno la media,
per mese.

| Variante | AUC | base del detector | guadagno | t mesi |
|---|---|---|---|---|
| batte la mediana, CON mercato — logistica | 0,513 | 0,498 | +0,043 | **3,50** |
| · stessa, replica sui 176 titoli della pre-analisi | 0,517 | | | 0,26 |
| · stessa, replica sui 274 titoli nuovi | 0,514 | | | 1,60 |
| batte la mediana, SENZA mercato — GBM | 0,511 | 0,498 | +0,020 | 1,61 |
| · gruppo 176 / gruppo 274 | | | +0,036 / +0,020 | 2,39 / 0,97 |
| · scelta DENTRO ciascun detector | | | +0,016 | 1,48 |
| batte il controllo, SENZA mercato — GBM | 0,626 | 0,602 | +0,022 | 2,59 |
| · gruppo 176 / gruppo 274 | | | +0,016 / +0,033 | 1,30 / 2,96 |
| · scelta DENTRO ciascun detector | | | +0,019 | 1,96 |
| **controlli permutati** (quattro, con e senza mercato) | 0,494-0,505 | | | **−2,61** … 0,86 |

Tre letture:

1. **Il risultato più forte non si replica.** La logistica con le variabili di
   mercato fa t 3,50 sul campione intero e 0,26 / 1,60 sui due gruppi di
   titoli. I due gruppi hanno le STESSE date, quindi le stesse variabili di
   mercato: un effetto di tempismo vero comparirebbe in entrambi. Le variabili
   di mercato valgono un'osservazione per data (regola A di `CLAUDE.md`), e il
   GBM che le ha a disposizione le usa per prime: sta facendo market timing su
   una manciata di regimi.
2. **Senza mercato resta un segnale debole, forse vero.** Il segno è positivo
   ovunque, anche dentro ciascun detector — quindi non è solo «evita i due
   detector del §5» — e l'AUC sta sopra i controlli permutati in tutti gli
   anni. Ma a ogni prova uno dei due gruppi cade sotto la significatività: il
   profilo di un effetto al bordo di ciò che dieci anni sanno vedere.
3. **Sugli alert di oggi, da solo, non vale la complessità.** +0,02 R a
   operazione sul 30% dei segnali: meno della metà di ciò che il solo piano
   breve perde in costi (0,05 R), buttando il 70% dei segnali.

**Sulla popolazione estesa — tutti i match, PRIMA dei cancelli, 401.181 righe
— lo stesso effetto regge a ogni prova**, con l'etichetta «batte il
controllo»:

| | guadagno del 30% scelto | t | dentro ciascun detector, t |
|---|---|---|---|
| tutti i titoli | +0,023 | **4,06** | 3,88 |
| gruppo 176 | +0,019 | **2,95** | 3,28 |
| gruppo 274 | +0,024 | **3,42** | 3,21 |

Sopra la banda del caso, replicato su entrambi i gruppi disgiunti, positivo
in tutti e 7 gli anni, e presente DENTRO ciascun detector: è l'unico effetto
ML sulla direzione che passa tutte le prove di questo studio. Con l'etichetta
«batte la mediana» lo stesso segno ma più debole (t 2,30; gruppi 2,19 e 2,02).

Piccolo, ma con un uso preciso. Il 30% scelto dal modello fra TUTTI i match ha
lo stesso volume degli alert che il motore emette oggi (~120mila contro
~105mila in dieci anni), e skill **+0,009 R contro −0,009** degli alert
attuali. Cioè: **come cancello di emissione, un meta-modello seleziona un po';
la soglia di Forza non seleziona affatto** (§3).

⚠️ **L'etichetta «vince / perde» inganna.** AUC 0,638 contro 0,615 della base,
e sembra il risultato migliore: il modello impara a scegliere i trade coi
target più VICINI (la variabile più usata è il rapporto target/stop), che
vincono più spesso e non rendono di più. La skill del 30% scelto sale di
+0,018, meno che con le etichette giuste. L'etichetta di un meta-modello deve
essere l'attesa, mai la frequenza di vincita.

⚠️ **Un t isolato non dice niente qui.** Nei controlli permutati, dove per
costruzione non c'è niente da imparare, il t economico arriva a **−2,61**. Due
ragioni, entrambe strutturali: i mesi adiacenti non sono indipendenti (un
trade a 63 barre ne attraversa tre), e anche un modello addestrato sul rumore
sceglie il suo 30% in base a variabili VERE, spostando la miscela di detector
— che hanno skill diverse. Quindi la banda del caso, per questa misura, è
circa ±2,6 e non ±2. Ogni t fra 1,6 e 3,5 del §6 ci sta dentro o sul bordo;
ciò che distingue un effetto è la replica su gruppi disgiunti, non il t.

Per la stessa ragione le prove del §4 e del §5 non poggiano sul t da solo: il
piano breve ha la replica (2,62 sui titoli della pre-analisi, 2,56 su quelli
nuovi) e un meccanismo misurato (i costi in R); i due detector negativi stanno
a −3,8 e −3,2, fuori dalla banda.

## 7. La controprova: la volatilità si prevede

Obiettivo: log(range medio delle 10 barre successive / ATR all'ingresso), cioè
di quanto l'ATR di oggi sbaglia la volatilità di domani. GBM, sole variabili
del titolo, walk-forward annuale.

| anno | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| R² contro «ATR di oggi» | 0,02 | 0,17 | 0,18 | 0,24 | 0,21 | 0,21 | 0,20 |
| Spearman | 0,31 | 0,34 | 0,28 | 0,39 | 0,40 | 0,40 | 0,47 |

Positivo in **tutti e 7 gli anni**, anche nel 2020. Le variabili che contano
sono tutte di volatilità e liquidità (vol20, rango dell'ATR sul proprio anno,
rapporto di volume, turnover). È il posto dove l'ML ha presa su questi dati:
dimensionare stop e posizione su una volatilità PREVISTA invece che su quella
passata.

⚠️ Un'ipotesi sbagliata scartata strada facendo: che la skill negativa venisse
da stop colpiti per un'espansione di volatilità dopo il segnale. Misurato: i
segnali hanno volatilità futura pari o inferiore ai controlli (0,92 contro
0,93 dell'ATR), e la skill non peggiora quando la volatilità si espande.

## 8. Difetti trovati

1. **Il pannello Prestazioni conta le finestre aperte.** Il 18% degli esiti di
   piano (1.015 su 5.540) viene da finestre non ancora chiuse, che per
   costruzione contengono solo le uscite veloci — cioè gli stop:

   | | attesa sul pannello | a finestre chiuse |
   |---|---|---|
   | structure_break | −0,198 | **+0,064** |
   | analyst_momentum | −0,319 | +0,136 |
   | trend_pullback | −0,238 | −0,135 |
   | squeeze_expansion | −0,455 | (tutte aperte) |
   | totale | −0,065 | −0,012 |

   `squeeze_expansion` e `adx_confirmation` emettono il livello solo dal
   2026-09-17, quindi TUTTI i loro piani sono in finestre aperte. La colonna
   che serve esiste già: `legs_window_complete`.
2. **Forza e fattori non sono misurati all'ingresso.** Lo snapshot viene
   sostituito a ogni revisione (80% degli alert), e la Forza del magazzino
   coincide con quella dello snapshot attuale nel 99,7% dei casi: sul 68% degli
   esiti è la Forza dell'ULTIMA revisione, misurata giorni o settimane dopo
   l'ingresso. Il magazzino live non può addestrare né validare un modello su
   quelle variabili. È la stessa forma già chiusa per `first_atr`.
3. **Il motore emette su titoli sospesi.** BMPS.MI nel 2017: prezzo riportato
   piatto per mesi a volume zero, ATR → 0, stop → 0, e `oversold_reversal` +
   `trend_pullback` emessi lo stesso. Nel replay 162 righe su 453mila (ATR <
   0,3% del prezzo o volume nullo per 20 barre) spostavano una media da −0,02 a
   −0,85 R. Nessun detector controlla che il titolo stia davvero scambiando.

⚠️ E un quarto, sugli strumenti: una SELECT delle serie complete lanciata nel
container dell'app è finita in OOM (exit 137). L'app è sopravvissuta perché il
killer ha scelto il processo giusto. Le esportazioni grandi passano da `\copy`
nel pod di Postgres.

## 9. Cosa migliorare, in ordine

### A. La misura (prerequisito di tutto il resto)

1. **Prestazioni solo su finestre chiuse.** Filtro su `legs_window_complete`
   e il conteggio delle aperte escluse dichiarato. Una riga di query; oggi un
   detector cambia segno sul pannello (§8.1).
2. **Variabili fissate all'emissione.** `first_strength`, `first_factors` e un
   vettore di contesto (le ~20 variabili del titolo di questo studio) congelati
   alla prima emissione, con la stessa meccanica di `INGRESSI_CONGELATI`. Senza,
   nessun modello — nemmeno la Forza — si potrà mai validare sugli esiti veri,
   perché le variabili del magazzino sono misurate DOPO l'ingresso.
3. **Registro dei candidati scartati.** I match che non passano i cancelli
   (Forza, trend, follow-through), col motivo, maturati come gli emessi. Oggi
   si osservano solo gli esiti di ciò che passa: l'effetto di un cancello non è
   misurabile dal vivo, per costruzione.
4. **Guardia sulle barre non negoziate.** Nessun segnale su un titolo con ATR
   sotto lo 0,3% del prezzo o volume nullo sulle ultime 20 barre (§8.3).

### B. Il motore (sostenute dai dati)

5. **Piano breve: stop più largo.** Il pavimento a 0,5 ATR fa pagare ~0,05 R di
   costi a operazione e rende peggio del caso; allargarlo (verso 2-4 ATR, TP1
   ~1,5 R) porta la skill a zero, confermato su 274 titoli mai visti (§4).
   Tocca i due gemelli del piano e i vettori d'oro, e va con un bump di
   `PLAN_METHOD_VERSION`. Chiude da solo anche il caso `candle_reversal`.
6. **`adx_confirmation` declassato.** Anti-skill di direzione che sopravvive a
   FDR (q 0,02, hit 47,9%). Non emetterlo come segnale — resta utile come
   conferma nella catena. Non invertirlo: −2 punti non sono un segnale da
   giocare al contrario.
7. **Forza per quello che è.** Non ordina gli esiti (§3): il cancello a 60 è un
   controllo di VOLUME, e va detto come tale a schermo e nel codice. Se serve
   un tetto di segnali, un tetto per detector è più onesto di una soglia che
   sembra di qualità.

Medio e lungo orizzonte, pesi dei fattori, soglia di Forza, allineamento al
trend: **da non toccare** — le alternative non battono l'attuale fuori campione.

### C. Machine learning: dove ha senso, e in che ordine

8. **Rischio prima del rendimento.** Un modello di volatilità prevista (§7:
   R² +0,17 sull'ATR, positivo in 7 anni su 7) al posto dell'ATR(14) per
   dimensionare stop e posizione. È l'unico punto dove l'ML ha presa
   dimostrata su questi dati. Prima in modalità ombra — calcolato e salvato,
   non usato — e promosso solo se il live conferma il replay.
9. **Nuova informazione, non nuovi modelli.** Sette studi dicono che le
   variabili ricavate dai prezzi sono esaurite: un modello più potente su di
   esse trova ciò che §6 ha trovato. L'ML può aggiungere valore solo con fonti
   ORTOGONALI e archiviate nel tempo (point-in-time): revisioni delle stime
   degli analisti, sorprese sugli utili, short interest, flussi insider,
   volatilità implicita delle opzioni, notizie. Ognuna va prima ARCHIVIATA
   puntualmente — oggi quasi tutte arrivano solo come «valore di adesso», che
   per un modello equivale a non averle.
10. **Il bersaglio giusto.** Classifica cross-sectional del rendimento
    market-neutral sull'intero universo (learning-to-rank), non «questo trade
    vince?». La seconda etichetta premia i target vicini (§6).
11. **Il cancello per ogni modifica.** Il replay di questo studio, con il
    controllo casuale, i controlli permutati e la replica su gruppi di titoli
    disgiunti, è il banco di prova che `retune.py` dichiara ma non ha: senza `--run`
    legge artefatti già calcolati, e nessuno dei suoi harness misura la
    geometria del piano contro un controllo. Ogni cambio di soglie, geometria o modello ci passa
    prima di andare in produzione.
12. **Meta-modello al posto della soglia di Forza, in ombra.** Il §6 mostra
    che un GBM che sceglie fra tutti i match il 30% con più probabilità di
    battere il controllo porta la skill da −0,009 a +0,009 R a parità di
    volume, replicato su gruppi disgiunti. Piccolo, e il costo di un modello
    in produzione non è piccolo: si parte calcolandone il punteggio accanto
    alla Forza, senza usarlo, e lo si promuove solo quando gli esiti live —
    con le variabili fissate all'emissione del punto 2 — confermano il replay.

## 10. Cosa non rifare

- **Tarare soglie, cancelli e pesi dei fattori sul replay dei prezzi.** Sette
  studi, sette nulli; questo ha avuto potenza (105mila alert, 81-243 mesi di
  test) e ha misurato anche il rumore (controlli permutati).
- **Usare «vince / perde» come etichetta.** Premia i target vicini: il modello
  impara a vincere più spesso senza guadagnare di più.
- **Leggere MAE e MFE dei soli vincenti** per stringere lo stop: i vinti sono
  tali anche perché lo stop non li ha toccati. Si rifà la gara su tutti.
- **Credere a un t isolato.** Nel controllo permutato, dove non c'è niente da
  imparare, il t economico sui mesi arriva a −2,6. Conta la replica su gruppi
  di titoli disgiunti.
