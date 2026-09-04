Righe OHLCV eliminate da `repair_price_basis --truncate` in PRODUZIONE il
2026-09-03. Questa e' l'unica copia: la fonte (yfinance) riproduce la rottura
di basis, quindi un refetch NON le ricostruisce corrette.

  SOXS  2444 righe  fino al 2026-05-22  (rottura 2026-05-26)
  KDP    548 righe  fino al 2018-07-09  (rottura 2018-07-10)
  ARWR   129 righe  fino al 2016-11-29  (rottura 2016-11-30)

Formato: CSV con header, colonne di ohlcv_daily (stock_id,date,open,high,low,
close,volume). Attenzione: `stock_id` e' quello del DB di PRODUZIONE, non del
DB locale di sviluppo.

Per rimetterle (solo se si stabilisce che il troncamento era sbagliato):
  \copy ohlcv_daily FROM '<file>' WITH CSV HEADER

Contesto e criteri della decisione: CLAUDE.md, sezione "Unrepaired splits
inside the stored history".
