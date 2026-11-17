# Analisi del frontend e piano — 2026-11-17

Lista dei miglioramenti possibili su grafica, tipografia, UI/UX, interazioni,
struttura delle pagine e organizzazione degli spazi, dal telefono al 4K, e il
piano con cui affrontarli.

**328 voci** in cinque rapporti di dettaglio, ognuna con Dove · Problema ·
Perché conta · Proposta · Impatto · Sforzo:

| Rapporto | Ambito | Metodo | Voci |
|---|---|---|---|
| [A — Dal vivo](analisi-frontend-parziali/A-dal-vivo.md) | 14 rotte a sei risoluzioni, in locale e in produzione coi dati veri; tema scuro e grafici a candele | browser | 55 |
| [B — Sistema di design](analisi-frontend-parziali/B-sistema-di-design.md) | tipografia, colore, spaziatura, superfici, componenti, icone, movimento, grafici, tema scuro, stati | codice | 76 |
| [C — Pagine](analisi-frontend-parziali/C-pagine-home-titoli-mercati.md) | dashboard, screener, dettaglio titolo, mercati e settori, guscio | codice | 71 |
| [D — Pagine](analisi-frontend-parziali/D-pagine-segnali-posizioni-resto.md) | segnali, posizioni, diagnostica, calendario e macro, superinvestor, studio, login, 404 | codice | 91 |
| [E — Accessibilità, telefono, prestazioni](analisi-frontend-parziali/E-accessibilita-mobile-prestazioni.md) | a11y, uso a 375px, prestazioni percepite | codice | 35 |

## Come leggerla

- **B, C, D, E vengono dalla lettura del codice**; **A dal browser**, due volte:
  su un backend locale con una copia migrata del database, poi **sulla produzione
  con i dati veri**. Risoluzioni: 375×812 (preset telefono), 768×1024, 1440×900,
  1920×1080, 2560×1440, 3840×2160; tema scuro a 1440, compresi i grafici a candele
  con i colori letti dai pixel. I numeri di questo documento sono quelli di produzione.
- **La passata dal vivo ha confermato le voci principali dei rapporti dal codice**
  e ne ha corretto due stime: il grafico del titolo a 375px parte a 6.616px, non
  ~3.900 (C-39); i campi che fanno zoomare iOS sono 1-4 per pagina, non ~20 (E-20).
- **L'unico limite rimasto è strumentale**: il preset telefono è Chrome che emula
  un telefono, non Safari su iOS. Zoom dei campi, barra del browser su `100vh`,
  aree sicure e icona PWA (E-17, E-20, E-26) e il grafico tagliato a 600px (A-40,
  visto una volta in locale, mai in produzione) si confermano solo da un iPhone.
- **Due voci del rapporto D sono superate**: D-02 e D-27, rettificate in fondo al file.

## Il quadro in sette punti

1. **Il contenuto principale sta sotto la piega, misurato in produzione.** Il
   grafico del titolo è nella prima schermata solo a 3840px; a 1440 parte a 2.151px
   su 900, a 375 a 6.838px (A-36). La tabella dei segnali parte a 1.335px a 1440 e a
   2.923px su telefono (A-37). Il dettaglio di un settore è lungo 32.958px su
   telefono, 40 schermate (A-38). Sotto la dashboard ci sono 8.000px di pagina
   vuota, causati da 185 etichette nascoste che escono da una lista (A-50).
2. **La dashboard aspetta la chiamata più lenta.** Tutta la pagina resta a scheletro
   finché non risponde il conto eToro (~15s in locale) e, se le API falliscono, lo
   scheletro non finisce mai, senza messaggio (A-05, A-06). Numeri e ticker
   troncati a una lettera nelle tessere degli indici e nella classifica (A-09,
   A-10, A-27).
3. **I componenti di base esistono e vengono aggirati.** 159 `<button>` a mano
   contro 50 `<Button>`, 49 pastiglie a mano, 34 tabelle a mano (B-39, B-41, B-44);
   19 gradini tipografici fra 9,5 e 15px, scritti in px e quindi fermi quando il
   resto cresce col corpo radice (B-01, A-42).
4. **Il telefono è servito a metà.** Menu solo a tendina (C-68), 221 bersagli su 225
   sotto 44px sulla dashboard (A-44), calendario con chip a tre pallini senza nome
   (A-46), due sbordi stabili su Macro e Settore (A-39).
5. **Lo schermo grande non è usato.** Da 1920px il corpo radice resta 19px e le pagine
   non hanno larghezza massima: a 4K la tabella dei segnali stende 11 colonne su
   3.500px (A-41).
6. **Comandi e numeri che non dicono il vero.** «Reset» di Segnali porta a «Tutti i
   titoli» (D-03), dopo il login si torna sempre alla home (D-89), `confirm()`
   nativo per chiudere una posizione (D-34), differenze e tassi senza campione
   (D-84, D-43).
