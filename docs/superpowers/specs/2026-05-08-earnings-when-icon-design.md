# Plan #1 — Icona pre/after-market nella tabella earnings di Stock Detail — Design Spec

**Data**: 2026-05-08
**Stato**: design approvato (auto-progressione autorizzata dall'utente)
**Tipo**: piccola UI feature + esposizione dato già calcolato lato backend

---

## §1 Obiettivo

Aggiungere l'icona ☀ / ☾ (sole = pre-market, luna = after-market) accanto alla data della riga "prossima" nella tabella trimestrale del componente `FundamentalsCard`, replicando il segnale già usato negli `EventChip` del calendario.

L'icona aiuta l'utente a capire a colpo d'occhio se la prossima earnings sarà rilasciata prima dell'apertura o dopo la chiusura della sessione, senza dover aprire il calendario.

## §2 Vincoli

- **Logica condivisa con calendario**: la classificazione pre/after è country-aware (US: pre <14:00 UTC, after ≥20:00; UK: pre <8:00, after ≥16:30). La funzione esistente in `calendar_service.py:_classify_session_timing` deve essere riusata, non duplicata.
- **Nessuna logica frontend**: il frontend deve solo renderizzare l'icona dato il valore `"pre"|"after"|null` ricevuto dal backend.
- **Backward compatible**: il campo è opzionale; se assente o null l'icona non viene renderizzata.
- **Nessuna nuova dipendenza** (né npm né pip).

## §3 Out of scope

- Esposizione raw del `next_earnings_time_utc` lato API (mantenuto interno).
- Tooltip che mostri l'orario esatto delle earnings — solo il pittogramma + title statico ("Pre-market: earnings rilasciati prima dell'apertura della sessione" / equivalente per after).
- Aggiungere l'icona in altri punti della UI (StockHeader, sidebar, pagine market) — task separato se necessario.

## §4 Architettura

### §4.1 Modulo backend condiviso

Spostare `_classify_session_timing` da `backend/app/services/calendar_service.py` a nuovo modulo:

```
backend/app/services/earnings_session_timing.py
    └─ classify_session_timing(time_utc: str | None, country: str | None) -> Literal["pre","after"] | None
```

`calendar_service.py` importa la funzione dal nuovo modulo. Nessun cambio di logica, solo refactor di posizione per evitare import circolari (l'API `stocks.py` non può importare da `calendar_service` perché `calendar_service` già importa dal `stock_fundamentals_service`).

### §4.2 Schema API

In `backend/app/schemas/stock_detail.py`, aggiungere a `FundamentalsBundleOut`:

```python
next_earnings_when: Literal["pre", "after"] | None = None
```

Posizionato vicino a `next_earnings_date`, `next_eps_estimate`, `next_revenue_estimate`.

### §4.3 Endpoint

In `backend/app/api/stocks.py` (al sito di assembly del bundle, attualmente intorno a L279):

```python
from app.services.earnings_session_timing import classify_session_timing

# ... dopo aver caricato `f` (FundamentalsData) e `stock` (Stock)
next_earnings_when = classify_session_timing(
    f.next_earnings_time_utc, stock.country
)
```

E aggiungerlo a `FundamentalsBundleOut(...)`.

### §4.4 Frontend types

In `frontend/src/api/types.ts`:

```typescript
export interface FundamentalsBundle {
  // ... campi esistenti
  next_earnings_date: string | null;
  next_earnings_when?: "pre" | "after" | null;
  next_eps_estimate: number | null;
  next_revenue_estimate: number | null;
}
```

### §4.5 Rendering icona

In `frontend/src/components/stock/FundamentalsCard.tsx`, `QuarterlyTabBody`:

- Aggiungere prop `nextEarningsWhen: "pre"|"after"|null` (passata dal parent come `f.next_earnings_when ?? null`).
- Nella riga "prossima" (intorno a L398), accanto a `{shortDate(nextEarningsDate!)}`, renderizzare lo stesso markup di `EventChip.tsx:109-126`:

```tsx
{nextEarningsWhen === "pre" && (
  <span className="text-[11px] leading-none shrink-0 ml-1"
        title="Pre-market: earnings rilasciati prima dell'apertura della sessione"
        aria-label="pre-market">☀</span>
)}
{nextEarningsWhen === "after" && (
  <span className="text-[11px] leading-none shrink-0 ml-1 opacity-80"
        title="After-market: earnings rilasciati dopo la chiusura della sessione"
        aria-label="after-market">☾</span>
)}
```

## §5 Test

### §5.1 Backend

Nuovo file `backend/tests/test_stock_detail_earnings_when.py` con i casi:

| Input `time_utc` | Country | Expected |
|---|---|---|
| `"13:30"` | `"US"` | `"pre"` |
| `"20:30"` | `"US"` | `"after"` |
| `"16:00"` | `"US"` | `None` (intra-session, edge case) |
| `"07:00"` | `"GB"` | `"pre"` |
| `"17:00"` | `"GB"` | `"after"` |
| `None` | `"US"` | `None` |
| `"13:30"` | `None` | `None` |

Più un test di integrazione che chiama `/api/stocks/{ticker}/bundle` con un fundamentals mockato e verifica che `next_earnings_when` arrivi correttamente nel JSON.

### §5.2 Frontend

Nessun test automatico (frontend non ha test files). Verifica visuale:
1. Open Stock Detail di un ticker US con earnings post-close → riga "prossima" mostra ☾.
2. Open di un ticker .L con earnings AM → mostra ☀.
3. Open di uno senza orario disponibile → nessuna icona, layout invariato.

## §6 Rilasciabilità

Una sola PR auto-contained. Nessuna migration. Nessun cambio runtime in produzione (backend restart sufficiente).

## §7 Ordine implementazione (dipendenze)

1. Creare `earnings_session_timing.py` con la funzione spostata.
2. Aggiornare `calendar_service.py` a importare dal nuovo modulo.
3. Eseguire pytest per assicurarsi che il calendario funzioni ancora.
4. Aggiungere il campo allo schema `FundamentalsBundleOut`.
5. Popolare il campo in `stocks.py`.
6. Test backend nuovi.
7. Aggiornare `frontend/src/api/types.ts`.
8. Modificare `FundamentalsCard.tsx`.
9. `npm run build` per verificare typecheck.
10. Verifica manuale via browser.
