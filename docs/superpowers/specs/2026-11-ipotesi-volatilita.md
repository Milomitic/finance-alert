# Ipotesi sulla volatilità — pre-registrazione (FA-153)

Scritta il 2026-11-15, **prima** di rigenerare il replay e prima di guardare
qualunque dato su questa ipotesi. Il commit che porta questo file precede
quello dei risultati: è la prova che criterio e soglie non sono stati scelti
dopo.

## L'ipotesi

Dai dati dal vivo viene una sola ipotesi nuova: i segnali nati su titoli molto
volatili rendono meno. Formulata in modo verificabile:

> Tra i match che lo scan emetterebbe, quelli sul **terzile più volatile**
> (`atr_pct` = ATR(14) / chiusura alla barra d'emissione) battono il proprio
> controllo **meno** dei match sugli altri due terzili.

L'ipotesi riguarda la **bravura del segnale** e non il premio della
volatilità. Il controllo è abbinato sulla volatilità, quindi un titolo
volatile che sale di più perché è volatile non conta.

## Popolazione

Replay decennale di `backend/scripts/studio_taratura/` (`replay_ml.py`),
popolazione **`ep_live`**: i match che passano i cancelli di oggi, cioè quelli
che sarebbero diventati alert. `adx_confirmation` resta fuori, perché non
emette. Sono escluse le barre non negoziate (`app.signals.negoziazione`), come
nello studio del 23 settembre.

## Variabile

`atr_pct` alla barra d'emissione. I terzili si calcolano a **finestra
espandibile**: i tagli di una data usano solo gli `atr_pct` dei match con data
**strettamente precedente**. Una data con meno di 500 match precedenti non
entra. Un taglio calcolato su tutto il campione metterebbe il futuro
nell'etichetta: è l'invariante 1 dello studio condizionale.

## Esito

Per ogni match, all'**orizzonte proprio del detector**
(`signal_drift_service._horizon_days`):

    eccesso = (rendimento del titolo − mediana dei rendimenti di 5 controlli) × segno del tono

I 5 controlli sono titoli con una barra lo stesso giorno e nello **stesso
terzile di volatilità a 20 sedute** del giorno, scelti con un seme
riproducibile (`esiti_orizzonti_service.ordine_dei_controlli`, seme = indice
della riga). Con meno di 5 candidati il match non entra. È il controllo di
FA-139, applicato al replay.

Gli orizzonti 5 e 21 si riportano come descrizione. Il verdetto si dà solo
all'orizzonte proprio: scegliere dopo il migliore fra tre sarebbe la regola B
dello studio condizionale.

## Statistica

    D = media(eccesso | terzile alto) − media(eccesso | terzili bassi)

- **Blocchi di tempo**: la data d'ingresso si divide in blocchi lunghi un
  orizzonte, con la copertura greedy di `independent_blocks` e l'orizzonte del
  detector più lungo nel gruppo. In ogni blocco si calcola D_b. Il t di Student
  si calcola sui D_b.
- **Gruppi disgiunti di titoli**: `stock_id` pari e `stock_id` dispari, fissati
  qui.
- **Anni**: gli anni solari 2018-2025, otto. Il 2017 resta fuori perché i
  terzili non hanno ancora una storia sufficiente; il 2026 resta fuori perché è
  incompleto.

## Soglia di conferma

L'ipotesi è **confermata** solo se valgono tutte e quattro le condizioni:

1. D < 0 sul campione intero, con t sui blocchi < −2,6. È la banda del caso
   misurata il 23 settembre, non ±2.
2. D < 0 su **entrambi** i gruppi di titoli (pari e dispari).
3. D < 0 in **almeno 6 anni su 8**.
4. Le condizioni 1-3 reggono anche **escludendo** `squeeze_expansion` e
   `gap_and_go`, i due detector con la quota più alta di titoli volatili. Un
   effetto portato da un solo detector è un fatto sul detector, non sulla
   volatilità.

Altrimenti l'ipotesi è **nulla**.

## Esiti possibili

- **Nulla**: si scrive il risultato in
  `docs/superpowers/specs/2026-11-ipotesi-volatilita-esito.md` e la voce si
  chiude. Non si prova una seconda variabile di volatilità sugli stessi dati.
- **Confermata**: si propone un cancello **in prova silenziosa**. Lo scan
  registra in `signal_candidates` un quarto esito, `passa_volatilita`, senza
  cambiare l'emissione. Si adotta solo dopo sei mesi dal vivo con lo stesso
  segno e le stesse condizioni 1-2 sui dati nuovi.
