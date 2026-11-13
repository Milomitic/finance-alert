# Analisi evolutiva dell'app — 2026-11-13

Che cosa migliorare dell'esistente e che cosa aggiungere, deciso sull'uso
misurato in produzione. Segue l'analisi del 2026-09-26, che guardava
soprattutto la salute; questa guarda il prodotto. Ogni proposta porta la
misura da cui nasce.

## 1. Da dove vengono i numeri

| Fonte | Cosa ha dato |
|---|---|
| `uso_pagine` (contatore nato dalla proposta D di settembre) | aperture per pagina, 30 giorni |
| Database di produzione | volumi di segnali, scartati ai cancelli, modelli in prova, uso delle funzioni |
| Prometheus, 7 giorni | latenze medie e richieste per endpoint, errori |
| Server MCP | esiti per detector e per piano |
| Nodo | disco, memoria, allarmi attivi |
| Codice | dimensioni, struttura, dipendenze |

Limite comune: la latenza viene da `increase()`, che sottostima le rotte poco
usate (CLAUDE.md), quindi le medie sono ottimiste.

## 2. Prima di tutto: il disco si riempie fra pochi giorni

Non è l'oggetto dell'analisi, ma va detto per primo perché ha una scadenza.

| | Valore |
|---|---|
| Disco `/` del nodo | **92%**, 6,7 GB liberi su 83 |
| `pg_wal` di Postgres | **51 GB**, 3.255 segmenti in coda (il database vero pesa 625 MB) |
| Crescita misurata | ~0,76 GB al giorno (22 GB il 6 ottobre) |
| Ultimo backup riuscito | 9 settembre; WAL non archiviati dal 19 ottobre |
| Allarmi critici attivi | backup fermo, backup fallito, drill di ripristino, disco |

È FA-129, ancora bloccata: la tenancy OCI risponde `StorageLimitExceeded`
perché il bucket ha il versioning senza regola di pulizia. La correzione è già
nel repo; va applicata a mano perché crea una policy IAM e cancella versioni
vecchie. k3s comincia a sfrattare i pod sotto il 5% libero (~4 GB): **il
margine è di 3-4 giorni**, poi si ferma Postgres e con lui l'app. Da due mesi
non esiste un backup recuperabile.

Il resto della salute è buono: zero errori 5xx in 7 giorni, due scansioni
riuscite al giorno in 7-12 minuti, pod a 1 GB su 3 di limite, nessun riavvio.
Un allarme minore: il catalogo del FTSE MIB non si rinnova da tre sabati.

## 3. Come viene usata l'app

Aperture negli ultimi 30 giorni (app aperta in 13 giorni su 24):

| Pagina | Aperture | Quota |
|---|---:|---:|
| Dettaglio titolo | 152 | 54% |
| Cruscotto | 77 | 27% |
| Calendario | 17 | 6% |
| Segnali (tre viste) | 12 | 4% |
| Screener | 12 | 4% |
| Diagnostica | 4 | 1% |
| Mercati, Superinvestor, Posizioni | 3, 5, 2 | 4% |
| Settori | 0 | 0% |

Tre fatti che orientano tutto il resto:

1. **L'app è una pagina di ricerca sul singolo titolo, più un cruscotto del
   conto.** Otto aperture su dieci stanno lì.
2. **I segnali, che sono il motore più grande del progetto, vengono aperti 12
   volte al mese** mentre ne nascono 60-165 al giorno. In archivio: 12.586
   alert, 15.702 scartati registrati, 9.063 esiti.
3. **Le funzioni manuali sono vuote**: 0 disegni, 0 prezzi-obiettivo, 0
   posizioni manuali (sostituite da eToro: 42 posizioni, 735 operazioni
   chiuse, 233 preferiti dalla watchlist). Eppure ogni apertura di un titolo
   chiede disegni e prezzi-obiettivo al server (44 richieste ciascuno in 7
   giorni).

Le domande fatte a mano in questo mese dicono la stessa cosa da un altro lato:
distanza degli stop su SOXL, probabilità di toccare un livello prima di un
altro, «quante volte il Nasdaq ha fatto X». Sono domande sul **rischio delle
posizioni** e sulla **statistica storica**, e l'app oggi non risponde a
nessuna delle due a schermo.

## 4. Migliorie all'esistente

### 4.1 Dettaglio titolo: più veloce e più fermo

