# Plan #3 — Actual-value sign tinting (calendar earnings table + macro strip) — Design Spec

**Data**: 2026-05-08
**Stato**: design approvato (auto-progressione autorizzata dall'utente)
**Tipo**: piccola modifica visuale frontend, nessun dato backend cambiato

---

## §1 Obiettivo

Estendere la colorazione verde/rossa basata sul segno della sorpresa — oggi
applicata solo alla cella "Sorpresa" — anche al **valore "Ultimo"** quando
è il dato post-release (un `actual_value` per le macro, un `eps_reported`
per le earnings), in modo che l'utente colga il segno della sorpresa già
nella cifra principale, senza dover leggere la pct di Sorpresa.

## §2 Ambito

Una sola surface: `frontend/src/components/calendar/DayDetailPanel.tsx`.

Due punti di modifica nello stesso file:
- La cella `"Ultimo"` della tabella earnings (riga `<NumCell value={formatEps(event.eps_reported)} />` ~L578).
- Il valore mostrato nello slot `"Ultimo"` della MacroInsightStrip (~L756).

## §3 Vincoli

- **Convenzione di segno**: verde quando `actual > expected`, rosso quando
  `actual < expected`. Letterale, simmetrica con "Sorpresa". Lasciamo
  fuori scope la semantica invertita per indicatori contrarian (CPI,
  unemployment claims) — richiederebbe metadata per indicator.
- **Pre-release**: per le macro, lo slot "Ultimo" mostra `prev_value`
  con la label "(prec.)" come fallback. In questo caso il valore resta
  neutro (no green/red) perché non c'è una sorpresa da rappresentare.
- **Mancanza di expected**: se `actual` esiste ma `expected` è null,
  la colorazione non si attiva (no segno comparabile).
- **Riusare `signedTone()`** esistente, no nuovi helper.

## §4 Out of scope

- Backend: nessun cambio. Il dato `actual_value` / `eps_reported` arriva
  già correttamente dall'API.
- Earnings table colonne nuove: già ci sono Ultimo + Atteso + Sorpresa.
- Indicator-specific sign semantics (CPI invertito, ecc.).
- Tooltip enhancement: il tooltip su "Sorpresa" già spiega il calcolo;
  non serve duplicarlo su "Ultimo".

## §5 Architettura

### §5.1 Earnings row (~L577-585)

Modifica atomica:

```tsx
// Prima
<NumCell value={formatEps(event.eps_reported)} />

// Dopo
<NumCell
  value={formatEps(event.eps_reported)}
  tone={
    event.eps_reported != null && event.eps_estimate != null
      ? signedTone(event.eps_reported - event.eps_estimate)
      : undefined
  }
/>
```

`signedTone()` esiste già (usato da "Sorpresa" alla riga successiva). `NumCell`
accetta `tone` come prop opzionale. Se `tone` è `undefined`, la cella resta
neutra (comportamento attuale).

### §5.2 Macro "Ultimo" slot (~L756-767)

Avvolgo lo `<span>` esistente con un `className` condizionale:

```tsx
// Prima
<span className="font-bold tabular-nums text-foreground">
  {actual != null ? formatMacroValue(actual, unit) : ...}
</span>

// Dopo
<span
  className={cn(
    "font-bold tabular-nums",
    actual != null && expected != null
      ? actual > expected
        ? "text-emerald-600 dark:text-emerald-400"
        : actual < expected
          ? "text-rose-600 dark:text-rose-400"
          : "text-foreground"
      : "text-foreground",
  )}
>
  {actual != null ? formatMacroValue(actual, unit) : ...}
</span>
```

`cn()` è già importato nel file (utility di shadcn).

## §6 Test

Frontend non ha test runner attivo (vitest installato, zero test files).
Verifica:
1. `npx tsc -b` clean.
2. `npm run build` clean.
3. Visual: aprire calendario e cliccare un giorno con earnings post-release
   (es. trimestre Q1 2026 di un US ticker grande). Confermare che la cella
   "Ultimo" è verde/rossa coerentemente con "Sorpresa".
4. Visual: aprire un evento macro con `actual` pubblicato (es. CPI release
   degli ultimi 30 giorni). Confermare che il valore "Ultimo" è colorato.
5. Spot check pre-release: macro futuro con solo `prev_value` → "Ultimo"
   resta neutro con "(prec.)".

## §7 Rilascio

Una sola modifica al file `DayDetailPanel.tsx`. Single commit. Nessuna
migration, nessuna nuova dipendenza. Compatibile back/forward con qualsiasi
stato del backend.
