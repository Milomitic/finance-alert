"""Il tipo di strumento va deciso dove la riga ENTRA nella colonna.

`instrument_type` era scritto UNA SOLA VOLTA, da una migration con lista fissa
di 24 ticker raccolti come «exactly the NYSE Arca listings» il 2026-07-04.
Nessun percorso di ingestione lo valorizzava, quindi ogni riga nuova nasceva
`equity` — e sette query in `api/sectors.py` filtrano su quel valore.

Misurato in produzione: il buco era UNA riga, QQQ, quotata NASDAQ e percio
assente da una lista costruita per borsa. Non una deriva, ma il meccanismo
l'avrebbe riaperta al prossimo fondo aggiunto.

⚠️ Due criteri sbagliati, entrambi scartati e fissati qui sotto:

  - **il nome**: "Netflix" contiene "etf". E il falso positivo da sottostringa
    che questo repository ha gia pagato con `mute` dentro
    `text-muted-foreground`.
  - **la borsa**: e esattamente il criterio che ha lasciato passare QQQ.

Il criterio giusto e l'industria GREZZA della riga, letta PRIMA che
`canonical_industry` la mandi su OTHER — cosa che fa di proposito, per non
inquinare i gruppi di confronto azionari, e che cosi facendo cancella l'unico
segnale disponibile.
"""
import io

from sqlalchemy.orm import Session

from app.models import Stock
from app.services.industry_normalizer import canonical_industry, is_fund_industry
from app.services.seed_service import seed_index_from_csv

HEADER = "ticker,name,exchange,sector,industry,country,currency\n"


def _seed(db: Session, *rows: str) -> None:
    seed_index_from_csv(
        db, io.StringIO(HEADER + "".join(r + "\n" for r in rows)),
        index_code="TST", index_name="Test", country="US",
    )
    db.commit()


def _type(db: Session, ticker: str) -> str:
    return db.query(Stock).filter_by(ticker=ticker).one().instrument_type


class TestIlSegnaleVaLettoPrimaDellaNormalizzazione:
    def test_la_normalizzazione_cancella_il_segnale(self):
        # Il fatto che rende necessario leggerlo al confine: dopo, un ETF a
        # leva e indistinguibile da una societa senza industria.
        assert canonical_industry("Leveraged ETF") == canonical_industry("Qualcosa di ignoto")

    def test_ma_prima_e_ancora_li(self):
        assert is_fund_industry("Leveraged ETF") is True
        assert is_fund_industry("Exchange Traded Fund") is True
        assert is_fund_industry("ETF") is True

    def test_il_confronto_e_sull_etichetta_intera_mai_su_una_sottostringa(self):
        # ⚠️ Il controllo che vale piu di tutti gli altri. Un criterio a
        # sottostringa classificherebbe Netflix come fondo.
        assert is_fund_industry("Movies & Entertainment") is False
        assert is_fund_industry("Netflix") is False
        assert is_fund_industry("Software") is False
        assert is_fund_industry(None) is False


class TestIlSeedClassificaAlConfine:
    def test_un_fondo_dichiarato_nel_csv_nasce_etf(self, db: Session):
        _seed(db, "SOXL,Direxion Semis Bull 3X,NYSE Arca,Financial Services,Leveraged ETF,US,USD")

        assert _type(db, "SOXL") == "etf"

    def test_una_societa_nasce_equity(self, db: Session):
        # Il controllo negativo: senza, un'implementazione che scrive sempre
        # "etf" supererebbe il test sopra.
        _seed(db, "AAPL,Apple Inc.,NASDAQ,Information Technology,Technology Hardware,US,USD")

        assert _type(db, "AAPL") == "equity"

    def test_una_societa_col_nome_che_contiene_etf_resta_equity(self, db: Session):
        # La riproduzione del criterio scartato, come regressione.
        _seed(db, "NFLX,Netflix Inc.,NASDAQ,Communication Services,Movies & Entertainment,US,USD")

        assert _type(db, "NFLX") == "equity"

    def test_la_borsa_non_e_il_criterio(self, db: Session):
        # QQQ e quotata NASDAQ ed e un fondo: e esattamente il caso che la
        # lista «exactly the NYSE Arca listings» ha lasciato passare.
        _seed(db, "QQQ,Invesco QQQ Trust,NASDAQ,Financial Services,Exchange Traded Fund,US,USD")

        assert _type(db, "QQQ") == "etf"


class TestUnRiseedCorreggeMaNonDeclassa:
    def test_un_riseed_corregge_una_riga_sbagliata(self, db: Session):
        _seed(db, "SOXL,Direxion Semis Bull 3X,NYSE Arca,Financial Services,Technology,US,USD")
        assert _type(db, "SOXL") == "equity"

        _seed(db, "SOXL,Direxion Semis Bull 3X,NYSE Arca,Financial Services,Leveraged ETF,US,USD")

        assert _type(db, "SOXL") == "etf"

    def test_un_csv_che_tace_non_declassa_una_riga_gia_etf(self, db: Session):
        """⚠️ Solo in salita, e non e una sfumatura.

        Le 24 righe classificate dalla migration del 2026-07 non hanno
        l'industria giusta nei file di seed: un riseed che declassasse
        riporterebbe tutte e ventiquattro a `equity`, cioe rifarebbe il
        difetto in grande mentre lo si corregge in piccolo.
        """
        _seed(db, "TQQQ,ProShares UltraPro QQQ,NYSE Arca,Financial Services,Leveraged ETF,US,USD")
        assert _type(db, "TQQQ") == "etf"

        _seed(db, "TQQQ,ProShares UltraPro QQQ,NYSE Arca,Financial Services,Other,US,USD")

        assert _type(db, "TQQQ") == "etf"
