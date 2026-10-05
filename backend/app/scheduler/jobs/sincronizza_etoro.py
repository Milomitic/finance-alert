"""APScheduler job: ogni 10 minuti, il portafoglio eToro (FA-124).

Spento senza le chiavi: lo dice una volta per processo e poi tace, perche' un
avviso ogni dieci minuti insegnerebbe a ignorarlo. Le chiusure trovate si
mandano su Telegram e si segnano solo quando l'invio e' riuscito, oppure
quando Telegram non e' configurato: accenderlo dopo non deve rovesciare in
chat settimane di chiusure vecchie.
"""
from loguru import logger

from app.core import db as db_module
from app.core.errors import UpstreamError
from app.services import etoro_client, notifier_service
from app.services import etoro_portafoglio_service as svc

_detto_spento = False


def run_sincronizza_etoro() -> None:
    global _detto_spento
    if not etoro_client.configurato():
        if not _detto_spento:
            logger.info("[etoro] chiavi non configurate: sincronizzazione spenta")
            _detto_spento = True
        return
    # Dal modulo e non per nome: i test sostituiscono `db_module.SessionLocal`.
    with db_module.SessionLocal() as db:
        try:
            esito = svc.sincronizza(db)
        except UpstreamError as e:
            logger.warning(f"[etoro] sincronizzazione fallita: {e}")
            return
        chiuse = svc.da_notificare(db)
        if chiuse:
            r = notifier_service.notify_etoro_chiuse(chiuse)
            if r.sent or r.reason == "telegram_disabled":
                svc.segna_notificate(db, [p.position_id for p, _, _ in chiuse])
    logger.info(
        f"[etoro] {esito.aperte} aperte ({esito.nuove} nuove), {len(esito.chiuse)} chiuse, "
        f"{esito.da_confermare} strumenti da confermare, conto={'si' if esito.conto_aggiornato else 'no'}"
    )
