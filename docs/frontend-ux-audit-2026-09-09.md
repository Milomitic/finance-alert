# Finance Alert — audit e roadmap frontend/UI/UX

Data: 2026-09-09  
Questo documento trasforma l'audit esplorativo in 72 interventi tracciabili. Le voci sono proposte: diventano lavoro eseguibile quando entrano nel backlog con criterio di accettazione e test.

## Tranche 1 — navigazione e orientamento (P0/P1)

| ID | Intervento | Risultato atteso |
|---|---|---|
| UX-001 | Breadcrumb su dettaglio titolo/settore/mercato | L'utente torna al contesto con un solo gesto |
| UX-002 | Stato pagina attivo nella navbar | La sezione corrente è sempre riconoscibile |
| UX-003 | Command palette globale | Apertura rapida di pagine, ticker e azioni |
| UX-004 | Shortcuts documentate | Le azioni frequenti sono scopribili |
| UX-005 | Deep link per ogni pannello principale | Un link riapre lo stesso contesto |
| UX-006 | Persistenza filtri per sezione | Cambio pagina non azzera il lavoro |
| UX-007 | 404 con suggerimenti contestuali | Un URL errato porta a una destinazione utile |
| UX-008 | Stati loading uniformi | Nessun salto di layout tra caricamento e dati |
| UX-009 | Stati vuoti con azione primaria | L'utente sa come ottenere il primo risultato |
| UX-010 | Error boundary per route | Un widget rotto non oscura tutta l'app |
| UX-011 | Toast con link alla risorsa | Un errore recuperabile diventa azione |
| UX-012 | Indicatore dati aggiornati | Età e fonte dei dati sono leggibili |

## Tranche 2 — ricerca, filtri e tabelle (P1)

| ID | Intervento | Risultato atteso |
|---|---|---|
| UX-013 | Ricerca con debounce configurabile | Meno richieste e risposta più stabile |
| UX-014 | Evidenziazione match nei risultati | Il motivo del risultato è immediato |
| UX-015 | Recenti e preferiti nella ricerca | Ritorno rapido ai titoli usati |
| UX-016 | Filtri salvabili come viste | Un set di filtri è riutilizzabile |
| UX-017 | Preset “apertura”, “rischio”, “liquidità” | Accesso a casi d'uso frequenti |
| UX-018 | Conteggio risultati per filtro | L'utente capisce l'impatto di una scelta |
| UX-019 | Rimozione filtri con chip | Reset granulare senza riaprire pannelli |
| UX-020 | Tabelle con colonne persistenti | La configurazione sopravvive alla sessione |
| UX-021 | Ordinamento multi-colonna | Confronti più precisi |
| UX-022 | Paginazione o virtualizzazione | Liste grandi restano fluide |
| UX-023 | Export CSV con filtri applicati | L'export corrisponde alla vista |
| UX-024 | Copia link riga/titolo | Condivisione del contesto senza spiegazioni |

## Tranche 3 — dashboard e segnali (P1)

| ID | Intervento | Risultato atteso |
|---|---|---|
| UX-025 | Layout dashboard personalizzabile | Ogni utente mette in primo piano i KPI |
| UX-026 | Riordino card con drag and drop accessibile | Personalizzazione anche da tastiera |
| UX-027 | Preset dashboard salvabili | Passaggio rapido tra analisi diverse |
| UX-028 | Drill-down KPI | Dal numero si arriva al dettaglio filtrato |
| UX-029 | Spiegazione del punteggio | Il segnale è interpretabile |
| UX-030 | Confronto segnale vs storico | La decisione ha un riferimento temporale |
| UX-031 | Timeline eventi con raggruppamento | Meno rumore nelle giornate affollate |
| UX-032 | Badge severità coerenti | Priorità leggibile a colpo d'occhio |
| UX-033 | Acknowledge/mute alert | Gli alert già valutati non disturbano |
| UX-034 | Azioni bulk sugli alert | Gestione rapida di più risultati |
| UX-035 | Stato “dati parziali” esplicito | Nessuna falsa certezza quando manca una fonte |
| UX-036 | Glossario inline | Termini finanziari comprensibili senza uscire |

