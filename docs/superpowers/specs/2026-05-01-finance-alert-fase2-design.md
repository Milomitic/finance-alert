# Finance Alert — Fase 2 Design (Alert Engine)

**Data**: 2026-05-01
**Stato**: Approvato in brainstorming, in attesa review utente
**Scope**: Solo Fase 2. Fase 3 (dashboard, charts, regole AND/OR, indicatori MACD/BB/volume) elencata in fondo per contesto.

---

## 1. Obiettivo della Fase 2

Trasformare l'app da "watchlist viewer" (Fase 1) ad "alert engine globale":

1. **Espandere il catalogo** a ~700 ticker unici: S&P 500 + NASDAQ-100 + DJIA (US, già seedati) + EuroStoxx 50 (top 50 EU per cap) + SSE 50 (top 50 Shanghai) + Hang Seng top 30 (HK) + FTSE MIB (già seedato).
2. **Recuperare quotidianamente** dati OHLCV per **tutti gli stock del catalogo** (non solo quelli in watchlist).
3. Calcolare indicatori tecnici (SMA, EMA, RSI) sui prezzi.
4. Valutare 4 regole **globali pre-installate** (RSI oversold/overbought, Golden/Death Cross 50/200) edge-triggered su tutto l'universo, con override opzionale per watchlist.
5. **Inviare un digest Telegram giornaliero** (08:00 Europe/Rome) con riepilogo degli alert delle ultime 24h. Modalità `stream` e `watchlist_only` previste in Fase 3.
6. Permettere all'utente di consultare lo storico alert via UI con filtri, mark-as-read, archive ed export CSV.

**Modello rules a 3 tier**:
- **Tier 1 — Regole globali**: 4 regole pre-installate con `watchlist_id = NULL`, applicate a tutti i ticker dell'universo. Modificabili via API (toggle, params).
- **Tier 2 — Override per watchlist (opt-in)**: per ogni `(watchlist, kind)` puoi creare una row che disabilita la regola globale per quella watchlist (`enabled=false`) o la sostituisce con params custom (`enabled=true, params={...}`).
- **Tier 3 — Override per singolo stock**: rinviato a Fase 3 (richiede Stock Detail page).

**La Fase 2 NON include**: editor visuale di regole con AND/OR, MACD/BB/volume/breakout, timeframe sub-daily, email/webhook notifications, modalità Telegram `stream` o `watchlist_only`, override per singolo stock, backtest hit rate, candlestick chart pages. Quelli sono Fase 3 / post-MVP.

## 2. Vincoli e principi guida

- **Continuità con Fase 1**: stesso stack (FastAPI + SQLAlchemy + APScheduler + SQLite + React + shadcn). Niente nuovi servizi a runtime.
- **Edge-triggering**: alert sparato una sola volta sulla transizione, non ad ogni scan finché la condizione resta vera. Riduce drasticamente il volume di notifiche.
- **Universo = catalogo intero**: lo scan giornaliero copre tutti i ticker seedati nel catalogo (~700), non solo quelli in watchlist. Le watchlist diventano un meccanismo di organizzazione e di override regole.
- **Tier 1 sempre attivo**: le 4 regole globali sono pre-installate al bootstrap con `enabled=True`; per disattivarne una a livello globale serve `PATCH /api/rules/{id}`.
- **Tier 2 opt-in**: la WatchlistDetailPage espone un editor regole-override con tre stati per ogni kind: "usa default globale", "disattiva per questa WL", "sostituisci con params custom".
- **Telegram via `.env`**: zero UI per setup; `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` in `.env`, README spiega la procedura BotFather.
- **Telegram delivery = digest** in Fase 2: un singolo messaggio riepilogativo giornaliero alle 08:00 Europe/Rome. La env var `TELEGRAM_DELIVERY_MODE` esiste ma accetta solo `digest` in Fase 2; `stream` e `watchlist_only` sono Fase 3.
- **Soglie standard**: RSI 30/70 con periodo 14, Cross 50/200. Modificabili via API per chi vuole sperimentare; nessuna UI per parametri in Fase 2 a livello globale (sì a livello override per watchlist).
- **Lingua**: codice/identifier inglese; testi UI italiano hard-coded; messaggi Telegram italiano.

## 3. Cosa è esplicitamente fuori scope per Fase 2

| Funzionalità | Fase prevista |
|---|---|
| Editor regole UI con AND/OR composizione | Fase 3 |
| Indicatori MACD, Bollinger Bands, ATR, ADX | Fase 3 |
| Regole volume spike, breakout su N-day high/low | Fase 3 |
| Timeframe 1h, 15m | Fase 3 |
| Email notifier, webhook generico | Post-MVP |
| **Modalità Telegram `stream` (1 messaggio per alert)** | Fase 3 |
| **Modalità Telegram `watchlist_only` (push solo per stock in WL)** | Fase 3 |
| **Override regole per singolo stock (Tier 3)** | Fase 3 |
| **UI per modificare params regole globali** | Fase 3 (Settings page) |
| Backtest hit rate / statistiche per regola | Fase 3 |
| Stock Detail page con candlestick + overlay indicatori | Fase 3 |
| Settings page (oggi tutto via .env) | Fase 3 |

**In scope Fase 2**: catalog espanso a ~700 ticker (US + EU + CN + HK + IT), scan daily 23:30 Europe/Rome su tutto l'universo, edge-triggered alerts, **digest Telegram giornaliero 08:00 Europe/Rome**, full Alerts page (filtri multi-campo, paginazione, mark-read, archive, export CSV), badge unread sidebar, **editor override regole per watchlist** (3 stati per kind).

## 4. Architettura tecnica

### 4.1 Stack additions

| Layer | Aggiunta | Versione |
|---|---|---|
| Data fetch | `yfinance` | ≥0.2 |
| Numeric | `numpy` (transitive da pandas, ma esplicitiamo) | ≥1.26 |
| HTTP client (notifier) | `httpx` (già installato) | usa l'esistente |

