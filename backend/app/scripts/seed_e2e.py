"""Semina un catalogo MINIMO e deterministico per il gate di layout end-to-end.

⚠️ Esiste per chiudere «un test puo' essere vero di niente», che questo repo ha
gia' registrato quattro volte. In CI il database e' vuoto: una pagina senza
righe non puo' traboccare, quindi un gate sul layout eseguito su un'app vuota
sarebbe verde per costruzione e non misurerebbe nulla. Gli otto difetti trovati
il 12 settembre 2026 stavano per lo piu' in intestazioni e barre, che si
disegnano anche senza dati — ma non tutti, e il gate deve poter vedere anche
gli altri.

⚠️ I nomi sono LUNGHI apposta. La compressione dell'identita' e' un difetto
ricorrente di questo progetto (audit §4.6, FA-040) e si manifesta solo con
stringhe che non entrano: seminare «Acme Inc» renderebbe il gate cieco
esattamente alla classe che deve sorvegliare. Le valute non sono tutte USD per
lo stesso motivo — 312 titoli su 1010 non sono quotati in dollari e il simbolo
sbagliato e' stato un difetto P1 (FA-025, FA-045).

Niente rete: e' l'unico modo perche' il gate sia riproducibile e veloce.
Idempotente, quindi rieseguirlo non duplica.

    cd backend && PYTHONPATH=. python -m app.scripts.seed_e2e
"""

from __future__ import annotations

import json
import random
import secrets
from datetime import UTC, date, datetime, time, timedelta

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.alert import Alert
from app.models.institutional import Institutional
from app.models.ohlcv import OhlcvDaily
from app.models.stock import Stock
from app.models.user import User
from app.services.institutional_scraper import ScrapedFiling, ScrapedHolding, ScrapedManager
from app.services.institutional_service import (
    compute_qoq_deltas,
    insert_holdings,
    upsert_filing,
    upsert_institutional,
)

#: Ticker, nome, borsa, settore, industria, valuta, market cap (valuta locale).
#: La coda non-USD e i nomi oltre i 30 caratteri sono il carico utile.
CATALOGO = [
    ("AAPL",  "Apple Inc.",                                        "NASDAQ", "Information Technology", "Technology Hardware & Equipment",        "USD", 3_400e9),
    ("TSM",   "Taiwan Semiconductor Manufacturing Company Limited", "NYSE",   "Information Technology", "Semiconductors & Semiconductor Equipment", "USD", 980e9),
    ("HPE",   "Hewlett Packard Enterprise Company",                 "NYSE",   "Information Technology", "Technology Hardware & Equipment",        "USD", 27e9),
    ("SHEL.L", "Shell plc",                                         "LSE",    "Energy",                 "Oil, Gas & Consumable Fuels",            "GBP", 196e9),
    ("BABCK.L", "Babcock International Group PLC",                  "LSE",    "Industrials",            "Aerospace & Defense",                    "GBP", 4.1e9),
    ("0016.HK", "Sun Hung Kai Properties Limited",                  "HKEX",   "Real Estate",            "Real Estate Management & Development",   "HKD", 220e9),
    ("1398.HK", "Industrial and Commercial Bank of China Limited",  "HKEX",   "Financials",             "Banks",                                  "HKD", 1_900e9),
    ("UCG.MI", "UniCredit S.p.A.",                                  "MIL",    "Financials",             "Banks",                                  "EUR", 62e9),
    ("7203.T", "Toyota Motor Corporation",                          "TSE",    "Consumer Discretionary", "Automobiles & Components",               "JPY", 40_000e9),
    ("NTAP",  "NetApp, Inc.",                                       "NASDAQ", "Information Technology", "Technology Hardware & Equipment",        "USD", 23e9),
    ("DELL",  "Dell Technologies Inc.",                             "NYSE",   "Information Technology", "Technology Hardware & Equipment",        "USD", 95e9),
    ("CRGY",  "Crescent Energy Company",                            "NYSE",   "Energy",                 "Oil, Gas & Consumable Fuels",            "USD", 2.3e9),
]

