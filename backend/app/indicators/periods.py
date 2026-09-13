"""I periodi canonici degli indicatori. Fonte unica, e IMPORTABILE.

Don't adapt these per timeframe — the user explicitly wants the same indicator
definition applied across timeframes so KPI values change naturally with bar
duration. RSI(14) su barre da 30m copre 7 ore; su barre giornaliere, 14 sedute.

May 2026: switched from SMA to EMA for the trend lines. Period numbers
(20/50/200) preserved — EMA just weights recent bars more heavily, so the same
window length produces a more responsive line.

⚠️ PERCHE' QUESTO MODULO ESISTE, ed e' una lezione sulla collocazione.

Queste costanti stavano in `app/services/timeframe_service.py`, che CLAUDE.md
dichiarava «fonte unica». Non lo erano: QUATTRO punti cablavano 200 a mano —
`signal_outcome_service._REGIME_EMA`, `market_detail_service`,
`market_stats_service` e `signals/context.py` — e il quarto spiega tutti gli
altri. `context.py` e' calcolo puro (numpy, pandas, `app.indicators`);
importare `timeframe_service` significherebbe trascinarsi dentro SQLAlchemy, i
modelli e loguru per leggere il numero 200.

Cioe' la costante NON ERA IMPORTABILE da chi ne aveva bisogno, quindi nessuno
la importava, quindi ognuno la riscriveva. Il difetto non era disattenzione:
era la collocazione. Una fonte unica che nessuno puo' consumare e' una fonte
unica solo nel commento — la stessa forma del `_RANGE_PERIODS` morto, dove una
tabella inerte corroborava una nota sbagliata.

Un modulo FOGLIA, senza una sola dipendenza, e' importabile da ogni livello.
`timeframe_service` le ri-esporta, cosi' chi scriveva
`from app.services.timeframe_service import FIXED_EMA_SLOW` continua a
funzionare.
"""

from __future__ import annotations

FIXED_RSI_PERIOD = 14
FIXED_BB_PERIOD = 20
FIXED_BB_K = 2.0
FIXED_EMA_FAST = 20
FIXED_EMA_MID = 50
FIXED_EMA_SLOW = 200
FIXED_MACD_FAST = 12
FIXED_MACD_SLOW = 26
FIXED_MACD_SIGNAL = 9
