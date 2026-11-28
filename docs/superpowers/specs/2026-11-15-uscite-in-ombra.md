# Uscite alternative in prova silenziosa (FA-141) — criterio scritto prima dei dati

## Perché

Sui piani a finestra chiusa, 322 stop su 2.238 erano passati da +1R prima di
chiudere in perdita, e 808 «scaduti» su 5.021 anche. Una regola d'uscita
diversa forse avrebbe tenuto parte di quel guadagno. Oppure lo avrebbe pagato
altrove, chiudendo a pareggio trade che poi andavano a target. I numeri sopra
mostrano solo il lato che fa sembrare buona l'idea, quindi non bastano per
decidere.

## Che cosa gira

`uscite_ombra_service.matura`, a fine scansione dopo i piani, scrive in
`plan_outcomes_ombra` una riga per (alert, variante) sui piani a **finestra
chiusa**. Ogni riga usa la stessa geometria della riga di `plan_outcomes`:
ingresso, stop iniziale, primo target, orizzonte.

| Variante | Regola |
|---|---|
| `attuale` | quella di oggi, ricalcolata: è il controllo di parità |
| `pareggio_1r` | dopo +1R di escursione favorevole lo stop va all'ingresso |
| `pareggio_05r` | lo stesso dopo +0,5R |
| `uscita_meta` | a metà orizzonte si esce alla chiusura se il trade vale meno di +0,25R |

Le convenzioni sono tre, tutte pessimiste:
- stop e target nella stessa barra contano come stop;
- lo stop si sposta dalla barra **successiva** a quella che tocca la soglia;
- l'uscita a metà orizzonte avviene alla chiusura.

Nessun consumatore a schermo.

## Come si legge

    kubectl exec -n finance-alert finance-alert-finance-alert-0 -- \
        python -m app.scripts.rapporto_uscite_ombra

