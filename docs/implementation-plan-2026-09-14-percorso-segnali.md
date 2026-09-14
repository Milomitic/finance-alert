# Percorso segnali — piano di implementazione

**Data**: 2026-09-14 · **Voci**: FA-051…FA-068 · **Backlog**: [PROJECT-BACKLOG.md](PROJECT-BACKLOG.md)

Il backlog dice **cosa** e **quando è chiusa**. Questo documento dice **come**, e
soprattutto **cosa può andare storto**. Non è una seconda lista operativa: ogni
attività ha il suo ID là, e qui non ne nasce nessuna.

Origine: un audit esterno sul ciclo setup → segnale → esito, **riverificato voce
per voce sul database di produzione** prima di impegnare lavoro. Undici
affermazioni su dodici reggono; tre sono più gravi di come erano descritte.

---

## Regole che valgono per tutte le voci

Scritte una volta qui invece che ripetute in ogni sezione.

1. **Le formule di Forza e Probabilità non si toccano.** Nessuna voce cambia un
   punteggio; cambiano identità, perimetri ed etichette.
2. **Le tre tabelle non si fondono.** `StockSetup`, `Alert` e `SignalOutcome`
   registrano fatti diversi — un'attesa, un evento, una misura.
3. **Mai filtrare una misura su un campo che scrive l'utente.** Sesta istanza
   già pagata: archiviazione e maturazione seguono entrambe l'ETÀ, quindi la
   loro intersezione è quasi vuota.
4. **Un rifacimento puro deve mostrare parità numerica** prima e dopo. Dove non
   la mostra, non è puro.
5. **Uno SHA si cita in un push SUCCESSIVO** a quello del codice: il rebase su
   `origin/cloud` riscrive i commit locali dopo che il riferimento è scritto.
6. **La linea di base si rigenera DOVE viene applicata** (CI), mai in locale, e
   mai su una sola osservazione.
7. **Ogni funzione nuova va ESEGUITA da un test.** Il cancello del codice morto
   lo pretende, e ha già preso in fallo lo script di bonifica di FA-052.

---

## Fase A — fermare ciò che peggiora ✅/🔶

### FA-051 — l'identità dell'evento ✅ fatto

`signal_scan_service.py`. La guardia «freeze post-esito» usciva dall'INTERA
condizione di dedup, quindi «non modificare» diventava «inserisci». Ora una
ri-lettura sulla stessa barra non fa niente; una barra diversa crea ancora.

### FA-052 — riconciliare lo storico 🔶 strumento pronto, bonifica NON eseguita

Rilevatore e script ci sono e sono provati. **Resta da eseguire**, e la sequenza
è vincolata:

1. attendere che `550bccf` (o successivo) sia il tag in esecuzione nel pod,
   verificato con `GIT_SHA` letto DA DENTRO il container;
2. `kubectl exec … python -m app.scripts.repair_duplicate_alerts` — **sola
   lettura**, e leggere i gruppi bloccati;
3. esportare le righe che verranno cancellate (`\copy (…) TO STDOUT` verso un
   file locale: il filesystem del pod pg è in sola lettura);
4. solo allora, e **solo dopo un via libera esplicito**, `--apply`;
5. rimisurare: il magazzino esiti deve calare della quantità prevista dalla
   mappa, **non di più**.

⚠️ Il punto 5 non è cerimoniale. Se cala di più, il `CASCADE` ha preso qualcosa
che non era previsto e lo si scopre mentre il backup è ancora fresco.

### FA-068 — il seme non copre `/institutionals` 🆕 aperta

Emersa dal gate UI andato rosso su una rotta che nessun commit toccava.
`seed_e2e` non semina `institutional_holdings`, quindi quella pagina misura
qualunque cosa ci sia nel database invece di un input controllato — la stessa
forma dei tre canali già chiusi nel seme.

