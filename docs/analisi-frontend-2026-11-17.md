# Analisi del frontend — 2026-11-17

Lista dei miglioramenti possibili su grafica, tipografia, UI/UX, interazioni,
struttura delle pagine e organizzazione degli spazi, desktop e telefono.

**273 voci** in quattro rapporti di dettaglio, ognuna con Dove (file:riga) ·
Problema · Perché conta · Proposta · Impatto · Sforzo:

| Rapporto | Ambito | Voci |
|---|---|---|
| [B — Sistema di design](analisi-frontend-parziali/B-sistema-di-design.md) | tipografia, colore, spaziatura, superfici, componenti, icone, movimento, grafici, tema scuro, stati | 76 |
| [C — Pagine](analisi-frontend-parziali/C-pagine-home-titoli-mercati.md) | dashboard, screener, dettaglio titolo, mercati e settori, guscio | 71 |
| [D — Pagine](analisi-frontend-parziali/D-pagine-segnali-posizioni-resto.md) | segnali, posizioni, diagnostica, calendario e macro, superinvestor, studio, login, 404 | 91 |
| [E — Accessibilità, telefono, prestazioni](analisi-frontend-parziali/E-accessibilita-mobile-prestazioni.md) | a11y, uso a 375 px, prestazioni percepite | 35 |

## Come leggerla, e i suoi limiti

- **Metodo:** lettura del codice di `frontend/src`, con conteggi da script sulle
  sorgenti. **Niente è stato misurato a schermo**: le posizioni in pixel
  («il grafico parte a ~1.700 px») sono ricavate dalle classi.
- **L'analisi dal vivo nel browser non è stata fatta**: copre solo `/login`
  ([A](analisi-frontend-parziali/A-dal-vivo.md)). Resa reale, tema scuro a
  schermo e comportamento su un telefono vero restano da guardare.
- **Verifica:** i rilievi segnati ✔ sono stati ricontrollati sul codice e
  reggono. Le altre voci non sono state ricontrollate una per una: un
  riferimento di riga può essere scivolato.
- **Due voci del rapporto D sono superate** e rettificate in fondo al file:
  D-02 (i pannelli di efficacia non sono più duplicati in Diagnostica) e D-27
  (il bottone si chiama «Traccia trade»).

## Il quadro in sei punti

1. **I primitivi esistono e vengono aggirati.** 159 `<button>` a mano contro 50
   `<Button>`, 49 pastiglie a mano contro un `Badge` usato in 2 file, 34 tabelle
   a mano, una dozzina di controlli segmentati ricostruiti (B-39, B-41, B-43,
   B-44). È la causa di quasi tutta l'incoerenza visiva: 19 gradini tipografici
   fra 9,5 e 15 px, 63 ricette di etichetta maiuscola, 59 anelli di focus
   (B-01, B-04, B-38).
2. **Il contenuto principale sta sotto la piega.** Il grafico è l'ottava sezione
   del dettaglio titolo (C-39 ✔), la lista dei segnali comincia dopo le
   statistiche e le confluenze (D-01), sulla dashboard i segnali non sono più
   in alto (C-01).
3. **Il telefono è servito a metà.** Navigazione solo da menu a tendina (C-68,
   E-16), bottoni da 34-38 px (E-19), campi sotto 16 px che fanno zoomare iOS
   (E-20), `100vh` invece di `dvh` (E-17 ✔), tabelle di Segnali e Posizioni
   senza colonna fissa (E-22, D-35), calendario a sette colonne da ~50 px (D-61).
4. **Filtri e comandi che non dicono il vero.** «Reset» di Segnali porta a
   «Tutti i titoli» invece che al predefinito (D-03 ✔), la ricerca dello
   screener non è un filtro (C-29), tre filtri senza chip (D-04), `confirm()`
   nativo per chiudere una posizione (D-34), «Pulisci» e «Stop» senza conferma.
5. **Il tema scuro non è sorvegliato.** Nessun gate gira in scuro, e lì
   `--primary` è un verde (`141 76% 48%` ✔) che si confonde col «su»; assi e
   griglie dei grafici sono scritti per il fondo chiaro (B-66, B-67, B-12).
6. **Lessico e orientamento.** Lo stesso concetto ha quattro nomi (Regola /
   Tipo segnale / Condizione / Detector, D-05), italiano e inglese mescolati,
   `1m` = mese e `5m` = minuti (C-43), i dettagli di titolo, mercato e settore
   senza un titolo di scheda proprio (C-65), otto pagine senza `h1` sotto
   1024 px (E-01, B-05).

## Le prime 15 priorità

Ordine per resa: impatto sull'uso quotidiano contro sforzo.