Nessuna dipendenza nuova frontend (riusiamo shadcn/Tailwind/TanStack Query/React Hook Form).

### 4.2 Topologia esecuzione

```
┌──────────────────────────────────────────────┐
│ uvicorn :8000                                │
│ FastAPI                                      │
│ ├── /api/* (auth, stocks, watchlists,        │
│ │            catalog, rules, alerts) → router│
│ └── /*     → StaticFiles(frontend/dist)      │
│ APScheduler                                  │
│ ├── refresh_catalog (weekly Sat 03:00)       │
│ ├── scan_alerts    (daily 23:30)  ← NUOVO    │
│ └── send_digest    (daily 08:00)  ← NUOVO    │
│ SQLite ./backend/data/app.db                 │
└──────────────────────────────────────────────┘
```

I due job Fase 2 sono indipendenti: `scan_alerts` produce alerts, li persiste, ma non manda Telegram individualmente; `send_digest` legge gli alerts dell'ultime 24h e invia un singolo messaggio Telegram riepilogativo. La separazione permette di cambiare modalità di delivery in Fase 3 (introducendo job o callback diversi) senza toccare lo scan.

## 5. Modello dati (4 nuove tabelle, no migrazioni Fase 1 alterate)

### 5.1 `ohlcv_daily` — bar giornaliero per stock

| Campo | Tipo | Note |
|---|---|---|
| stock_id | INTEGER FK → stocks.id ON DELETE CASCADE | PK composta |
| date | DATE NOT NULL | PK composta |
| open | NUMERIC(12,4) NOT NULL | |
| high | NUMERIC(12,4) NOT NULL | |
| low | NUMERIC(12,4) NOT NULL | |
| close | NUMERIC(12,4) NOT NULL | |
| volume | BIGINT NOT NULL | |

PK: `(stock_id, date)`. Indice secondario su `date` per query "tutti gli stock al giorno X".

### 5.2 `rules` — regola globale (Tier 1) o override per watchlist (Tier 2)

| Campo | Tipo | Note |
|---|---|---|
| id | INTEGER PK | |
| watchlist_id | INTEGER FK → watchlists.id ON DELETE CASCADE **NULLABLE** | NULL = regola globale (Tier 1); valorizzato = override per watchlist (Tier 2) |
| kind | TEXT NOT NULL | uno di: `rsi_oversold`, `rsi_overbought`, `golden_cross`, `death_cross` |
| params | TEXT NOT NULL | JSON serialized; default per-kind documentato in §6 |
| enabled | BOOLEAN NOT NULL DEFAULT TRUE | |
| created_at | TIMESTAMP server_default | |
| updated_at | TIMESTAMP server_default + onupdate | |

Vincolo unico: `(watchlist_id, kind)` con SQLite trattamento di NULL come "valore distinto" — quindi esattamente una global per kind (4 righe Tier 1 totali) e al massimo una override per (watchlist, kind).

**Risoluzione regola effettiva per (stock, kind)**:
1. Se lo stock è in almeno una watchlist con override Tier 2 per quel kind: usa l'override (può essere `enabled=false` per disattivare la regola per quello stock, o `enabled=true` con params custom).
2. Se più watchlist contengono lo stesso stock con override conflittuali: **vince il più restrittivo** — disabled override > enabled override > global. (Documentato in §7.4.)
3. Altrimenti: usa la regola globale Tier 1.

### 5.2.1 Bootstrap delle 4 regole globali

Al primo avvio (script `bootstrap.py`, vedi Fase 1), se nella tabella `rules` non esistono righe con `watchlist_id IS NULL`, vengono inserite le 4 regole globali con `enabled=True` e default params (vedi §6). Operazione idempotente — re-run non duplica.

### 5.3 `rule_states` — ultimo stato valutato per (rule, stock), per edge-triggering

| Campo | Tipo | Note |
|---|---|---|
| rule_id | INTEGER FK → rules.id ON DELETE CASCADE | PK composta |
| stock_id | INTEGER FK → stocks.id ON DELETE CASCADE | PK composta |
| last_evaluation | BOOLEAN NOT NULL | era la condizione vera all'ultimo scan? |
| last_evaluated_at | TIMESTAMP NOT NULL | |

Servono per detectare la transizione: alert sparato solo se `previous_evaluation == False AND new_evaluation == True`. Tabella bounded: 1 riga per (rule, stock); non cresce nel tempo.

### 5.4 `alerts` — evento sparato

| Campo | Tipo | Note |
|---|---|---|
| id | INTEGER PK | |
| rule_id | INTEGER FK → rules.id ON DELETE CASCADE | |
| stock_id | INTEGER FK → stocks.id ON DELETE CASCADE | |
| triggered_at | TIMESTAMP NOT NULL server_default | |
| trigger_price | NUMERIC(12,4) NOT NULL | close del bar che ha scattato |
| snapshot | TEXT NOT NULL | JSON con valori indicatori al trigger (es. `{"rsi":28.4,"sma50":180.5,"sma200":175.2}`) per debug e UI dettaglio |
| read_at | TIMESTAMP NULL | NULL = non letto |
| archived_at | TIMESTAMP NULL | NULL = non archiviato |

Indici: `triggered_at DESC` (per default ordering), `rule_id`, `stock_id`, `(read_at)` per filtro unread, `(archived_at)` per filtro archived.

### 5.5 Migration

Una sola migration Alembic `2026_05_01_alert_engine_schema.py` con `render_as_batch=True` (SQLite ALTER TABLE limitations). Aggiunta delle 4 tabelle, indici, FK cascade.

## 6. Default parametri regole (in `params` JSON)

| Kind | Default params |
|---|---|
| `rsi_oversold` | `{"period": 14, "threshold": 30}` |
| `rsi_overbought` | `{"period": 14, "threshold": 70}` |
| `golden_cross` | `{"fast": 50, "slow": 200}` |
| `death_cross` | `{"fast": 50, "slow": 200}` |