È la pagina che conta. Oggi apre ~20 richieste e 17 schede.

- **Un solo payload per il primo schermo.** `detail`, `score`, `technical`,
  `quote`, `multi-tf-kpis`, `fundamentals`, `etf-holdings`, `drawings`,
  `price-alerts` partono insieme; `fundamentals` e `detail` stanno a 1,1-1,4 s
  di media. Un endpoint aggregato per intestazione, punteggi e grafico, con il
  resto a seguire, toglie una decina di round-trip e buona parte dei salti di
  layout corretti scheda per scheda a novembre.
- **Togliere le due richieste vuote** (disegni, prezzi-obiettivo) finché le
  funzioni non sono usate: caricarle solo all'apertura del relativo strumento.
- **Confronto con i pari.** I dati ci sono (settore, industria, punteggi,
  multipli): una scheda «contro il settore» con 5-6 titoli vicini per
  capitalizzazione dà contesto a ogni numero della pagina. Oggi c'è solo il
  rango «X su Y nel settore».
- **Reazione alle trimestrali passate.** Lo storico delle sorprese è già nei
  fondamentali e le barre sono nel database: movimento del giorno e a 5 sedute
  dopo ogni trimestrale, accanto alla prossima data. È la domanda naturale
  prima di un evento, e oggi richiede il server MCP.
- **Note sul titolo.** Un campo di testo datato per titolo. È la funzione
  manuale con più probabilità d'uso, visto che i disegni non lo sono.

### 4.2 Cruscotto: dal mercato al portafoglio

Il cruscotto ha 12 schede, in gran parte sul mercato (movers, heatmap,
istogramma RSI, top picks). L'utente lo apre per il conto.

- **`/api/dashboard/summary` 2,1 s, `analyst-actions` 1,7 s, `scores/top`
  1,7 s, `cruscotto/visita` 1,6 s**: sono tutte letture del database, quindi
  si possono precalcolare a fine scansione e servire da cache.
- **Ordinare le schede per rilevanza personale**: conto, poi «sui tuoi
  titoli» (trimestrali vicine, notizie, azioni degli analisti sulle
  posizioni), poi il mercato. Le azioni degli analisti e i movers filtrati sui
  233 preferiti valgono più della lista sull'universo.
- **Decidere su istogramma RSI, top picks e heatmap settori**: Settori ha zero
  aperture in 30 giorni e la classifica Qualità «non prevede i rendimenti» per
  dichiarazione. Candidati a scendere sotto la piega o a uscire.

### 4.3 Segnali: da elenco a filtro d'attenzione

Cento segnali al giorno per dodici letture al mese non è un problema di
interfaccia: è un prodotto senza destinatario. Gli studi dicono che non c'è
vantaggio direzionale dimostrato, quindi la strada non è «più segnali
migliori» ma **meno segnali, dove l'utente sta già guardando**.

- **La lista parte da «i miei titoli»** (posizioni e preferiti) e l'universo
  diventa la vista secondaria. Il filtro esiste già (FA-113): si inverte il
  default.
- **I segnali compaiono dove servono**: sulla riga della posizione in
  Posizioni e nella striscia preferiti del cruscotto, non in una pagina a
  parte.
- **Esiti e «In formazione» escono dalla pagina Segnali** verso Diagnostica →
  Motore: 4 e 3 aperture al mese, e sono misure del motore, non lavoro
  quotidiano.

### 4.4 Posizioni: la pagina meno usata e quella col potenziale maggiore

Due aperture in un mese, perché il conto sta già nel cruscotto e la pagina
aggiunge poco. Qui va la capability nuova più importante (§5.1).

### 4.5 Prestazioni

| Endpoint | Media 7 g | Proposta |
|---|---:|---|
| `/api/institutionals/aggregate` | 6,3 s | precalcolo dopo il refresh 13F: i dati cambiano una volta a trimestre |
| `/api/markets/{symbol}/detail` | 2,4 s | cache della storia completa, che il server scarica a ogni apertura |
| `/api/dashboard/summary` | 2,1 s | precalcolo a fine scansione |
| `/api/calendar` | 1,7 s | cache per mese |
| `/api/etoro/andamento` | 1,7 s | la serie è append-only: cache fino alla prossima sincronizzazione |