7. **Tema scuro e lessico.** In scuro gli assi dei grafici a candele stanno a 1,7:1
   sul fondo (A-51), le candele usano il rosso dei guasti (A-52) e la selezione è il
   verde del rialzo (B-67, A-47);
   lo stesso concetto ha quattro nomi (D-05), italiano e inglese mescolati (A-17),
   otto pagine su quattordici senza titolo (A-43).

## Il piano

Sei fasi, in ordine. Ognuna è un'unità di lavoro con il suo commit e un criterio
di chiusura **misurabile con la stessa sonda della passata dal vivo**, così la
chiusura non dipende da un'impressione. Le voci elencate sono quelle da leggere
nei rapporti prima di cominciare.

### Fase 0 — Correzioni piccole (FA-171) · sforzo S · una sessione

| Intervento | Voci |
|---|---|
| CSS globale: campi a 16px su touch, `:focus-visible` unico, `prefers-reduced-motion`, `color-scheme`; `h-dvh` nel guscio e nei dialoghi | E-20, A-45, E-17, B-48, B-55, B-68 |
| Dopo il login, ritorno alla pagina di partenza | D-89 |
| Filtri di Segnali: Reset al predefinito, conteggio sul differenziale, chip mancanti, via il chip doppio | D-03, D-04 |
| I due sbordi a 375px: gruppo «Livello/Sul periodo/Sull'anno» di Macro, tabella del dettaglio settore | A-39 |
| Dettaglio settore: prime 20 aziende e «mostra tutte» | A-38 |
| Numeri e ticker interi nelle tessere degli indici, nella classifica qualità e nei top picks | A-09, A-10, A-11, A-27 |
| 8.000px di pagina vuota sotto la dashboard: `relative` sulle liste che scorrono con etichette `sr-only`, e un test di regola | A-50 |
| `vertTouchDrag: false` in `MarketChart` | E-25 |
| Linea di base axe da 23 a 10: `<span>` nel `<dl>` di `/sectors`, `aria-label` sui `<select>`, wrapper delle tabelle raggiungibile da tastiera | E-09, E-06, E-04 |
| Bottoni-icona con nome; «Chiudi» al posto di «Close» | E-07 |
| Dollaro scritto a mano → `lib/money` con la valuta del titolo | C-20 |
| Toast di scansione senza «regole» e con conferma su «Stop»; conferma su «Pulisci» del grafico | C-70, C-44 |
| Icona PWA vera; tema che segue il sistema alla prima apertura | E-26, E-28 |

**Chiusura:** zero sbordi a 375-3840 su tutte le 14 rotte; dashboard alta quanto
il suo contenuto (oggi 12.116px per 4.072 di schede a 1440); dettaglio settore sotto
5.000px a 375; linea di base axe stretta dopo due corse concordi di CI.

### Fase 1 — Le pagine principali mostrano prima ciò per cui esistono (FA-172) · M

| Intervento | Voci |
|---|---|
| Grafico del titolo subito sotto un'intestazione più bassa, senza l'area colorata alta 350px | C-39, A-36, A-48 |
| Segnali: lista prima; confluenze vuote ridotte a una riga; efficacia dopo o richiudibile | D-01, A-37 |
| Dashboard: ogni scheda esce dallo scheletro con la propria query, errore visibile con «Riprova»; segnali in alto; un solo «chi si muove», un solo «i miei titoli» | A-05, A-06, A-07, C-01, C-02, C-04, C-09, A-26 |
| Un titolo per pagina: `h1`, titolo della scheda del browser anche sui dettagli, focus al cambio rotta | C-65, E-01, E-02, A-43 |

**Chiusura:** grafico del titolo entro 900px a 1440 ed entro 1.700px a 375 (oggi
2.151 e 6.838); tabella dei segnali entro 900px a 1440 (oggi 1.335); dashboard
leggibile in meno di 1s con il conto
eToro ancora in caricamento; `h1` su 14 rotte su 14.

### Fase 2 — Telefono (FA-173) · M, il calendario L

| Intervento | Voci |
|---|---|
| Barra di navigazione inferiore (Dashboard · Screener · Segnali · Posizioni · Altro), con aree sicure | C-68, E-16 |
| Bersagli a 44px dove c'è un dito (`pointer: coarse`), rapporto nel gate accanto ai 24px | E-19, A-44, A-34 |
| Prima colonna fissa in Segnali e Posizioni; poi schede per riga | E-22, D-35, A-29 |
| Calendario: agenda della settimana sotto `lg` (a 768 oggi 115 testi troncati), giorno aperto in un foglio | D-61, D-62, A-46, A-55 |
| Filtri dello screener in un pannello con «Mostra N titoli» | C-31 |
| Grafici SVG: larghezza iniziale reale, mai 600px | A-40 |
| axe anche sul progetto telefono, posizioni nel seme | E-15 |

