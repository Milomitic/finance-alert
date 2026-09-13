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
from app.models.ohlcv import OhlcvDaily
from app.models.stock import Stock
from app.models.user import User

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
        for s in stocks:
            if db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == s.id).count() >= BARRE:
                continue
            prezzo = rng.uniform(20, 600)
            for giorno in _giorni_feriali(oggi, BARRE):
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
                    db.add(Alert(
                        stock_id=s.id,
                        triggered_at=_ancora(oggi) - timedelta(hours=6 * (i + j)),
                        signal_date=oggi - timedelta(days=1 + (i + j) % 5),
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
        db.commit()
        print(f"seme e2e: {db.query(User).count()} utenti, {len(stocks)} titoli, "
              f"{db.query(Alert).count()} segnali, {db.query(OhlcvDaily).count()} barre")
    finally:
        db.close()


if __name__ == "__main__":
    main()