Bundle: 2,3 MB totali; il pezzo più grande è recharts (337 KB) accanto a
lightweight-charts. Due librerie di grafici per un'app: portare i pochi
grafici recharts su una sola toglie il chunk più pesante.

### 4.6 Accesso fuori casa

L'app è una PWA, ma la 443 è aperta a un solo IP: dal telefono in rete mobile
non si apre, e a ottobre un cambio di IP l'ha resa irraggiungibile per giorni.
Tailscale (o un tunnel con autenticazione) al posto dell'allowlist rende
usabile il telefono e toglie il guasto ricorrente. È la miglioria con il
rapporto più alto fra effetto e lavoro.

## 5. Nuove capability

### 5.1 Rischio delle posizioni (la proposta principale)

Tutto descrittivo, calcolato dalla storia dello strumento; nessun consiglio.

- **Distanza dallo stop in ATR e in sedute tipiche**, per posizione: uno stop
  a 0,4 ATR e uno a 3 ATR oggi si leggono allo stesso modo.
- **Statistica di primo passaggio**: dato prezzo, stop e target, in quante
  finestre storiche dello strumento il prezzo ha toccato prima l'uno o
  l'altro entro N sedute, con il numero di finestre indipendenti e
  l'intervallo. È il calcolo fatto a mano per SOXL; il codice di base
  (`leggi_storico`, `app/stats/sizing`) esiste.
- **Esposizione aggregata**: per sottostante (SOXL e i semiconduttori in
  portafoglio sono la stessa scommessa), per settore, leva effettiva, e
  scenario «indice a −5%» col beta storico di ogni posizione.
- **Correlazione fra le posizioni**: una matrice a 60 sedute, con il numero
  di posizioni «effettive» dopo la correlazione, nello stesso spirito di
  `_effective_n` per le confluenze.
- **Costi di mantenimento**: l'endpoint `costi` c'è già; manca il conto di
  quanto costa tenere una posizione a leva per N settimane contro la distanza
  dal target.

### 5.2 Statistica storica a schermo

Lo strumento `storico` del server MCP risponde a domande sul passato, ma solo
dentro una sessione di Claude. Una pagina «Studio» con tre modelli fissi
copre la maggior parte dei casi senza chat:

- dopo un calo/rialzo di X% in N sedute, distribuzione a 5/21/63 sedute;
- stagionalità per mese e per giorno della settimana;
- comportamento attorno a un evento (trimestrali, dati macro).

Sempre con finestre indipendenti e confronto col caso base, secondo le regole
già scritte per il motore.

### 5.3 Notifiche centrate sulle posizioni

Telegram oggi manda il digest dei segnali, le chiusure eToro e i promemoria
delle trimestrali. Mancano le tre che contano per chi ha posizioni a leva:

- prezzo entro una soglia dallo stop (in ATR, non in percentuale);
- mossa anomala di un titolo in portafoglio (oltre 2 ATR in seduta);
- brief del mattino sulle posizioni: eventi di oggi, notizie della notte,
  distanza dagli stop. Sostituisce il digest «N alert nelle ultime 24 ore».

`live_movers_sweep` gira già ogni pochi minuti a mercato aperto: il controllo
si appoggia lì.

### 5.4 Assistente nell'app

Il server MCP ha già 11 strumenti in sola lettura. Un pannello «chiedi» che
usa l'API di Claude con gli stessi strumenti porta nell'app le domande che
oggi richiedono Claude Code sul PC, e funziona dal telefono. Usi concreti:
riassunto delle notizie di un titolo, spiegazione di una trimestrale,
confronto fra due titoli. Costi: una chiave API in più nel Secret, spesa a
consumo, e un confine da tenere (sola lettura, niente consigli
personalizzati). Da fare dopo 5.1 e 5.2, che gli danno gli strumenti utili.

### 5.5 Estensioni del server MCP

- `rischio_posizioni` e `primo_passaggio` (le stesse funzioni di 5.1);
- `screener` con i filtri della pagina Screener;
- `prestazioni_detector` riassunto: oggi rende 58.000 caratteri e supera il
  limite del client, quindi non è leggibile in una chiamata.

### 5.6 Dati nuovi

- **Fonte di prezzi di riserva.** yfinance è l'unica fonte per barre,
  quotazioni, fondamentali e opzioni, ed è alla versione minima 1.3.0.
  Finnhub è già configurato per le notizie: usarlo come ripiego per le
  quotazioni chiude il guasto singolo più probabile.
