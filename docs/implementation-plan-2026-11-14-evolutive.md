# Piano di implementazione — evolutive 2026-11

Mette in ordine tutte le voci di `docs/analisi-evolutiva-2026-11-13.md` e le
proposte sui motori di segnali ed esiti del 2026-11-13. Trentuno voci in sette
filoni, da FA-133 a FA-163, più FA-129 che è già aperta.

## Come leggere il piano

Ogni voce ha: cosa cambia, i file toccati, i test che la tengono chiusa, come
si verifica in produzione. Le regole che valgono per tutte:

- un commit per voce, push su `cloud`, verifica sul pod (immagine, `GIT_SHA`,
  stringa nel bundle) prima di chiuderla nel backlog;
- ogni test nuovo va visto fallire con la correzione tolta;
- niente soglie, pesi o cancelli del motore toccati senza uno studio fuori
  campione: le voci del filone C e D **misurano**, non decidono;
- ciò che è «in ombra» non ha consumatori a schermo finché il criterio scritto
  nella voce non è soddisfatto;
- le migrazioni si provano su Postgres (corsia M7), andata e ritorno.

Stime in giorni di lavoro di una sessione; sono ordini di grandezza.

## Ordine di esecuzione

| Fase | Voci | Perché in quest'ordine |
|---|---|---|
| 0 | FA-129 | il database si ferma fra pochi giorni |
| 1 | FA-138, 139, 140, 150 | substrato che accumula dati: ogni giorno di ritardo è un giorno non misurabile |
| 2 | FA-133, 134, 135, 136, 163 | l'app che si usa: accesso, velocità, segnali dove servono |
| 3 | FA-143, 144, 145, 146, 147, 148 | rischio delle posizioni, la capability principale |
| 4 | FA-141, 142, 151, 152, 153 | resto dei motori |
| 5 | FA-137, 149, 154, 155, 156 | ricerca sul titolo e cruscotto |
| 6 | FA-157, 158, 159, 160, 161 | struttura e assistente |
| — | FA-162 | decisione dell'utente, nessun lavoro finché non c'è |

La fase 1 viene prima del prodotto di proposito: FA-138, 139 e 150 scrivono
dati che non si ricostruiscono all'indietro (o solo in parte), e la lettura di
marzo 2027 dipende da quanti mesi avranno accumulato.

---

## Filone 0 — Blocco

### FA-129 · Backup e disco (già aperta, BLOCKED)

Non è lavoro nuovo: la correzione è in `infra/terraform/storage.tf`. Serve
l'utente perché crea una policy IAM e cancella versioni di oggetti.

1. `terraform plan`: deve dire 2 da aggiungere, 0 da distruggere.
2. `terraform apply`; entro 24-48 ore OCI esegue la lifecycle rule.
3. Chiusura: un backup base riuscito, `ContinuousArchiving=True`, `pg_wal`
   che scende da 51 GB, drill del lunedì verde, ArgoCD non più Degraded.

Se il disco arriva sotto 4 GB liberi prima che la regola agisca, la mossa
d'emergenza è svuotare a mano le versioni non correnti del bucket dalla
console OCI. Anche quella è dell'utente.

---

## Filone A — Accesso e prestazioni

### FA-133 · Accesso fuori casa (1 g)

Tailscale sul nodo al posto dell'allowlist IP per 443 e 6443.

- `infra/terraform/cloud-init/k3s.yaml`: installazione e `tailscale up` con
  chiave d'autenticazione letta da un file fuori da git.
- `infra/terraform/vcn.tf`: le regole `https_ingress` e `api_ingress` restano
  ma con `allowlist_cidrs` vuota; SSH resta com'è come porta d'emergenza.
- Certificato: il nome `sslip.io` punta all'IP pubblico. Due strade: nome
  MagicDNS con certificato Tailscale, oppure tenere il nome attuale e
  risolverlo sull'IP della tailnet. Si sceglie alla prima prova.
- `mcp/finance_alert_mcp.py`: `URL` di default sul nome nuovo.
- CLAUDE.md: la sezione «L'app non si apre da casa» diventa storia.

