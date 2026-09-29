"""Il promemoria delle trimestrali sui titoli che contano (2026-09-29).

Una posizione tenuta attraverso i conti e' il rischio di salto piu' grande che
l'app vede, e fino a qui nessuna notifica ne parlava: il calendario delle
trimestrali c'era, ma solo come pagina da andare a guardare. Ogni sera il job
`promemoria_trimestrali` manda su Telegram le trimestrali di DOMANI sulle
posizioni aperte e sui preferiti — gli stessi titoli di FA-113, dallo stesso
proprietario (`rilevanza_service`).

Tre scelte che non sono dettagli:

- **La finestra e' «domani», e basta.** Il job gira una volta al giorno, tutti
  i giorni, quindi ogni data si ricorda una volta sola, la sera prima — anche
  il lunedi', la domenica sera. Una trimestrale spostata in avanti si ricorda
  di nuovo la vigilia della data nuova, che e' il comportamento giusto.
- **Prima di leggere la cache, la si rinfresca per QUESTI titoli.**
  `get_fundamentals` senza `force_refresh` rispetta la scadenza della cache e
  scarica solo cio' che e' stantio: per una manciata di titoli costa poco, e
  senza un titolo mai aperto non avrebbe nessuna data in memoria e il
  promemoria tacerebbe in silenzio. Sconosciuto non e' «nessuna trimestrale».
- **L'orario e' quello di yfinance, convertito in ora italiana.** La DATA e'
  quella della borsa, l'orario arriva in UTC (`_extract_earnings`); si mostra
  solo l'ora, perche' e' l'informazione che serve (prima dell'apertura o dopo
  la chiusura). Senza orario si dice la data e basta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock
from app.services import rilevanza_service, stock_fundamentals_service

ROMA = ZoneInfo("Europe/Rome")

_GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
_MESI = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")


@dataclass(frozen=True)
class Trimestrale:
    ticker: str
    nome: str | None
    rilevanza: str
    data: date
    ora_utc: str | None


def ora_italiana(data: date, ora_utc: str | None) -> str | None:
    """«22:05» per un orario UTC «20:05» di un giorno d'estate; None se manca o
    non si legge."""
    if not ora_utc:
        return None
    try:
        hh, mm = (int(x) for x in ora_utc.split(":")[:2])
        istante = datetime.combine(data, time(hh, mm), tzinfo=UTC)
    except (ValueError, TypeError):
        return None
    return istante.astimezone(ROMA).strftime("%H:%M")


def etichetta_data(d: date) -> str:
    """«mar 30 set»."""
    return f"{_GIORNI[d.weekday()]} {d.day} {_MESI[d.month - 1]}"


def _rinfresca(tickers: set[str]) -> None:
    for t in sorted(tickers):
        try:
            stock_fundamentals_service.get_fundamentals(t)
        except Exception as exc:  # noqa: BLE001 — un titolo non ferma gli altri
            logger.warning(f"[promemoria_trimestrali] {t}: fondamentali non disponibili: {exc}")


def di_domani(db: Session, oggi: date, *, rinfresca: bool = True) -> list[Trimestrale]:
    """Le trimestrali di domani sui titoli che contano, posizioni prima."""
    rilevanti = rilevanza_service.titoli_rilevanti(db)
    if not rilevanti:
        return []
    titoli = db.execute(select(Stock).where(Stock.id.in_(rilevanti))).scalars().all()
    tickers = {s.ticker for s in titoli}
    if rinfresca:
        _rinfresca(tickers)
    date_ = stock_fundamentals_service.next_earnings_cached(tickers)
    domani = oggi + timedelta(days=1)
    out = [
        Trimestrale(s.ticker, s.name, rilevanti[s.id], *date_[s.ticker])
        for s in titoli
        if s.ticker in date_ and date_[s.ticker][0] == domani
    ]
    out.sort(key=lambda t: (-rilevanza_service.PESO[t.rilevanza], t.ticker))
    return out
