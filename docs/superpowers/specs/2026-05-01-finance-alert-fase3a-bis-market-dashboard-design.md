# Fase 3A-bis — Market Dashboard Redesign — Design Spec

**Data**: 2026-05-01
**Stato**: design approvato (wireframe v2 + §1-§3 confermate)
**Tipo**: redesign della Dashboard Home introdotta in Fase 3A

---

## §1 Obiettivo

Ridisegnare la Dashboard Home (`/`) per portare in primo piano statistiche tecniche derivate dai dati di mercato fetchati (OHLCV + indicatori), retrocedere gli alert al ruolo di pannello secondario, e aumentare drasticamente la densità informativa con breakdown per-indice.

L'utente vuole vedere a colpo d'occhio:
- la salute aggregata del mercato (mood, breadth, A/D ratio)
- la salute di **ciascuno** dei 7 indici monitorati (SP500, NDX, DJI, EUSTX50, FTSEMIB, SSE50, HSI30)
- chi si sta muovendo oggi (gainers, losers, volume spikes, 52w events)
- la distribuzione e i settori
- gli alert come riepilogo compatto, non più protagonisti

## §2 Vincoli

- **Single-user, local-first** (Windows): nessuna concorrenza, niente multi-tenancy
- **Dati EOD** (non intraday): aggiornamenti via scan giornaliero o manuale
- **Stack invariato**: React 19, Vite, TanStack Query, shadcn/ui, Recharts 3.8.1 (già installato), FastAPI, SQLAlchemy 2, SQLite WAL, Alembic
- **Nessuna nuova dipendenza**: Recharts ha già `<Treemap>` built-in
- **Compatibile** con Fase 1+2+3A esistenti — non rompere alert engine, scan, watchlist

## §3 Out of scope (rimandati esplicitamente)

