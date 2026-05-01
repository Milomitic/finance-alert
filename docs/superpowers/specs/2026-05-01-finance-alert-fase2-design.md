# Finance Alert — Fase 2 Design (Alert Engine)

**Data**: 2026-05-01
**Stato**: Approvato in brainstorming, in attesa review utente
**Scope**: Solo Fase 2. Fase 3 (dashboard, charts, regole AND/OR, indicatori MACD/BB/volume) elencata in fondo per contesto.

---

## 1. Obiettivo della Fase 2

Trasformare l'app da "watchlist viewer" (Fase 1) ad "alert engine":

1. Recuperare quotidianamente dati OHLCV per gli stock presenti nelle watchlist.
2. Calcolare indicatori tecnici (SMA, EMA, RSI) sui prezzi.
3. Valutare 4 regole pre-installate (RSI oversold/overbought, Golden/Death Cross 50/200) edge-triggered: alert sparato solo sulla transizione `condizione_falsa → vera`.
4. Inviare notifiche Telegram per ogni nuovo alert.
5. Permettere all'utente di consultare lo storico alert via UI con filtri, mark-as-read, archive ed export CSV.

**La Fase 2 NON include**: editor visuale di regole con AND/OR, MACD/BB/volume/breakout, timeframe sub-daily, email/webhook notifications, backtest hit rate, candlestick chart pages. Quelli sono Fase 3 / post-MVP.

## 2. Vincoli e principi guida

- **Continuità con Fase 1**: stesso stack (FastAPI + SQLAlchemy + APScheduler + SQLite + React + shadcn). Niente nuovi servizi a runtime.
- **Edge-triggering**: alert sparato una sola volta sulla transizione, non ad ogni scan finché la condizione resta vera. Riduce drasticamente il volume di notifiche.
- **Rules pre-installate**: niente UI di creazione/edit regole in Fase 2 (è Fase 3). L'utente attiva/disattiva via toggle nella WatchlistDetailPage; le 4 regole vengono auto-create con `enabled=True` quando si crea una nuova watchlist.
- **Telegram via `.env`**: zero UI per setup; `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` in `.env`, README spiega la procedura BotFather.
- **Soglie standard**: RSI 30/70 con periodo 14, Cross 50/200. Modificabili via API `/api/rules/{id}` per chi vuole sperimentare; nessuna UI per parametri in Fase 2.
- **Lingua**: codice/identifier inglese; testi UI italiano hard-coded; messaggi Telegram italiano.

## 3. Cosa è esplicitamente fuori scope per Fase 2

| Funzionalità | Fase prevista |
|---|---|
| Editor regole UI con AND/OR composizione | Fase 3 |
| Indicatori MACD, Bollinger Bands, ATR, ADX | Fase 3 |
| Regole volume spike, breakout su N-day high/low | Fase 3 |
| Timeframe 1h, 15m | Fase 3 |
| Email notifier, webhook generico | Post-MVP |
| Backtest hit rate / statistiche per regola | Fase 3 |
| Stock Detail page con candlestick + overlay indicatori | Fase 3 |
| Editor parametri regole via UI | Fase 3 |
| Settings page (oggi tutto via .env) | Fase 3 |

**In scope Fase 2**: scansione daily post-chiusura mercati, edge-triggered alerts, notifier Telegram, full Alerts page (filtri multi-campo, paginazione, mark-read, archive, export CSV), badge unread sidebar, toggle regole nella WatchlistDetailPage.

## 4. Architettura tecnica

### 4.1 Stack additions

| Layer | Aggiunta | Versione |
|---|---|---|
| Data fetch | `yfinance` | ≥0.2 |
| Numeric | `numpy` (transitive da pandas, ma esplicitiamo) | ≥1.26 |
| HTTP client (notifier) | `httpx` (già installato) | usa l'esistente |

Nessuna dipendenza nuova frontend (riusiamo shadcn/Tailwind/TanStack Query/React Hook Form).

### 4.2 Topologia esecuzione (invariata da Fase 1)

```
┌──────────────────────────────────────────────┐
│ uvicorn :8000                                │
│ FastAPI                                      │
│ ├── /api/* (auth, stocks, watchlists,        │
│ │            catalog, rules, alerts) → router│
│ └── /*     → StaticFiles(frontend/dist)      │
│ APScheduler                                  │
│ ├── refresh_catalog (weekly Sat 03:00)       │
│ └── scan_alerts    (daily 23:30)  ← NUOVO    │
│ SQLite ./backend/data/app.db                 │
└──────────────────────────────────────────────┘
```

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

### 5.2 `rules` — istanza di una regola attiva su una watchlist