- **Insider e 13F come eventi sul titolo**, non solo come schede: «un fondo
  seguito ha aperto una posizione su un tuo preferito» è una notifica che i
  dati permettono già.

## 6. Il motore

### 6.1 Cosa dicono gli esiti dal vivo

Sei mesi di magazzino, 9.063 esiti: **tutti i 17 detector leggono «non
concludente»**, com'è giusto con 2-26 finestre indipendenti. Totale al netto
del mercato 50,7% (intervallo 19-82). Sui piani, attesa fra +0,13 R
(macd_divergence) e −0,21 R, tutti con intervalli che contengono lo zero.

Due cose però si vedono senza bisogno di significatività:

- **candle_reversal e gap_and_go non producono un'operazione**: 97% dei piani
  scade senza toccare né stop né target (2.289 su 2.360). È voluto (stop a 4
  ATR su 5 sedute), ma un piano che non si risolve mai non è un piano. O
  l'orizzonte si allunga, o per questi due il piano non si mostra.
- **squeeze_expansion ha un piano su un alert ogni quattro** (434 su 1.705):
  il tono «non determinato» non ha direzione. Coerente, ma a schermo il 75%
  dei suoi alert è senza piano e non lo dice.

### 6.2 I cancelli, visti dal registro degli scartati

Il registro nato a settembre ha 7.847 esiti maturati su 37 giorni di segnale.

| Gruppo | n | Colpi al netto del mercato | Eccesso medio |
|---|---:|---:|---:|
| Emessi nello stesso periodo | 1.708 | 46,3% | −1,47% |
| Scartati per sola Forza | 6.436 | 47,8% | −0,15% |
| Scartati per Forza e trend | 651 | 54,1% | +1,32% |
| Scartati per Forza e follow-through | 348 | 60,1% | +1,53% |

Per detector, fra gli scartati per Forza: hidden_divergence 66,9%,
macd_divergence 69,8%, rsi_divergence 67,6% (130-204 casi ciascuno).

⚠️ **Non è un risultato**: 37 giorni sono 7 finestre da 5 sedute e meno di 2
da 21, e le divergenze sono contrarian in un mese che è rimbalzato. Va nella
stessa direzione dello studio di settembre (la Forza non seleziona), e lo
dice dal vivo. Il momento per leggerlo è a 6 mesi di registro (marzo 2027),
con la stessa regola pre-registrata dei modelli in prova.

### 6.3 Modelli in prova

Volatilità: R² +0,19 e +0,22 contro l'ATR nei due addestramenti, stabile.
Selezione: AUC 0,61 entrambe le volte, ma il guadagno mensile è passato da
+0,02 a −0,05 (t −1,96). Come da criterio, non si legge prima di marzo.

**Il modello di volatilità è l'unico pezzo con evidenza ripetuta**, e ha un
uso che non richiede di prevedere la direzione: dimensionare stop e target
del piano e alimentare il rischio delle posizioni (§5.1) al posto dell'ATR.
È la sola promozione che i dati oggi sosterrebbero, e va comunque decisa col
criterio scritto il 24 settembre.

### 6.4 Punteggi

Qualità e Tecnico sono descrittori (studio score-IC: nessun pilastro
predittivo). Migliorie che non pretendono di predire:

- **Scomposizione della variazione**: la storia del composito è già nella
  scheda del punteggio; manca quale pilastro lo ha mosso a 30 e 90 giorni.
- **Confidenza**: già fatta a novembre; estenderla allo screener come filtro
  («solo titoli con dati completi»).

### 6.5 Cosa non fare

Non ritarare soglie, pesi o cancelli: sette studi e ora il registro dal vivo
dicono che non rende. Non aggiungere detector: ne esistono 17 e nessuno è
distinguibile dal caso.

## 7. Architettura

Il backend è 76.700 righe in 350 file, 111 endpoint, 33 modelli, 27 job; il
frontend 65.500 righe in 367 file. I test sono 57.800 e 18.500 righe. Il
rapporto test/codice è alto e i presidi sono molti; i punti deboli sono di
forma, non di qualità.