L'utente deve creare l'account Tailscale e installare il client su PC e
telefono. Verifica: app aperta dal telefono in rete mobile; 443 chiusa
dall'esterno (`curl` da una rete qualunque scade).

### FA-134 · Viste precalcolate per gli endpoint lenti (2 g)

Una tabella `viste_precalcolate (chiave, payload, calcolata_il, versione)` e
un proprietario unico, `app/services/viste_service.py`, con `leggi(chiave,
calcola)` e `rigenera(chiavi)`.

- Consumatori: `/api/institutionals/aggregate` (6,3 s), `/api/dashboard/summary`
  (2,1 s), `/api/scores/top`, `/api/dashboard/analyst-actions`,
  `/api/calendar` per mese, `/api/etoro/andamento`.
- Rigenerazione: a fine scansione in `scan_runner` (dopo le maturazioni),
  dopo `refresh_institutionals` e dopo `sincronizza_etoro`. Mai dentro la
  richiesta, tranne al primo avvio a tabella vuota.
- `/api/markets/{symbol}/detail` (2,4 s) ha una causa diversa: scarica la
  storia a ogni apertura. Cache L2 in `fetch_cache` con scadenza a fine seduta.
- Test: la vista si rigenera quando cambia l'ingresso; una vista assente
  calcola e salva; il payload servito è identico a quello calcolato al volo.
- Verifica: `latenza_per_vita.py` sui sei endpoint prima e dopo, non
  `increase()`.

### FA-135 · Dettaglio titolo: primo schermo in un payload (2 g)

- `GET /api/stocks/{ticker}/primo-schermo`: intestazione, quotazione nota,
  punteggi Qualità e Tecnico, barre del grafico all'intervallo richiesto.
  Compone servizi esistenti, nessun calcolo nuovo.
- Frontend: `useStockPrimoSchermo` semina la cache di react-query delle
  query singole (`setQueryData`), così le schede non cambiano.
- Disegni e prezzi-obiettivo: `enabled` solo quando lo strumento è aperto.
- Test: il payload aggregato coincide campo per campo con gli endpoint
  singoli; le due richieste vuote non partono al montaggio.
- Verifica: richieste al caricamento contate nel gate UI (da ~20 a ~10) e
  tetto CLS invariato.

### FA-136 · Segnali a partire dai miei titoli (1 g)

- `AlertsPage`: il filtro «solo i miei titoli» è il default; l'universo è la
  seconda scheda. Lo stato vive nell'URL come oggi.
- `EtoroPortafoglioCard` e `PreferitiStrip`: pastiglia coi segnali vivi sul
  titolo, che apre il dialogo del segnale.
- Le viste Esiti e In formazione passano in `/diagnostics?vista=motore`;
  `/alerts?vista=esiti|formazione` reindirizza.
- Test: default, reindirizzamenti, pastiglia assente senza segnali.

### FA-137 · Un solo motore di grafici (2 g)

Sette file usano recharts (chunk da 337 KB). Si portano su lightweight-charts
o su SVG scritto a mano dove il grafico è una barra o un istogramma; poi si
toglie la dipendenza.

⚠️ La rimozione da `package.json` è una scrittura npm: si fa con la ricetta
del lockfile a superset (CLAUDE.md), controllando che nessuna chiave
`node_modules/*` sparisca oltre a quelle di recharts.

---

## Filone B — Motore degli esiti

### FA-138 · Ogni segnale misurato a tutti gli orizzonti (2 g)

Oggi una riga di `signal_outcomes` ha l'orizzonte del suo detector. I detector
a 63 sedute hanno 2 finestre indipendenti; misurati anche a 5 ne avrebbero ~25.

- Realizzata come `esiti_orizzonti`, ancorata al giorno di emissione invece
  che a `signal_date`. Disegno iniziale: tabella `signal_outcomes_orizzonti (alert_id, horizon_days,
  fwd_return, universe_median, mkt_neutral_excess, mkt_neutral_hit,
  matured_at, method_version)`, unica su `(alert_id, horizon_days)`, per
  h ∈ {1, 5, 21, 63}. La tabella esistente non si tocca: resta la fonte
  dell'orizzonte proprio, con i suoi cinque consumatori.