| Campo | Tipo | Note |
|---|---|---|
| id | INTEGER PK | |
| watchlist_id | INTEGER FK → watchlists.id ON DELETE CASCADE | |
| kind | TEXT NOT NULL | uno di: `rsi_oversold`, `rsi_overbought`, `golden_cross`, `death_cross` |
| params | TEXT NOT NULL | JSON serialized; default per-kind documentato in §6 |
| enabled | BOOLEAN NOT NULL DEFAULT TRUE | |
| created_at | TIMESTAMP server_default | |
| updated_at | TIMESTAMP server_default + onupdate | |

Vincolo unico: `(watchlist_id, kind)` — una watchlist ha al massimo un'istanza per ogni kind.

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

### 7.2 Flusso

1. **Universo**: `SELECT DISTINCT s.id FROM stocks s JOIN watchlist_items wi ON wi.stock_id = s.id JOIN watchlists w ON w.id = wi.watchlist_id JOIN rules r ON r.watchlist_id = w.id WHERE r.enabled = TRUE`. Tipicamente 20-50 stock; max 79 (catalogo seedato).

2. **Fetch OHLCV**: `yfinance.download(tickers=[...], group_by='ticker', period=...)` batch.
   - Se `ohlcv_daily` è vuoto per uno stock o l'ultimo bar è > 30gg fa: `period="1y"` (~250 trading days, copre 200-day SMA + buffer).
   - Altrimenti: `period="1mo"` (overlap di 5-30 giorni per gap di calendario / weekend / festivi).
   - Retry 3× con backoff esponenziale (10s, 30s, 90s) su eccezione di rete; al terzo fail logga errore e salta lo stock (gli altri continuano).

3. **Upsert** delle righe nuove in `ohlcv_daily`. Per SQLite usiamo `INSERT ... ON CONFLICT(stock_id, date) DO UPDATE SET ...`.

4. **Valutazione regole**: per ogni `(rule, stock)` dove `rule.enabled=TRUE` e `stock` è nella `rule.watchlist_id`:
   - Query OHLCV ultimi N giorni necessari (max 250 per Cross con SMA200 + 1 bar in più per Cross detection).
   - `Rule.evaluate(ohlcv, params)` ritorna `bool`.
   - Confronta con `rule_states.last_evaluation` per quella `(rule_id, stock_id)`:
     - **Nessuna riga in `rule_states`**: prima valutazione. Se `True` → spara alert (assume edge dal "non monitorato" al "vero"); se `False` → solo INSERT del state senza alert.
     - **`last_evaluation == False AND new == True`**: TRANSIZIONE → INSERT alert + UPDATE state.
     - **`last_evaluation == True AND new == True`**: condizione persiste → solo UPDATE `last_evaluated_at`, no alert (edge-triggering).
     - **`last_evaluation == True AND new == False`**: cessazione → solo UPDATE state, no alert (no "alert di fine condizione" in Fase 2).
     - **`last_evaluation == False AND new == False`**: nessun cambio.

5. **Notifica**: per ogni nuovo alert appena INSERTed, chiama `notifier.send_telegram(alert)`. Errore di invio NON rollback dell'alert in DB (quello sopravvive); logga solo l'errore.

6. **Riepilogo log**: `Scan complete: N stocks scanned, M alerts fired, K notifier failures`.

### 7.3 Trigger manuale

`POST /api/alerts/scan` (auth richiesta). Body opzionale `{"watchlist_id": N}` per scoped scan. Esegue il job sincrono (BackgroundTasks come per `/api/catalog/refresh`), restituisce `202 {accepted: true}`.

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

## 10. Notifier Telegram (`backend/app/notifiers/telegram.py`)

### 10.1 Configurazione

`.env.example` aggiunge:

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

`Settings` aggiunge i due campi (default stringa vuota).

### 10.2 Setup utente (documentato in README)

1. Su Telegram, parla con `@BotFather`, comando `/newbot`, scegli un nome → ricevi `BOT_TOKEN`.
2. Apri la chat con il tuo nuovo bot, manda `/start`.
3. `curl https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` → cerca `result[0].message.chat.id` → quello è `CHAT_ID`.
4. Incolla i due valori in `backend/.env`.

### 10.3 Invio messaggio

```python
def send_telegram(alert: Alert, stock: Stock, rule: Rule) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("Telegram disabled: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID empty")
        return
    message = _format_message(alert, stock, rule)
    try:
        httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10.0,
        ).raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"Telegram send failed for alert {alert.id}: {e}")
```

### 10.4 Template messaggio (italiano, HTML)

```
🔔 <b>Finance Alert</b>

<b>{ticker}</b> — {rule_label}
Prezzo: <b>${trigger_price}</b> al {triggered_at:%Y-%m-%d %H:%M}
{indicator_line}

Watchlist: <i>{watchlist_name}</i>
🔗 {public_base_url}/alerts/{alert_id}
```