**Come**: seminare un piccolo insieme deterministico di fondi e posizioni, con
nomi lunghi e valute miste come il resto del seme (è input avversariale, non
decorazione). **Non** aumentare la soglia dei 30rem né togliere lo scroll: il
difetto di accesso è già corretto, questo riguarda la ripetibilità della misura.

---

## Fase B — ciò che A nascondeva ✅

### FA-053 — dimensionamento del drift ✅ fatto

Finestre indipendenti al posto delle righe, quarto stato `insufficient`, e le
primitive estratte in `app/stats/sizing.py` perché vivevano dentro uno dei due
consumatori.

⚠️ **Conseguenza da aspettarsi in produzione**: il pannello diventerà silenzioso.
Con finestra 90 giorni e `min_n=30` il tetto delle finestre è 12 a orizzonte 5 e
3 a 21, quindi nessun detector può superarlo. È la risposta corretta, ed è la
stessa che il cubo dà da settembre. **Non abbassare `min_n` perché qualcosa
passi**: la soglia è la soglia, il problema è il tempo.

---

## Fase C — perimetri e serializzazione

### FA-054 + FA-055 — lo storico del titolo, e la serializzazione

**Queste due collassano in un cambio solo**, e la ragione è che il codice
corretto esiste già.

`alert_service._row_to_item` è il serializzatore canonico, e il suo docstring
**prevede letteralmente questo difetto**:

> *«due percorsi che costruiscono a mano la stessa forma divergono, e qui la
> divergenza sarebbe silenziosa — il frontend riceverebbe un alert con meno
> campi solo quando lo apre da una posizione invece che dalla lista»*

`api/stocks.py:454` è il terzo percorso di cui quel commento avvertiva, ed è già
divergente: omette `currency`, `outcome_hit`, `outcome_fwd_return`,
`outcome_horizon_days`, `outcome_mkt_excess`, `next_earnings_date`.

E `list_alerts` accetta già tutto ciò che serve: `ticker`, `archived` (con
`None` = entrambi), `limit`, `offset`, e rende `total`.

**Come**:

1. `stock_detail_service` smette di costruire `alerts_history` con la propria
   query. Il dettaglio titolo tiene un **riepilogo breve** (i recenti), servito
   dalla serializzazione canonica.
2. Lo **Storico completo** non è un campo nuovo del payload di dettaglio: è la
   lista esistente `GET /api/alerts?ticker=X&archived=&limit=&offset=`. Nessun
   endpoint nuovo, nessuna seconda serializzazione.
3. Il frontend aggiunge la scheda «Recenti / Storico completo» che punta a
   quella lista, con paginazione su `total`.

**Test**: (a) aprire lo stesso alert dalla lista e dal dettaglio titolo rende
gli stessi campi — asserzione sull'insieme delle chiavi, non su un campione;
(b) un alert archiviato con esito maturato COMPARE nello storico completo e non
nei recenti; (c) pavimento sul numero di campi, senza il quale (a) sarebbe vera
anche di due payload vuoti.

⚠️ **Rischio**: il dettaglio titolo oggi rende 50 alert dentro un payload già
grasso. Passare a «tutti» senza paginazione lo appesantirebbe su titoli come
CPRX (41 alert, e ce ne sono con più). La paginazione non è un extra.

⚠️ **E il grafico va disaccoppiato dalla tabella**: i marker devono interrogare
gli eventi del PROPRIO intervallo temporale, non la pagina corrente della
tabella, altrimenti cambiare pagina cambia il grafico.

### FA-056 — perimetro della lista setup

**Come**: `api/setups.py` guadagna `offset` e rende `total` (filtrato) accanto a
`setups`; l'ordinamento e il filtro detector si spostano nella query;
`useSetups.ts` chiede le pagine successive.