- `signal_outcome_service.mature_outcomes_orizzonti`: stessa `_label`, stesso
  caricamento a finestra, idempotente, chiamata in `scan_runner` dopo
  `mature_outcomes`.
- Riempimento all'indietro: possibile per intero, perché `_label` legge solo
  barre. `app/scripts/backfill_orizzonti.py`, con il conteggio di parità: la
  riga all'orizzonte proprio deve coincidere con `signal_outcomes`.
- Cubo: `detector_performance_service` aggiunge per detector una riga per
  orizzonte, ognuna con le sue finestre indipendenti.
- UI (Diagnostica → Motore): la tabella mostra l'orizzonte proprio e, accanto,
  il migliore per numero di finestre, dichiarando quale.
- ⚠️ Quattro orizzonti per detector sono quattro confronti: la regola B dello
  studio condizionale vale qui. Il verdetto «concludente» si dà solo
  sull'orizzonte dichiarato prima; gli altri sono descrizione.
- Test: parità con la tabella esistente; un orizzonte non trascorso non
  scrive; il controllo negativo sulla mediana asimmetrica resta verde.

### FA-139 · Controllo casuale abbinato (2 g)

La mediana dell'universo non distingue «il segnale sbaglia» da «i titoli
volatili vanno diversamente». Nel terzo più volatile i rialzisti leggono 39%
di colpi e i ribassisti 48,8% con eccesso −2,46%.

- Per ogni esito, K=5 titoli di controllo: stesso giorno, stesso terzile di
  volatilità realizzata a 20 sedute (dalle chiusure, la stessa finestra di
  `vol20`; l'ATR avrebbe chiesto massimi e minimi di tutto l'universo per un
  ordinamento quasi identico), nessun alert dello stesso detector nei ±5
  giorni, scelti con un generatore seminato su `alert_id`.
- Colonne in `esiti_orizzonti`: `controllo` (MEDIANA dei cinque, non la
  media: con la mediana di un numero dispari l'ipotesi nulla vale 50% esatti
  per qualunque distribuzione), `eccesso_controllo`, `colpo_controllo`.
- Cubo e UI: «contro la mediana» e «contro il controllo» affiancati.
- Riempimento all'indietro possibile (solo barre).
- Test: stesso seme, stessi controlli; il titolo del segnale non è mai fra i
  suoi controlli; un terzile con meno di K candidati rende None, non un
  controllo più piccolo; su dati sintetici senza effetto il tasso è 50%.

### FA-140 · Medie per giorno accanto a quelle per riga (1 g)

Dieci giorni contengono 1.984 esiti su 9.212.

- `detector_performance_service`: per ogni cella, oltre al tasso per riga, il
  tasso a pesi uguali per giorno (media delle medie giornaliere) e il numero
  di giorni.
- UI: la seconda cifra accanto alla prima quando divergono di oltre 3 punti.
- Test: un giorno con 300 righe e trenta giorni con una riga ciascuno.

### FA-141 · Uscite alternative, in ombra (2 g)

322 stop su 2.238 erano passati da +1R; 808 scaduti su 5.021 anche.

- `plan_outcome_service.corri_la_gara` accetta una variante; tre varianti
  misurate oltre a quella di oggi: stop a pareggio dopo +1R, uscita a metà
  orizzonte se sotto +0,25R, stop a pareggio dopo +0,5R.
- Tabella `plan_outcomes_ombra (alert_id, variante, esito, r_multiple,
  bars_to_outcome, method_version)`.
- Rapporto: `python -m app.scripts.rapporto_uscite_ombra`, a finestre chiuse,
  con finestre indipendenti e il controllo casuale di FA-139 sulla stessa
  geometria.
- Criterio scritto prima, in `docs/superpowers/specs/`: una variante si
  adotta solo se batte l'attuale sul replay decennale fuori campione **e**
  dal vivo dopo sei mesi. Nessuna pastiglia a schermo prima.