#: Detector reali, con catene lunghe: la colonna «Catena» e' quella che ha
#: prodotto stringhe da 756px su un viewport di 375.
SEGNALI = [
    ("trend_pullback",   "bull", "Vicino al massimo 52 settimane → Trend rialzista → Conferma breakout/volume → Trend ADX in rafforzamento"),
    ("macd_divergence",  "bear", "Incrocio EMA bear → Candela di rifiuto → Rottura neckline → Compressione (squeeze)"),
    ("candle_reversal",  "bull", "Pivot iniziale → Candela di rifiuto → Divergenza RSI confermata"),
    ("structure_break",  "bear", "Doppio massimo → Rottura neckline → Trend ADX in indebolimento"),
    ("high52_momentum",  "bull", "Compressione (squeeze) → Espansione bull → Rifiuto su EMA200 → Candela di rifiuto"),
]

BARRE = 260  # sopra la soglia di 200 di `has_full_data`

# ─── Superinvestor: fondi e posizioni (FA-068) ──────────────────────────────
#
# ⚠️ Prima di questa sezione il seme non scriveva UNA riga in
# `institutional_holdings`, quindi in CI `/institutionals` rendeva tre tabelle
# vuote e il gate misurava cio' che capitava: `scrollable-region-focusable`
# e' passato da 0 a 2 fra due corse a sei minuti di distanza, su una rotta che
# nessun commit aveva toccato. Le tre regioni scorrevoli sono il difetto che il
# gate aveva trovato, e su tabelle vuote NON possono scorrere: il controllo che
# le sorveglia era vero di niente.
#
# Quindi le posizioni sono abbastanza da far scorrere tutte e tre le regioni
# (30rem), e i nomi sono lunghi per la stessa ragione del catalogo sopra.
#
# Tre scelte che non si vedono dai numeri:
#
# 1. Le azioni (new/add/reduce/sold_out) NON sono scritte a mano. Si semina la
#    materia prima — due filing per fondo — e le etichette le calcola
#    `compute_qoq_deltas`, cioe' il codice che le calcola in produzione. Un
#    seme che stampasse le etichette misurerebbe una pagina alimentata da una
#    regola che l'app non applica.
# 2. Niente generatore casuale. Il `rng` del catalogo consuma un'estrazione
#    per barra, e aggiungere estrazioni PRIMA o IN MEZZO sposterebbe l'intera
#    serie di prezzi di tutte le altre pagine — la trappola documentata in
#    `_giorni_feriali`. Qui ogni valore e' aritmetica sugli indici.
# 3. I valori sono in USD perche' un 13F e' in USD per definizione. Le «valute
#    miste» stanno nel CATALOGO a cui le posizioni si agganciano: SHEL.L e
#    0016.HK sono righe non-USD del catalogo, e l'arricchimento per paese e
#    settore passa di li'.

#: Ticker e nome della societa' come compare in un 13F. GOOG e GOOGL sono
#: ENTRAMBE presenti di proposito: il cruscotto le fonde su GOOG, e un fondo che
#: le tiene tutte e due deve contare una volta sola.
TITOLI_13F = [
    ("AAPL",    "Apple Inc."),
    ("TSM",     "Taiwan Semiconductor Manufacturing Company Limited Sponsored ADR"),
    ("BRK-B",   "Berkshire Hathaway Inc. Class B Common Stock"),
    ("MSFT",    "Microsoft Corporation"),
    ("AMZN",    "Amazon.com, Inc."),
    ("GOOG",    "Alphabet Inc. Class C Capital Stock"),
    ("GOOGL",   "Alphabet Inc. Class A Common Stock"),
    ("BABA",    "Alibaba Group Holding Limited American Depositary Shares"),
    ("TCEHY",   "Tencent Holdings Limited Unsponsored American Depositary Receipt"),
    ("SHEL.L",  "Shell plc Ordinary Shares"),
    ("0016.HK", "Sun Hung Kai Properties Limited"),
    ("HPE",     "Hewlett Packard Enterprise Company"),
    ("DELL",    "Dell Technologies Inc. Class C Common Stock"),
    ("NTAP",    "NetApp, Inc."),
    ("OXY",     "Occidental Petroleum Corporation"),
    ("CVX",     "Chevron Corporation"),
    ("KO",      "The Coca-Cola Company"),
    ("V",       "Visa Inc. Class A Common Stock"),
    ("MA",      "Mastercard Incorporated Class A Common Stock"),
    ("UNH",     "UnitedHealth Group Incorporated"),
    ("JNJ",     "Johnson & Johnson"),
    ("META",    "Meta Platforms, Inc. Class A Common Stock"),
]