Modificabili via `PATCH /api/rules/{id}` (body: `{"params": {...}}`). Validation: i param accettati per kind sono fissi (vedi §10.2).

## 7. Daily scan job

### 7.1 Scheduler

APScheduler cron: `day_of_week='*', hour=23, minute=30, timezone='Europe/Rome'`. Coalesce=True (al riavvio dopo downtime esegue una sola volta), max_instances=1. Job id: `scan_alerts`.

### 7.2 Universo scansionato

**Tutti gli stock del catalogo** — query semplice `SELECT id FROM stocks`. Dimensione attesa: ~700 ticker dopo dedup (vedi §8 per espansione catalogo).

Lo scan è **independent dalle watchlist**: avviene anche su stock che nessuna watchlist contiene. Le watchlist intervengono solo in §7.4 per risolvere quale rule applicare.

### 7.3 Flusso

1. **Determina universo**: tutti gli stock del catalogo.

2. **Fetch OHLCV**: `yfinance.download(tickers=[...], group_by='ticker', period=...)` in **batch da 100 ticker** (yfinance limit pratico). Iterazione su chunks.
   - Se `ohlcv_daily` è vuoto per uno stock o l'ultimo bar è > 30gg fa: `period="1y"` (~250 trading days, copre 200-day SMA + buffer).
   - Altrimenti: `period="1mo"` (overlap di 5-30 giorni per gap di calendario / weekend / festivi).
   - Retry 3× con backoff esponenziale (10s, 30s, 90s) su eccezione di rete a livello di chunk; al terzo fail logga errore e marca tutti gli stock del chunk come "fetch failed" (non bloccano gli altri chunk).
   - Stock con dati incompleti (es. ticker delisted, no data on Yahoo) vengono loggati e skippati per quella iterazione.

3. **Upsert** delle righe nuove in `ohlcv_daily`. Per SQLite usiamo `INSERT ... ON CONFLICT(stock_id, date) DO UPDATE SET ...`.

4. **Valutazione regole — risoluzione effettiva per (stock, kind)**:
   - Carica in memoria una volta sola le 4 regole globali (Tier 1) e tutte le override Tier 2 (`watchlist_id IS NOT NULL`).
   - Costruisci la mappa `effective_rules: dict[(stock_id, kind)] -> resolved_rule | None`:
     - Per ogni stock, trova le watchlist che lo contengono.
     - Per ogni `kind`, controlla se almeno una di quelle WL ha un override:
       - Se uno o più hanno `enabled=False`: la regola è **disabled** per questo stock (skip evaluation). [Più restrittivo vince]
       - Se uno o più hanno `enabled=True` con params: **prendi i params della prima trovata** (warn nei log se conflitto multi-WL — Fase 2 single-user lo rende edge case).
       - Se nessun override: usa Tier 1 globale.
   - Se la global stessa è `enabled=False`, skip senza considerare le override (le override hanno senso solo se il kind globalmente attivo).

5. **Per ogni `(stock, kind)` con effective rule**:
   - Query OHLCV ultimi N giorni necessari (max 251 per Cross 50/200 con detection di transizione).
   - `Rule.evaluate(ohlcv, effective_params)` ritorna `bool`.
   - Confronta con `rule_states.last_evaluation` per quella `(global_rule_id, stock_id)` (rule_states è SEMPRE indicizzata per global rule_id, anche se l'evaluation usava params Tier 2 — l'edge-triggering fa riferimento alla "stessa regola logica"):
     - **Nessuna riga in `rule_states`**: prima valutazione. Se `True` → spara alert; se `False` → solo INSERT del state senza alert.
     - **`last_evaluation == False AND new == True`**: TRANSIZIONE → INSERT alert (con `rule_id = global_rule_id`, snapshot include params usati) + UPDATE state.
     - **`last_evaluation == True AND new == True`**: condizione persiste → solo UPDATE `last_evaluated_at`, no alert.
     - **`last_evaluation == True AND new == False`**: cessazione → solo UPDATE state, no alert.
     - **`last_evaluation == False AND new == False`**: nessun cambio.

6. **Persistenza alerts**: tutti gli alert vengono salvati in DB con `read_at=NULL, archived_at=NULL`. **Niente invio Telegram individuale** in Fase 2 — il digest job lo gestisce.

7. **Riepilogo log**: `Scan complete: N stocks scanned, X chunks, Y fetch failures, Z alerts fired`.

### 7.4 Trigger manuale

`POST /api/alerts/scan` (auth richiesta). Body opzionale `{"stock_ids": [...]}` per scoped scan su un subset specifico. Esegue il job in BackgroundTasks (come per `/api/catalog/refresh`), restituisce `202 {accepted: true}`. Utile per debug e test.

## 7.5 Espansione catalogo

### 7.5.1 Nuovi indici da seedare

In aggiunta ai 4 indici già seedati in Fase 1 (SP500, NDX, DJI, FTSEMIB), aggiungiamo 3 nuovi indici. Tutti via `pandas.read_html` da Wikipedia, riusando il pattern già consolidato di `catalog_refresh_service.py`.

| Codice | Nome | URL Wikipedia | Stocks | Suffisso ticker |
|---|---|---|---|---|
| `EUSTX50` | EuroStoxx 50 | https://en.wikipedia.org/wiki/EURO_STOXX_50 | 50 | misto: `.DE`, `.PA`, `.AS`, `.MC`, `.MI`, `.HE`, `.IR` |
| `SSE50` | SSE 50 (Shanghai) | https://en.wikipedia.org/wiki/SSE_50_Index | 50 | `.SS` |
| `HSI30` | Hang Seng top 30 | https://en.wikipedia.org/wiki/Hang_Seng_Index | top 30 di ~80 totali | `.HK` |

### 7.5.2 Modifiche a `INDEX_SOURCES`

Aggiungere 3 entries al dict in `app/services/catalog_refresh_service.py`. Lo schema è identico a quelli esistenti (url, name, country, table_index, ticker_col, name_col, sector_col, industry_col, default_exchange, currency).

