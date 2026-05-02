# Fase 3C — Indicatori avanzati + regole composite + Rule Editor UI — Design Spec

**Data**: 2026-05-02
**Stato**: design approvato (auto-progressione autorizzata dall'utente)
**Tipo**: estensione capability dell'alert engine + nuova UI di configurazione regole

---

## §1 Obiettivo

Aggiungere al motore di alert:
- **Nuovi indicatori tecnici**: MACD, Bollinger Bands, ATR, ADX (oltre a SMA/RSI/EMA esistenti)
- **Nuove regole alert atomiche**: `volume_spike`, `breakout`, `macd_bullish_cross`, `macd_bearish_cross`, `bollinger_squeeze`, `bollinger_breakout`
- **Composizione AND/OR**: una Rule può ora valutare un'espressione ad albero che combina più condizioni (es. `RSI<30 AND volume>2× AND price > SMA200`)
- **Rule Editor UI**: nuova pagina `/rules` con lista regole esistenti + form di creazione/modifica con tree-builder per expression composite

L'utente vuole superare i 4 segnali atomici hardcoded di Fase 1+2 verso un sistema flessibile che permette di esprimere strategie reali (es. "compra quando RSI rimbalza E volume conferma E trend lungo è rialzista").

## §2 Vincoli

- **Single-user, local-first** Windows
- **Backward compatible** con regole esistenti (Tier 1 globali e Tier 2 per-watchlist) — nessuna migrazione dati richiesta, le regole pre-3C continuano a funzionare invariate
- **Non rompere** scan_service, alert engine, dashboard, Stock Detail, price alerts (3B)
- **Stack invariato**: pandas/numpy per indicatori, FastAPI/SQLAlchemy backend, React/shadcn frontend
- **Nessuna nuova dipendenza npm** — il rule tree builder usa shadcn esistenti (Card, Button, Select, Input)
- **Edge-trigger semantics** preservate: una rule firea un Alert solo quando passa da False a True tra due valutazioni successive (riusa esistente `RuleState`)

## §3 Out of scope (rimandati esplicitamente)

- Backtest sulle nuove regole composite → Fase 3E
- Hit-rate stats per regola → Fase 3E
- Indicatori intraday (tutto resta EOD su OHLCV daily)
- Editor visuale "drag-and-drop" stile no-code — l'editor è form-based gerarchico
- Regola `composite` salvabile come template riusabile → fuori scope (ogni Rule è standalone)
- Tier 3 vero (override di regole composite per-stock) — fuori scope come confermato in 3B

## §4 Stack additions

Nessuna nuova dipendenza. Tutti i 4 nuovi indicatori sono implementabili con pandas/numpy.

## §5 Modello dati

### Modifica tabella `rules`

Aggiungere un singolo campo nullable:

```python
class Rule(Base):
    # ... campi esistenti
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)
```

`expression` è una stringa JSON che, se valorizzata, prende **precedenza** su `kind`+`params` durante la valutazione. Se `expression IS NULL`, lo scan engine usa il legacy path (`kind`+`params`) come oggi — backward compat totale.

### Schema dell'albero di expression

```jsonc
// Atomic node (foglia)
{
  "op": "atomic",
  "kind": "rsi_oversold",     // uno dei kind in RULES registry
  "params": {"period": 14, "threshold": 30}
}

// Composite node (internal AND/OR)
{
  "op": "and",                 // | "or"
  "children": [
    { "op": "atomic", "kind": "rsi_oversold", "params": {...} },
    { "op": "atomic", "kind": "volume_spike", "params": {"threshold": 2.0} },
    { "op": "or",
      "children": [
        { "op": "atomic", "kind": "breakout", "params": {"period": 20} },
        { "op": "atomic", "kind": "macd_bullish_cross", "params": {} }
      ]
    }
  ]
}
```

Vincoli:
- Profondità albero massima: 5 livelli (validazione client+server)
- Numero massimo nodi atomici per albero: 8 (evita expression patologiche)
- Atomic node `kind` deve esistere nel `RULES` registry, altrimenti errore in evaluate

### Migration

`backend/alembic/versions/<auto>_add_rule_expression.py`:
```python
def upgrade():
    with op.batch_alter_table("rules") as batch_op:
        batch_op.add_column(sa.Column("expression", sa.Text(), nullable=True))

def downgrade():
    with op.batch_alter_table("rules") as batch_op:
        batch_op.drop_column("expression")
```

## §6 Nuovi indicatori

Quattro moduli puri sotto `backend/app/indicators/`:

### `macd.py`
```python
def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram).
    macd_line = EMA(close, fast) - EMA(close, slow)
    signal_line = EMA(macd_line, signal)
    histogram = macd_line - signal_line"""
```

### `bb.py` (Bollinger Bands)
```python
def bollinger(close: pd.Series, period: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, middle, lower). middle=SMA, upper/lower=middle ± k·stddev."""

def bb_width(close: pd.Series, period: int = 20, k: float = 2.0) -> pd.Series:
    """Width = (upper - lower) / middle. Used for squeeze detection."""
```

### `atr.py` (Average True Range)
```python
def atr(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ATR using true range = max(high-low, |high-prev_close|, |low-prev_close|)."""
```

### `adx.py` (Average Directional Index)
```python
def adx(ohlcv: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (adx, plus_di, minus_di). Standard Wilder formula."""
```

Ogni modulo ha test unit `tests/test_indicators_<name>.py` con OHLCV deterministico e valori attesi.

## §7 Nuove regole atomiche

Sei nuove classi in `backend/app/rules/`:

### `volume_rules.py`
- `VolumeSpikeRule(kind="volume_spike", default_params={"window": 20, "threshold": 2.0})` — `volume_today / mean(volume[-window:]) > threshold`

### `breakout_rules.py`
- `BreakoutRule(kind="breakout", default_params={"period": 20})` — `close_today > max(close[-period:-1])` (escluso bar corrente)

### `macd_rules.py`
- `MacdBullishCrossRule(kind="macd_bullish_cross", default_params={"fast": 12, "slow": 26, "signal": 9})` — macd_line oggi > signal AND macd_line ieri ≤ signal ieri (cross verso l'alto)
- `MacdBearishCrossRule(kind="macd_bearish_cross", ...)` — simmetrica

### `bollinger_rules.py`
- `BollingerSqueezeRule(kind="bollinger_squeeze", default_params={"period": 20, "k": 2.0, "lookback": 50, "percentile": 0.20})` — BB width oggi è nel percentile più basso degli ultimi `lookback` giorni (compressione di volatilità)
- `BollingerBreakoutRule(kind="bollinger_breakout", default_params={"period": 20, "k": 2.0, "direction": "either"})` — close oggi sopra upper (`upper`) o sotto lower (`lower`) o entrambi (`either`)

Tutte registrate in `app/rules/registry.py` aggiungendole al dict `RULES`.

Ogni rule espone `evaluate()` (bool) e `snapshot()` (dict JSON-serializzabile) come quelle esistenti.

## §8 Composition evaluator

Nuovo modulo `app/rules/composite.py`:

```python
def evaluate_expression(node: dict, ohlcv: pd.DataFrame) -> bool:
    """Walk the expression tree and return True iff the tree evaluates to True
    on the last OHLCV bar.

    Validates structure inline: missing 'op' or invalid kind raises ValueError.
    """
    op = node.get("op")
    if op == "atomic":
        kind = node["kind"]
        if kind not in RULES:
            raise ValueError(f"Unknown rule kind in expression: {kind}")
        return RULES[kind].evaluate(ohlcv, node.get("params", {}))
    elif op == "and":
        return all(evaluate_expression(c, ohlcv) for c in node["children"])
    elif op == "or":
        return any(evaluate_expression(c, ohlcv) for c in node["children"])
    else:
        raise ValueError(f"Invalid expression op: {op!r}")


def snapshot_expression(node: dict, ohlcv: pd.DataFrame) -> dict:
    """Return a snapshot tree mirroring the expression structure, with each
    atomic node augmented with its computed snapshot values."""
    # ... recursive walk, returns { op, kind?, params?, snapshot?, children?: [...] }


def validate_expression(node: dict, *, max_depth: int = 5, max_atomic: int = 8) -> None:
    """Raise ValueError if tree violates structural constraints. Used by
    POST/PATCH /api/rules to reject malformed input early."""
```

Modifica a `scan_service.scan_universe` (path resolver):
```python
def _evaluate_rule(rule: Rule, ohlcv: pd.DataFrame, eff_params: dict) -> bool:
    if rule.expression:
        return evaluate_expression(json.loads(rule.expression), ohlcv)
    rule_obj = RULES.get(rule.kind)
    if rule_obj is None:
        return False
    return rule_obj.evaluate(ohlcv, eff_params)
```

`Alert.snapshot` per regole composite contiene il tree snapshot completo (utile per debugging in UI).

## §9 API surface

### Endpoint estesi (modello già esiste)

`POST /api/rules`, `PATCH /api/rules/{id}`:
- Body può ora includere `expression: object | null`
- Validazione: se `expression` presente, valida struttura tree (depth, atomic count, kind validi)
- Se `expression` valorizzata, `kind` può essere settato a `"composite"` per chiarezza UI (ma non è strettamente necessario perché evaluator ignora `kind` quando `expression` non è null)

### Nuovo endpoint: preview

`POST /api/rules/preview` — body `{ expression: object, ticker: string }` → response `{ matched: boolean, snapshot: object }`

Carica gli ultimi 252 bar OHLCV dello stock, valuta l'expression, ritorna risultato + snapshot ad albero. Permette all'utente di testare una regola in costruzione contro uno stock noto.

### Endpoint catalog (helper UI)

`GET /api/rules/catalog` → `[{ kind, label, description, default_params, params_schema }]` per ogni atomic kind nel registry. Permette al frontend di costruire dinamicamente i form senza hardcoding.

`params_schema` è un mini-schema JSON tipo `{ "period": { "type": "int", "min": 2, "max": 200, "default": 14 } }`. Generato dalle classi rule via metodo `params_schema()` (nuovo, opzionale — fallback a default_params se assente).

## §10 Frontend Rule Editor

### Nuova pagina `/rules`

Layout:
```
┌─────────────────────────────────────────────────────────────┐
│ HEADER: Regole alert                          [+ Nuova regola]│
├─────────────────────────────────────────────────────────────┤
│ TABLE list:                                                  │
│ Stato  Tipo            Watchlist     Condizioni     Azioni  │
│ ☑      RSI Oversold    Globale       atomic         [edit]  │
│ ☑      Composite       FAANG         3 cond.        [edit]  │
│ ☐      Breakout 20d    Globale       atomic         [edit]  │
└─────────────────────────────────────────────────────────────┘
```

Click su `[edit]` o `[+ Nuova regola]` → modal/page con il form:

```
┌─────────────────────────────────────────────────────────────┐
│ EDIT REGOLA                                                  │
│ Nome: [____________]                                         │
│ Scope: ( ) Globale (Tier 1)  (•) Watchlist [select ▾]        │
│ Stato: [☑ Enabled]                                           │
│                                                              │
│ CONDIZIONI:                                                  │
│ ┌─ AND ─────────────────────────────────────┐  [+ AND] [+ OR]│
│ │ ◆ RSI Oversold (period=14, threshold=30) │ [×]            │
│ │ ◆ Volume Spike (window=20, threshold=2)  │ [×]            │
│ │ ┌─ OR ───────────────────────────┐       │                │
│ │ │ ◆ Breakout (period=20)         │ [×]   │                │
│ │ │ ◆ MACD bullish cross           │ [×]   │                │
│ │ └────────────────────────────────┘       │                │
│ └──────────────────────────────────────────┘                │
│                                                              │
│ Anteprima su ticker: [AAPL___] [Test]                        │
│ Risultato: ✗ Non scatta · RSI 58 ✗, Vol 1.2× ✗               │
│                                                              │
│ [Annulla]                                  [Salva]           │
└─────────────────────────────────────────────────────────────┘
```

### Componenti

```
frontend/src/pages/RulesPage.tsx                    — orchestrator (lista + form)
frontend/src/components/rules/RulesTable.tsx        — lista esistenti
frontend/src/components/rules/RuleEditorDialog.tsx  — modal create/edit
frontend/src/components/rules/ExpressionTree.tsx    — tree builder (recorsivo)
frontend/src/components/rules/AtomicConditionForm.tsx — form per singola condizione (kind + params dinamici)
frontend/src/components/rules/ExpressionPreview.tsx — preview button + risultato
```

### Hooks
```
useRules() — list (TanStack Query)
useCreateRule() / useUpdateRule() / useDeleteRule()
useRuleCatalog() — kinds disponibili (5min cache)
useRulePreview() — mutation per POST /preview
```

### Routing
- `/rules` route in `App.tsx`
- Sidebar `Layout.tsx`: voce "Regole" da `enabled: false` → `enabled: true`

## §11 Decomposizione fasi (per implementation plan)

Per ridurre rischio e permettere release intermedie, l'implementazione è decomposta in 3 sotto-fasi atomiche e shippabili indipendentemente:

### **3C-A** — Indicatori avanzati + 6 atomic rules (backend only)
- 4 indicator modules + tests
- 6 rule classes + tests
- Registrazione in RULES registry
- `/api/rules/catalog` endpoint con metadata
- Migration NON necessaria (atomic rules usano kind+params esistenti)

**Deliverable**: utente può creare via API `POST /api/rules` con `kind="volume_spike"` o `kind="macd_bullish_cross"` ecc., e gli alert scattano correttamente.

### **3C-B** — Composition schema + evaluator + preview endpoint (backend only)
- Migration aggiunge `Rule.expression` nullable
- `app/rules/composite.py` (evaluate, snapshot, validate)
- `scan_service` usa expression se presente
- `POST /api/rules/preview` endpoint
- POST/PATCH /api/rules accetta expression con validazione
- Tests

**Deliverable**: API supporta expression composite via JSON body. Backward-compat preservato.

### **3C-C** — Rule Editor UI (frontend only)
- Nuova pagina `/rules` + 5 componenti rule editor
- Hooks per CRUD + preview
- Routing + sidebar attivata

**Deliverable**: utente crea/modifica regole composite con tree builder visuale, fa preview su ticker, salva. La pagina sostituisce il "RulesOverrideEditor" 3-stati esistente nelle WatchlistDetailPage (che resta solo per legacy override).

## §12 Error handling

| Caso | Backend | Frontend |
|---|---|---|
| Expression con `kind` invalido | 422 con messaggio "Unknown rule kind: X" | Error toast + highlight nel form |
| Expression troppo profonda (>5 livelli) | 422 "Expression depth exceeds 5" | Disabilita "+ AND/OR" button quando max depth raggiunto |
| Expression con >8 atomic node | 422 "Too many conditions (max 8)" | Disabilita "+" quando count==8 |
| Preview con ticker inesistente | 404 | "Ticker non trovato" inline |
| Preview con OHLCV insufficiente | 200 con `matched=false`, `snapshot.error="insufficient data"` | Mostra warning |
| Scan crash su composite rule (es. malformed JSON in DB) | Logga error, skip stock per quella rule, continua scan | — |

## §13 Testing strategy

### Backend (pytest)
- `tests/test_indicators_macd.py`, `_bb.py`, `_atr.py`, `_adx.py` — ~3 test ciascuno con OHLCV deterministico
- `tests/test_volume_rules.py`, `_breakout_rules.py`, `_macd_rules.py`, `_bollinger_rules.py` — ~2 test ciascuno (positive + negative case)
- `tests/test_rules_composite.py` — ~6 test (atomic, AND, OR, nested, validation errors, snapshot)
- `tests/test_api_rule_preview.py` — ~3 test (auth, valid expression, invalid expression)
- `tests/test_api_rule_catalog.py` — ~1 test smoke

Target: ~30 nuovi test, totale ~210 passing.

### Frontend
- Build verification (tsc + vite), nessun test runtime UI

### Smoke test E2E manuale
- Login → /rules → "+ Nuova regola" → builder con AND di 2 condizioni → Preview su AAPL → Salva → execute scan → verifica alert in /alerts

## §14 Definition of Done

### 3C-A
- [ ] 4 indicator modules + 12 test passing
- [ ] 6 rule classes registrate, ~12 test passing
- [ ] `/api/rules/catalog` ritorna 10 entries (4 esistenti + 6 nuove)
- [ ] Smoke: POST /api/rules con `kind="volume_spike"` → scan → alert generato

### 3C-B
- [ ] Migration `<hash>_add_rule_expression.py` applicata
- [ ] `evaluate_expression` + `validate_expression` + tests (~6)
- [ ] `scan_service` usa expression con backward-compat
- [ ] POST/PATCH /api/rules accetta expression con validation
- [ ] POST /api/rules/preview funziona

### 3C-C
- [ ] Pagina `/rules` montata, sidebar entry attivata
- [ ] Lista regole + create/edit modal funzionanti
- [ ] Tree builder con AND/OR + atomic, max 5 deep, max 8 atomic
- [ ] Preview button funzionante
- [ ] `npm run build` clean
- [ ] ARCHITECTURE.md aggiornato + push

## §15 Roadmap follow-up (3E+)

Resta fuori da 3C, in fasi future:
- **3E** Settings + hit-rate stats: backtest "questa rule avrebbe generato N alert nei 90gg, di cui M sono saliti del 2% nei 5gg successivi"
- Preset di regole condivise (template library)
- Composizione visuale drag-and-drop
- Notifica via canali alternativi (era 3D — rimossa dal piano)

---

## Appendice A — Rationale design choices

**Perché expression in JSON tree e non tabella relazionale?**
- Albero è naturalmente nested → JSON struttura nativa
- Lettura/scrittura singolo round-trip (no JOIN ricorsivo)
- Migrazione futura a tabella possibile se serve query complesse cross-rule (per ora YAGNI)
- Validazione semplice (validator ricorsivo Python)

**Perché backward-compat invece di migrare le regole esistenti a expression-only?**
- Le 4 regole esistenti (rsi_oversold/overbought, golden/death cross) sono semplici atomic — nessun beneficio nel forzarle a `{op:"atomic", kind:..., params:...}` JSON
- Risk-free: lo scan engine vecchio path continua a funzionare senza tocchi
- Permette refactor incrementale del frontend (legacy 3-stati editor in WatchlistDetail può restare; nuova /rules page ha tree-builder)

**Perché max depth 5 / max atomic 8?**
- Limita complessità delle expression (no infinite trees → no infinite eval)
- 8 condizioni in AND/OR sono già più di quanto qualsiasi strategia retail tipicamente usa
- Limiti facilmente ampliabili in futuro modificando i 2 numeri in `validate_expression`