#: slug, nome, gestore, tipo, fonte, trimestri all'indietro dell'ultimo filing.
#: ⚠️ L'ultimo fondo ha il suo filing piu' recente DUE trimestri indietro: e'
#: la sola riga con la pastiglia «stale», e c'e' per esercitare quel ramo — vedi
#: `_trimestre` sul perche' due e non uno.
FONDI = [
    ("berkshire-hathaway-e2e",     "Berkshire Hathaway Inc. and Subsidiaries Consolidated Equity Portfolio", "Warren Edward Buffett",          "superinvestor", "dataroma",    0),
    ("pershing-square-e2e",        "Pershing Square Capital Management, L.P. Concentrated Long Portfolio",   "William Albert Ackman",          "superinvestor", "dataroma",    0),
    ("himalaya-capital-e2e",       "Himalaya Capital Management LLC Long-Only Value Partnership",            "Li Lu",                          "superinvestor", "dataroma",    0),
    ("vanguard-group-e2e",         "The Vanguard Group, Inc. Total Institutional Equity Holdings",            None,                             "institutional", "sec_13f",     0),
    ("state-street-e2e",           "State Street Global Advisors Trust Company Aggregate 13F Report",         None,                             "institutional", "sec_13f",     0),
    ("renaissance-technologies-e2e", "Renaissance Technologies LLC Medallion-Adjacent Institutional Equities", "Peter Brown",                    "hedge_fund",    "hedgefollow", 0),
    ("baupost-group-e2e",          "The Baupost Group, L.L.C. Opportunistic Value Portfolio (ultimo filing vecchio)", "Seth Andrew Klarman", "superinvestor", "dataroma",    2),
]

#: Posizioni per filing. Con lo slittamento di 2 fra i due filing, ogni fondo
#: ha 2 aperture, 2 uscite e 10 posizioni in comune che crescono, calano o
#: restano ferme a rotazione — cioe' tutte e quattro le azioni, per costruzione.
POSIZIONI_PER_FILING = 12
SLITTAMENTO = 2
FILING_PER_FONDO = 2

#: Deposito 13F: il filing esce fino a 45 giorni dopo la fine del trimestre.
RITARDO_DEPOSITO = 45