Per HSI30 useremo un post-fetch slice: l'indice ha più di 30 costituenti; selezioniamo i primi 30 ordinati per "weight" o "market cap" se presente nella tabella Wikipedia, altrimenti i primi 30 per ordine di apparizione.

### 7.5.3 CSV statici di seed iniziale

Per il primo bootstrap (offline-friendly) servono CSV in `backend/app/data/seed/`:
- `eustx50.csv` (~50 righe top costituenti)
- `sse50.csv` (~50 righe top Shanghai)
- `hsi30.csv` (top 30 HK)

Mantenere lo schema esistente: `ticker,name,exchange,sector,industry,country,currency`. Curare manualmente come per gli altri seed di Fase 1 (~25-30 righe ben note ciascuno).

### 7.5.4 Aggiornare bootstrap.py

`SEEDS` list in `app/scripts/seed.py` aggiunge le 3 nuove entries. Il refresh settimanale Wikipedia mantiene allineato.

### 7.5.5 Esempi ticker per validazione yfinance

| Mercato | Esempio ticker | Yahoo URL |
|---|---|---|
| EuroStoxx — Germany | `SAP.DE` | finance.yahoo.com/quote/SAP.DE |
| EuroStoxx — France | `MC.PA` (LVMH) | finance.yahoo.com/quote/MC.PA |
| EuroStoxx — Netherlands | `ASML.AS` | finance.yahoo.com/quote/ASML.AS |
| SSE 50 — Kweichow Moutai | `600519.SS` | finance.yahoo.com/quote/600519.SS |
| Hang Seng — Tencent | `0700.HK` | finance.yahoo.com/quote/0700.HK |
| Hang Seng — Alibaba | `9988.HK` | finance.yahoo.com/quote/9988.HK |

Validazione: dopo seed iniziale, eseguire scan manuale e verificare nel log che yfinance restituisca dati per almeno il 90% dei ticker. Stock non risolti loggati come warning.

## 8. Indicatori (`backend/app/indicators/`)

Modulo puro, zero dipendenze esterne (solo numpy/pandas già presenti). Una funzione per indicatore.

```python
# app/indicators/sma.py
def sma(close: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return close.rolling(window=period).mean()

# app/indicators/ema.py
def ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=period, adjust=False).mean()

# app/indicators/rsi.py
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
```

Test TDD: golden test data con valori RSI noti su una serie di prezzi reale (verificati contro TradingView per uno stock specifico). Tolleranza: `assert rsi(...).iloc[-1] == pytest.approx(expected, abs=0.5)` (TradingView arrotonda).

## 9. Regole (`backend/app/rules/`)

### 9.1 Interfaccia

```python
class Rule(Protocol):
    kind: str
    default_params: dict
    def evaluate(self, ohlcv: pd.DataFrame, params: dict) -> bool: ...
```

### 9.2 Implementazioni

```python
# app/rules/rsi.py
class RsiOversoldRule:
    kind = "rsi_oversold"
    default_params = {"period": 14, "threshold": 30}
    def evaluate(self, ohlcv, params):
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 30))
        return rsi(ohlcv["close"], period).iloc[-1] < threshold

class RsiOverboughtRule:
    kind = "rsi_overbought"
    default_params = {"period": 14, "threshold": 70}
    def evaluate(self, ohlcv, params):
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 70))
        return rsi(ohlcv["close"], period).iloc[-1] > threshold

# app/rules/cross.py
class GoldenCrossRule:
    kind = "golden_cross"
    default_params = {"fast": 50, "slow": 200}
    def evaluate(self, ohlcv, params):
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        sma_f = sma(ohlcv["close"], fast)
        sma_s = sma(ohlcv["close"], slow)
        if sma_f.iloc[-2:].isna().any() or sma_s.iloc[-2:].isna().any():
            return False  # not enough data
        return sma_f.iloc[-2] <= sma_s.iloc[-2] and sma_f.iloc[-1] > sma_s.iloc[-1]

class DeathCrossRule:
    kind = "death_cross"
    default_params = {"fast": 50, "slow": 200}
    def evaluate(self, ohlcv, params):
        fast = int(params.get("fast", 50))
        slow = int(params.get("slow", 200))
        sma_f = sma(ohlcv["close"], fast)
        sma_s = sma(ohlcv["close"], slow)
        if sma_f.iloc[-2:].isna().any() or sma_s.iloc[-2:].isna().any():
            return False
        return sma_f.iloc[-2] >= sma_s.iloc[-2] and sma_f.iloc[-1] < sma_s.iloc[-1]
```

### 9.3 Registry

```python
# app/rules/registry.py
RULES: dict[str, Rule] = {
    r.kind: r for r in [
        RsiOversoldRule(), RsiOverboughtRule(),
        GoldenCrossRule(), DeathCrossRule(),
    ]
}

def get_rule(kind: str) -> Rule:
    if kind not in RULES:
        raise KeyError(f"Unknown rule kind: {kind}")
    return RULES[kind]
```

### 9.4 Snapshot per UI/debug

Quando una regola spara un alert, oltre a `trigger_price` salviamo in `alerts.snapshot` (JSON):

| Rule kind | Snapshot fields |
|---|---|
| `rsi_oversold`/`rsi_overbought` | `{"rsi": float, "period": int, "threshold": float}` |
| `golden_cross`/`death_cross` | `{"fast_sma": float, "slow_sma": float, "fast_period": int, "slow_period": int}` |

Servono per la modal di dettaglio nella pagina Alerts e per future statistiche.

## 10. Notifier Telegram — Digest Mode (`backend/app/notifiers/telegram.py`)

### 10.1 Configurazione