### FA-142 · Costi eToro nel conto in R (1,5 g)

- `etoro_catalogo_service.costi` dà apertura e notte per ticker, lato, leva.
  Una tabella `costi_tipici (stock_id, lato, spread_pct, notte_pct,
  aggiornato_il)` riempita da un job settimanale sui titoli tradabili.
- `plan_performance_service`: `expectancy_r_netta` = R lordo − (spread +
  notti × barre) / distanza dello stop, a leva 1 e alla leva tipica del conto.
- UI Motore: colonna «netto» accanto al lordo; assente dove il titolo non è
  su eToro.
- Test: una posizione di 21 barre paga 21 notti più i fine settimana; il
  netto non supera mai il lordo.

---

## Filone C — Motore dei segnali

### FA-150 · Contesto d'emissione, versione 2 (1,5 g)

Variabili che oggi mancano e che non si ricostruiscono a posteriori con
fedeltà: vanno fissate da subito.

- `contesto_emissione.contesto` a `VERSIONE = "2"`, con:
  `giorni_a_trimestrale` e `giorni_da_trimestrale` (dalla cache dei
  fondamentali, senza rete), `beta_252` contro il rendimento mediano del
  catalogo (gli indici non sono nel database), `rs_settore_63` (rendimento a
  63 sedute meno la mediana del settore).
- Restano fuori, per la regola già scritta nel modulo, l'ampiezza del mercato
  e il numero di segnali del giorno: sono una per data e si ricostruiscono
  dal catalogo e dalla tabella degli alert.
- `signal_scan_service`: le fissa in `first_contesto` per gli alert e in
  `contesto` per gli scartati. Le variabili di mercato si calcolano una volta
  per scansione.
- Nessun riempimento all'indietro: beta e forza relativa si ricalcolano
  dalle barre quando uno studio ne ha bisogno, e le date delle trimestrali
  non si ricostruiscono fedelmente. Gli alert vecchi restano in versione 1.
- Test: nessuna chiamata di rete; una cache dei fondamentali vuota rende
  None e non solleva; la versione 1 resta leggibile.

### FA-151 · Segnali in conflitto (1 g)

199 coppie titolo-giorno hanno un alert rialzista e uno ribassista.

- Nessun cambiamento all'emissione: i due alert restano, perché il magazzino
  li misura separati.
- `alert_service`: campo derivato `in_conflitto_con` (id dell'alert di verso
  opposto, stesso titolo, emissione entro 1 giorno).
- UI: pastiglia «in conflitto» sulla riga e nel dialogo, con il collegamento
  all'altro; nel digest la coppia è una riga sola.
- Test: stesso verso non è conflitto; `undetermined` non entra.

### FA-152 · Giornate di mercato (1,5 g)

Un giorno con 348 segnali è il mercato visto 348 volte.

- `stats_service.giornate_di_mercato`: giorni in cui i segnali di un verso
  superano il 95° percentile mobile a 60 giorni.
- UI Segnali (scheda universo): quei giorni si chiudono in una riga
  «giornata di mercato: N segnali ribassisti», espandibile. I segnali sui
  miei titoli restano sempre visibili per riga.
- Digest e notifiche: stessa compressione.
- Test: la soglia è sul verso, non sul totale; un giorno sotto soglia non si
  comprime.

### FA-153 · Ipotesi sulla volatilità, sul replay (1,5 g)

L'unica ipotesi nuova che i dati dal vivo suggeriscono: i segnali sul terzo
più volatile rendono meno.

- Pre-registrazione in `docs/superpowers/specs/2026-11-ipotesi-volatilita.md`
  prima di guardare i dati: variabile (`atr_pct`, terzili a finestra
  espandibile), esito (eccesso contro il controllo casuale di FA-139),
  orizzonti, soglia (stesso segno su entrambi i gruppi disgiunti di titoli e
  su almeno 6 anni su 8, test a blocchi di tempo).