`indicator_line` cambia per kind:
- RSI: `RSI({period}) = {rsi:.1f} (soglia: {threshold})`
- Cross: `SMA({fast})={fast_sma:.2f}, SMA({slow})={slow_sma:.2f}`

`rule_label` (italiano): `RSI Oversold` / `RSI Overbought` / `Golden Cross` / `Death Cross`.

### 10.5 Anti-spam safety net

Il cooldown effettivo è già garantito dall'edge-triggering (alert sparato solo su transizione). Come defense in depth aggiuntiva contro bug logici, prima di ogni `send_telegram` controlla se per la stessa `(rule_id, stock_id)` esiste un alert ricevente con `triggered_at > now() - 1h`. Se sì:

- L'alert corrente **viene comunque persistito in DB** (resta visibile nella pagina `/alerts`)
- L'invio Telegram **viene saltato** (logga `notifier: cooldown skip for (rule=X, stock=Y)`)

Effetto: la pagina UI non perde mai informazioni; il canale Telegram è protetto da burst causati da bug. In condizioni normali (edge-triggering corretto) questa branch non si attiva mai.

## 11. API surface (Fase 2 additions)

Tutti gli endpoint sotto `/api`, JSON, autenticazione richiesta.

### 11.1 Rules

| Method | Path | Note |
|---|---|---|
| GET | `/api/rules?watchlist_id=N` | Lista regole della watchlist N |
| POST | `/api/rules` | Body `{watchlist_id, kind, params?, enabled?}`. Errore 409 se la (watchlist_id, kind) esiste già |
| PATCH | `/api/rules/{id}` | Body `{enabled?, params?}`. Validazione params per kind (vedi §6) |
| DELETE | `/api/rules/{id}` | Hard delete; cascade rimuove anche `rule_states` e `alerts` riferiti |

**Auto-creazione**: quando si crea una nuova watchlist (POST `/api/watchlists`) il backend crea automaticamente le 4 rules con `enabled=True` e default params, all'interno della stessa transazione. La response shape di `/api/watchlists` resta invariata (le rules si fetchano separatamente via `GET /api/rules?watchlist_id=...`); cambia solo il side effect interno del POST.

### 11.2 Alerts

| Method | Path | Note |
|---|---|---|
| GET | `/api/alerts` | Query: `ticker?`, `rule_kind?`, `from?` (ISO date), `to?`, `read?` (bool), `archived?` (bool, default False). Pagina con `limit` (default 50, max 500) + `offset`. Order: `triggered_at DESC`. Risposta: `{items: [...], total, has_more}` |
| PATCH | `/api/alerts/{id}` | Body `{read?: bool, archived?: bool}`. `read=true` setta `read_at=now()`; `read=false` lo annulla. Idem `archived`. |
| POST | `/api/alerts/bulk` | Body `{ids: int[], action: "mark_read"|"mark_unread"|"archive"|"unarchive"}` |
| GET | `/api/alerts/unread-count` | Risposta `{count: int}` (alert con `read_at IS NULL AND archived_at IS NULL`) |
| GET | `/api/alerts/export.csv` | Stessi filtri di GET /api/alerts ma senza paginazione (max 10000 righe). Risposta `Content-Type: text/csv` con header e tutte le colonne |
| POST | `/api/alerts/scan` | Body `{watchlist_id?: int}`. Trigger manuale dello scan in BackgroundTasks. 202. |

### 11.3 Modifica a `/api/watchlists`

POST `/api/watchlists` ora crea anche le 4 rules nello stesso commit (atomicità). Risposta inalterata (la WatchlistDetailOut non include rules — quelle si fetchano separatamente via `/api/rules?watchlist_id=...`).

DELETE `/api/watchlists/{id}` cascade rimuove rules e relativi alerts (FK ON DELETE CASCADE).

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

### 12.3 WatchlistDetailPage — nuova sezione "Regole attive"

Sotto la card Watchlist (o accordion espandibile in fondo):

```
┌─ Regole attive ──────────────────────────┐
│ [✓] RSI Oversold    (default: RSI<30)   │
│ [✓] RSI Overbought  (default: RSI>70)   │
│ [✓] Golden Cross    (SMA 50/200)        │
│ [✓] Death Cross     (SMA 50/200)        │
└──────────────────────────────────────────┘
```

Toggle ON/OFF chiama `PATCH /api/rules/{id}`. Stato pesco da `useRulesByWatchlist(id)` (TanStack Query). Default per nuova watchlist: tutte e 4 ON (creato dal backend al POST).

Niente editor parametri qui (Fase 3). Le label dei parametri di default sono mostrate come testo grigio per chiarezza.

### 12.4 AlertsPage (nuova, full-feature)