`.env.example` aggiunge:

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_DELIVERY_MODE=digest
DIGEST_HOUR=8
DIGEST_MINUTE=0
```

`Settings` aggiunge:

```python
telegram_bot_token: str = ""
telegram_chat_id: str = ""
telegram_delivery_mode: str = "digest"  # in Fase 2 only "digest" is implemented
digest_hour: int = 8
digest_minute: int = 0
```

In Fase 2, se `telegram_delivery_mode != "digest"` il notifier logga warning e usa comunque digest. Le modalità `stream` e `watchlist_only` sono Fase 3.

### 10.2 Setup utente (documentato in README)

1. Su Telegram, parla con `@BotFather`, comando `/newbot`, scegli un nome → ricevi `BOT_TOKEN`.
2. Apri la chat con il tuo nuovo bot, manda `/start`.
3. `curl https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` → cerca `result[0].message.chat.id` → quello è `CHAT_ID`.
4. Incolla i due valori in `backend/.env`.

### 10.3 Digest job

APScheduler cron: `day_of_week='*', hour=8, minute=0, timezone='Europe/Rome'`. Job id: `send_digest`. Coalesce=True, max_instances=1.

Flusso:

1. Query `SELECT * FROM alerts WHERE triggered_at > now() - 24h ORDER BY triggered_at DESC`
2. Se zero alert: skip invio (no "ti riporto che non c'è niente"); logga `digest: no alerts in last 24h, skipping`.
3. Se >0 alert: costruisci messaggio formattato (vedi §10.4) e invia via Telegram.
4. Logga esito.

Se Telegram non configurato (token o chat_id vuoti): logga `digest: Telegram disabled, skipping` e termina.

### 10.4 Template messaggio digest (italiano, HTML, max ~4000 char per limit Telegram)

```
🔔 <b>Finance Alert — Digest del {date}</b>

<b>{N} alert</b> nelle ultime 24h:

<b>Per regola:</b>
• RSI Oversold: 5
• RSI Overbought: 3
• Golden Cross: 1
• Death Cross: 0

<b>Top 10 alert per timestamp:</b>
🟢 AAPL — RSI Oversold ($182.50, RSI 28.4) — 23:35
🟢 MSFT — RSI Oversold ($410.20, RSI 29.1) — 23:35
🔴 NVDA — RSI Overbought ($940.00, RSI 72.3) — 23:35
⚡ TSLA — Golden Cross (SMA50 $245, SMA200 $244) — 23:35
... (max 10)

