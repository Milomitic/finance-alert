# Ipotesi sulla volatilità — esito (FA-153)

Pre-registrazione: [2026-11-ipotesi-volatilita.md](2026-11-ipotesi-volatilita.md).
L'analisi è eseguita il 2026-11-15 da
`backend/scripts/studio_taratura/ipotesi_volatilita.py`, sul replay
rigenerato lo stesso giorno (450 titoli, 2016-2026).

## Esito: nulla

Nessuna delle quattro condizioni è soddisfatta. Anche il **segno** è quello
opposto all'ipotesi: i match sul terzile più volatile battono il proprio
controllo leggermente **di più** degli altri, non di meno.

| | n | D (punti %) | blocchi | t sui blocchi |
|---|---:|---:|---:|---:|
| Tutto | 80.019 | **+0,30** | 32 | 1,74 |
| Titoli pari | 42.144 | +0,18 | 32 | 1,18 |
| Titoli dispari | 37.875 | +0,43 | 32 | 1,59 |
| Senza squeeze_expansion e gap_and_go | 68.256 | +0,40 | 32 | 1,90 |

D = eccesso medio contro il controllo nel terzile alto, meno quello negli altri
due. L'ipotesi chiedeva D < 0 con t < −2,6.

Il segno di D per anno è negativo nel 2018, 2021, 2022 e 2023, cioè in
**4 anni su 8** (la soglia era 6). Il 2025 vale +1,97 punti e il 2020 +1,08.

## Cosa non dice

- **Non** dice che i segnali sui titoli volatili siano migliori. +0,30 punti con
  t 1,74 su 32 blocchi sta dentro la banda del caso, e lo stesso numero col
  segno cambiato sarebbe stato altrettanto poco.
- La lettura dal vivo che aveva suggerito l'ipotesi non trova conferma sullo
  storico: con ogni probabilità erano pochi mesi di un regime.
- Per detector, il più negativo è candle_reversal (−0,38, t −2,18); il più
  positivo è trend_pullback (+1,09, t 2,30). Sono 13 confronti senza
  correzione per i test multipli, nessuno supera 2,6 e non erano ipotesi
  pre-registrate. Restano descrizione, e cercarvi una regola sarebbe la regola
  B dello studio condizionale.

## Scostamento dalla lettera, dichiarato

Il controllo di FA-139 esclude i titoli con un alert dello stesso detector
entro 5 giorni. Nel replay i segnali si conoscono solo per i 450 titoli
campionati, quindi l'esclusione vale solo per quelli. Lo scostamento può solo
far somigliare i controlli ai segnali, cioè diluire D, e non cambia un esito
nullo.

## Conseguenza

La voce si chiude. Nessun cancello `passa_volatilita`, e nessuna seconda
variabile di volatilità provata sugli stessi dati.