⚠️ **Il filtro `shortlisted` delle statistiche NON è un difetto** e non va tolto:
`conversion_stats` lo applica con la ragione scritta accanto — *un setup che
l'utente non ha mai visto non gli ha fatto nessuna promessa*. Il difetto è che
la pagina mostra una popolazione (1.415 attivi, 50 resi) e ne descrive un'altra
(18 chiusi in shortlist) **senza dirlo**. Si corregge dichiarando il perimetro a
schermo, non uniformando le due popolazioni.

**Test**: il totale reso è il totale FILTRATO, non quello di tabella; ordinare
per una colonna cambia la prima pagina (cioè l'ordinamento vede tutte le righe,
non solo quelle già ricevute).

---

## Fase D — affermazioni predittive residue

Tre voci a costo basso. Nessuna richiede dati nuovi: **si tolgono affermazioni,
non se ne aggiungono**, quindi non c'è nessuno studio da aspettare.

### FA-057 — la «convinzione» multi-orizzonte

`AlertsInsightCard.tsx:176` (icona con `aria-label="Convinzione: multi-orizzonte
rialzista"`) e `confluence_service.py:222` (tie-break `multi_horizon and
direction == "bull"`).

⚠️ **Non è senza fondamento**: il codice cita lo studio del 2026-06-09. L'argomento
è interno e verificabile — **il trade playbook ha cancellato la parola
`conviction` il 2026-09-02 per questa identica ragione** («il piano descrive una
geometria, non impartisce un'istruzione») e qui è sopravvissuta.

**Come**: via l'icona e via il termine del tie-break. Gli orizzonti restano
descrittivi (`HorizonChips`). L'ordinamento a parità di Forza ricade sul conteggio
segnali, che è un fatto.

**Test**: due confluenze a parità di Forza, una multi-orizzonte rialzista e una
no, si ordinano per conteggio e non per direzione. Con controllo negativo: la
forma vecchia le ordinava al contrario.

### FA-058 — ripetizioni del riepilogo confluenze

Via `Top long`/`Top short` (righe 375-376), che stanno **sopra** una graduatoria
che li contiene già; via `Forza media` (riga 424), aggregata su composizioni
eterogenee senza un impiego dichiarato. Resta una graduatoria sola, filtrabile
per direzione.

### FA-059 — «Movimento del titolo, non una condizione di mercato»

`SignalBreadthRow.tsx:66`. L'assenza di altri match non dimostra la causa del
movimento, e il perimetro non è il mercato: è il catalogo scansionato quel
giorno. Diventa «nessun altro match osservato nel perimetro coperto», col
perimetro nominato.

⚠️ La riga accanto (il caso non-solitario) è già scritta bene e **non va toccata**:
dichiara già che la coincidenza non è una conferma.

---

## Fase E — significati

### FA-060 — «esito», «orizzonte», «prezzo»

Tre divergenze misurate, che vanno trattate **separatamente** perché hanno cause
diverse.

| Divergenza | Misura | Causa |
|---|---|---|
| verdetto assoluto ≠ market-neutral | 596 / 5.313 | due domande diverse, una sola etichetta |
| etichetta orizzonte ≠ orizzonte misurato | `sr_flip`: 407 short + 252 long + 148 medium, tutti misurati a 21 | l'etichetta viene dalla CAMPATA della catena (per segnale), la misura dal detector |
| prezzo alert ≠ prezzo d'ingresso | 2.886 / 5.313 | l'aggiornamento in cooldown sposta il prezzo, la misura resta ancorata alla barra |

**Come**: quattro etichette distinte — conversione del setup, variazione del
titolo, risultato nella direzione indicata, eccesso sulla mediana dell'universo;
**durata della struttura** separata da **finestra di misurazione** (due campi,
due nomi, mai lo stesso); prezzo e data della misura mostrati accanto a prezzo e
data della rilevazione.

⚠️ **Non uniformare misure legittimamente diverse.** I 596 verdetti divergenti non
sono errori da riconciliare: un segnale può salire e fare peggio del mercato. Il
difetto è che portano la stessa parola.

⚠️ E `classify_horizon` **non va cambiato per farlo coincidere** con
`_horizon_days`: la campata della catena è un'informazione vera e utile. Il
difetto è chiamarle entrambe «orizzonte».

### FA-061 — episodi di setup (migrazione)

La voce più costosa e l'unica con perdita storica dichiarata.

**Stato attuale**: `UniqueConstraint(stock_id, detector)` più la riattivazione a
`setup_service.py:140`, che azzera `resolved_at`, `converted_alert_id` e
`lead_days`. Lo storico dei setup non è uno storico: è l'ultimo episodio di ogni
coppia.

**Come**, in quest'ordine:

1. migrazione: nuova colonna `episode_seq` (o una chiave surrogata), **unicità
   limitata all'episodio APERTO** — indice parziale su Postgres, e su SQLite
   `op.batch_alter_table` come questo repo già fa;
2. `upsert_setup` smette di riattivare: una nuova formazione **inserisce**;
3. motivi di chiusura distinti: condizioni decadute / attesa massima / dati
   insufficienti / cambio di direzione (oggi `db.delete(row)` a riga 117 non
   lascia traccia di nessuno dei quattro);
4. direzione «non determinata»: tutti i 63 collegamenti con tono setup diverso
   dal tono alert sono `squeeze_expansion`, che dichiara di non conoscere ancora
   il verso;
5. storia della visibilità in shortlist, separata dal flag corrente.

⚠️ **Gli episodi già sovrascritti non sono ricostruibili** e vanno dichiarati
mancanti, non stimati. Lo stesso vale per `lead_days` degli episodi persi.

⚠️ **La migrazione va provata sul ripristino, non solo in avanti.** Il drill del
lunedì esiste; una migrazione che non si ripercorre all'indietro va scoperta
prima, non durante un ripristino.

### FA-062 — osservabilità di aggiornamenti e maturazione — ✅ FATTA

Commit `92df901` (stati + provenienza) e `b4d4c85` (perimetro).

⚠️ **Questo piano prevedeva QUATTRO stati e la misura ne ha sostenuti DUE.**
Vale la pena leggere perché, perché il piano era sbagliato in entrambe le
direzioni e nessuno dei due errori si vedeva dal codice.

Misurato in produzione il 2026-09-14, su 3.734 alert senza esito:

| stato previsto dal piano | popolazione misurata | esito |
|---|---|---|
| maturato | 4.662 | esisteva già |
| in attesa dell'orizzonte | 3.686 | **costruito** (prima confuso col prossimo) |
| bloccato per dati mancanti | **48**, su 12 titoli | **costruito** |
| avrebbe dovuto maturare | **0** | non costruito — popolazione vuota, come FA-067 |
| non valutabile | **1** | non costruito — un'etichetta per una riga |

**La misura che aveva motivato questa voce era sbagliata, e l'ho smentita io.**
I «7 alert oltre 120 giorni» venivano da una soglia in giorni di CALENDARIO,
mentre i detector a 63 sedute sono ~88 giorni di calendario: a 73 giorni quegli
alert stavano legittimamente aspettando. La soglia giusta conta le BARRE dopo la
barra del segnale, che è ciò da cui un esito nasce davvero.

**E lo stato che è sopravvissuto è verificato, non assunto.** Il predicato
`ohlcv_nodata_streak >= 3` seleziona *esattamente* i 12 titoli la cui ultima
barra ha più di dieci giorni — zero falsi positivi, zero falsi negativi, cioè la
stessa condizione misurata per due vie indipendenti. Poi la fonte è stata
interrogata: nove non hanno più barre, e per WBS, EQR e AVB l'ultima barra
disponibile è **al giorno** la stessa che abbiamo noi, con AAPL come controllo
positivo nella stessa chiamata a provare che la rete del pod risponde.

⚠️ **Il catalogo lo sapeva dal 2026-08-26.** Quella data chiuse il lato FETCH —
smettere di scaricare i simboli morti, smettere di chiederne le quotazioni — e
`not_quarantined_clause` nomina per esteso BK, CTRA, APLS, TERN, VSCO. Nessuno
chiese cosa significasse per gli alert appesi a quei titoli. È la forma
ricorrente di questo progetto: una conoscenza che esiste in un livello e non
attraversa il confine.

**Perimetro.** Il proprietario comune esisteva già (`run_post_scan_bookkeeping`,
2026-09-02) e non prendeva scopo. Ora `universe` è obbligatorio e **senza
default**: un default a True darebbe il comportamento pericoloso a chi si
dimentica di dichiarare. Difetto latente — 37 scansioni parziali, tutte di
maggio, zero negli ultimi dieci giorni — ma FA-061 ne ha alzato il prezzo: una
chiusura sbagliata ora scrive `closed_reason` in modo permanente e finisce nel
denominatore del tasso di conversione.

⚠️ **Una scansione parziale non può dichiarare scaduto nulla** di ciò che non ha
valutato. È il difetto che il CronJob di parità ha già pagato in un'altra forma:
uno strumento che risponde su un perimetro diverso da quello che crede.

**Due cose trovate qui sono state REGISTRATE, non assorbite**: FA-071 (i dodici
titoli morti hanno ancora punteggi, classifiche e nove setup aperti) e FA-072
(«processa segnali» non invalida la lista globale).

### FA-067 — i diciotto esiti disallineati

`signal_outcomes.signal_date ≠ alerts.signal_date`: 18 righe su 5.313, 16 a
giugno, 2 a luglio, **zero da agosto**. La guardia ha chiuso il canale; questo è
il residuo.

⚠️ **Non si ricalcolano in silenzio.** Un ricalcolo storico va versionato e
confrontabile, altrimenti sostituisce misure precedenti senza che nessuno possa
vedere cosa è cambiato. Le due opzioni sono: rimisurare **con provenienza
dichiarata**, oppure marcarle come non allineate ed escluderle dalle
aggregazioni **con la ragione a schermo**. La seconda è più economica e più
onesta; la prima è preferibile solo se il ricalcolo porta una provenienza.

---

## Fase F — contesto e consolidamento

### FA-063 — i marker sul grafico

`signalMarkers.ts:101`. Due difetti indipendenti nello stesso punto:

1. `Date.parse(day)` è **mezzanotte UTC**, e `enclosingBarTime` sceglie l'ultima
   barra con tempo ≤ t: su un grafico intraday quella mezzanotte precede la
   prima barra della seduta, quindi il marker scivola nella seduta PRECEDENTE.
   Una data giornaliera non contiene l'ora di emissione e il codice non deve
   fingere che la contenga.
2. Il colore deriva dalla **maggioranza** bull/bear delle righe sulla barra: due
   segnali correlati rialzisti coprono un ribassista. È una logica diversa dalla
   de-correlazione per famiglia che `confluence_service` applica altrove.

**Come**: collocazione giornaliera esplicita (la barra che CONTIENE il giorno,
non quella che precede l'istante); simbolo misto con conteggi separati quando
coesistono i due versi; dimensioni uniformi e nessun premio visivo alla Forza.

**Test**: un segnale datato al giorno X su una serie a 30 minuti cade su una
barra del giorno X. ⚠️ Con controllo negativo sulla forma vecchia, altrimenti il
test passa su una serie giornaliera dove i due comportamenti coincidono.

### FA-064 — l'ampiezza senza direzione

`signal_breadth_service.breadth_for` raggruppa su `(signal_name, signal_date)`
senza filtrare il tono: **557 gruppi contengono entrambi i versi**.

⚠️ **Il conteggio degli archiviati è invece deliberato e documentato, e va
lasciato.** Il docstring spiega perché, e toglierlo riaprirebbe il difetto delle
19 righe su 4.880.

**Come**: conteggio per settore × famiglia × data × **direzione**, con titoli
distinti e collegamento ai componenti. Le percentuali **solo quando esiste il
denominatore** dei titoli effettivamente valutabili in quella scansione — non il
catalogo di oggi, che è un numero diverso e più grande.

⚠️ Il confine da non superare: «quel giorno 12 titoli hanno mostrato questa
condizione» è descrizione. «La diffusione conferma questo titolo» è previsione
mascherata, e i sei studi nulli restano il riferimento.

### FA-065 — `build_context` costruito due volte

`signal_scan_service.py:143` e `runner.py:41`, sullo stesso DataFrame, nella
stessa valutazione — e il docstring di `runner` dichiara proprio che la
condivisione della costruzione è il punto.

⚠️ **Non è una voce di prestazioni**, e non va venduta come tale senza
profilazione. L'argomento è che due proprietari dello stesso calcolo divergono,
come è già successo con la riga Tecnico duplicata fra `finalize` e
`recompute_one` — che aveva prodotto un 500 in produzione.

⚠️ E va distinto il conteggio `effective_n` della confluenza (corretto per
FAMIGLIA) da quello del cubo (finestre TEMPORALI indipendenti): **stesso nome,
significati diversi**, e ora che `app/stats/sizing.py` possiede il secondo la
collisione è più facile da fare.

**Test**: parità numerica su un campione di titoli, prima e dopo.

### FA-066 — il dettaglio titolo attorno al percorso

Dipende da C ed E: senza storico completo e senza etichette distinte, la
riorganizzazione poggerebbe su dati instabili. **È l'ultima voce, non la prima.**

Si evolve la scheda storica esistente: riepilogo compatto (eventi recenti,
risultati disponibili, freschezza), cronologia navigabile con origine/revisioni/
esito, selezione sincronizzata col grafico, origine setup dell'evento
selezionato, collegamento filtrato a `/setups`.

⚠️ **La scheda setup rimossa NON torna.** Nessuna seconda lista di setup, nessun
doppio pannello di statistiche. Il dettaglio titolo racconta la storia di quel
titolo; «In formazione» resta il luogo dove si confrontano le attese.

Su `/setups`, le otto statistiche e la tabella per detector si spostano in una
vista «Misurazione», lasciando davanti alla lista **cosa manca**, ultima
osservazione e durata dell'attesa — con il denominatore accanto a ogni tasso.

---

## Cosa NON si spedisce, e cosa manca per poterlo fare

Non è lavoro rimandato: sono affermazioni che i dati attuali non reggono.

| Proposta | Condizione per riaprirla |
|---|---|
| Probabilità che un setup converta entro una finestra | FA-061 (episodi conservati) + storia della visibilità + copertura delle scansioni, poi validazione temporale fuori campione |
| «Questo detector funziona meglio su questo titolo/settore» | Numerosità indipendente sufficiente e correzione per confronti multipli |
| Vantaggio da co-temporalità, famiglia o multi-orizzonte | Studio preregistrato nuovo, finestre non sovrapposte, fuori campione |
| Rendimento del piano stop/target come risultato realizzabile | Regole di esecuzione, gap, costi, dati intrabar, barre che toccano entrambi i livelli |

---

## Ordine consigliato e dipendenze

```
A  FA-051 ──► FA-052 ──┐
   FA-068              │
B                      ├──► FA-053
C  FA-054+055 ─────────┤
   FA-056              │
D  FA-057 FA-058 FA-059   (indipendenti, in qualunque momento)
E  FA-060 ─────────────┤
   FA-061  FA-062  FA-067
F  FA-063 FA-064 FA-065
   FA-066 ◄── dipende da C ed E
```

La fase D non dipende da niente e può essere intercalata quando serve un blocco
corto. FA-066 è l'ultima per costruzione.