- Aggiornamenti intraday real-time
- Backtest / hit-rate per regola → Fase 3E
- Multi-currency normalization (ogni indice resta in valuta nativa)
- Filtri persistenti utente (richiede settings UI, Fase 3E)
- Confronto storico ("breadth oggi vs 30gg fa") → richiede storicizzare snapshot
- Notifiche desktop su cambio mood
- Customizzazione layout utente (drag-drop widget)
- Endpoint manuale `POST /market-summary/recompute` (overkill: "Esegui scan ora" copre il caso d'uso)

## §4 Stack additions

Nessuna. Tutti gli strumenti necessari sono già nel progetto. La Treemap usa il componente Recharts esistente.

## §5 Modello dati

### Nuova tabella `market_snapshot`

```python
class MarketSnapshot(Base):
    __tablename__ = "market_snapshot"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stocks_total: Mapped[int] = mapped_column(Integer, nullable=False)
    stocks_with_data: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    scan_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("scan_runs.id", ondelete="SET NULL"), nullable=True
    )
```

**Scrittura**: UPSERT con `id=1`, una sola riga viva. La precedente è sovrascritta da ogni `recompute_snapshot`.

### Migration

`backend/alembic/versions/0006_add_market_snapshot.py` — `render_as_batch=True` per SQLite, FK opzionale a `scan_runs(id)`.

### Definizioni precise

- **`stocks_with_data`**: stock con ≥ 200 bar OHLCV (sufficiente per SMA200). Stock con `21 ≤ bars < 200` partecipano alle stat che non richiedono SMA200 (RSI14 ne basta 14, change_pct 2, vol_avg_20 20) ma sono esclusi dal `pct_above_sma200`. Stock con < 21 bar sono esclusi da tutto.
- **Volume spike**: `vol_today / vol_avg_20 > 2.0`. La soglia 2× è hardcoded in Fase 3A-bis (configurabile in 3E).
- **Mood thresholds**: bullish se `pct_above_sma200 ≥ 60` E `advancers > decliners`; bearish se `pct_above_sma200 ≤ 40` E `decliners > advancers`; altrimenti neutral.
- **Near 52w high/low**: distanza `|last_close - extremum| / extremum ≤ 5%`, dove `extremum` è max/min dei `close` ult. 252 bar.
- **Movers ordering**: `gainers` DESC per `change_pct` (più positivi prima); `losers` ASC per `change_pct` (più negativi prima); `volume_spikes` DESC per `vol_today / vol_avg_20`.

### Shape del `payload` JSON

```jsonc
{
  "computed_at": "2026-05-01T17:30:00Z",
  "scan_run_id": 42,
  "global": {
    "stocks_total": 209,
    "stocks_with_data": 201,
    "advancers": 132,
    "decliners": 77,
    "unchanged": 0,
    "avg_change_pct": 0.41,
    "pct_above_sma200": 61.2,
    "pct_above_sma50": 68.5,
    "rsi_oversold_count": 12,         // RSI(14) < 30
    "rsi_overbought_count": 8,        // RSI(14) > 70
    "near_52w_high_count": 23,        // entro 5% del max(close, 252 bar)
    "near_52w_low_count": 4,
    "mood": "bullish"                  // derivato: bullish/neutral/bearish
  },
  "by_index": [
    {
      "code": "SP500", "name": "S&P 500", "n": 25,
      "pct_above_sma200": 68.0, "pct_above_sma50": 76.0,
      "rsi_oversold_count": 2, "rsi_overbought_count": 3,
      "avg_change_pct": 0.52,
      "advancers": 17, "decliners": 8,
      "new_52w_highs": 5, "new_52w_lows": 0,
      "volume_spikes_count": 3
    }
    // ... 6 altre righe (NDX, DJI, EUSTX50, FTSEMIB, SSE50, HSI30)
  ],
  "rsi_distribution": {
    "all": [0,1,11,28,42,55,32,15,8,0],   // 10 bin di width 10
    "by_index": { "SP500": [...], "NDX": [...] /* per ogni indice */ }
  },
  "sectors": [
    { "sector": "Technology", "n_stocks": 35,
      "avg_change_pct": 1.21, "pct_above_sma200": 78.0 }
    // ordinati DESC per avg_change_pct
  ],
  "movers": {
    "gainers": [
      { "ticker":"NVDA","index":"NDX","sector":"Technology",
        "change_pct":4.2,"last_close":876.5,"prev_close":840.7 }
      // top 10 DESC per change_pct
    ],
    "losers": [/* top 10 ASC per change_pct */],
    "volume_spikes": [/* top 10 DESC per vol_today / vol_avg_20 */],
    "new_52w_high": [/* tutti i ticker che oggi fanno nuovo high */],
    "new_52w_low":  [/* tutti i ticker che oggi fanno nuovo low */]
  },
  "treemap": [
    { "ticker":"NVDA","index":"NDX","sector":"Technology",
      "market_cap":2.1e12,"change_pct":4.2 }
    // tutti gli stock con market_cap noto e dati validi
  ]
}
```

## §6 API surface

### Endpoint singolo nuovo

`GET /api/dashboard/market-summary` (auth: cookie session)

**Response 200 con snapshot**:
```json
{
  "available": true,
  "is_stale": false,
  "computed_at": "2026-05-01T17:30:00Z",
  "scan_run_id": 42,
  ... // resto del payload (vedi §5)
}
```

**Response 200 senza snapshot** (primo avvio):
```json
{ "available": false, "reason": "no_scan_yet" }
```

**Response 401**: senza cookie auth.

`is_stale` = `True` se `computed_at < now - 24h`.

### Endpoint esistente NON modificato

`GET /api/dashboard/summary` (Fase 3A) resta com'è — alert-centric. I due hook frontend girano in parallelo.

## §7 Service layer

### `app/services/market_stats_service.py` [NEW]

```python
def recompute_snapshot(db: Session) -> MarketSnapshot:
    """
    1. Carica tutti gli stock + ultime 252 OHLCV bars con eager-load
       (1 query per stocks, 1 per ohlcv via JOIN o IN-clause)
    2. Per ogni stock calcola:
       - last_close, prev_close, change_pct
       - sma50, sma200 (riusa app.indicators.sma)
       - rsi14 (riusa app.indicators.rsi)
       - high_252 = max(close ult.252 bar), low_252 = min(close ult.252 bar)
       - vol_avg_20 = media volume ult.20 bar, vol_today = volume oggi
    3. Aggrega per index_code (join stock_indices)
    4. Aggrega per sector
    5. Costruisce 'movers', 'treemap', 'rsi_distribution'
    6. UPSERT market_snapshot con payload JSON serializzato
    """

def get_latest_snapshot(db: Session) -> MarketSnapshot | None:
    """Restituisce la riga corrente o None se la tabella è vuota."""

def derive_mood(global_block: dict) -> str:
    """
    bullish:  pct_above_sma200 >= 60 AND advancers > decliners
    bearish:  pct_above_sma200 <= 40 AND decliners > advancers
    neutral:  altrimenti
    """
```

Funzioni pure salvo l'ultimo step di scrittura.

### Modifica a `app/services/scan_runner.py`

A fine `run_scan` (dopo l'emissione alert e prima di marcare lo scan completato), invoca:
```python
market_stats_service.recompute_snapshot(db)
```
in try/except — fallimento del snapshot logga warning ma NON marca lo scan come failed (la pipeline alert principale è andata a buon fine).

## §8 Frontend: componenti

### Struttura

```
frontend/src/pages/HomePage.tsx                                  [REWRITE]
└── frontend/src/components/dashboard/
    ├── HeroStrip.tsx                              [NEW] composizione delle 3 sotto
    ├── MoodCard.tsx                               [NEW] gradient + label da global.mood
    ├── GlobalKpiTiles.tsx                         [NEW] 6 tile compatti
    ├── DataFreshnessCard.tsx                      [NEW] computed_at + next scan + is_stale banner
    ├── BreadthMatrixTable.tsx                     [NEW] 7 indici × 11 colonne, righe estreme highlight
    ├── MoversCard.tsx                             [NEW] shadcn Tabs: Gainers / Losers / Volume× / 52w events
    ├── RsiHistogramCard.tsx                       [NEW] Recharts BarChart + Select indice
    ├── SectorsHeatmapCard.tsx                     [NEW] tabella settori, bg-color via cn()
    ├── FiftyTwoWeekVolCard.tsx                    [NEW] Tabs: 52w events / Volume spikes
    ├── MarketTreemap.tsx                          [NEW] Recharts <Treemap>, dropdown indice
    ├── SpotlightPlaceholder.tsx                   [NEW] empty card (Fase 3B/3C)
    ├── AlertsCompactPanel.tsx                     [NEW] tabs che riusano:
    │   ├── AlertsByDayChart                       [REUSE, prop compact?]
    │   ├── TopStocksTable                         [REUSE]
    │   ├── RecentAlertsFeed                       [REUSE]
    │   └── AlertsByIndexBars.tsx                  [NEW small Recharts BarChart]
    └── SystemStatusFooter.tsx                     [NEW slim 1-line]

[REMOVE]  frontend/src/components/dashboard/SystemStatusCard.tsx (sostituito)
[NEW]     frontend/src/api/market.ts
[EXTEND]  frontend/src/api/types.ts (aggiunti MarketSummary + 12 sub-types)
[NEW]     frontend/src/hooks/useMarketSummary.ts
```

### Hook

```typescript
export function useMarketSummary() {
  return useQuery({
    queryKey: ["dashboard", "market-summary"],
    queryFn: () => market.summary(),
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    staleTime: 10_000,
  });
}
```

`useMarketSummary` e `useDashboardSummary` indipendenti — failure isolata.

### Stato locale

Selettori indice (RSI histogram, Treemap) usano `useState<string>("all")`. Niente URL state in Fase 3A-bis.

### Responsive

- `lg:grid-cols-4` (≥1024px) per la mid grid · `md:grid-cols-2` · `grid-cols-1`
- Hero: `lg:grid-cols-[200px_1fr_200px]` desktop, stack mobile
- Matrice breadth: `overflow-x-auto` su mobile (11 col non riducibili)

### Densità tabelle

- Padding: `py-1 px-2` (vs default shadcn `py-3 px-4`)
- Font: `text-[11px]` con `tabular-nums`
- Bordo riga: `border-b border-border/50`
- Override creando wrapper `CompactTable` interno OPPURE applicando classi `cn` sulle Table esistenti

## §9 UX — riferimento al wireframe v2

Il wireframe approvato è in `.superpowers/brainstorm/3828-1777668567/content/hybrid-layout-v2.html` (gitignored, mockup brainstorm).

Layout dall'alto al basso:

1. **Hero strip** (3 colonne fisse): MoodCard 200px | 6 KPI tiles fluid | DataFreshness 200px
2. **Breadth matrix** (full width): 7 righe × 11 colonne, intestazione `bg-muted/50`, righe estreme con `bg-yellow-50/30` (NDX bullish) o `bg-red-50/30` (SSE50 bearish)
3. **Mid grid 4 colonne**: Movers | RSI Histogram | Sectors Heatmap | 52w events
4. **Treemap row**: Treemap (2/3) | Spotlight placeholder (1/3)
5. **Alerts compact panel**: 1 strip con tab Trend / Top stocks / Feed / Per indice — altezza ~80-120px
6. **System status footer**: 1 riga inline con scheduler/Telegram/next runs

Gerarchia tipografica: titolo h2 (Dashboard) solo se utile (probabile rimozione per max densità), section title `text-xs font-semibold uppercase text-muted-foreground` su ogni card.

## §10 Error handling

| Caso | Backend | Frontend |
|---|---|---|
| Snapshot mai generato | `200 {"available": false, "reason": "no_scan_yet"}` | Hero empty-state "Nessuno scan eseguito → /alerts"; resto pagina con placeholder grigi |
| Snapshot stale (>24h) | Flag `is_stale: true` nel payload | Banner giallo discreto sopra la matrice |
| Stock con OHLCV insufficiente | Escluso, contato in `global.stocks_with_data` | "201/209 con dati" nel KPI Universe |
| Indice senza dati | Riga `n=0`, metriche `null` | Cella "—" `text-muted-foreground` |
| `recompute_snapshot` crasha | Logga, NON marca scan failed | UI usa lo snapshot precedente |
| Fetch fallisce | 500 | Card retry (pattern Fase 3A) |
| Polling fallisce | TanStack retry default | `keepPreviousData` → ultimo successo resta visibile |

**Failure isolata**: market e summary hook indipendenti — uno fallisce, l'altro mostra dati.

## §11 Definition of Done

- [ ] Migration `0006_add_market_snapshot.py` applicata, tabella creata
- [ ] `market_stats_service.recompute_snapshot` invocato a fine ogni scan
- [ ] Endpoint `/api/dashboard/market-summary` 200 con auth, payload conforme allo schema
- [ ] HomePage `/` mostra: hero strip + matrice 7×11 + 4-col grid + treemap + alerts compact + footer
- [ ] Tabs e dropdown indice interattivi
- [ ] Empty state se snapshot mancante; banner stale se >24h
- [ ] Polling 30s background-aware
- [ ] `npm run build` clean
- [ ] `pytest -q` green (~130 passing, +12 nuovi)
- [ ] ARCHITECTURE.md aggiornato con changelog entry
- [ ] Push a `origin/master`

## §12 Placeholder strategy (Fase 3B+)

| Punto UI | Comportamento oggi | Si attiva in |
|---|---|---|
| **Spotlight cards** | Card grigia "Disponibile in Fase 3B/3C — sparkline + RSI mini + segnale" | 3B (sparkline) + 3C (segnali avanzati) |
| **Click riga matrice breadth** | Tooltip "Drill-down disponibile in Fase 3B"; cursor passivo | 3B (Stock Detail + index drill-down) |
| **Click tile treemap** | Tooltip "Disponibile in Fase 3B"; cursor passivo | 3B (rotta `/stocks/:ticker`) |
| **Tab "Per indice" alerts** | **Implementato subito** (i dati ci sono già: alert → stock → stock_indices) | — (Fase 3A-bis) |
| **Hit-rate per regola** | Non incluso | 3E (hit-rate stats) |

Filosofia: placeholder visivo solo dove la UI prenota fisicamente spazio. Le interazioni passive (click) usano tooltip + cursor `default`. Niente dead-link visibili.

## §13 Testing strategy

**Backend (pytest):**
- `tests/test_market_stats_service.py` (~6-8 test):
  - Snapshot generation con fixture seeded (3-4 stock × 250 bar OHLCV deterministici)
  - Per-index aggregation correttezza
  - Sectors aggregation
  - Movers ordering (gainers DESC, losers ASC)
  - 52w high/low edge case (= massimo storico)
  - RSI distribution binning
  - Idempotenza chiamate multiple
- `tests/test_api_market_summary.py` (~3 test):
  - 401 senza auth
  - Empty response quando snapshot manca
  - Shape check con snapshot in DB
- `tests/test_models_market_snapshot.py` (~1 test): UPSERT

Target: ~12 test backend, totale ~130 passing.

**Frontend:** build verification (tsc + vite build), nessun test UI runtime (consistente con il resto del codebase).

**Smoke test E2E manuale:**
- Login → `/` → tutti i blocchi popolati
- Esegui scan → entro 30s la matrice si aggiorna
- DB svuotato → empty state visibile

## §14 Roadmap delle prossime fasi (riferimento)

Questo redesign apre la strada a:
- **3B** Stock Detail page (`/stocks/:ticker`) + Tier 3 per-stock rule overrides → riempie i placeholder click + Spotlight (sparkline)
- **3C** Indicatori avanzati (MACD/BB/ATR/ADX) + regole volume/breakout → arricchisce Spotlight con segnali; aggiunge nuove righe alla matrice (es. % MACD bullish cross)
- **3D** Multi-channel notifiers (Telegram per-watchlist, email, webhook) → impatto principale su /alerts e settings, marginale su Dashboard
- **3E** Settings + hit-rate stats + AND/OR rule editor → potrebbe aggiungere una sezione "Performance regole" sotto la matrice

---

## Appendice A — Vincoli operativi

- **Database**: SQLite locale, WAL mode, ~50k righe OHLCV. La query `SELECT * FROM ohlcv_daily WHERE stock_id IN (...)` su 209 stock è veloce (<200ms con eager load).
- **Compute snapshot**: stimato 1-3s end-to-end (200 stock × 5 indicatori × pandas vectorized).
- **Payload JSON**: stimato 50-80KB serializzato. Negligible per polling 30s in localhost.
- **Recharts Treemap**: tested fino a 200 leaves senza problemi. Se in futuro >500, valutare manual-chunking.
