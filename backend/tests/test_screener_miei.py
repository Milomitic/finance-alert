"""C-33: lo screener si restringe ai titoli in posizione o fra i preferiti."""
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Stock
from app.models.preferito import Preferito
from app.services.stock_service import StockFilter, search_stocks


def test_solo_i_miei_titoli(db: Session) -> None:
    a, b, c = (Stock(ticker=t, exchange="X", name=t) for t in ("MIO", "ALTRO", "TERZO"))
    db.add_all([a, b, c])
    db.flush()
    db.add(Preferito(stock_id=a.id, aggiunto_il=datetime.now(UTC)))
    db.flush()
    miei = {i.stock.ticker for i in search_stocks(db, StockFilter(solo_miei=True)).items}
    assert miei == {"MIO"}
    tutti = {i.stock.ticker for i in search_stocks(db, StockFilter()).items}
    assert {"MIO", "ALTRO", "TERZO"} <= tutti