## Tranche 4 — grafici e analisi (P1/P2)

| ID | Intervento | Risultato atteso |
|---|---|---|
| UX-037 | Preset timeframe persistenti | Il grafico riapre nell'orizzonte scelto |
| UX-038 | Crosshair sincronizzato tra pannelli | Una data è confrontabile su tutti i grafici |
| UX-039 | Zoom/reset sempre visibili | Recupero rapido dopo esplorazione |
| UX-040 | Legenda con unità e valuta | Nessuna ambiguità sui numeri |
| UX-041 | Tooltip accessibile da tastiera | I dati non dipendono solo dal puntatore |
| UX-042 | Download immagine/CSV del grafico | Risultati riutilizzabili fuori dall'app |
| UX-043 | Overlays per earnings/dividendi | Il contesto fondamentale è sul prezzo |
| UX-044 | Confronto benchmark | Performance relativa più immediata |
| UX-045 | Soglie configurabili per indicatori | Analisi adattabile al metodo dell'utente |
| UX-046 | Preset indicatori per strategia | Setup ripetibili con meno clic |
| UX-047 | Messaggio dati insufficienti | Il grafico non appare “vuoto” senza spiegazione |
| UX-048 | Riduzione animazioni rispettosa di prefers-reduced-motion | Comfort e prevedibilità migliorati |

## Tranche 5 — accessibilità, mobile e resilienza (P0/P1)

| ID | Intervento | Risultato atteso |
|---|---|---|
| UX-049 | Audit axe automatizzato in CI | Regressioni WCAG intercettate prima del deploy |
| UX-050 | Focus order documentato | Navigazione tastiera coerente |
| UX-051 | Annunci aria-live per aggiornamenti | Cambi dati percepibili da screen reader |
| UX-052 | Contrasto verificato per temi | Testo leggibile in ogni modalità |
| UX-053 | Target touch minimo 44px | Azioni affidabili su telefono |
| UX-054 | Tabelle responsive con vista card | Informazioni fruibili su schermi stretti |
| UX-055 | Drawer con focus restore | Chiusura senza perdere il punto di lavoro |
| UX-056 | Offline/read-only snapshot | L'utente vede l'ultimo dato utile durante un errore rete |
| UX-057 | Retry per singolo pannello | Recupero senza ricaricare la pagina |
| UX-058 | Timeout e cancellazione richieste | Navigazione senza aggiornamenti tardivi |
| UX-059 | Web Vitals p75 per device | Performance percepita misurabile |
| UX-060 | Budget bundle per route | Crescita del frontend sotto controllo |

## Tranche 6 — personalizzazione e operatività (P2)

| ID | Intervento | Risultato atteso |
|---|---|---|
| UX-061 | Watchlist ordinabile | Monitoraggio costruito sull'ordine dell'utente |
| UX-062 | Note e tag sui titoli | Memoria operativa vicino al dato |
| UX-063 | Price alert con valuta nativa | Soglie coerenti con il mercato |
| UX-064 | Canali notifica configurabili | Ogni alert raggiunge il canale scelto |
| UX-065 | Digest giornaliero | Riduzione del rumore durante la giornata |
| UX-066 | Quiet hours | Nessuna notifica in finestre definite |
| UX-067 | Registro modifiche | Azioni sensibili ricostruibili |
| UX-068 | Import/export impostazioni | Trasferimento semplice tra ambienti |
| UX-069 | Pagina stato fonti dati | Diagnosi trasparente di provider degradati |
| UX-070 | Centro preferenze privacy | Controllo esplicito su RUM e storage |
| UX-071 | Help contestuale per errori API | Diagnosi comprensibile senza log tecnici |
| UX-072 | Tour iniziale ignorabile e ripetibile | Le capability principali sono scopribili |

## Criteri comuni

Ogni voce deve avere: criterio di accettazione osservabile, test unit/component o browser quando serve, telemetria dell'azione critica e verifica responsive. Le voci che cambiano dati finanziari richiedono anche controllo di valuta, timestamp e fonte.
