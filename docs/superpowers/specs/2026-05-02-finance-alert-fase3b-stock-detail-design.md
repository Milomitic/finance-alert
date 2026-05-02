# Fase 3B — Stock Detail Page — Design Spec

**Data**: 2026-05-02
**Stato**: design approvato
**Tipo**: nuova pagina `/stocks/:ticker` + nuovo dominio Price Alerts

---

## §1 Obiettivo

Creare una pagina dedicata per singolo stock (`/stocks/:ticker`) accessibile dai placeholder lasciati in Fase 3A-bis (Spotlight cards, click su Treemap, click su righe BreadthMatrix). La pagina concentra:

- Dati anagrafici (ticker, nome, exchange, sector, market cap, valuta)
- KPI tecnici (last close, change %, 52w high/low, vol×avg20, SMA50/200, RSI14)
- Candlestick chart con overlay SMA50/SMA200 + volume bars + pannello RSI separato (sincronizzato sull'asse temporale)
- Selettore time range (1M / 3M / 6M / 1Y / All)
- Toggle visibilità SMA50/SMA200
- Drawing tools (horizontal price line, trend line) persistiti in localStorage
- **Price Alerts** per-stock per-istanza (price-target alerts) creabili dal chart
- Lista alert storici per quel ticker
- Vista read-only delle regole signal-based effettivamente applicate (Tier 1 + override Tier 2 derivate dalle watchlist che contengono lo stock)
- News headlines (5 più recenti, fonte yfinance)

In aggiunta, la HomePage Dashboard 3A-bis riceve **Spotlight cards reali** al posto del placeholder esistente: 3 card mini ("top gainer", "most alerted 7d", "volume spike") con sparkline + click → `/stocks/:ticker`.

## §2 Vincoli

- **Single-user, local-first** Windows
- **Compatibile** con Fase 1+2+3A+3A-bis — non rompere alert engine, scan, watchlist, dashboard
- **NON modifica** lo schema `Rule`/`RuleState`. Tier 3 (per-stock override delle regole signal-based esistenti) è esplicitamente fuori scope; le regole sono mostrate read-only.
- **Stack additions limitate**: lightweight-charts (già pre-approvato in ARCHITECTURE.md); nessun'altra nuova dipendenza npm. yfinance già presente per news.
- **Bundle target**: < 1.1 MB (oggi 999 kB; lightweight-charts gz ~45 kB)

## §3 Out of scope (rimandati esplicitamente)

- **Stock comparison** (sovrapporre 2+ stock chart)
- **CSV export** OHLCV
- **Alert da chart per indicatori complessi** (RSI threshold custom, MACD cross): richiede Tier 3 vero
- **Drawing tools complessi** (channel, fibonacci, pitchfork) — solo H-line e trend line
- **Server-side persistence drawings**
- **News sentiment analysis**
- **Watchlist management** dal Stock Detail (l'utente usa `/watchlists/:id`)
- **Index drill-down** (`/indices/:code`) → 3C
- **Lista stocks `/stocks` page** (browse del catalogo) → 3C/E
- **Tier 3 per-stock override delle regole esistenti** (RSI/golden cross, ecc.) — definitivamente fuori scope per 3B

## §4 Stack additions

- **`lightweight-charts`** v4.x (TradingView, MIT) — `npm install lightweight-charts`. Bundle gz ~45 kB. Usato per: candlestick, line series (SMA), histogram series (volume), separate panel (RSI), drawing primitives (price lines via `series.createPriceLine`).
- **Backend**: nessuna nuova dependency. yfinance ha già `Ticker.news`.

## §5 Modello dati

### Nuova tabella `price_alerts`

```python
class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # "above" | "below"
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

**Edge-trigger semantics** (replicano il modello esistente di `RuleState`):
- `direction="above"` scatta quando `prev_close <= target AND last_close > target`
- `direction="below"` scatta quando `prev_close >= target AND last_close < target`
- Quando scatta, viene generato un `Alert` con `rule_id=NULL` e `snapshot` JSON contenente `{"price_alert_id": N, "target": X, "direction": "above"}`
- `triggered_at` viene popolato → la price alert NON si ripete (one-shot). L'utente può riabilitarla con PATCH `{enabled: True, target_price: Y}` (reset implicito: triggered_at torna NULL su qualsiasi PATCH che cambia target/direction).

### Modifica `alerts` esistente

Schema attuale: `Alert.rule_id` è `nullable=False` con FK `ON DELETE CASCADE` su `rules.id`. Per unificare alert da regole signal-based (rule_id valorizzato) e alert da price-target (rule_id=NULL, `snapshot.price_alert_id` valorizzato) si **rende `rule_id` nullable**. La FK CASCADE resta — quando una rule viene eliminata, gli alert collegati seguono; gli alert da price-target restano (rule_id=NULL non triggera CASCADE).

Anche il modello SQLAlchemy `app/models/alert.py` deve aggiornare `rule_id: Mapped[int | None]` con `nullable=True`.

### Migration

`backend/alembic/versions/<auto>_add_price_alerts.py` — Alembic con `render_as_batch=True` per SQLite:
1. `op.create_table("price_alerts", ...)` con index su `stock_id`
2. `op.alter_column("alerts", "rule_id", nullable=True)` (in `batch_alter_table` perché SQLite non supporta ALTER nativo)

## §6 API surface

### Stock detail (read-only)

```
GET /api/stocks/{ticker}/detail?range=1m|3m|6m|1y|all   (default 1y)
```
Response 200:
```jsonc
{
  "stock": { "id": 1, "ticker": "AAPL", "exchange": "NASDAQ", "name": "Apple Inc.",
             "sector": "Technology", "industry": "Consumer Electronics",
             "country": "US", "currency": "USD", "market_cap": 2700000000000 },
  "ohlcv": [ { "date": "2025-05-02", "open": 168.5, "high": 170.2, "low": 167.8,
               "close": 169.4, "volume": 45000000 }, ... ],
  "indicators": {
    "sma50":  [ {"date": "...", "value": 168.0}, ... ],   // null nelle prime 49 entries
    "sma200": [ {"date": "...", "value": 162.0}, ... ],   // null nelle prime 199 entries
    "rsi14":  [ {"date": "...", "value": 58.2}, ... ]     // null nelle prime 14 entries
  },
  "kpis": {
    "last_close": 172.45, "prev_close": 170.40, "change_pct": 1.20,
    "high_52w": 198.0, "low_52w": 124.0,
    "vol_avg_20": 50000000, "vol_today": 45000000, "vol_ratio": 0.9
  },
  "effective_rules": [
    { "kind": "rsi_oversold", "enabled": true,  "params": {"period":14,"threshold":30}, "source": "tier1", "watchlist_name": null },
    { "kind": "death_cross",  "enabled": false, "params": {},                            "source": "tier2", "watchlist_name": "FAANG" }
  ],
  "alerts_history": [ AlertOut, ... ]   // ultimi 50 per quel ticker, sorted desc by triggered_at
}
```

Response 404 se ticker non esiste. Response 401 senza auth.

### Stock news

```
GET /api/stocks/{ticker}/news?limit=5    (default 5, max 20)
```
Response 200:
```jsonc
{ "items": [ { "title": "Apple beats Q3 estimates", "publisher": "Reuters",
               "link": "https://...", "published_at": "2026-05-02T14:00:00Z" }, ... ] }
```
Server-side cache in-memory dict TTL 1h (key: ticker). Fallback graceful: se yfinance error → response 200 con `{"items": []}` + log warning.

### Price alerts CRUD

```
GET    /api/stocks/{ticker}/price-alerts          → [PriceAlertOut]
POST   /api/stocks/{ticker}/price-alerts          → body {target_price, direction, note?}, ret PriceAlertOut
PATCH  /api/price-alerts/{id}                     → body {enabled?, target_price?, direction?, note?}, ret PriceAlertOut
DELETE /api/price-alerts/{id}                     → 204
```

Validations:
- `direction` ∈ `{"above", "below"}`
- `target_price > 0`
- PATCH che modifica `target_price` o `direction` resetta `triggered_at = NULL`

### Spotlight (per Dashboard)

```
GET /api/dashboard/spotlight    → { "cards": [SpotlightCardOut, ...] }   // 3 cards
```
Response shape:
```jsonc
{
  "cards": [
    { "type": "top_gainer",      "ticker": "NVDA", "change_pct": 4.2,  "last_close": 876.5,  "sparkline": [870, 875, 873, 878, 876] },
    { "type": "most_alerted_7d", "ticker": "TSLA", "alerts_count": 5,  "last_close": 245.0,  "sparkline": [230, 240, 245, 248, 245] },
    { "type": "vol_spike",       "ticker": "PLTR", "vol_ratio":  3.2,  "last_close": 28.50,  "sparkline": [25, 26, 27, 28, 28.5] }
  ]
}
```

`sparkline`: ultimi 30 close per quel ticker (per il chart mini). Se nessun stock soddisfa un type (es. nessun alert in 7gg), card omessa o card vuota con `ticker: null`.

### Endpoint che NON cambiano

- `/api/dashboard/summary` — invariato
- `/api/dashboard/market-summary` — invariato

## §7 Service layer

### Nuovo `app/services/stock_detail_service.py`

```python
def get_stock_detail(db: Session, ticker: str, range_key: str) -> StockDetailPayload:
    """Carica stock + OHLCV (limit by range) + computa indicatori + risolve effective rules + alert history."""

def resolve_effective_rules(db: Session, stock_id: int) -> list[EffectiveRule]:
    """Per ogni rule kind, trova la regola applicabile a questo stock seguendo Tier 2 -> Tier 1.
    Tier 2 vince se lo stock è in una watchlist con override per quel kind."""
```

### Nuovo `app/services/price_alert_service.py`

```python
def list_price_alerts(db, stock_id) -> list[PriceAlert]
def create_price_alert(db, stock_id, target_price, direction, note=None) -> PriceAlert
def update_price_alert(db, alert_id, **fields) -> PriceAlert
def delete_price_alert(db, alert_id) -> None

def evaluate_price_alerts(db: Session) -> int:
    """Per ogni price alert enabled & not yet triggered:
       - carica last 2 OHLCV bar dello stock
       - se direction='above' AND prev_close <= target AND last_close > target → fire
       - se direction='below' AND prev_close >= target AND last_close < target → fire
       - fire = create Alert(rule_id=None, stock_id, trigger_price=last_close, snapshot=json) + price_alert.triggered_at = now
    Returns: number of alerts fired."""
```

### Nuovo `app/services/stock_news_service.py`

```python
_NEWS_CACHE: dict[str, tuple[datetime, list[dict]]] = {}
NEWS_TTL = timedelta(hours=1)

def get_news(ticker: str, limit: int = 5) -> list[dict]:
    """Wrapper di yfinance.Ticker(ticker).news con cache TTL 1h."""
```

### Modifica `app/services/scan_runner.py`

A fine `run_tracked_scan`, dopo `recompute_snapshot` (anch'esso non-fatal), aggiungere uno step parallelo:
```python
# Evaluate price alerts — non-fatal, scan succeeded already
try:
    from app.services import price_alert_service
    fired = price_alert_service.evaluate_price_alerts(db)
    logger.info(f"[scan_runner] {fired} price alert(s) fired for ScanRun {run.id}")
except Exception as exc:
    logger.warning(f"[scan_runner] price alert evaluation failed (non-fatal): {exc}")
```

### Estensione `app/services/stats_service.py`

Aggiungere helper:
```python
def get_top_alerted_stock_7d(db: Session) -> tuple[Stock, int] | None:
    """Top 1 stock by alert count in last 7 days. Returns (stock, count) or None."""
```
Usato dal nuovo endpoint spotlight.

### Nuovo `app/services/spotlight_service.py`

```python
def build_spotlight(db: Session) -> list[dict]:
    """Combina:
       - top_gainer: legge dal market_snapshot.movers.gainers[0]
       - most_alerted_7d: chiama stats_service.get_top_alerted_stock_7d
       - vol_spike: legge dal market_snapshot.movers.volume_spikes[0]
    Per ogni card aggiunge sparkline (ultimi 30 close)."""
```

## §8 Frontend: componenti + routing

### Routing (`App.tsx`)
```tsx
<Route path="/stocks/:ticker" element={<StockDetailPage />} />
```

### Sidebar (`Layout.tsx`)
Promuovere voce "Stocks" da `enabled: false` a `enabled: true`, link `/stocks/AAPL` come default. (In 3C/E aggiungeremo una pagina lista vera.)

### Nuova pagina

`frontend/src/pages/StockDetailPage.tsx` — orchestrator:
- `useParams<{ticker: string}>()`
- `useSearchParams()` per `range` (default `1y`)
- 4 hook: `useStockDetail(ticker, range)`, `useStockPriceAlerts(ticker)`, `useStockNews(ticker)`, `useEffectiveRules` (incluso in detail)
- Layout grid 2-col `lg:grid-cols-[1fr_320px]`

### Nuovi componenti (in `frontend/src/components/stock/`)

```
StockHeader.tsx              — riga in alto: bandiera (via getIndexMeta su sector? No — uso Stock.country) + nome + KPI breve
PriceChart.tsx               — wrapper lightweight-charts: candlestick + SMA + volume + drawing layer + price-alert lines
RsiPanel.tsx                 — separata `IChartApi` con line series RSI, sync time-axis con PriceChart
RangeSelector.tsx            — pill selector 1M/3M/6M/1Y/All, scrive in URL
IndicatorToggles.tsx         — checkbox SMA50 / SMA200
DrawingToolbar.tsx           — bottoni: H-line / Trend-line / Set alert / Clear all
TechnicalKpiCard.tsx         — sidebar KPI list (last close, change%, 52w hi/lo, SMA50/200, RSI, vol×)
PriceAlertsCard.tsx          — sidebar list + add/edit/delete, mostra "+ crea da chart"
PriceAlertDialog.tsx         — modal create/edit (shadcn Dialog), pre-compilato dal click sul chart
StockAlertsHistoryCard.tsx   — sidebar lista alert storici per quel ticker (riusa AlertDetailDialog)
EffectiveRulesCard.tsx       — sidebar regole effettive Tier 1/2 (read-only, badge sorgente)
NewsCard.tsx                 — sidebar 5 headline (titolo + fonte + data + link external)
```

### Hook nuovi (in `frontend/src/hooks/`)

```
useStockDetail.ts            — TanStack Query, key=["stock-detail", ticker, range], keepPreviousData
useStockPriceAlerts.ts       — invalidate on mutate, key=["price-alerts", ticker]
useStockNews.ts              — staleTime 1h, key=["stock-news", ticker]
useSpotlight.ts              — refetchInterval 60s (cambia poco), key=["dashboard", "spotlight"]
useStockDrawings.ts          — wrapper localStorage, key locale `stock-drawings:{ticker}` JSON
```

### API client (in `frontend/src/api/`)

`stocks.ts` esistente esteso con: `detail(ticker, range)`, `news(ticker, limit)`. Nuovo `priceAlerts.ts` con CRUD. Nuovo `spotlight.ts` con `summary()`.

### Tipi (in `frontend/src/api/types.ts`)

Aggiungere: `StockDetail`, `OhlcvBar`, `IndicatorSeries`, `StockKpis`, `EffectiveRule`, `StockNewsItem`, `PriceAlert`, `SpotlightCard`.

### Dashboard

- **`SpotlightPlaceholder.tsx`** sostituito da `SpotlightCards.tsx` (nuovo, in `components/dashboard/`)
- HomePage importa `SpotlightCards` invece di `SpotlightPlaceholder`
- Click su tile `MarketTreemap` → `navigate("/stocks/" + ticker)` (rimossi tooltip placeholder)
- Click su righe `BreadthMatrixTable` → tooltip aggiornato a "Drill-down per indice in Fase 3C" (resta placeholder finché 3C non c'è)

## §9 UX dettagli sensibili

### Drawing tools (localStorage)
Schema localStorage `stock-drawings:{ticker}`:
```json
{
  "horizontal": [180.0, 165.5],
  "trend": [{"x1": 1714694400, "y1": 168.0, "x2": 1716595200, "y2": 175.0}]
}
```
- H-line: bottone toolbar → cursor crosshair → click sul chart → `series.createPriceLine({price: clickedPrice, color: gray, lineStyle: dashed, axisLabelVisible: true})` + push in localStorage. Doppio-click sulla linea → remove.
- Trend line: bottone toolbar → 2 click → `chart.addLineSeries()` con 2 points. Stesso meccanismo delete.
- Re-render dei drawings al mount della pagina dal localStorage.

### Set alert from chart (UX flow)
1. User click bottone "📍 Set alert" in toolbar
2. Cursor diventa crosshair, hint "Click on chart to set price target"
3. User clicca sul chart al prezzo desiderato
4. Modal `PriceAlertDialog` si apre pre-compilato:
   - `target_price` = prezzo cliccato (rounded a 2 decimali)
   - `direction` = "above" se prezzo > last_close, altrimenti "below" (auto-suggested, modificabile)
   - `note` = "" (campo opzionale)
5. Submit → POST `/api/stocks/{ticker}/price-alerts` → invalidate `useStockPriceAlerts`
6. Nuova price-alert appare in sidebar `PriceAlertsCard` + linea tratteggiata sul chart (verde per above, rossa per below)

### Edit/delete price alert
- Click sulla linea price-alert sul chart → tooltip mini con bottoni "Modifica" / "Disabilita" / "Elimina"
- "Modifica" apre `PriceAlertDialog` con valori attuali
- "Disabilita" PATCH `{enabled: false}` (linea diventa grigia tratteggiata)
- "Elimina" DELETE con conferma inline

### Range selector
- Pill selector orizzontale (1M, 3M, 6M, 1Y, All) sopra il chart
- Selezione persistita in URL: `/stocks/AAPL?range=3m`. Default `1y` se assente.
- Click → invalidate `useStockDetail` con nuovo range

### News card
- 5 headline più recenti, format `[Reuters] Apple beats Q3 (2g fa)`, ognuna `<a target="_blank" rel="noopener">`
- Loading skeleton 5 righe placeholder
- Empty state "Nessuna news disponibile" se API ritorna vuoto o errore
- Footer card "Powered by yfinance"

### Sparkline in Spotlight
- Recharts `<LineChart>` mini, no axis, no tooltip, color = green/red basato su trend (`prev <= last ? green : red`), height 32px, width 80px
- Card layout: icona type (📈/🔔/⚡) + ticker + metric + sparkline → click → navigate

## §10 Error handling

| Caso | Backend | Frontend |
|---|---|---|
| Ticker non esiste | `404 {"detail": "Ticker not found"}` | Card "Ticker non trovato" + link a /watchlists |
| OHLCV insufficiente (<21 bar) | Detail returns ohlcv=[] e indicators tutti vuoti | Header + sidebar funzionano, chart area mostra "Dati insufficienti" |
| yfinance news API down | `200 {"items": []}` + warning log | NewsCard mostra empty state, niente errore globale |
| Price alert validation fail | `422 Unprocessable Entity` | Dialog mostra errore inline ("target_price deve essere positivo") |
| price_alert_service crash | Logged warning, scan succeeds | UI mostra alerts esistenti, nessuna notifica errore |
| Chart render error | — | ErrorBoundary attorno a PriceChart, fallback "Errore rendering chart, ricarica" |
| Drawing localStorage corrupt | — | Try/catch su parse, reset silenzioso a `{horizontal: [], trend: []}` |

**Failure isolata**: ogni hook (detail, alerts, news, spotlight) ha errore indipendente. Se news fallisce, il resto della pagina funziona.

## §11 Definition of Done

- [ ] Migration `<hash>_add_price_alerts.py` applicata (crea `price_alerts`, rende `alerts.rule_id` nullable se necessario)
- [ ] Modello `PriceAlert` registrato in `app/models/__init__.py`
- [ ] 6 endpoint backend live e testati: detail, news, price-alerts CRUD (4), spotlight
- [ ] `evaluate_price_alerts` integrato in `scan_runner.run_tracked_scan` come step non-fatal
- [ ] Pagina `/stocks/:ticker` montata, accessibile via:
  - Click su Spotlight cards in HomePage
  - Click su tile MarketTreemap
  - Sidebar voce "Stocks"
- [ ] PriceChart con candlestick + SMA50/200 toggle + volume + RSI panel sincronizzato + drawing tools (H-line, trend) + price-alert lines visibili
- [ ] Range selector funzionante con URL state
- [ ] Set alert from chart end-to-end funzionante (click → modal → POST → linea sul chart)
- [ ] News card popolato (con cache + fallback)
- [ ] Spotlight cards reali in HomePage al posto del placeholder
- [ ] `npm run build` clean (bundle < 1.1 MB)
- [ ] `pytest -q` green (~160 passing, +17 nuovi)
- [ ] ARCHITECTURE.md aggiornato (changelog + roadmap "Fase 3B implementata")
- [ ] Push su `origin/master`

## §12 Testing strategy

**Backend (pytest):**
- `tests/test_models_price_alert.py` (~1 test): UPSERT/CRUD smoke
- `tests/test_api_stock_detail.py` (~4 test): 401 senza auth, 404 ticker sconosciuto, payload shape, range filter funziona
- `tests/test_api_price_alerts.py` (~5 test): CRUD complete + auth + validation
- `tests/test_api_stock_news.py` (~2 test): cache hit/miss, fallback graceful su yfinance error (mock)
- `tests/test_price_alert_evaluator.py` (~4 test): edge-trigger above/below, doesn't re-fire when triggered_at set, disabled price-alerts skipped
- `tests/test_api_dashboard_spotlight.py` (~2 test): payload shape, query "most alerted 7d"
- `tests/test_stock_detail_service.py` (~3 test): effective_rules resolver Tier1/Tier2, indicators computation

Target: ~21 nuovi test, totale ~165 passing.

**Frontend:** build verification (tsc + vite build), nessun test runtime UI (consistente con il resto del codebase).

**Smoke test E2E manuale:**
- Login → click su Treemap tile AAPL → atterra su `/stocks/AAPL` → vedi tutto popolato
- Crea price alert da chart → appare in sidebar PriceAlertsCard → linea sul chart
- News card mostra 5 articoli reali da yfinance
- Riavvia uvicorn, modifica un OHLCV manualmente per superare un target → scan → vedi alert generato in `/alerts`

## §13 Roadmap follow-up (3C+)

Questo design **NON include** ma facilita:
- **Index drill-down** (`/indices/:code`) — può riusare `StockDetailPage` come componente parziale
- **Stock comparison** — può estendere `PriceChart` con un secondo `addCandlestickSeries`
- **Tier 3 vero** (override delle regole signal-based per-stock) — può aggiungere `EffectiveRulesCard` con bottoni edit
- **Indicatori avanzati** (MACD/BB/ATR) — sidebar nuova card "Advanced indicators"
- **Settings page** (`/settings`) per configurare default range, preferenze UI, ecc.

---

## Appendice A — Vincoli operativi

- **Lightweight-charts**: testato fino a 5000 bar candlestick senza lag. 252 bar (1Y) è trivialmente performante.
- **News cache**: dict in-memory (no Redis). Reset al restart del backend. Sufficiente per single-user.
- **Price alert evaluator**: O(N) su `price_alerts` enabled & not-triggered. Con previsioni di poche decine/centinaia di alert per utente, trivialmente performante. Esegue in <100ms.
- **Spotlight cache**: il payload usa `market_snapshot` esistente per top_gainer/vol_spike → zero costo. La query "most_alerted_7d" è 1 SELECT GROUP BY + JOIN su `alerts`+`stocks`, indici esistenti, < 50ms.
