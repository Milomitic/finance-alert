# Finance Alert — Fase 3A Design (Dashboard Home)

**Data**: 2026-05-01
**Stato**: Approvato in brainstorming, in attesa review utente
**Scope**: Solo Fase 3A. Sub-progetti 3B/3C/3D/3E sono fuori scope qui (ognuno avrà il suo spec).

---

## 1. Obiettivo della Fase 3A

Trasformare la rotta `/` da semplice redirect a `/watchlists` in una **dashboard riepilogativa** che mostra all'utente, al primo sguardo:

1. Lo stato del sistema (scan, scheduler, Telegram).
2. Il volume e l'andamento degli alert (ultime 24h vs ieri, ultimi 30 giorni).
3. I ticker più "rumorosi" (Top 10 per numero di alert recenti).
4. Il flusso degli alert appena generati (feed con auto-refresh ogni 30s).

L'utente non dovrà più cercare nelle pagine `/alerts` o nelle finestre cmd dei log per capire "cosa è successo oggi": apre l'app e lo vede subito.

**La Fase 3A NON include**: candlestick / Stock Detail (3B), nuovi indicatori (3C), modalità Telegram alternative (3D), Settings page (3E), heatmap performance, filtri.

## 2. Vincoli e principi guida

- **Single endpoint BFF**: un solo `GET /api/dashboard/summary` aggrega tutti i dati. Niente 5 chiamate parallele dal frontend; una sola query React Query.
- **Polling 30s, no SSE**: gli eventi (alert) arrivano max 1 volta al giorno (scan 23:30) o on-demand (scan manuale). SSE è infrastructure overkill per questa cadenza. Polling è stateless e indistinguibile dall'utente per questo pattern di update.
- **Nessuna nuova tabella DB**: tutte le query aggregano dati già presenti (`alerts`, `stocks`, `indices`, `scan_runs`).
- **Recharts** come libreria di grafici (già pianificata nello stack Fase 3).
- **Polish progressivo**: empty state pulito quando non ci sono ancora alert, non layout pieno di zeri.
- **Lingua**: codice/identifier inglese; testi UI italiano hard-coded.

## 3. Cosa è esplicitamente fuori scope per Fase 3A

| Funzionalità | Sub-progetto previsto |
|---|---|
| Stock Detail page con candlestick + overlay indicatori | 3B |
| Override regole per singolo stock (Tier 3) | 3B |
| Indicatori MACD, BB, ATR, ADX | 3C |
| Regole volume spike, breakout | 3C |
| Editor params regole UI (sliders) | 3C |
| Modalità Telegram `stream` / `watchlist_only` | 3D |
| Email + webhook notifier | 3D |
| Settings page (Telegram/preferenze/log viewer) | 3E |
| Statistiche hit rate per regola | 3E |
| Editor regole UI con AND/OR composizione | 3E |
| Heatmap performance watchlist | Non previsto in 3A; rivalutare in 3B (richiede daily return calc su OHLCV) |
| SSE / WebSocket | Non previsto (polling sufficiente per il pattern di update) |
| Filtri / drill-down sulla dashboard | Non previsto (è una vista riepilogativa; filtri stanno in `/alerts`) |

## 4. Architettura

### 4.1 Stack additions

| Layer | Aggiunta | Versione |
|---|---|---|
| Frontend chart | `recharts` | ≥2.x |

Nessuna nuova dipendenza backend. Frontend riusa shadcn/ui, TanStack Query, Tailwind già presenti.

### 4.2 Topologia esecuzione (invariata da Fase 2)

Stesso processo `uvicorn :8000` + `vite :5173` (dev) o `prod-local`. Nessun nuovo job APScheduler.

## 5. Modello dati (zero nuove tabelle)

Tutti i KPI/aggregati derivano da query SQL su tabelle esistenti:

| KPI | Query (high level) |
|---|---|
| `alerts_last_24h` | `COUNT(*) FROM alerts WHERE triggered_at > now() - 24h AND archived_at IS NULL` |
| `alerts_prev_24h` | `COUNT(*) FROM alerts WHERE triggered_at BETWEEN now()-48h AND now()-24h AND archived_at IS NULL` |
| `alerts_unread` | `COUNT(*) FROM alerts WHERE read_at IS NULL AND archived_at IS NULL` (riusa `unread_count` esistente) |
| `stocks_monitored` | `COUNT(*) FROM stocks` (catalogo intero) |
| `indices_count` | `COUNT(*) FROM indices` |
| `last_scan` | Latest row from `scan_runs` (riusa `scan_status` logic) |
| `alerts_by_day` (30gg) | `SELECT date(triggered_at), kind, COUNT(*) FROM alerts JOIN rules ON ... GROUP BY date, kind WHERE triggered_at > now()-30d` |
| `top_stocks_30d` | Due step: (1) `SELECT stock_id, COUNT(*) c FROM alerts WHERE triggered_at > now()-30d AND archived_at IS NULL GROUP BY stock_id ORDER BY c DESC LIMIT 10`; (2) per ogni stock_id risultato, `SELECT rule.kind FROM alerts a JOIN rules ON a.rule_id=rules.id WHERE stock_id=? AND triggered_at > now()-30d GROUP BY rule.kind ORDER BY COUNT(*) DESC LIMIT 1` per ricavare `top_kind`. SQLite-compatible (no `MODE()` function). |
| `recent_alerts` | Riusa `alert_service.list_alerts(limit=10, archived=False)` |
| `next_scan_at` / `next_digest_at` | Da `scheduler.get_job(...).next_run_time` |
| `last_digest_sent_at` | Esposto come `null` in 3A. Sarà valorizzato in 3D introducendo audit log notifier. |

**Nessuna nuova tabella, nessuna nuova migration** in Fase 3A.

## 6. API surface

### 6.1 Nuovo endpoint: `GET /api/dashboard/summary`

Auth richiesta. Risposta JSON. Nessun parametro query in v1.

```python
class KpiSummaryOut(BaseModel):
    alerts_last_24h: int
    alerts_prev_24h: int
    alerts_unread: int
    stocks_monitored: int
    indices_count: int
    last_scan: ScanStatusOut | None  # Riusa schema da Fase 2
    next_scan_at: datetime | None
    next_digest_at: datetime | None


class AlertsByDayPoint(BaseModel):
    date: date
    count: int
    by_kind: dict[str, int]  # {"rsi_oversold": 5, ...}


class TopStockOut(BaseModel):
    stock_id: int
    ticker: str
    alert_count: int
    top_kind: str | None  # rule kind più frequente per quello stock


class SystemStatusOut(BaseModel):
    scheduler_running: bool
    scan_alerts_next_run: datetime | None
    send_digest_next_run: datetime | None
    refresh_catalog_next_run: datetime | None
    telegram_configured: bool
    last_digest_sent_at: datetime | None  # Sempre null in 3A


class DashboardSummaryOut(BaseModel):
    kpis: KpiSummaryOut
    alerts_by_day: list[AlertsByDayPoint]    # 30 punti, oggi compreso
    top_stocks_30d: list[TopStockOut]         # max 10
    recent_alerts: list[AlertOut]             # max 10, riusa schema esistente
    system_status: SystemStatusOut
```

Tutto in un solo round-trip. ~5KB JSON tipico.

### 6.2 Nessun endpoint mutating

La dashboard è read-only. Nessun POST/PATCH/DELETE.

## 7. Service layer

### 7.1 Nuovo modulo `app/services/stats_service.py`

Funzioni pure (nessuno stato mutabile, prendono `Session` ritornano dataclass):

```python
def get_kpi_summary(db: Session) -> KpiSummary: ...
def get_alerts_by_day(db: Session, days: int = 30) -> list[AlertsByDayPoint]: ...
def get_top_stocks(db: Session, *, days: int = 30, limit: int = 10) -> list[TopStock]: ...
def get_system_status(db: Session) -> SystemStatus: ...
```

L'API endpoint chiama queste 4 funzioni + `alert_service.list_alerts(limit=10)` e compone `DashboardSummaryOut`.

### 7.2 Test strategy

**TDD strict** sul service:
- `test_kpi_alerts_24h_counts_only_unarchived`
- `test_kpi_prev_24h_window_correct`
- `test_alerts_by_day_groups_correctly`
- `test_alerts_by_day_includes_zero_days_in_range` (importante per chart continuo)
- `test_top_stocks_orders_by_count_desc_limit_10`
- `test_top_stocks_top_kind_is_most_frequent`
- `test_system_status_reads_scheduler_jobs`
- `test_system_status_telegram_configured_when_token_set`

