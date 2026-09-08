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

Formato: CSV con header, colonne di ohlcv_daily (stock_id,date,open,high,low,
close,volume). Attenzione: `stock_id` e' quello del DB di PRODUZIONE, non del
DB locale di sviluppo.

Per rimetterle (solo se si stabilisce che il troncamento era sbagliato):
  \copy ohlcv_daily FROM '<file>' WITH CSV HEADER

Contesto e criteri della decisione: CLAUDE.md, sezione "Unrepaired splits
inside the stored history".