- Strumenti: `backend/scripts/studio_taratura/`, sul replay decennale.
- Esiti possibili: nulla → si scrive e si chiude; conferma → proposta di un
  cancello **in ombra** (registrato in `signal_candidates` come quarto esito
  `passa_volatilita`), adozione solo dopo sei mesi dal vivo.

### FA-154 · Piani che non si risolvono (0,5 g)

candle_reversal e gap_and_go: 97% dei piani scade senza stop né target.

- Decisione dell'utente fra due strade, entrambe senza toccare la soglia:
  (a) nessun piano per questi due, con la frase «orizzonte troppo breve per
  un piano»; (b) piano a 21 sedute, dichiarato diverso dall'orizzonte del
  segnale. Proposta: (a), perché (b) inventa una geometria che il detector
  non sostiene.
- `trade_plan.costruisci_piano` e il gemello `tradePlaybook.ts`, coi vettori
  d'oro aggiornati; `PLAN_METHOD_VERSION` a "5" e rimisura.
- **squeeze_expansion**: 1.271 alert su 1.705 non hanno un piano perché il
  tono è «non determinato», e lo schermo non lo dice. Nel dialogo e nella
  riga, al posto del piano vuoto: «nessun piano: il verso non è ancora
  determinato». Nel pannello Motore la copertura (`with_plan` su `alerts`)
  compare accanto all'attesa, perché una media su un quarto degli alert non
  descrive il detector.
- Test: un alert `undetermined` rende la frase e non un piano; la copertura
  è nel payload.

### FA-155 · Modello di volatilità per stop e target (2 g, vincolata)

Vincolata al criterio del 24 settembre: non prima di marzo 2027 e solo se la
lettura dal vivo conferma R² > 0 contro l'ATR.

- Preparazione che si può fare subito: `rapporto_modelli_ombra` aggiunge la
  geometria che il piano AVREBBE avuto con la volatilità del modello, e la
  misura in ombra accanto alle varianti di FA-141.
- Adozione, se il criterio passa: `ingressi_del_piano` legge
  `first_ombra.volatilita` con l'ATR come ripiego; nuova versione del metodo.

---

## Filone D — Portafoglio

### FA-143 · Servizio di rischio delle posizioni (3 g)

`app/services/rischio_posizioni_service.py`, calcolo puro sulle barre.

- **Distanza dallo stop**: in ATR(14) e in «sedute tipiche» (distanza /
  mediana del range giornaliero).
- **Primo passaggio**: `primo_passaggio(barre, lato, stop_pct, target_pct,
  orizzonte)` scorre la storia dello strumento con finestre non sovrapposte e
  conta stop prima, target prima, nessuno dei due. Rende i tre conteggi, le
  finestre indipendenti e l'intervallo di Wilson. Stessa convenzione di
  `corri_la_gara` sulle barre ambigue (stop prima).
- **Esposizione**: per sottostante (mappa dei fondi a leva sul loro indice:
  SOXL → SOX ×3), per settore, leva effettiva.
- **Scenario**: beta a 252 sedute di ogni posizione contro Nasdaq 100 e
  S&P 500; P/L stimato a −5% e −10%, con la leva. Dichiarato come stima
  lineare, non come previsione.
- **Correlazione**: matrice a 60 sedute e numero di posizioni effettive.
- `GET /api/etoro/rischio`, in cache fino alla prossima sincronizzazione.
- Test: su una serie sintetica a passeggiata casuale simmetrica il primo
  passaggio con stop e target equidistanti dà ~50/50; uno stop a zero
  distanza non divide per zero; uno strumento con meno di 252 barre rende
  «storia insufficiente» e non un numero.

### FA-144 · Pagina Posizioni: scheda Rischio (2 g)

- `PositionsPage`: schede «Portafoglio / Rischio / Diario».
- Rischio: tabella per posizione (distanza in ATR, primo passaggio come barra
  a tre segmenti col numero di finestre), riquadro esposizione per
  sottostante, scenario, matrice di correlazione sotto `sm` come elenco delle
  coppie più correlate.
- Testo fisso in testa: statistica storica dello strumento, non una
  previsione né un consiglio.