🔗 Vedi tutti: {public_base_url}/alerts
```

Emoji per kind:
- RSI Oversold → 🟢 (opportunità di acquisto)
- RSI Overbought → 🔴 (segnale di vendita / attenzione)
- Golden Cross → ⚡ (cambio trend bullish)
- Death Cross → ⚠️ (cambio trend bearish)

Se >10 alert nel digest: mostra i primi 10 in ordine temporale + suffisso `... e altri X. Vedi /alerts.`. Tronca il messaggio se supera i 4000 caratteri (Telegram limit) con `... [tronca]`.

### 10.5 Trigger manuale digest

`POST /api/alerts/send-digest` (auth richiesta) — utile per test o per "invia subito senza aspettare le 8". Esegue il digest job sincrono. Restituisce `200 {sent: true, alerts_count: N}` oppure `{sent: false, reason: "no_alerts"|"telegram_disabled"}`.

### 10.6 Anti-spam safety net

Con il digest mode il rischio di spam è strutturalmente eliminato (max 1 messaggio Telegram al giorno). Manteniamo comunque un guard idempotency a livello DB: se `send_digest` viene chiamato due volte nello stesso giorno (manuale + cron), il secondo invio viene loggato e inviato comunque (utente può chiamare manualmente per "preview"). Nessun deduplication a livello Telegram.

In Fase 3 (modalità stream): il safety net ridiventerà rilevante (max 1 invio per (rule, stock) ogni 1h).

## 11. API surface (Fase 2 additions)

Tutti gli endpoint sotto `/api`, JSON, autenticazione richiesta.

### 11.1 Rules

| Method | Path | Note |
|---|---|---|
| GET | `/api/rules` | Senza query: lista delle 4 rules globali (Tier 1). Con `?watchlist_id=N`: lista override Tier 2 per quella WL (può ritornare 0-4 righe) |
| POST | `/api/rules` | Body `{watchlist_id?: int|null, kind, params?, enabled?}`. Errore 409 se la `(watchlist_id, kind)` esiste già. Tier 1 se `watchlist_id=null`, Tier 2 se valorizzato. Tier 1 normalmente già pre-creata al bootstrap |
| PATCH | `/api/rules/{id}` | Body `{enabled?, params?}`. Validazione params per kind (vedi §6) |
| DELETE | `/api/rules/{id}` | Hard delete; cascade rimuove anche le `rule_states` riferiti. Per Tier 1 (regole globali): permesso ma scoraggiato (la regola può essere ricreata dal bootstrap al prossimo riavvio). Per Tier 2 (override): cancella semplicemente l'override, restaurando il comportamento globale |

**No auto-creazione su POST `/api/watchlists`**: nuovo modello senza override default. La WatchlistDetailPage offre l'editor opt-in per creare/modificare override Tier 2. La response shape di `/api/watchlists` resta invariata.

**Esempio risoluzione**: la WL "Tech USA" contiene AAPL. Se `GET /api/rules?watchlist_id=tech_usa_id` ritorna `[{kind: "rsi_oversold", enabled: false}]` significa: per AAPL (e altri stock di Tech USA) la regola `rsi_oversold` globale è disabilitata. Le altre 3 (overbought, golden cross, death cross) restano attive con i params globali.

### 11.2 Alerts

| Method | Path | Note |
|---|---|---|
| GET | `/api/alerts` | Query: `ticker?`, `rule_kind?`, `from?` (ISO date), `to?`, `read?` (bool), `archived?` (bool, default False). Pagina con `limit` (default 50, max 500) + `offset`. Order: `triggered_at DESC`. Risposta: `{items: [...], total, has_more}` |
| PATCH | `/api/alerts/{id}` | Body `{read?: bool, archived?: bool}`. `read=true` setta `read_at=now()`; `read=false` lo annulla. Idem `archived`. |
| POST | `/api/alerts/bulk` | Body `{ids: int[], action: "mark_read"|"mark_unread"|"archive"|"unarchive"}` |
| GET | `/api/alerts/unread-count` | Risposta `{count: int}` (alert con `read_at IS NULL AND archived_at IS NULL`) |
| GET | `/api/alerts/export.csv` | Stessi filtri di GET /api/alerts ma senza paginazione (max 10000 righe). Risposta `Content-Type: text/csv` con header e tutte le colonne |
| POST | `/api/alerts/scan` | Body `{stock_ids?: int[]}`. Trigger manuale dello scan in BackgroundTasks. Senza body: scan dell'intero universo. 202. |
| POST | `/api/alerts/send-digest` | Trigger manuale del digest job. Sincrono. 200 con `{sent: bool, alerts_count: int, reason?: str}`. |

### 11.3 Modifica a `/api/watchlists`

POST `/api/watchlists` resta invariato: NESSUNA auto-creazione di rules (nuovo modello — le regole globali sono già attive su tutti gli stock; gli override Tier 2 sono opt-in dalla UI dopo la creazione).

DELETE `/api/watchlists/{id}` cascade rimuove le SOLE rules Tier 2 di quella WL (le globali Tier 1 hanno `watchlist_id IS NULL` e non sono toccate). Gli alert già esistenti per stock di quella WL **restano** (sono indicizzati per global rule_id, non per WL).

## 12. Frontend (Fase 2 additions)

### 12.1 Routing

```
/alerts          → AlertsPage (NUOVA)
/alerts/:id      → AlertsPage con modal aperta sul dettaglio (NUOVA)
```

Le rotte Fase 1 restano invariate.

### 12.2 Sidebar `Layout.tsx`

- Voce "Alerts" passa da disabled (placeholder Fase 1) ad attiva.
- Badge rosso a destra del label con il counter delle unread (poll via `useUnreadAlertsCount` ogni 60s; opzionale upgrade a SSE in Fase 3).

### 12.3 WatchlistDetailPage — nuova sezione "Override regole"

Sotto la card Watchlist, un accordion espandibile "Override regole per questa watchlist":

```
┌─ Override regole ────────────────────────────────────────┐
│ Le regole globali sono attive su tutto il catalogo.      │
│ Qui puoi disabilitarle o personalizzarle solo per gli    │
│ stock di QUESTA watchlist.                               │
│                                                          │
│ RSI Oversold    [● Default globale ○ Disabilita ○ Custom]│
│   default: RSI(14) < 30                                  │
│                                                          │
│ RSI Overbought  [● Default globale ○ Disabilita ○ Custom]│
│   default: RSI(14) > 70                                  │
│                                                          │
│ Golden Cross    [○ Default globale ● Disabilita ○ Custom]│
│   ⚠ Disabilitata: gli stock di questa WL non scattano   │
│                                                          │
│ Death Cross     [○ Default globale ○ Disabilita ● Custom]│
│   Custom: SMA(20) attraversa SMA(50) verso il basso      │
│   [Modifica params]                                      │
└──────────────────────────────────────────────────────────┘
```

3 stati per kind, gestiti come radio button:
- **Default globale**: nessuna riga override (`DELETE /api/rules/{id}` se esisteva)
- **Disabilita**: `POST /api/rules` o `PATCH` con `enabled=false, params={}` (vuoto, non rilevante)
- **Custom**: `POST/PATCH` con `enabled=true, params={...}`. In Fase 2 modifica params via JSON editor inline (textarea con validazione client-side). Editor user-friendly con sliders è Fase 3.

Stato pescato da `useRulesByWatchlist(id)` (TanStack Query, ritorna le 0-4 override Tier 2). I default globali sono pescati una tantum da `useGlobalRules()` (cached 5 min).

Le watchlist esistenti pre-Fase 2 mostrano l'editor con stato iniziale "Default globale" per tutti e 4 i kind (no override).

### 12.4 AlertsPage (nuova, full-feature)

**Layout**:
- Header con titolo "Alerts" + due bottoni secondari:
  - "Esegui scan ora" (POST `/api/alerts/scan`)
  - "Invia digest ora" (POST `/api/alerts/send-digest`) — utile per testare Telegram subito senza aspettare le 8
- Filtri toolbar (sticky):
  - Input ricerca ticker (autocomplete contro `/api/stocks/search`)
  - Multiselect rule kind (4 opzioni hard-coded)
  - Date range picker (from / to)
  - Radio: Tutti / Non letti / Letti / Archiviati
  - Bottone "Reset filtri"
- Tabella centrale:
  - Colonne: checkbox, timestamp (locale it), ticker, rule kind (badge colorato per kind), prezzo, status icona (📩 unread / ✅ read / 🗄 archived)
  - Click su riga: apre Dialog modal con i dettagli (snapshot JSON pretty + link a future Stock Detail page)
  - Stato vuoto: "Nessun alert con questi filtri" + suggerimento "Prova ad allargare il range di date"
- Bulk action bar (visibile quando ≥1 selezionato):
  - "Marca come letti", "Marca come non letti", "Archivia", "Disarchivia", "Esporta CSV (selezionati)"
- Footer paginazione: "Pagina X di Y" + Prev/Next buttons.
- Bottone in alto a destra: "Esporta CSV (con filtri)" → download tutti i risultati filtrati (max 10000).

### 12.5 Component breakdown

Nuovi file:
- `frontend/src/pages/AlertsPage.tsx`
- `frontend/src/components/AlertFilters.tsx`
- `frontend/src/components/AlertsTable.tsx`
- `frontend/src/components/AlertDetailDialog.tsx`
- `frontend/src/components/RulesEditor.tsx` (la sezione regole nella WatchlistDetailPage)
- `frontend/src/hooks/useAlerts.ts`, `useAlertMutations.ts`, `useUnreadAlertsCount.ts`, `useRulesByWatchlist.ts`
- `frontend/src/api/alerts.ts`, `frontend/src/api/rules.ts`

shadcn components da aggiungere se mancanti: `popover` (per date picker), `checkbox`, `command` (per autocomplete ticker). Tutti via `npx shadcn@2 add ...`.

## 13. Configurazione

### 13.1 Aggiunte a `.env.example`

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SCAN_HOUR=23
SCAN_MINUTE=30
```