API smoke test:
- `test_dashboard_summary_requires_auth`
- `test_dashboard_summary_payload_shape`

## 8. Frontend

### 8.1 Routing

```
/           → HomePage (NUOVO — era redirect a /watchlists)
/watchlists → WatchlistListPage (invariato)
/watchlists/:id → WatchlistDetailPage (invariato)
/alerts     → AlertsPage (invariato)
/login      → LoginPage (invariato)
```

`App.tsx` modificato per puntare `/` a `<HomePage />` invece del redirect.

### 8.2 Sidebar `Layout.tsx`

L'entry "Dashboard" è oggi placeholder disabled. Lo abilito a `to: "/"` con icon `LayoutDashboard` (lucide).

### 8.3 Pagina `/`

`frontend/src/pages/HomePage.tsx`:

```
┌─────────────────────────────────────────────────────────────┐
│ <h2>Dashboard</h2>                                          │
│ <p class="text-sm text-muted-foreground">                   │
│   Riepilogo dell'attività di monitoring                     │
│ </p>                                                        │
├─────────────────────────────────────────────────────────────┤
│ <KpiRow> 4 <KpiCard /> orizzontale, responsive grid         │
├──────────────────────────┬──────────────────────────────────┤
│ <AlertsByDayChart />     │ <TopStocksTable />               │
│ recharts AreaChart       │ shadcn Table compatta            │
│ x: date, y: count        │ ticker · count · kind            │
│ tooltip: by_kind          │                                  │
├──────────────────────────┴──────────────────────────────────┤
│ <RecentAlertsFeed /> 10 alert ultime                        │
│ click row → reuse AlertDetailDialog from AlertsPage         │
├─────────────────────────────────────────────────────────────┤
│ <SystemStatusCard /> footer-style, una sola riga            │
└─────────────────────────────────────────────────────────────┘
```

### 8.4 Componenti (5 nuovi sotto `frontend/src/components/dashboard/`)

| File | Responsabilità |
|---|---|
| `KpiCard.tsx` | Card singola con title, value, optional sub-text (delta vs ieri, format icon). Riusabile. |
| `AlertsByDayChart.tsx` | Recharts AreaChart 30gg. Tooltip custom con breakdown per kind. |
| `TopStocksTable.tsx` | Tabella compatta top 10 stock + count alerts + kind più frequente (badge). |
| `RecentAlertsFeed.tsx` | Lista 10 alert più recenti con badge kind + timestamp + prezzo. Click row → modal. |
| `SystemStatusCard.tsx` | Compact card: scheduler ✓/✗, Telegram configurato/no, prossimo scan/digest, ultimo scan. Verde se OK, giallo se warning, rosso se errore. |

### 8.5 Hook

`frontend/src/hooks/useDashboardSummary.ts`:

```typescript
export function useDashboardSummary() {
  return useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => dashboard.summary(),
    refetchInterval: 30_000,           // 30s polling
    refetchIntervalInBackground: true,
    staleTime: 10_000,                 // accept up to 10s stale UX
  });
}
```

### 8.6 API client

`frontend/src/api/dashboard.ts`:

```typescript
import { api } from "./client";
import type { DashboardSummary } from "./types";

export const dashboard = {
  summary: () => api<DashboardSummary>("/api/dashboard/summary"),
};
```

### 8.7 Types in `frontend/src/api/types.ts`

`DashboardSummary`, `KpiSummary`, `AlertsByDayPoint`, `TopStock`, `SystemStatus` — riflettono il backend.

### 8.8 Empty states

- Se `last_scan == null`: KPI "Ultimo scan" mostra "Mai eseguito" + link "Vai a Alerts e clicca Esegui scan ora".
- Se `alerts_last_24h == 0`: chart mostra giorni con count 0 (line bottom). Top 10 mostra "Nessun alert nei 30 giorni" se vuoto. Feed mostra "Nessun alert recente".
- Se `telegram_configured == false`: Card sistema mostra "Telegram non configurato (vedi `.env`)" come info, non errore.

### 8.9 Loading / error

- Loading iniziale (no data ancora): skeleton placeholders su ogni card.
- Errore 401: già gestito globalmente da `ProtectedRoute`.
- Errore 5xx: card error con bottone "Riprova" che invalida la query.