Per ogni variante, e per detector, il rapporto riporta:
- la **differenza appaiata** in R rispetto ad `attuale` sugli stessi trade;
- le **finestre indipendenti** (blocchi di tempo lunghi un orizzonte, per data
  d'ingresso);
- il t sulle medie per blocco;
- lo stesso confronto sul **controllo casuale**: la stessa geometria, espressa
  in ATR(14) del titolo del segnale, applicata alla stessa data a cinque
  titoli scelti a caso con un seme riproducibile. I risultati si riassumono
  nella mediana della differenza.

La parità va controllata per prima: `attuale` deve coincidere con
`plan_outcomes.r_multiple` sulle stesse righe. Se non coincide, il resto del
rapporto non vale.

## Criterio d'adozione

Una variante sostituisce la regola attuale solo se valgono **tutte** queste
condizioni:

1. **Replay decennale, fuori campione** (`backend/scripts/studio_taratura/`):
   - differenza appaiata media > 0;
   - stesso segno su entrambi i gruppi disgiunti di titoli;
   - stesso segno in almeno 6 anni su 8;
   - t sui blocchi di tempo > 2,6 (la banda del caso misurata nello studio del
     23 settembre, non 2).
2. **Dal vivo, dopo almeno sei mesi da oggi** (non prima del 2027-05-15):
   - differenza appaiata media > 0;
   - almeno 20 finestre indipendenti nel piano breve, 6 nel medio;
   - nessun detector con differenza negativa e t < −2.
3. **Il vantaggio è dei segnali, o comunque non è un artefatto della
   convenzione.** Se la variante migliora anche il controllo casuale della
   stessa quantità, il guadagno sta nella regola d'uscita e non nei segnali.
   È comunque un guadagno per chi segue il piano, ma va scritto così. Se
   invece migliora i segnali e **peggiora** il controllo, va sospettata la
   convenzione «dalla barra successiva»: prima di adottarla si rimisura con
   barre intraday su un campione.

Una variante che non passa si scrive e si chiude. Non si cerca una quinta
variante dentro gli stessi dati: sarebbe la regola B dello studio
condizionale.

## La variante del modello di volatilità (FA-155, aggiunta il 2026-11-15)

`vol_modello` usa la regola di oggi, con le distanze di stop e target
moltiplicate per `snapshot.first_ombra.vol.fattore`. È la stima del modello in
prova di quanto si muoverà il titolo rispetto al suo ATR, quindi la geometria
risulta espressa in «ATR del modello» invece che nell'ATR. Esiste solo per gli
alert che hanno il fattore, cioè quelli nati dal 2026-09-24 in poi.

⚠️ La scala vale per **tutta** la distanza dello stop, anche quando il piano
la ricava da un livello strutturale (l'invalidazione del detector) e non
dall'ATR. È un'approssimazione dichiarata. Se la variante supera il criterio,
prima di adottarla si rifà la geometria dentro `trade_plan`, dove la parte
strutturale e quella di volatilità sono separate.

Il criterio è quello delle altre varianti, più il vincolo già scritto per
FA-155: niente prima di marzo 2027, e solo se la lettura dal vivo di
`rapporto_modelli_ombra` conferma R² > 0 contro l'ATR.

## Le uscite di chi chiude a mano (FA-206, aggiunte il 2026-11-28, prima dei dati)

Le posizioni non sono automatiche: l'utente le può chiudere prima. Un target
mancato di poco va bene comunque, e conta il profitto raggiunto prima
dell'inversione. Le tre varianti sotto traducono quel modo di operare in
regole misurabili. Sono scritte qui prima di eseguire il replay.

| Variante | Regola |
|---|---|
| `restituz_50` | dopo che il massimo favorevole ha coperto il 50% del tragitto verso TP1, si esce alla chiusura se il prezzo ha restituito metà del guadagno massimo |
| `restituz_75` | lo stesso, attivata dal 75% del tragitto |
| `presa_75` | si esce alla chiusura appena questa supera il 75% del tragitto verso TP1 |

Convenzioni: stop e target della barra si guardano per primi, quindi lo stop
vince ancora nella stessa barra e il target vince sulla presa. Il massimo
della barra entra nel picco prima della decisione, perché alla chiusura è già
noto. L'uscita avviene alla chiusura, senza attrito; il replay riporta anche
5 punti base sul nozionale della chiusura anticipata.

Il criterio d'adozione è quello sopra, senza sconti. Si aggiunge una cosa:
le tre varianti nuove sono tre ipotesi in più sulla stessa storia. Con le
cinque precedenti fanno otto, e una sola che passi a t 2,6 va letta con quel
numero davanti. Il replay riporta per ciascuna anche **da dove viene** la
differenza: quanto si guadagna sugli stop evitati e quanto si perde sui
target accorciati.

### Replay del 28 novembre 2026: nessuna delle tre batte il piano fisso

`python -m scripts.studio_taratura.uscite_discrezionali` (da `backend`), sugli
stessi 108.138 piani del replay del percorso (450 titoli, ingressi dal
2017-05-10 al 2026-10-15). La parità con la gara ordinaria è verificata su
ogni piano.

| Variante | Uscite anticipate | Δ R a 21 sedute (t blocchi) | Δ R a 63 sedute (t) | Anni positivi | Dev. std di R |
|---|---:|---:|---:|---:|---:|
| piano fisso | — | — | — | — | 1,181 |
| `restituz_50` | 23.485 | −0,0034 (−1,07) | −0,0124 (−0,97) | 2 su 10 | 1,052 |
| `restituz_75` | 7.790 | −0,0011 (−0,78) | −0,0046 (−0,96) | 2 su 10 | 1,136 |
| `presa_75` | 18.090 | +0,0039 (+2,34) | +0,0016 (+0,84) | 5 su 10 | 1,141 |

**Da dove viene la differenza.** `restituz_50` guadagna in media +0,16 R su
ciascuno dei 45.524 stop, e perde −0,45 R su ciascuno dei 17.863 TP1
completati. Le due somme quasi si annullano: +7.419 R contro −8.100 R. Vale
anche per le altre due, in proporzione minore. La regola che salva gli stop è
la stessa che accorcia i target, perché le barre giornaliere non sanno quale
dei due ritracciamenti è quello buono.

**Verdetto.** Nessuna passa il criterio. `presa_75` è la più vicina: positiva
a 21 sedute, ma con t 2,34 sotto la banda del caso di 2,6, un gruppo di titoli
a 1,51, e 5 anni positivi su 10 invece di 6 su 8. Con l'attrito di 5 punti
base scende a +0,0026 e +0,0000.

**Che cosa vuol dire per chi chiude a mano.** Chiudere prima non costa in
media, ma non rende nemmeno. L'attesa resta la stessa entro pochi millesimi
di R, mentre si scambia varianza con frequenza di vincita: `restituz_50` porta
la quota di trade in utile dal 42,5% al 48,8% e la deviazione standard da
1,18 a 1,05 R. È una scelta di comodità e di rischio, non di rendimento.

Le tre varianti restano in prova silenziosa nel magazzino vivo, insieme alle
altre, fino al confronto dal vivo previsto dal punto 2 del criterio.
