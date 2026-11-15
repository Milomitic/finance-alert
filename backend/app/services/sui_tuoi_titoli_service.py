"""«Sui tuoi titoli»: che cosa succede ai titoli in posizione e fra i
preferiti (FA-149).

Tre elenchi, tutti letti dalle cache e mai dalla rete: le trimestrali dei
prossimi `GIORNI_TRIMESTRALI` giorni, i cambi di rating degli ultimi
`GIORNI_ANALISTI` e le notizie degli ultimi `GIORNI_NOTIZIE`. Il cruscotto si
apre una ventina di volte al giorno; una scheda che chiamasse Yahoo a ogni
apertura sarebbe la scheda lenta.

⚠️ Una cache fredda produce un elenco vuoto, non un errore. Chi legge vede
«nessuna trimestrale nei prossimi 14 giorni», che sarebbe falso solo se la
cache dei fondamentali non contenesse quel titolo: la cache si riscalda a ogni
avvio (`hydrate_l1_from_db`) e copre tutto il catalogo.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock
from app.services import analyst_actions_feed, rilevanza_service
from app.services import stock_fundamentals_service as sfs
from app.services import stock_news_service as sns

GIORNI_TRIMESTRALI = 14
GIORNI_ANALISTI = 30
GIORNI_NOTIZIE = 3
MASSIMO = 8


def _istante(testo: str | None) -> datetime | None:
    if not testo:
        return None
    try:
        t = datetime.fromisoformat(str(testo).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def riepilogo(db: Session, *, adesso: datetime | None = None) -> dict:
    adesso = adesso or datetime.now(UTC)
    oggi = adesso.date()
    per_id = rilevanza_service.titoli_rilevanti(db)
    titoli = {
        ticker: (sid, per_id[sid], nome)
        for sid, ticker, nome in db.execute(
            select(Stock.id, Stock.ticker, Stock.name).where(Stock.id.in_(per_id))
        ).all()
    } if per_id else {}
    out: dict = {"titoli": len(titoli), "trimestrali": [], "analisti": [], "notizie": []}
    if not titoli:
        return out

    for ticker, (data, ora) in sfs.next_earnings_cached(set(titoli)).items():
        giorni = (data - oggi).days
        if 0 <= giorni <= GIORNI_TRIMESTRALI:
            out["trimestrali"].append({
                "ticker": ticker, "nome": titoli[ticker][2], "rilevanza": titoli[ticker][1],
                "data": data.isoformat(), "ora_utc": ora, "giorni": giorni,
            })
    out["trimestrali"].sort(key=lambda r: (r["data"], r["ticker"]))

    dal = (oggi - timedelta(days=GIORNI_ANALISTI)).isoformat()
    for a in analyst_actions_feed.recent_actions(
        limit=10_000, actions=analyst_actions_feed.CHANGE_ACTIONS,
    ):
        if a.ticker in titoli and a.date >= dal:
            out["analisti"].append({
                "ticker": a.ticker, "rilevanza": titoli[a.ticker][1], "data": a.date,
                "societa": a.firm, "azione": a.action, "da": a.from_grade, "a": a.to_grade,
            })
    out["analisti"] = out["analisti"][:MASSIMO]

    limite = adesso - timedelta(days=GIORNI_NOTIZIE)
    notizie = []
    for ticker in titoli:
        voce = sns._CACHE.get(ticker)
        for n in (voce[1] if voce else []) or []:
            quando = _istante(n.get("published_at"))
            if quando is None or quando < limite:
                continue
            notizie.append({
                "ticker": ticker, "rilevanza": titoli[ticker][1], "titolo": n.get("title"),
                "link": n.get("link"), "fonte": n.get("publisher"),
                "pubblicata": quando.isoformat(), "tono": n.get("sentiment"),
            })
    notizie.sort(key=lambda n: n["pubblicata"], reverse=True)
    # Un titolo con venti articoli non deve coprire gli altri: al massimo due
    # per titolo, poi i piu' recenti.
    visti: dict[str, int] = {}
    for n in notizie:
        if visti.get(n["ticker"], 0) < 2:
            out["notizie"].append(n)
            visti[n["ticker"]] = visti.get(n["ticker"], 0) + 1
        if len(out["notizie"]) >= MASSIMO:
            break
    return out