`SCAN_HOUR` / `SCAN_MINUTE` sono opzionali; default 23/30 hard-coded nel codice. Configurabili per testing (es. utente vuole eseguire alle 21:00).

### 13.2 Aggiunte a `Settings`

```python
telegram_bot_token: str = ""
telegram_chat_id: str = ""
scan_hour: int = 23
scan_minute: int = 30
```

## 14. Logging

Loguru già configurato in Fase 1. Aggiungiamo log dedicati con prefissi:
- `[scan]` per il job daily (start, per-stock fetch, evaluation count, end summary)
- `[notifier]` per Telegram (send success/failure, disabled-skip)
- `[rule]` per evaluation (in DEBUG mode: per-rule per-stock decision)

Log file invariato (`backend/data/logs/app.log`, rotated 10MB, 7gg retention).

## 15. Test strategy

### 15.1 Backend (TDD strict su servizi e regole; test puro per indicatori)

Disciplina TDD obbligatoria (red → green → commit) per: indicators (golden test data), rules (evaluate per condizione + edge cases), `scan_service` (transition matrix), `notifier_service` (config + cooldown), API endpoints (filtri, paginazione, bulk).

| Modulo | Test cases |
|---|---|
| `app/indicators/sma.py` | `test_sma_period_3_on_known_series`, `test_sma_returns_nan_in_warmup` |
| `app/indicators/ema.py` | `test_ema_period_3`, `test_ema_starts_from_first_value` |
| `app/indicators/rsi.py` | `test_rsi_on_golden_data` (valori verificati TradingView), `test_rsi_warmup_returns_nan`, `test_rsi_constant_price_returns_nan_or_50` |
| `app/rules/rsi.py` | `test_oversold_returns_true_below_threshold`, `test_oversold_returns_false_at_exactly_threshold`, ecc. |
| `app/rules/cross.py` | `test_golden_cross_detects_transition`, `test_no_cross_when_already_above`, `test_returns_false_with_insufficient_data` |
| `app/services/scan_service.py` | `test_scan_inserts_alert_on_first_true`, `test_scan_no_alert_when_state_was_already_true`, `test_scan_updates_state_without_alert_on_persistence`, `test_scan_continues_when_one_stock_fetch_fails` |
| `app/services/notifier_service.py` | `test_telegram_disabled_when_no_token`, `test_telegram_called_with_correct_payload`, `test_safety_net_blocks_dup_within_1h` |
| `app/api/rules.py` | CRUD + 409 su duplicate kind, validation params per kind |
| `app/api/alerts.py` | List con filtri, paginazione, bulk action, mark/archive, unread-count, export CSV |

`yfinance.download` viene **mockato** in tutti i test (come `pandas.read_html` in catalog_refresh_service).

### 15.2 Frontend (smoke + key flows)

- `useAlerts.test.tsx` — fetch + filter state
- `AlertsTable.test.tsx` — render + bulk selection
- `RulesEditor.test.tsx` — toggle action invia PATCH

### 15.3 Test integrazione end-to-end

Manuale via README "Definition of Done Fase 2": scan manuale post-bootstrap → verifica alert creati su dati reali per AAPL/ENI.MI / RSI valori plausibili → verifica messaggio Telegram ricevuto (se token config).

## 16. Definition of Done — Fase 2

L'utente, partendo dal repo aggiornato:

```bash
git pull
just install         # applica migration nuove + aggiunge nuovi seed CSV (EuroStoxx 50, SSE 50, HSI 30)
just up
```

Bootstrap riporta: `Seeded SP500: ...`, `Seeded NDX: ...`, `Seeded DJI: ...`, `Seeded FTSEMIB: ...`, `Seeded EUSTX50: ~50`, `Seeded SSE50: ~50`, `Seeded HSI30: ~30`. Catalogo totale ~700 stocks.

Bootstrap inserisce anche le 4 regole globali Tier 1 con `enabled=True`.

Apre /alerts → vede pagina vuota con CTA "Esegui scan ora". Clicca → toast "Scan in corso (può richiedere 5-10 min al primo run)". Dopo qualche minuto ricarica: vede gli alert iniziali generati dal first-run (potenzialmente molti, dovuti a edge-trigger su stato corrente).

Apre una watchlist esistente (Fase 1) → la nuova sezione "Override regole" è visibile, vuota di default (= "default globale" per tutti i kind). Imposta `RSI Oversold` a "Disabilita" per quella WL → API call. Riapre la WL → l'override è persistito.

