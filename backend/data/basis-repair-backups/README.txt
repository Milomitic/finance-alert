Righe OHLCV eliminate da `repair_price_basis --truncate` in PRODUZIONE il
2026-09-03. Questa e' l'unica copia: la fonte (yfinance) riproduce la rottura
di basis, quindi un refetch NON le ricostruisce corrette.

  SOXS  2444 righe  fino al 2026-05-22  (rottura 2026-05-26)
  KDP    548 righe  fino al 2018-07-09  (rottura 2018-07-10)
  ARWR   129 righe  fino al 2016-11-29  (rottura 2016-11-30)

Aggiunto il 2026-09-08 da `repair_bar_quality --truncate-to-clean`, che e' un
criterio DIVERSO: non una rottura di basis, ma barre mai scambiate.

  INDV  1765 righe  fino al 2023-06-01  (coda pulita dal 2023-06-02)

INDV non aveva tre barre corrotte come sembrava dalle sue due rotture opposte
del novembre 2022: aveva 562 barre a volume zero e il 61% di OHLC collassato
(o=h=l=c) su tutto il periodo 2016-2023, contro lo 0% dal giugno 2023 in poi.
Indivior ha spostato la quotazione primaria sul Nasdaq: prima era una linea
secondaria dove il prezzo veniva RIPORTATO, non osservato. Restano 818 barre,
sopra la soglia di 200 di `has_full_data`.

Anche qui il refetch non ricostruisce nulla: la fonte riproduce quelle barre.

Il 2026-09-08, stessa modalita', altri 13 titoli — 8132 righe. La scansione di
catalogo (possibile solo dopo aver costruito `repair_bar_quality`) ha trovato
267 titoli con 9216 barre mai scambiate; questi 13 sono quelli il cui prefisso
e' un ALTRO REGIME DI DATI, non un danno sparso.

  SW      2055 righe  fino al 2024-07-07   (nascita di Smurfit Westrock)
  FER     2012 righe  fino al 2024-05-02   (Ferrovial sposta la primaria)
  FERG    1152 righe  fino al 2021-03-07
  EDV.L    851 righe  fino al 2021-06-13   (Endeavour approda al LSE)
  AMCR     779 righe  fino al 2019-06-10   (quotazione NYSE dopo Bemis)
  KEEL     314 righe  fino al 2020-11-11
  ASTS     262 righe  fino al 2020-11-15   (guscio SPAC prima della fusione)
  HIMS     227 righe  fino al 2020-08-06   (guscio SPAC)
  AVIO.MI  202 righe  fino al 2017-02-14
  CMPX     148 righe  fino al 2021-11-01
  DKNG      93 righe  fino al 2019-12-04   (guscio SPAC)
  PR        35 righe  fino al 2016-07-18
  ONTO       2 righe  fino al 2019-10-29

Le date di taglio cadono su eventi societari reali — quotazioni, fusioni,
gusci SPAC — che e' il controllo di plausibilita' fatto PRIMA di applicare:
lo strumento non stava pescando a caso, stava trovando storie di entita'
precedenti. Ogni conteggio combacia con la previsione dello strumento e con
il CSV esportato prima della cancellazione. Tutti restano sopra le 200 barre
(il piu' corto e' SW con 544).

RESTANO 254 titoli con 4151 barre mai scambiate, tutti a danno SPARSO
(`--drop-untraded`), NON applicato. Sono festivita' di borsa locali che
yfinance riempie col prezzo riportato: DB1.DE e MUV2.DE hanno la lista di
date IDENTICA (60 barre, incluso il 3 ottobre tedesco), quindi e' il
calendario di Francoforte e non i titoli. BMPS.MI si addensa sulla chiusura
d'anno milanese.

Formato: CSV con header, colonne di ohlcv_daily (stock_id,date,open,high,low,
close,volume). Attenzione: `stock_id` e' quello del DB di PRODUZIONE, non del
DB locale di sviluppo.

Per rimetterle (solo se si stabilisce che il troncamento era sbagliato):
  \copy ohlcv_daily FROM '<file>' WITH CSV HEADER

Contesto e criteri della decisione: CLAUDE.md, sezione "Unrepaired splits
inside the stored history".