- Test, axe, gate UI a 375 px; tetto CLS con scheletro della stessa altezza.

### FA-145 · Costo di mantenimento (1 g)

- Nella scheda Rischio: notti pagate finora e costo previsto a 1, 4 e 12
  settimane contro la distanza dal target, da `etoro_catalogo_service.costi`
  con i parametri veri della posizione.
- Test: una posizione senza leva non paga notti.

### FA-146 · Notifiche sulle posizioni (2 g)

- `live_movers_sweep`: a ogni giro, per le posizioni aperte, due controlli.
  Stop vicino: prezzo entro 1 ATR dallo stop. Mossa anomala: variazione di
  seduta oltre 2 ATR.
- `notifier_service.notify_posizione`: una notifica per posizione e per tipo
  al giorno, registrata in `novita_notificate`.
- Impostazioni nel chart: `telegram.posizioni.stopAtr`, `mossaAtr`, spente di
  default e accese in `values-oci.yaml`.
- Test: la seconda notifica dello stesso giorno non parte; a mercato chiuso
  nessun controllo; una posizione senza stop salta il primo controllo.

### FA-147 · Brief del mattino (1,5 g)

- `notifier_service.build_brief`: conto (valore, P/L aperto), poi per
  posizione distanza dallo stop, trimestrale entro 7 giorni, notizie della
  notte; poi gli eventi macro di oggi; in fondo i segnali sui miei titoli.
- Sostituisce il digest delle 08:00; il conteggio «N alert nelle ultime 24
  ore» esce.
- Test: senza posizioni il brief cade sul formato segnali di oggi.

### FA-148 · Fondi e insider come eventi sui miei titoli (1 g)

- Dopo `refresh_sec_13f` e l'aggiornamento insider: se un fondo seguito ha
  aperto, chiuso o variato oltre il 25% una posizione su un titolo in
  portafoglio o fra i preferiti, una riga in `novita_notificate` e nel brief.
- Test: una variazione sul numero di azioni dovuta a uno split non conta.

---

## Filone E — Ricerca sul titolo e cruscotto

### FA-149 · Cruscotto ordinato sul portafoglio (1,5 g)

- `HomePage`: conto, «Sui tuoi titoli» (trimestrali vicine, azioni degli
  analisti, movers, notizie filtrati su posizioni e preferiti), poi mercato.
- `AnalystActionsCard` e `TopMoversCard` prendono un interruttore «miei /
  tutti», default miei.
- Le schede che FA-162 decide di togliere escono qui.
- Altezze riservate per restare sotto il tetto CLS.

### FA-156 · Dettaglio titolo: pari, trimestrali, note, variazione del punteggio (3 g)

- **Confronto con i pari**: `GET /api/stocks/{ticker}/pari`, sei titoli della
  stessa industria più vicini per capitalizzazione in USD, con Qualità,
  Tecnico, P/E, crescita, rendimento a 3 mesi. Scheda `PariCard`.
- **Reazione alle trimestrali**: `GET /api/stocks/{ticker}/reazioni-trimestrali`,
  per ogni trimestrale nota movimento della seduta successiva e a 5 sedute,
  con la sorpresa. Dentro `FundamentalsCard`, accanto alla prossima data.
  Usa `earnings_session_timing` per scegliere la barra giusta.
- **Note**: tabella `note_titolo (stock_id, testo, creata_il, aggiornata_il)`,
  `GET/PUT /api/stocks/{ticker}/nota`, campo nell'intestazione. Il token MCP
  resta in sola lettura.
- **Variazione del punteggio**: la storia è già a schermo in `StockScoreCard`.
  Si aggiunge quale pilastro ha mosso il composito negli ultimi 30 e 90
  giorni, da `score_history`.
- **Confidenza nello screener**: filtro «dati completi» su
  `completezzaFondamentali`.

### FA-157 · Pagina Studio: statistica storica a schermo (3 g)

- `app/services/studio_service.py`, tre modelli: dopo una variazione di X% in
  N sedute; stagionalità per mese e giorno della settimana; attorno a un
  evento (trimestrali del titolo, rilasci macro).