**Chiusura:** bersagli sotto 44px sotto il 10% per rotta a 375; nessun chip del
calendario senza nome; axe verde sul progetto telefono.

### Fase 3 — Sistema di design (FA-174) · L, a ondate per cartella

| Intervento | Voci |
|---|---|
| Colori di significato in due soli file (`lib/toni.ts`, `lib/coloriGrafico.ts`), mappe letterali | B-11…B-20 |
| Scala tipografica a sei livelli in rem, pavimento 11px, tre ricette di etichetta | B-01…B-10, A-42, A-24 |
| `Button`, `Badge`, `Input`, `Segmentato`, `Table` portati sull'uso reale; migrazione per cartella | B-39…B-47, B-43, B-44 |
| Superfici: raggi, rilievo, bordi, anello di focus a 2px | B-29…B-38 |
| Stati: `QueryError` a tre varianti, `StatoVuoto`, `NoValue` con `InfoHint` | B-72…B-76, A-13, A-14 |
| Schermi larghi: larghezza massima per le pagine a tabella e a testo, terzo gradino del corpo radice | A-41, B-21, B-22 |
| Grafici leggibili: testo del grafico del segnale a pixel veri, `GraficoSvg` con tastiera | B-60, B-61 |

**Chiusura:** nessun testo sotto 11px a nessuna risoluzione; `<button>` a mano sotto
20; a 3840 nessuna tabella più larga della larghezza massima.

### Fase 4 — Tema scuro misurato (FA-175) · M

| Intervento | Voci |
|---|---|
| `--primary` scuro distinto dal verde «su» | B-67, A-47 |
| Progetto Playwright in scuro su tre rotte, con linea di base propria | B-66 |
| Assi, griglie e candele dei grafici dal tema: assi oggi a 1,7:1 in scuro, candele in red-600 | B-12, B-62…B-65, A-51, A-52 |
| Un solo cartellino di prezzo sulla scala, i valori delle medie in legenda | A-53 |

**Chiusura:** gate scuro verde; contrasto AA dei toni calcolato anche sulle varianti
scure; testo degli assi dei grafici sopra 4,5:1 in entrambi i temi, misurato sui pixel.

### Fase 5 — Pagine e lessico (FA-176) · M per pagina

| Pagina | Voci |
|---|---|
| Screener: 10 colonne di default con ticker fisso, ricerca dentro i filtri, viste salvate con nome | C-27, C-29, C-30, C-33 |
| Posizioni: due portafogli con nome, dialogo vero per chiudere/eliminare, Rischio con gli aggregati in cima | D-31, D-34, D-36, D-37, D-39 |
| Diagnostica: banner che guarda anche l'infrastruttura, palette dei guasti, spiegazioni in `InfoHint` | D-48, D-50, D-51, D-54 |
| Macro: livello e consenso separati, colonne del consenso anche su telefono | D-69 |
| Studio: esempi d'ingresso, intervallo accanto alla differenza, colori solo dove l'effetto esce dal caso | D-81, D-84, D-85 |
| Superinvestor: ricerca dei fondi in cima | D-72 |
| Mercati: pagina `/markets` e sezioni Mercati/Settori nella ricerca globale | C-55, C-69 |
| Ritorno allo screener con la ricerca di partenza | C-42 |
| Lessico: un nome per il tipo di segnale, «Comparso» per la data, timeframe non ambigui, italiano ovunque, un formato numerico | D-05, D-06, C-43, A-16, A-17 |
| Numeri senza campione: Diario eToro, Forza colorata come un voto | D-43, D-08 |
| Tablet a due colonne per dashboard e dettaglio titolo | A-49 |

**Chiusura:** per pagina, i criteri delle voci.

## Da verificare a parte, non di interfaccia

- **Diagnostica mostra errori in produzione** (A-54): «In errore», «Conteggio non
  disponibile», «Catalogo non disponibile». È un guasto o un ripiego del backend da
  indagare, non una voce del piano frontend.

## Fuori dal piano, deliberatamente

- **Prestazioni del bundle:** a posto (~203 KB gzip sulla home, 16 rotte separate).
  Il pool unico di quotazioni della home (E-31) va misurato prima dal pannello rete
  e dal RUM, poi deciso.
- **Scorrimento del documento invece di `<main>` sotto `lg`** (E-18): da provare su
  un iPhone vero; cambia il presidio dei traboccamenti scritto in CLAUDE.md.
- Le voci a impatto basso non citate sopra restano nei rapporti, da prendere quando
  si lavora sulla pagina che toccano.