**Layout**:
- Header con titolo "Alerts" + bottone secondario "Esegui scan ora" (POST `/api/alerts/scan`).
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
just install         # applica migration nuove
just set-password-arg <password>
just up
```

Apre /watchlists, crea una nuova watchlist "Test alert" con dentro AAPL + MSFT + ENI.MI. Apre la WatchlistDetailPage, vede le 4 regole attive di default. Disattiva Death Cross. Salva (autosave già esistente).

Apre /alerts → vede pagina vuota con CTA "Esegui scan ora". Clicca → toast "Scan in corso". Dopo ~30s ricarica la pagina, vede alert (se RSI o Cross condizioni vere su quei ticker; altrimenti "Nessun alert").

Configura `.env` con token Telegram, riavvia, esegue scan: riceve messaggio Telegram per ogni nuovo alert.

Prova filtri (per ticker, per kind, per stato), bulk archive, export CSV. Verifica che la sidebar mostra `(N)` badge quando ci sono unread.

Tutti i test passano: `just test` → 48 (Fase 1) + ~30 (Fase 2) = ~78 verdi.
`just lint` clean.

## 17. Future fasi (riferimento, non in scope qui)

### Fase 3 — Dashboard & analytics
- Home con KPI cards + feed live SSE
- Stock Detail page con candlestick + overlay indicatori
- Editor regole UI con AND/OR composizione
- Indicatori MACD, BB, ATR, ADX
- Regole volume spike, breakout
- Statistiche hit rate per regola
- Settings page (Telegram, preferenze, log viewer)
- Email + webhook notifier

## 18. Assunzioni esplicite

1. **yfinance** è la fonte primaria; degrada a "skip stock" se rotto. Nessun fallback in Fase 2 (Stooq, Alpha Vantage in post-MVP).
2. **Daily timeframe only**: alert calcolati su bar giornalieri. Niente intraday.
3. **Edge-triggering**: alert sparato solo su transizione `False → True`; nessun "alert di fine condizione".
4. **Cooldown safety net 1h** è defense in depth, non meccanismo primario di anti-spam.
5. **4 regole pre-installate** auto-create per nuova watchlist con `enabled=True`.
6. **Nessun editor parametri UI**: modifica via `PATCH /api/rules/{id}` per chi vuole.
7. **Scan time 23:30 Europe/Rome** copre chiusura US (22:00 IT) + chiusura FTSE MIB (17:30 IT) + buffer.
8. **Universo scansionato**: solo stock in watchlist con almeno una rule enabled. Non scansioniamo tutti i 79 catalogati a priori.
9. **OHLCV history**: 250 trading days per il primo backfill, incrementale dopo.
10. **Snapshot in alerts** è JSON (TEXT in SQLite) per estensibilità — accettiamo un piccolo overhead di storage in cambio di flessibilità.

## 19. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| yfinance scraper rotto / rate-limited | Retry exp.backoff 3×; per-stock isolamento (un fail non blocca gli altri); log warning + alert mancanti = nessuna falsa allerta |
| Yahoo cambia struttura risposta | yfinance lib gestisce; se rotto a livello lib, errore loggato, scan continua con eventuale dati cached |
| Job non gira se PC spento alle 23:30 | APScheduler `coalesce=True`: al primo avvio dopo downtime, esegue una sola volta (recupero parziale, OK per daily) |
| Telegram bot ban / rate limit | Defense in depth: 1h cooldown safety net evita burst; max ~10 messaggi/giorno realisticamente |
| Edge-trigger sbagliato per dati storici (primo run) | Prima valutazione: se True spara alert "iniziale" che riflette stato corrente (documentato come comportamento atteso); utente può marcare come read |
| `alerts` cresce indefinitamente | ~3000 righe/anno realistiche; archive = soft delete (read_at + archived_at), no hard prune in Fase 2 |
| Wikipedia / yfinance entrambi falliti per refresh + scan stesso giorno | Job indipendenti; refresh catalogo è settimanale, scan è daily; failure di uno non impatta l'altro |
| Migration fallisce su DB esistente Fase 1 | `render_as_batch=True` per SQLite; migration solo additive (CREATE TABLE), no destructive |
| FK cascade rimuove alerts utili quando elimino una watchlist | Documentato: eliminare watchlist = perdita alert/regole associati. Nessun soft-delete in Fase 2 (può venire in F3) |
| `httpx.post` blocca il thread del scheduler | Notifier sync ma con `timeout=10s`; al massimo 10s × N alert blocca scan; trade-off accettabile per Fase 2 |
| Edge-trigger memory drift se state DB perso | `rule_states` table backup-ato come parte di SQLite file backup; ricostruibile re-running scan (con possibile "re-fire" iniziale) |