- Ogni risposta porta casi, finestre indipendenti, intervallo e il caso base
  (tutte le finestre della stessa lunghezza).
- `GET /api/studio/{modello}`; pagina `/studio` con simbolo, modello e
  parametri nell'URL; raggiungibile dal dettaglio titolo.
- Test: una serie costante rende zero casi e non una media.

---

## Filone F — Dati, MCP, assistente

### FA-158 · Fonte di riserva per le quotazioni (2 g)

- `live_quote_service`: quando la corsia delle quotazioni di
  `yfinance_health` è aperta, il prezzo viene da Finnhub (`/quote`), marcato
  con la fonte. Solo titoli USA, che è ciò che il piano gratuito copre.
- Aggiornamento di yfinance alla versione corrente, in un commit a parte, con
  la suite intera e una scansione di prova.
- Test: breaker aperto → Finnhub; entrambe giù → ultimo valore L2 marcato
  `STALE`, come oggi.

### FA-159 · Estensioni del server MCP (1 g)

- `rischio_posizioni()` e `primo_passaggio(simbolo, lato, stop, target,
  sedute)` sugli endpoint di FA-143.
- `screener(filtri)` su `/api/stocks`.
- `studio(modello, simbolo, …)` su FA-157.
- `prestazioni_detector` riassunto: una riga per detector, con il dettaglio
  su richiesta (`detector=`); oggi rende 58.000 caratteri.
- Test nello stile di `test_finance_alert_mcp.py`; tutti gli strumenti nuovi
  in sola lettura.

### FA-160 · Assistente nell'app (4 g)

Dopo FA-143, 157 e 159, che gli danno gli strumenti.

- Backend: `POST /api/assistente` in streaming; ciclo di tool-use dell'API di
  Claude con gli stessi strumenti del server MCP, chiamati in-process.
  Chiave `ANTHROPIC_API_KEY` nel Secret, `optional` nel chart; senza chiave
  l'endpoint risponde «non configurato» e il pannello non compare.
- Confini nel prompt di sistema e nel codice: sola lettura, nessun consiglio
  personalizzato, ogni numero con la sua fonte.
- Tetto di spesa: limite di turni per conversazione e di richieste al giorno,
  contati in una tabella.
- Frontend: pannello laterale richiamabile da ogni pagina, col titolo
  corrente come contesto.
- Dipende da una decisione dell'utente sulla spesa a consumo.

---

## Filone G — Struttura

### FA-161 · Worker separato (3 g)

- `settings.ruolo` ∈ {`web`, `worker`, `tutto`} (default `tutto`, così locale
  e test non cambiano). Lo scheduler e i recuperi all'avvio partono solo con
  `worker` o `tutto`.
- Chart: un Deployment `worker` con la stessa immagine e `RUOLO=worker`; lo
  StatefulSet passa a `web`. Il volume `data` resta al web; il worker non ne
  ha bisogno dopo il passaggio a Postgres (da verificare sui log su disco).
- Le scansioni avviate dall'utente passano dal web al worker con una riga in
  `scan_runs` in stato `richiesta`, che il worker raccoglie; lo stato SSE
  legge il database, non la memoria del processo.
- L'hook PreSync di FA-109 guarda il worker.
- ⚠️ I contatori in memoria (`data_source_metrics`) vivono nel processo che
  fa le chiamate: la pagina Piattaforma deve leggerli dal worker o da
  Prometheus. È il punto che decide se la voce vale 3 giorni o 6.

### Divisione di `services/` e tipi generati (senza numero, opportunistica)

Non una voce a sé: ogni filone sposta i file che tocca in un sottopacchetto
di dominio (`services/etoro/`, `services/esiti/`, `services/prezzi/`) con
ri-esportazione dal vecchio percorso, e i modelli nuovi del frontend nascono
da `schema.gen.ts` invece che in `types.ts`.

### FA-163 · Catalogo del FTSE MIB fermo (0,5 g)