def _fine_trimestre(d: date) -> date:
    """L'ultima fine di trimestre <= d."""
    trimestre_mese = ((d.month - 1) // 3) * 3 + 3
    fine = date(d.year, trimestre_mese, 1) + timedelta(days=32)
    fine = fine.replace(day=1) - timedelta(days=1)
    if fine <= d:
        return fine
    # Il trimestre corrente non e' ancora finito: si prende il precedente.
    inizio = date(d.year, trimestre_mese - 2, 1)
    return inizio - timedelta(days=1)


def _trimestre(oggi: date, indietro: int) -> date:
    """La fine di trimestre `indietro` trimestri prima dell'ultimo DEPOSITABILE.

    L'ultimo depositabile e' l'ultima fine di trimestre che ha gia' avuto i 45
    giorni di deposito: un filing il cui periodo e' finito ieri non puo'
    esistere.

    ⚠️ **Perche' il fondo vecchio sta DUE trimestri indietro e non uno.** La
    pagina marca «stale» un fondo il cui ultimo periodo supera i 183 giorni, e
    il cruscotto esclude i filing oltre i 18 mesi. Contando dal primo giorno
    utile, l'eta' del filing piu' recente vale:

        0 trimestri indietro   45 ..  136 giorni   sempre fresco
        1 trimestre  indietro  135 ..  228 giorni   ATTRAVERSA i 183
        2 trimestri indietro  226 ..  320 giorni   sempre stale, sempre < 548

    Un trimestre vale 90-92 giorni, quindi e' UNO indietro a stare a cavallo
    della soglia. Con un trimestre solo, quanti fondi portano la pastiglia
    dipenderebbe dal GIORNO in cui gira il job — la trappola che il seme ha gia' pagato tre volte con
    barre, ancora e data dei segnali. `test_seed_e2e_deterministico.py` scorre
    un anno intero di «oggi» e lo pretende.
    """
    q = _fine_trimestre(oggi - timedelta(days=RITARDO_DEPOSITO))
    for _ in range(indietro):
        q = _fine_trimestre(q - timedelta(days=1))
    return q


def _filing(indice_fondo: int, ordine: int) -> list[tuple[str, str, int, int]]:
    """(ticker, nome, azioni, valore_usd) per un filing, senza estrazioni casuali.

    `ordine` 0 e' il filing PRECEDENTE, 1 il piu' recente. Il precedente e'
    spostato di SLITTAMENTO posizioni, quindi i due non coincidono ai bordi.
    """
    n = len(TITOLI_13F)
    base = indice_fondo * 3 + (SLITTAMENTO if ordine == 0 else 0)
    righe = []
    for k in range(POSIZIONI_PER_FILING):
        i = (base + k) % n
        ticker, nome = TITOLI_13F[i]
        azioni_prima = 1_000 * (i + 1) * (indice_fondo + 1)
        if ordine == 0:
            azioni = azioni_prima
        else:
            # Rotazione sul TICKER, non sulla posizione nel filing: la stessa
            # riga deve cambiare nello stesso verso in entrambi i calcoli.
            azioni = {0: azioni_prima * 125 // 100, 1: azioni_prima * 80 // 100, 2: azioni_prima}[i % 3]
        prezzo = 50 + 37 * i
        righe.append((ticker, nome, azioni, azioni * prezzo))
    return righe


def semina_istituzionali(db, oggi: date) -> int:
    """Fondi, due filing ciascuno, e le azioni calcolate dal codice vero.

    Idempotente: `upsert_filing` cancella e reinserisce le posizioni di un
    periodo gia' presente, e le uscite sintetiche le rigenera
    `compute_qoq_deltas`. Rende quanti fondi ci sono dopo.
    """
    for f, (slug, nome, gestore, tipo, fonte, indietro) in enumerate(FONDI):
        fondo, _ = upsert_institutional(
            db,
            ScrapedManager(code=slug, slug=slug, name=nome, manager_name=gestore),
            type_=tipo,
            source=fonte,
        )
        # ⚠️ In ordine CRONOLOGICO: `compute_qoq_deltas` cerca il filing
        # precedente, e senza di esso scrive `action=None` su ogni riga — che
        # e' la regola onesta sul primo filing, e qui svuoterebbe le schede.
        for ordine in range(FILING_PER_FONDO):
            periodo = _trimestre(oggi, indietro + (FILING_PER_FONDO - 1 - ordine))
            righe = _filing(f, ordine)
            totale = sum(v for *_, v in righe)
            posizioni = [
                ScrapedHolding(
                    ticker=t, company_name=nome_soc, shares=azioni, value_usd=valore,
                    portfolio_pct=round(valore / totale * 100, 2),
                    qoq_change_pct=None, qoq_change_shares=None, action=None,
                )
                for t, nome_soc, azioni, valore in righe
            ]
            riga, _ = upsert_filing(db, fondo, ScrapedFiling(
                code=slug, period_end_date=periodo, total_value_usd=totale,
                filed_date=periodo + timedelta(days=RITARDO_DEPOSITO),
                holdings=posizioni,
            ))
            insert_holdings(db, riga, posizioni)
            compute_qoq_deltas(db, fondo, riga)
    db.flush()
    return db.query(Institutional).count()


def _giorni_feriali(fino_a: date, quanti: int) -> list[date]:
    """Esattamente `quanti` giorni feriali, dal piu' vecchio al piu' recente.

    ⚠️ Non e' la stessa cosa di «i feriali dentro gli ultimi N giorni», ed e'
    la differenza fra un gate ripetibile e uno che cambia esito da solo.
    Contando all'indietro su un intervallo FISSO di giorni, quanti feriali ci
    cadono dipende da che giorno della settimana e' oggi: misurato, 215 barre
    il sabato e la domenica, 214 il lunedi'.

    Il generatore casuale e' seminato, ma consuma UN ESTRAZIONE PER BARRA:
    una barra in meno sposta tutte le estrazioni successive, quindi l'intera
    serie di prezzi cambia, e con essa le percentuali a schermo e i colori che
    le vestono. E' cosi' che la pagina Esplora ha guadagnato una violazione di
    contrasto in una notte, senza che nessuno toccasse una riga di quel codice.
    """
    fuori: list[date] = []
    g = fino_a
    while len(fuori) < quanti:
        g -= timedelta(days=1)
        if g.weekday() < 5:
            fuori.append(g)
    fuori.reverse()
    return fuori


def _ancora(oggi: date) -> datetime:
    """Mezzogiorno UTC di oggi — l'istante da cui i segnali contano all'indietro.

    ⚠️ Era `datetime.now(UTC)`, cioe' l'ORA in cui gira il job. Gli scarti dei
    segnali sono ore (fino a 78), quindi lo stesso seme produce una differenza
    in GIORNI DI CALENDARIO fra `signal_date` e `triggered_at` che cambia con
    l'ora della giornata: una corsa alle 00:18 UTC — l'ora reale del job che ha
    fatto arrossare il gate — fa scivolare indietro di un giorno gli scarti
    piccoli. La UI ne fa una pastiglia «in ritardo» (soglia 4 giorni), quindi
    il numero di elementi resi dipendeva dall'orologio.

    Mezzogiorno e' lontano da entrambi i bordi del giorno: nessun arrotondamento
    di fuso puo' spostarlo oltre la mezzanotte.
    """
    return datetime.combine(oggi, time(12, 0), tzinfo=UTC)


def main() -> None:
    rng = random.Random(20260912)  # deterministico: un gate che cambia esito da solo non e' un gate
    db = SessionLocal()
    try:
        # ⚠️ L'UTENTE, prima di tutto il resto.
        #
        # Un token firmato correttamente NON basta: `read_session_token`
        # verifica la firma, ma la dipendenza di autenticazione poi CERCA
        # l'utente e risponde 401 «User not found» se non c'e'. In CI il
        # database nasce da `create_all`, quindi vuoto, e ogni rotta protetta
        # rimandava al login — il gate misurava la pagina di accesso e
        # riportava «la pagina e' vuota», che e' il sintomo e non la causa.
        #
        # La password non serve a nessuno: il gate entra col cookie firmato,
        # mai dal modulo di login. E' casuale e non viene stampata proprio
        # perche' non deve diventare una credenziale di cui fidarsi.
        if db.query(User).filter(User.username == settings.admin_username).first() is None:
            db.add(User(
                username=settings.admin_username,
                password_hash=hash_password(secrets.token_urlsafe(32)),
            ))
            db.flush()

        stocks: list[Stock] = []
        for ticker, nome, borsa, settore, industria, valuta, cap in CATALOGO:
            s = (
                db.query(Stock)
                .filter(Stock.ticker == ticker, Stock.exchange == borsa)
                .first()
            )
            if s is None:
                s = Stock(ticker=ticker, exchange=borsa, name=nome)
                db.add(s)
            s.name = nome
            for campo, valore in (
                ("sector", settore), ("industry", industria),
                ("currency", valuta), ("market_cap", cap), ("country", "US"),
                ("is_active", True),
            ):
                if hasattr(s, campo):
                    setattr(s, campo, valore)
            stocks.append(s)
        db.flush()

        oggi = date.today()
        # ⚠️ Il calendario dei feriali si calcola UNA volta e lo usano sia le
        # barre sia i segnali. Vedi il commento su `signal_date` piu' sotto: e'
        # la meta' della ripetibilita' che la correzione precedente non copriva.
        feriali = _giorni_feriali(oggi, BARRE)
        for s in stocks:
            if db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == s.id).count() >= BARRE:
                continue
            prezzo = rng.uniform(20, 600)
            for giorno in feriali:
                prezzo *= 1 + rng.uniform(-0.025, 0.027)
                alto = prezzo * (1 + rng.uniform(0, 0.02))
                basso = prezzo * (1 - rng.uniform(0, 0.02))
                db.add(OhlcvDaily(
                    stock_id=s.id, date=giorno,
                    open=round(basso, 4), high=round(alto, 4),
                    low=round(basso, 4), close=round(prezzo, 4),
                    volume=int(rng.uniform(3e5, 8e7)),
                ))
        db.flush()

        if db.query(Alert).count() < len(stocks) * 2:
            for i, s in enumerate(stocks):
                for j, (nome, tono, catena) in enumerate(SEGNALI[: 2 + (i % 3)]):
                    # ⚠️ La data del segnale e' un GIORNO FERIALE preso dal
                    # calendario delle barre, non `oggi - N giorni`.
                    #
                    # Con lo scarto di calendario, quanti segnali cadevano su un
                    # giorno che HA una barra dipendeva dal giorno della
                    # settimana in cui girava il job: misurato, 29 su 36 di
                    # domenica e 21 su 36 di lunedi'. E' la stessa lezione della
                    # correzione precedente applicata a meta' — si era reso
                    # stabile il numero di BARRE e non quello dei SEGNALI — ed
                    # e' bastato che la CI passasse la mezzanotte per far
                    # arrossare il gate su un commit che non toccava ne' il seme
                    # ne' il frontend.
                    k = (i + j) % 5
                    giorno_segnale = feriali[-(1 + k)]
                    # ⚠️ E `triggered_at` si conta dal SEGNALE, non da oggi. La
                    # UI fa una pastiglia «in ritardo» sullo scarto in giorni di
                    # CALENDARIO (soglia 4): ancorandolo a `oggi` lo scarto
                    # cambiava con i fine settimana di mezzo. Cosi' lo scarto e'
                    # il numero scritto qui, e quanti segnali indossano la
                    # pastiglia non dipende da quando gira il job. Solo i piu'
                    # vecchi la indossano, per esercitare entrambi i rami.
                    ritardo = 5 if k == 4 else 1
                    db.add(Alert(
                        stock_id=s.id,
                        triggered_at=_ancora(giorno_segnale) + timedelta(days=ritardo),
                        signal_date=giorno_segnale,
                        signal_name=nome,
                        trigger_price=round(rng.uniform(20, 600), 4),
                        snapshot=json.dumps({
                            "tone": tono,
                            "nature": "continuation" if tono == "bull" else "reversal",
                            "horizon": ["short", "medium", "long"][(i + j) % 3],
                            "strength": round(rng.uniform(60, 98), 1),
                            "probability": round(rng.uniform(47, 52), 1),
                            "chain_summary": catena,
                        }),
                    ))
        # ⚠️ Per ULTIMA, e senza toccare `rng`: vedi la sezione FA-068 in cima.
        fondi = semina_istituzionali(db, oggi)
        db.commit()
        print(f"seme e2e: {db.query(User).count()} utenti, {len(stocks)} titoli, "
              f"{db.query(Alert).count()} segnali, {db.query(OhlcvDaily).count()} barre, "
              f"{fondi} fondi")
    finally:
        db.close()


if __name__ == "__main__":
    main()