Configura `.env` con `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, riavvia. Clicca "Invia digest ora" → riceve un messaggio Telegram riepilogativo con N alert delle ultime 24h.

Aspetta il giorno dopo: alle 23:30 lo scan parte automaticamente. Alle 08:00 del mattino successivo riceve il digest Telegram in automatico.

Prova filtri (per ticker, per kind, per stato), bulk archive, export CSV. Verifica che la sidebar mostra `(N)` badge per gli unread.

Tutti i test passano: `just test` → 48 (Fase 1) + ~40 (Fase 2) = ~88 verdi.
`just lint` clean.

## 17. Future fasi (riferimento, non in scope qui)

### Fase 3 — Dashboard & analytics
- Home con KPI cards + feed live SSE
- Stock Detail page con candlestick + overlay indicatori
- **Override regole per singolo stock (Tier 3)** dalla Stock Detail page
- **Modalità Telegram `stream`** (1 messaggio per alert, con safety net 1h)
- **Modalità Telegram `watchlist_only`** (push solo per stock in WL, digest per il resto)
- Editor regole UI con AND/OR composizione
- Editor user-friendly per params Tier 1/Tier 2 (sliders, preview live)
- Indicatori MACD, BB, ATR, ADX
- Regole volume spike, breakout
- Statistiche hit rate per regola
- Settings page (Telegram, preferenze, log viewer)
- Email + webhook notifier

## 18. Assunzioni esplicite

1. **yfinance** è la fonte primaria; degrada a "skip stock" se rotto per quel ticker. Nessun fallback in Fase 2 (Stooq, Alpha Vantage in post-MVP).
2. **Daily timeframe only**: alert calcolati su bar giornalieri. Niente intraday.
3. **Edge-triggering**: alert sparato solo su transizione `False → True`; nessun "alert di fine condizione".
4. **4 regole globali pre-installate** al bootstrap con `enabled=True` e default params; modificabili via API, **NON auto-create per watchlist**.
5. **Override Tier 2 opt-in** dalla WatchlistDetailPage; 3 stati per kind (default globale / disabilita / custom).
6. **Override Tier 3 (per stock) deferred** a Fase 3.
7. **Scan time 23:30 Europe/Rome** copre chiusura US (22:00 IT) + chiusura HK (10:00 IT, mattina prossima sessione asiatica) + chiusura europee. Per la HK la chiusura è alle 10:00 mattina di oggi → il bar daily HK è già consolidato alle 23:30 di oggi.
8. **Universo scansionato = catalogo intero (~700 ticker)** indipendentemente dalle watchlist. Il primo scan richiede ~5-10 minuti (backfill 250gg × 700); i successivi ~30-90s.
9. **Digest Telegram** unico messaggio giornaliero alle 08:00 Europe/Rome con riepilogo ultime 24h. Modalità `stream` e `watchlist_only` sono Fase 3.
10. **OHLCV history**: 250 trading days per il primo backfill, incrementale dopo.
11. **Snapshot in alerts** è JSON (TEXT in SQLite) per estensibilità.
12. **HK index "top 30"**: usiamo l'Hang Seng e prendiamo i primi 30 costituenti per ordine d'apparizione nella tabella Wikipedia (non rigorosamente "top per cap" se non disponibile come colonna; documentato come limit accettato).
13. **Conflict resolution multi-WL**: se uno stock è in più watchlist con override Tier 2 conflittuali sullo stesso kind, vince il più restrittivo (disabled > enabled-with-params > global). Documentato in §7.4.
14. **Edge-trigger su params custom**: `rule_states` è indicizzato per global rule_id. Cambiare params Tier 2 NON resetta lo state (potrebbe causare 1 alert "ritardato" o saltato in caso di edit; trade-off accettato per semplicità).

## 19. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| yfinance scraper rotto / rate-limited per alcuni ticker | Retry exp.backoff 3× a livello chunk (100 ticker); per-stock isolamento dentro il chunk; log warning + alert mancanti = nessuna falsa allerta |
| **yfinance non supporta alcuni ticker HK/CN** | Validazione post-seed: scan iniziale logga ticker che restituiscono no data; documentati come "skipped" — non rompono l'app |
| **Backfill iniziale 250gg × 700 stock** | Una tantum ~5-10 min via batch da 100. Documentato in README come "first scan takes a few minutes". Successivi scan ~30-90s |
| **Volume DB OHLCV ~30 MB dopo 1 anno** | SQLite gestisce facilmente; nessuna gestione esplicita |
| **Volume DB alerts** | ~30-60/giorno × 700 stock × 4 regole con edge-trigger ≈ 10-20k righe/anno; gestibile per anni |
| **Conflict multi-watchlist su override Tier 2** | Risoluzione "più restrittivo vince" documentata; warn nei log se conflict |
| **Cambio params Tier 2 ed edge-trigger state stale** | `rule_states` indicizzato per global rule_id (non per params); accettiamo possibile alert "ritardato"; documentato in §18.14 |
| Yahoo cambia struttura risposta | yfinance lib gestisce; se rotto a livello lib, errore loggato, scan continua con eventuali dati cached |
| Job non gira se PC spento alle 23:30 | APScheduler `coalesce=True`: al primo avvio dopo downtime, esegue una sola volta (recupero parziale, OK per daily) |
| **Digest job parte ma scan non è ancora finito** | Scan 23:30 → digest 08:00: 8.5h di buffer, scan completa in <10 min anche al primo run; nessun race realistico |
| **Digest non inviato se PC spento alle 08:00** | APScheduler coalesce: al riavvio successivo invia comunque il digest (con copertura "ultime 24h" rispetto al momento di invio) |
| Edge-trigger sbagliato per dati storici (primo run) | Prima valutazione: se True spara alert "iniziale" che riflette stato corrente (documentato come comportamento atteso); utente può marcare come read in massa |
| **Primo digest dopo bootstrap potrebbe contenere centinaia di alert iniziali** | Documentato come "first scan effect": l'utente bombardato di RSI initial-state. Mitigazione: clic "marca tutti letti" disponibile dalla pagina /alerts |
| Migration fallisce su DB esistente Fase 1 | `render_as_batch=True` per SQLite; migration solo additive (CREATE TABLE), no destructive |
| FK cascade rimuove rule overrides quando elimino una watchlist | Le rules globali (Tier 1) restano; solo le Tier 2 di quella WL vengono rimosse — comportamento desiderato |
| Wikipedia / yfinance entrambi falliti stesso giorno | Job indipendenti; refresh catalogo è settimanale, scan è daily; failure di uno non impatta l'altro |
| `httpx.post` blocca il thread del scheduler durante digest | Una sola call HTTP per digest; `timeout=10s`; trade-off accettabile per single-user app |
| Edge-trigger memory drift se state DB perso | `rule_states` table fa parte del SQLite file backup; ricostruibile re-running scan (con possibile "re-fire" iniziale = un digest iniziale grosso) |
| **Prossima switch a modalità `stream` o `watchlist_only` (Fase 3)** | Settings `TELEGRAM_DELIVERY_MODE` già definita; cambio = nuova implementazione del notifier dispatch + non breaking. Edge-trigger e DB schema non cambiano. |