## 9. Test backend (TDD strict)

In ordine:

1. `tests/test_stats_service.py` — service layer puro (8 test elencati in §7.2)
2. `tests/test_api_dashboard.py` — endpoint smoke (auth + payload shape, ~3 test)

Test totali aggiunti: ~11. Coverage finale Fase 3A: 103 (Fase 2) + ~11 = ~114 test.

## 10. Test frontend

- `HomePage.test.tsx`: render con dati mockati (verifica le 5 sezioni siano presenti, niente crash)
- Skip test interattivi (TanStack Query mock complica; il valore è basso per dashboard read-only)

## 11. Definition of Done — Fase 3A

L'utente, partendo dal repo aggiornato:

```bash
git pull
cd frontend && npm install   # recharts nuovo
just up
```

Apre `http://localhost:5173`. **Senza fare nulla**, vede:
- 4 KPI in alto (con dati attuali — alert 24h, unread, monitored, last scan)
- Chart alert per giorno (30 giorni di storia o "0 in tutti i giorni" se nuovo)
- Top 10 stock per alert (o stato vuoto)
- Feed 10 alert recenti (click → modal dettaglio)
- Card stato sistema (scheduler ✓, Telegram, prossimi run)

Aspetta 30s → la dashboard si auto-aggiorna senza refresh.

Trigger uno scan da `/alerts`, torna su `/`. Entro 30s vedi:
- Counter alert 24h aumentato
- Top 10 aggiornata
- Feed con i nuovi alert

Sidebar voce "Dashboard" attiva e linka a `/`.

`just test` → 114 test passing. `just lint` clean.

## 12. Out of scope (rinviato)

| Feature | Quando |
|---|---|
| Drill-down click su KPI → pagina filtrata | Post-3A |
| Heatmap performance watchlist | Post-3B (richiede daily return da OHLCV) |
| `last_digest_sent_at` reale | 3D (insieme a digest audit log) |
| Custom date range sui KPI | Post-MVP |
| Export PNG/PDF dashboard | Post-MVP |

## 13. Assunzioni esplicite

1. Polling 30s è "real-time abbastanza" per il pattern di update (1-2 eventi/giorno tipici).
2. `recharts` è la libreria scelta (vs alternative come `victory`, `chart.js`); già nello stack pianificato.
3. Top 10 stock è ordinata per `COUNT(alerts) DESC` ultimi 30gg. Niente weighting per kind (un Golden Cross conta come un RSI Oversold).
4. `alerts_by_day` include esplicitamente i giorni con count=0 (per chart continuo); il backend riempie il range di 30 giorni anche quando non c'è alcun alert.
5. `top_kind` per uno stock è la `rule.kind` con più alert ultimi 30gg per quello stock (subquery `GROUP BY kind ORDER BY COUNT(*) DESC LIMIT 1`); in caso di pareggio, ordine alfabetico secondario per determinismo (`ORDER BY count DESC, kind ASC`).
6. `last_digest_sent_at` è `null` in 3A; sarà valorizzato in 3D.
7. La policy archived: alert archiviati sono **esclusi** da KPI e chart (mostrare solo "active" alert).
8. La policy unread: il counter `alerts_unread` è limitato agli alert active (non archiviati).

## 14. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Performance query `top_stocks_30d` con 100k+ alert | Indice già presente su `alerts.triggered_at`; query con `LIMIT 10`. Per oggi (~hundreds di alert) non è un problema; rivedere se >100k. |
| Polling 30s × molti utenti = carico | Single-user; il carico è 1 query/30s — irrilevante. |
| Recharts bundle size | Recharts ~70KB gzipped — accettabile, già nel piano stack. |
| Empty state primo run | Esplicitamente progettato (vedi §8.8) — niente layout vuoto deprimente. |
| `alerts_by_day` query SQLite con `date(triggered_at)` | SQLite supporta `date()` su DATETIME timezone-aware; verificato in test. |
| Sidebar "Dashboard" mostra notifica diversa da Alerts | Il badge unread resta solo su Alerts; Dashboard è solo "vista riepilogativa". |
| Click su KPI Alert (24h) — non navigabile in 3A | Card non clickable in 3A; sarà drill-down post-MVP. Tooltip "Vedi tutti" → `/alerts?date_from=...` può essere un quick win se +1 task. |
