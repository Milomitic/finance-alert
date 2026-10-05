"""«Dall'ultima visita»: che cosa e' cambiato da quando hai aperto il cruscotto
l'ultima volta (2026-09-29).

Il cruscotto e' la pagina piu' aperta (~17 volte al giorno), e ogni volta
mostrava lo STATO — che per chi l'ha visto un'ora prima e' in gran parte gia'
noto. Questa riga dice la DIFFERENZA: segnali nati, novita' sui titoli seguiti,
target di prezzo raggiunti, posizioni chiuse.

⚠️ Che cos'e' «l'ultima visita» e' la scelta che conta. Il riferimento e'
l'apertura precedente a una PAUSA di almeno `PAUSA`: una ricarica, un doppio
montaggio di React, un andirivieni fra cruscotto e titolo non lo spostano,
quindi la riga resta la stessa per tutta una sessione e cambia quando se ne
comincia un'altra. Con «l'apertura precedente» e basta, direbbe quasi sempre
«niente di nuovo» di dieci minuti fa.

Niente rete: le novita' si leggono dalla cache senza rinfrescarla (lo fa il
digest del mattino). Un'apertura della pagina non aspetta Yahoo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, EtoroPosizione, Position, PriceAlert, VisitaCruscotto
from app.services import novita_titoli_service, rilevanza_service
from app.services.novita_titoli_service import Novita

PAUSA = timedelta(minutes=30)
_RIGA = 1


def _utc(ts: datetime | None) -> datetime | None:
    """SQLite rende istanti senza fuso; qui sono tutti UTC."""
    if ts is None or ts.tzinfo is not None:
        return ts
    return ts.replace(tzinfo=UTC)


def registra_apertura(db: Session, adesso: datetime) -> datetime | None:
    """Segna un'apertura e rende il riferimento da cui contare; None alla
    prima visita di sempre."""
    riga = db.get(VisitaCruscotto, _RIGA)
    if riga is None:
        db.add(VisitaCruscotto(id=_RIGA, riferimento=None, ultima_apertura=adesso))
        db.commit()
        return None
    ultima = _utc(riga.ultima_apertura)
    if ultima is not None and adesso - ultima >= PAUSA:
        riga.riferimento = ultima
    riga.ultima_apertura = adesso
    db.commit()
    return _utc(riga.riferimento)


@dataclass
class Riepilogo:
    dal: datetime | None
    segnali: int = 0
    segnali_miei: int = 0
    target_raggiunti: int = 0
    posizioni_chiuse: int = 0
    novita: list[Novita] = field(default_factory=list)


def riepilogo(db: Session, dal: datetime | None) -> Riepilogo:
    if dal is None:
        return Riepilogo(dal=None)
    nati = select(func.count()).select_from(Alert).where(
        Alert.signal_name.is_not(None), Alert.emitted_at > dal,
    )
    return Riepilogo(
        dal=dal,
        segnali=db.execute(nati).scalar_one(),
        segnali_miei=db.execute(
            nati.where(rilevanza_service.filtro_rilevanti(Alert.stock_id))
        ).scalar_one(),
        target_raggiunti=db.execute(
            select(func.count()).select_from(PriceAlert).where(PriceAlert.triggered_at > dal)
        ).scalar_one(),
        # Le manuali e quelle chiuse su eToro (FA-124).
        posizioni_chiuse=db.execute(
            select(func.count()).select_from(Position).where(Position.closed_at > dal)
        ).scalar_one() + db.execute(
            select(func.count()).select_from(EtoroPosizione).where(EtoroPosizione.chiusa_il > dal)
        ).scalar_one(),
        # Le novita' hanno una data e non un'ora: si prendono dal giorno del
        # riferimento, e un fatto di quella mattina puo' riapparire la sera.
        novita=novita_titoli_service.raccogli(db, dal.date(), rinfresca=False),
    )
