# Plan #2 — Sweep C: data integrity audit + fix unità di prezzo + regression check — Design Spec

**Data**: 2026-05-08
**Stato**: design approvato (auto-progressione autorizzata dall'utente)
**Tipo**: bug-hunt + fix architetturale + audit di regressioni recenti
**Trigger**: bug IAG.L (prezzo "totalmente sballato" rispetto al grafico) → indagine ha rivelato che `ohlcv_daily` memorizza i quote LSE in **pence** mentre `live_quote_service` li restituisce in **pounds**, causando confronti cross-source incoerenti.

---

## §1 Obiettivo

1. **Mappare ogni punto del backend dove l'incoerenza pence/pounds può manifestarsi** (audit, Fase 1).
2. **Eliminare l'incoerenza alla radice**: l'OHLCV è autoritario in pounds dopo questo piano. Fix a write-time, mai a read-time. (Fasi 2-3)
3. **Verificare che le altre regressioni recenti** (`c506158`, `df5ff78`, `83a5631`) non abbiano introdotto bug analoghi sui consumer del prezzo (Fase 4).

## §2 Vincoli

- **Migration idempotente**: il backfill non deve mai scalare due volte. Riconoscibile da una flag `Stock.ohlcv_in_pounds`.
- **Nessuna riscrittura dei consumer**: il fix è a livello di ingestion, non di lettura. I consumer (chart, score, indicatori, alert engine) restano invariati e diventano automaticamente corretti.
- **Test prima dei fix**: ogni fase produce test che falliscono prima e passano dopo (TDD-style sul tagging dei consumer rotti).
- **Single-user, local-first** (DB SQLite, no zero-downtime requirement → la migration può fermare il backend per ~30s).

## §3 Out of scope

- **Altri suffissi minor-unit** (`.JO` ZAc Sudafrica, `.TA` ILA Israele, `.HK` HKD-cents) — promossi a in-scope solo se la Fase 1 li trova attivi nel catalogo. Probabile out-of-scope perché il catalogo è US/UK/EU.
- **Storicizzazione dei vecchi pence** (mantenere una colonna `close_native_units`) — YAGNI, in caso di bisogno futuro la migration è reversibile.
- **Refactor di `_override_prev_close_from_ohlcv`** — diventa corretto automaticamente dopo Fase 3.
- **Fix per ticker fuori catalogo** (delisted, ecc.).

## §4 Fasi

### §4.1 Fase 1 — Detection (no production code)

**Output**: `docs/superpowers/audits/2026-05-08-price-units-audit.md`

Script ad-hoc: `backend/scripts/audit_price_units.py`. Non esegue nessuna scrittura DB. Per ogni stock con suffisso minor-unit candidato (`.L`, `.JO`, `.TA`, `.HK`):

1. **Ratio test**: `live_quote.price` vs `ohlcv_daily.close[-1]` più recente. Se `0.5 < live/db < 1.5` → consistenti. Se `0.005 < live/db < 0.015` → DB in pence. Altre soglie → flag manuale.
2. **prev_close override test**: chiamare `_override_prev_close_from_ohlcv(ticker, live_price)` e verificare se il valore è coerente con `live_quote.prev_close` post-yfinance (deve avere stesso ordine di grandezza del prezzo corrente).
3. **52w hi/lo test**: query `MAX(close), MIN(close)` per ticker negli ultimi 252 trading days; verificare che siano nello stesso ordine di grandezza del live price.
4. **Indicators test**: confrontare l'ultimo SMA(20) calcolato per il ticker col live price. Se ratio ≈ 100 → SMA è in pence, prezzo in pounds → indicator-vs-price comparisons (es. "price > SMA200" alert) sono **rotti** per quei ticker.
5. **Score test**: lo score composito è basato su returns/momentum (% changes, unit-invariant) → atteso OK. Verificare empiricamente comunque.
6. **Alert backtest test**: per ogni alert kind che fa confronti assoluti (`price_above_sma`, `breakout`, ecc.) verificare se ci sono alert spuri o mancanti per .L tickers.

L'audit produce una tabella:

| Ticker | Live (pounds) | DB close (pence?) | prev_close OK? | SMA OK? | Alerts spuri? |
|---|---|---|---|---|---|
| IAG.L | 3.27 | 327.5 | ✗ | ✗ | TBD |
| HSBA.L | ... | ... | ... | ... | ... |

E una **shortlist di tutti i consumer rotti**, ordinata per priorità (price-cross alerts > chart > KPI panel > sparkline).

### §4.2 Fase 2 — Fix at write (ingestion)

**File**: `backend/app/services/ohlcv_service.py`, `backend/app/services/stooq_ohlcv_service.py`.

Aggiungere helper:

```python
def _normalize_minor_unit(ticker: str, currency: str | None, value: float | None) -> float | None:
    """Scale pence→pounds for LSE quotes returned by yfinance.history.
    Mirror of live_quote_service._scale_pence_to_pounds.
    Returns None unchanged. Idempotent if currency is already 'GBP'."""
    if value is None:
        return None
    if currency in ("GBp", "GBX"):
        return value / 100.0
    return value
```

In `_upsert_one_stock`, prima di costruire i parametri dell'INSERT, capture la currency dal frame yfinance (è disponibile da `yf.Ticker(stock.ticker).fast_info["currency"]`, ma per ridurre chiamate API la prendiamo da `stock.currency` se disponibile e fresca, altrimenti fast_info come fallback).

Per il fallback Stooq (`stooq_ohlcv_service.py`):
1. Prima cosa nella Fase 2: scrivere un **diagnostic test** che invoca Stooq per IAG.L su un giorno noto e confronta col live_quote in pounds dello stesso giorno.
2. Se ratio ≈ 1 → Stooq serve in pounds, no scaler.
3. Se ratio ≈ 100 → Stooq serve in pence, applicare lo stesso scaler di yfinance.
4. Decisione **prima** di scrivere il code path; lo spec viene aggiornato col risultato.

**Test**: nuovo file `backend/tests/test_ohlcv_minor_unit_scaling.py`:
- Mock yfinance.download che ritorna un frame in pence per IAG.L → asserire che il DB contiene pounds.
- Mock per ticker US (currency='USD') → asserire pass-through.
- Mock per .L con currency mancante (edge case): se ticker termina in `.L` E ratio del valore vs un benchmark (es. 50) è "alto", flag warning + scala. Decisione: **non scalare se currency è None** (fail-safe).

### §4.3 Fase 3 — Backfill migration

**File**: `backend/alembic/versions/<rev>_normalize_lse_ohlcv_to_pounds.py`.

Aggiungere colonna a tabella `stocks`:

```python
ohlcv_in_pounds = Column(Boolean, nullable=False, server_default=sa.false())
```

Logica della migration:

```python
def upgrade():
    # 1) Add the flag column
    with op.batch_alter_table('stocks') as batch_op:
        batch_op.add_column(sa.Column('ohlcv_in_pounds', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))

    # 2) For every .L stock, divide ohlcv_daily by 100 and flip flag
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id FROM stocks WHERE ticker LIKE '%.L' AND ohlcv_in_pounds = 0"
    )).fetchall()
    for (stock_id,) in rows:
        conn.execute(sa.text("""
            UPDATE ohlcv_daily
            SET open=open/100.0, high=high/100.0, low=low/100.0, close=close/100.0
            WHERE stock_id = :sid
        """), {"sid": stock_id})
        conn.execute(sa.text(
            "UPDATE stocks SET ohlcv_in_pounds = 1 WHERE id = :sid"
        ), {"sid": stock_id})
```

**Idempotenza**: la `WHERE ohlcv_in_pounds = 0` clause assicura che ri-esecuzioni siano no-op per stock già normalizzati.

**Invalidazione downstream**:
- `stock_scores` rows per i ticker toccati: `DELETE FROM stock_scores WHERE stock_id IN (SELECT id FROM stocks WHERE ticker LIKE '%.L')`. I score sono ricomputati al prossimo scan (~5min).
- Indicatori (SMA/RSI/BB/MACD/ATR/ADX) non hanno tabella dedicata: sono computati on-demand da OHLCV → automaticamente corretti dopo la migration.
- `fetch_cache` non è impattato (contiene fundamentals/news, non prezzi).
- `live_quote._CACHE` viene cleared al backend restart che accompagna la migration.
- Stessa cosa per `score` (storico per dashboard) — rebuilt al prossimo scan.

**Rollback**: `downgrade()` moltiplica per 100 e droppa la colonna, simmetrico.

### §4.4 Fase 4 — Regression audit dei commit recenti

Per ogni commit, scrivere un test di regressione che fallisce sul comportamento bacato e passa col fix. Se il commit è OK, il test diventa un **regression guard** permanente.

#### `c506158` — prev_close from OHLCV
- Test: IAG.L con OHLCV bars in pounds (post-Fase 3), live_price in pounds → `_override_prev_close_from_ohlcv` ritorna prev_close in pounds.
- Test: ARM (US) col caso descritto nel commit (prev_close yfinance 222.12 ≠ DB 237.30) → l'override usa il DB.

#### `df5ff78` — futures fallback per indici
- Test: mockare `_is_market_open(^GSPC)` = False → endpoint `live-assets` ritorna prezzo dai futures (ES=F).
- Edge case: futures in flat trading hours (weekend) → ritorna ultimo close noto, non error.

#### `83a5631` — FOMC freshness + Forex Factory consensus
- Test: evento FOMC con `actual_value` set e `surprise_pct` ricalcolato → la UI mostra "Sorpresa" non "Atteso".
- Test: evento futuro senza `actual_value` → consenso da FF, non come fallback dell'actual.
- Test (gating): se l'evento è < 7 giorni nel passato e l'actual è ancora None → polling ri-attivo.

#### Eventuali bug emersi dalla Fase 1
Ogni voce della shortlist Fase 1 → test + fix. Iterativo.

## §5 Sequenza di esecuzione

```
Fase 1 (audit) ──┐
                 │
                 ▼
        Fase 2 (write fix + tests)
                 │
                 ▼
        Fase 3 (migration + backfill)
                 │
                 ▼
        Fase 4 (regression guards)
                 │
                 ▼
            Commit & push
```

Ogni fase → 1 commit dedicato. Push solo a fine sweep (o per fasi se l'utente lo richiede).

## §6 Verifica finale

- `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q` → tutti verde, comprese le nuove regression guards.
- `cd frontend && npm run build` → typecheck OK.
- Smoke manuale: `/stocks/IAG.L` → header price ≈ chart series ≈ KPI 52w ≈ score (tutti pounds).
- Smoke manuale: `/stocks/AAPL` → niente regressione (controllo che il fix non abbia rotto US).
- Endpoint health `/api/health` → ok.

## §7 Rischi e mitigazioni

| Rischio | Probabilità | Impatto | Mitigazione |
|---|---|---|---|
| Migration runs twice | bassa | alto (/10000) | Flag `ohlcv_in_pounds`, WHERE clause |
| Non-.L ticker erroneamente scalato | bassissima | medio | Doppio check ticker LIKE '%.L' AND currency='GBp/GBX' |
| Score/Indicators stale dopo migration | alta | basso | Recompute automatico al prossimo scan (~5min) |
| Stooq fallback restituisce già pounds | media | basso | Fase 2 verifica empiricamente, branch separato per Stooq |
| Live_quote breaks during migration window | bassa | basso | Backend restart già richiesto; migration < 5s |
| Altri minor-unit currencies emergono in Fase 1 | media | medio | Estendere helper, non architetturale |

## §8 Definition of Done

- Audit doc committato in `docs/superpowers/audits/`.
- Tutti i ticker `.L` mostrano lo stesso prezzo nel chart, nell'header, nei KPI 52w.
- 0 alert spuri di tipo `price_above_sma` per ticker `.L` nelle prossime 24h dal deploy.
- Tutti i pytest verdi (281+ test esistenti + ~15 nuovi).
- 3 regression guards permanenti per i commit recenti.
- Spec, plan, e ogni fase committati in atomic commits con messaggio descrittivo.