`FinanceAlertCatalogRefreshFailing` è attivo dal 6 novembre: tre sabati di
rinnovo falliti. Stessa forma del Dow Jones di settembre.

- Leggere `catalog_refresh_log` e il log del job per la causa (tabella
  sorgente cambiata o irraggiungibile dal pod).
- Correggere il parser o la fonte in `catalog_refresh`; il blocco
  anti-svuotamento resta com'è.
- Test su una copia salvata della pagina sorgente, così il prossimo cambio
  di formato rompe un test e non il sabato.
- Verifica: rinnovo riuscito a mano dal pod e allarme rientrato.

---

## Decisione dell'utente

### FA-162 · Funzioni non usate

Zero righe in archivio o zero aperture in 30 giorni: disegni sul grafico,
prezzi-obiettivo, posizioni manuali, pagina Settori, istogramma RSI e top
picks del cruscotto. Per ognuna: tenere, nascondere dietro un'impostazione, o
togliere. Togliere le posizioni manuali cancella codice e non dati (la
tabella è vuota).

---

## Cosa serve dall'utente

| Voce | Cosa |
|---|---|
| FA-129 | applicare Terraform (IAM e lifecycle) |
| FA-133 | account Tailscale e client su PC e telefono |
| FA-154 | scelta fra (a) e (b) |
| FA-160 | chiave API e tetto di spesa |
| FA-162 | tenere, nascondere o togliere, funzione per funzione |

## In calendario

- **Marzo 2027**: lettura di modelli in prova, registro degli scartati,
  orizzonti multipli (FA-138), controllo casuale (FA-139) e uscite in ombra
  (FA-141), ognuna col criterio scritto nella sua voce.
- **Settembre 2027**: prima lettura utile del contesto versione 2 (FA-150) e
  dell'archivio non-prezzo.

## Totale

Circa 53 giorni di lavoro: fase 1 sei e mezzo, fase 2 sei e mezzo, fase 3 dieci e mezzo,
fase 4 sette e mezzo, fase 5 nove, fase 6 tredici.

---

## Stato dopo le fasi 1 e 2 (2026-11-14)

Le misure fatte prima di implementare hanno cambiato tre voci; restano qui
perché il piano dica cosa si è deciso e perché.

- **FA-134**: la cache precalcolata NON è stata costruita. A riposo, misurati
  nel pod, gli endpoint «lenti» rispondono in 0,03-0,4 s; le medie di 2 s in
  Prometheus vengono da concorrenza, scansioni e cache fredde. Unico caso vero
  il dettaglio mercato giornaliero (15 MB, 5,6 s): ora porta dieci anni.
- **FA-135**: l'endpoint aggregato NON è stato fatto. Il dettaglio titolo è
  già compresso e arrotondato (0,6-1 s); l'aggregato toglierebbe solo round
  trip su HTTP/2.
- **FA-136**: Esiti e In formazione restano nella pagina Segnali. Spostarli in
  Diagnostica era una proposta fatta sulle sole aperture; sono le tappe dello
  stesso episodio, e la scelta di tenerle insieme era documentata.
- **FA-164 (nuova)**: la prova di parità di FA-138 ha trovato che il 90% delle
  mediane conservate in `signal_outcomes` non si riproduce dai dati di oggi.
- **FA-133** resta in attesa dell'utente (account Tailscale e client).
- **Decisioni dell'utente del 2026-11-14:** FA-154 fatta con la variante (b),
  piano medio a 21 sedute per tutti; FA-162 chiusa tenendo tutte le funzioni;
  FA-133 e FA-160 escluse per ora.
- **Fase 3 (2026-11-14):** fatta. Differenze dal piano: la scheda Rischio e'
  una scheda sotto il conto, non una scheda di pagina; la soglia dello stop
  vicino e' 0,5 ATR (a 1 suonava ogni giorno); gli avvisi stanno nella
  sincronizzazione eToro invece che nello sweep; FA-148 esisteva gia' per
  insider e analisti, e si e' aggiunta la regola sui fondi. Nuova FA-165: il
  segmentation fault in CI dei thread d'avvio.