- **Web e lavori nello stesso processo.** Le 27 schedulazioni, le scansioni e
  l'addestramento dei modelli (60 minuti, 731 MiB) girano dentro il pod che
  serve le pagine. Ogni rilascio interrompe ciò che sta girando (da cui
  l'hook d'attesa di FA-109) e un job pesante toglie CPU alle richieste.
  Un secondo Deployment «worker» con la stessa immagine e lo scheduler acceso
  solo lì separa i due cicli di vita. È il cambiamento strutturale che
  semplifica di più il resto.
- **`services/` è metà del backend** (39.000 righe, 121 file) senza
  sottostruttura; `stock_fundamentals_service` ha 2.088 righe e fa fetch,
  normalizzazione, cache e calcolo. Dividere per dominio (prezzi,
  fondamentali, segnali, eToro, calendario, istituzionali) come è già stato
  fatto per `score_service/`.
- **Cache precalcolate come concetto unico.** Cinque endpoint lenti hanno la
  stessa cura (§4.5) e oggi ognuno ha la sua cache scritta a mano. Una
  tabella «viste materializzate» riempita a fine scansione, con un
  proprietario solo, le copre tutte.
- **Dipendenza da una fonte sola** (§5.6).
- **Un nodo, un disco.** Accettabile per un'app personale, a condizione che
  il backup funzioni: oggi non funziona (§2).
- **`api/types.ts` è a 1.669 righe scritte a mano**; il controllo generato
  (FA-111) intercetta le divergenze ma non toglie la doppia scrittura.
  Generare i tipi, non solo verificarli, è il passo successivo.

## 8. Priorità

Punteggio: (Impatto + Rischio) × (6 − Sforzo), ciascuno da 1 a 5.

| # | Voce | I | R | S | Punti |
|---:|---|:-:|:-:|:-:|---:|
| 0 | Applicare FA-129: backup e disco (§2) | 5 | 5 | 1 | **50** |
| 1 | Accesso fuori casa, Tailscale (§4.6) | 4 | 3 | 2 | **28** |
| 2 | Rischio delle posizioni (§5.1) | 5 | 1 | 3 | **18** |
| 3 | Precalcolo degli endpoint lenti (§4.5) | 3 | 1 | 2 | **16** |
| 4 | Segnali a partire dai miei titoli (§4.3) | 3 | 1 | 2 | **16** |
| 5 | Notifiche sulle posizioni (§5.3) | 4 | 1 | 3 | **15** |
| 6 | Dettaglio titolo: payload unico, richieste vuote (§4.1) | 3 | 1 | 3 | **12** |
| 7 | Storia del punteggio, reazione alle trimestrali (§4.1, §6.4) | 3 | 1 | 3 | **12** |
| 8 | Cruscotto riordinato sul portafoglio (§4.2) | 3 | 1 | 3 | **12** |
| 9 | Fonte di prezzi di riserva (§5.6) | 2 | 4 | 4 | **12** |
| 10 | Estensioni MCP (§5.5) | 2 | 1 | 2 | **12** |
| 11 | Piani di candle_reversal e gap_and_go (§6.1) | 2 | 1 | 2 | **12** |
| 12 | Statistica storica a schermo (§5.2) | 4 | 1 | 4 | **10** |
| 13 | Worker separato (§7) | 2 | 3 | 4 | **10** |
| 14 | Assistente nell'app (§5.4) | 3 | 2 | 4 | **10** |
| — | Disegni, prezzi-obiettivo, posizioni manuali, Settori | — | — | — | decisione |

## 9. Percorso proposto

**Subito.** Voce 0. Tutto il resto non ha senso su un database che si ferma
fra tre giorni e non ha un backup.

**Fase 1 — l'app che si usa davvero (1-2 settimane).** Voci 1, 3, 4, 6: stesso
prodotto, più veloce, raggiungibile dal telefono, con i segnali dove servono.

**Fase 2 — il portafoglio (2-3 settimane).** Voci 2, 5, 8, 10: rischio delle
posizioni a schermo, nelle notifiche e nel server MCP. È il salto di
capability che l'uso misurato chiede.

**Fase 3 — la ricerca (a scelta).** Voci 7, 11, 12, 14: storia dei punteggi,
statistica storica, assistente.

**Fase 4 — struttura.** Voci 9, 13 e la divisione di `services/`.

**In calendario, senza lavoro:** marzo 2027, lettura dei modelli in prova e
del registro degli scartati col criterio già scritto.