| # | Intervento | Voci | Sforzo |
|---|---|---|---|
| 1 | Blocchi di CSS globale: campi a 16 px su touch, `:focus-visible` unico, `prefers-reduced-motion`, `color-scheme`; `h-dvh` nel guscio e nei dialoghi | E-20, E-17, B-48, B-55, B-68 | S |
| 2 | Dopo il login tornare alla pagina di partenza (oggi sempre `/` ✔) | D-89 | S |
| 3 | Filtri di Segnali coerenti: Reset torna al predefinito, conteggio sul differenziale, chip mancanti, via il chip doppio | D-03, D-04 | S |
| 4 | Grafico del titolo subito sotto l'intestazione | C-39 | M |
| 5 | Barra di navigazione inferiore su telefono, con aree sicure | C-68, E-16 | M |
| 6 | Un titolo per pagina: `h1`, `document.title` anche sui dettagli, focus al cambio rotta | C-65, E-01, E-02, B-05 | M |
| 7 | Segnali: lista prima, confluenze ed efficacia dopo o richiudibili | D-01 | M |
| 8 | Screener: 10 colonne di default con ticker fisso, ricerca dentro i filtri, viste salvate con nome attivo; filtri in un pannello su telefono | C-27, C-29, C-30, C-31 | M |
| 9 | Bersagli tattili a 44 px dove c'è un dito, più il rapporto nel gate | E-19 | M |
| 10 | Prima colonna fissa in Segnali e Posizioni su telefono; poi schede per riga | E-22, D-35 | S poi L |
| 11 | Numeri che non affermano più di quanto misurano: differenza dalla base senza intervallo (Studio), tassi del Diario su 4-9 casi, Forza colorata come un voto | D-84, D-43, D-08 | S |
| 12 | Tema scuro misurato: progetto Playwright in scuro, `--primary` non verde, grafici dal tema | B-66, B-67, B-12 | M |
| 13 | Dashboard riordinata: segnali in alto, un solo «chi si muove», un solo blocco «i miei titoli»; la parte personale non sparisce se il riepilogo di mercato fallisce | C-01, C-02, C-04, C-09 | M |
| 14 | Posizioni: due portafogli con nome, dialogo vero per chiudere/eliminare, Rischio con gli aggregati in cima | D-31, D-34, D-39 | M |
| 15 | `Button`, `Badge`, `Input`, `Segmentato` portati sull'uso reale e migrazione per cartella; scala tipografica a sei livelli | B-39…B-43, B-01, B-04 | L |

## Quick win (sforzo S)

- `vertTouchDrag: false` in `MarketChart` ✔: l'hanno già gli altri tre grafici (E-25).
- Tre correzioni che portano la linea di base axe da 23 a 10 nodi: `<span>` nel
  `<dl>` di `/sectors`, `aria-label` su sei `<select>`, wrapper scorrevole delle
  tabelle raggiungibile da tastiera (E-09, E-06, E-04).
- `aria-label` sui bottoni-icona con solo `title`; «Chiudi» al posto di «Close» (E-07).
- Dollaro scritto a mano sulla dashboard → `lib/money` con la valuta del titolo (C-20).
- Tre direzioni di mercato ancora in rosso; errori in quattro colori (B-11, B-16).
- Bordo dei campi più scuro di quello delle schede (B-35).
- Toast di scansione: le «regole» non esistono più; «Stop» chiede conferma (C-70).
- Colonna «Segnale» che contiene una data → «Comparso»; un nome solo per il tipo di segnale (D-06, D-05).
- Icona PWA vera al posto del logo del template Vite (E-26).
- Tema che segue il sistema alla prima apertura (E-28).
- Ricerca globale: o cerca i settori o smette di prometterlo (C-69).
- `.ambient-pulse` è CSS morto (B-59).

## Per area

### Grafica e tipografia (rapporto B)

- **Tipografia:** scala a sei livelli con pavimento a 11 px; tre ricette di
  etichetta al posto di 63 (B-01…B-10).
- **Colore:** un significato per colore, in due soli file come mappe letterali;
  oggi ogni famiglia ha 6-10 coppie chiaro/scuro (B-11…B-20).
- **Spazio:** un contenitore di pagina unico; tre pagine di dettaglio annidano
  il proprio padding dentro quello di `<main>`; il padding predefinito di `Card`
  non lo usa quasi nessuno (B-21…B-28).
- **Superfici:** scala dei raggi, tre livelli di rilievo, anello di focus a 2 px (B-29…B-38).
- **Icone e movimento:** `[&_svg]:size-4` nei `Button` ignora le misure dei
  figli; movimento ridotto rispettato da 3 componenti su 64 file (B-49…B-59).
- **Grafici:** il grafico annotato del segnale ha `viewBox` fisso e testo a 9 px
  che su telefono scende a ~4 px; `GraficoSvg` si legge solo col mouse (B-60, B-61).
- **Stati:** l'errore ha cinque forme, il vuoto 38 formulazioni, 268 «—»
  letterali contro 8 `NoValue` (B-72…B-76).

### Struttura delle pagine (rapporti C e D)

- **Dashboard:** C-01…C-26. **Screener:** C-27…C-38. **Dettaglio titolo:** C-39…C-54.
  **Mercati e settori:** C-55…C-64 (non esiste `/markets` ✔). **Guscio:** C-65…C-71.
- **Segnali:** D-01…D-30. **Posizioni:** D-31…D-47.
- **Diagnostica:** D-48…D-60. Il banner «Tutti i sistemi operativi» non guarda
  l'infrastruttura (D-48); stati di salute in emerald/rose invece di green/red
  (D-50); circa 30 spiegazioni in `title=` (D-51).
- **Calendario e macro:** D-61…D-71. **Superinvestor:** D-72…D-80.
  **Studio:** D-81…D-87. **Login e 404:** D-88…D-91.

### Accessibilità, telefono, prestazioni (rapporto E)

- **Accessibilità:** E-01…E-15. axe gira solo sul desktop; `/positions` è a zero
  perché il seme non ha posizioni, non perché è sana (E-15).
- **Telefono:** E-16…E-29.
- **Prestazioni:** E-30…E-35. Il peso del bundle è a posto (~203 KB gzip sulla
  home, 16 rotte in `React.lazy`). Da fare: un solo pool di quotazioni sulla home
  (oggi cinque chiavi, prezzi diversi per lo stesso ticker, E-31), precaricamento
  delle rotte (E-30), pausa del nastro (E-33), potatura della cache del service
  worker (E-27).

## Cosa resta da fare sull'analisi

- Passata dal vivo a 1440 e 375 px, chiaro e scuro, per confermare le stime in
  pixel e trovare ciò che il codice non mostra.
- Prova su un iPhone vero per E-18, E-21, E-26, E-31.
