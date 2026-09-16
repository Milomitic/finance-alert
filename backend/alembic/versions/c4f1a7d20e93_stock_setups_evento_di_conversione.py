"""stock_setups: l'evento di conversione immutabile, e la riconciliazione dello storico

Revision ID: c4f1a7d20e93
Revises: a7c3e19d2b60
Create Date: 2026-09-16

Tre difetti misurati in produzione il 2026-09-16, e la ragione per cui questa
migrazione tocca DATI oltre allo schema:

1. **La conversione stava su un ramo solo della scansione.** Il ramo che
   aggiorna un alert esistente terminava senza convertire: 95 setup attivi
   avevano gia' visto scattare la loro condizione, tutti e 95 passati da li'.
2. **Il setup puntava a un'entita' viva.** 71 conversioni su 334 puntavano a un
   alert la cui `signal_date` era poi scivolata oltre la conversione, fino a 28
   giorni: l'esito futuro avrebbe misurato un altro momento.
3. **La conversione non guardava il verso.** 68 conversioni su 334 erano un
   setup rialzista chiuso da un segnale ribassista, o viceversa.

Le regole sui dati, e perche' ognuna e' la meno inventiva possibile:

- Ogni conversione esistente diventa `legacy`. La data dell'evento si scrive
  SOLO se l'alert non e' mai stato rivisto (`amend_count` assente o zero):
  allora i suoi campi sono esattamente quelli del momento della conversione.
  Negli altri casi la data resta NULL — quella vera non fu registrata.
- Verso opposto (rialzista contro ribassista, entrambi dichiarati) -> chiuso
  con ragione `mislinked`, fuori dal tasso di conversione. Un setup senza
  direzione, o un alert senza tono, non e' giudicabile e non si tocca.
- Attivi con un alert dello stesso detector, di verso compatibile, su una barra
  STRETTAMENTE successiva al giorno d'apertura -> convertiti come `reconciled`,
  senza data d'evento, anticipo ed esito: la condizione e' scattata, ma la
  PRIMA rilevazione non fu registrata e non si ricostruisce. Quelli con la barra
  sullo stesso giorno d'apertura restano attivi: non si puo' dire se l'evento
  fosse gia' passato quando il setup si e' aperto.

Il riempimento degli esiti non sta qui: lo fa `mature_setup_outcomes` alla
prima scansione, con la stessa aritmetica del magazzino.
"""
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "c4f1a7d20e93"
down_revision: str | None = "a7c3e19d2b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLONNE = [
    ("first_seen_bar", sa.Date()),
    ("converted_signal_date", sa.Date()),
    ("converted_price", sa.Float()),
    ("converted_tone", sa.String(16)),
    ("conversion_source", sa.String(16)),
    ("bar_lead_days", sa.Integer()),
    ("outcome_signal_date", sa.Date()),
    ("outcome_horizon_days", sa.Integer()),
    ("outcome_fwd_return", sa.Float()),
    ("outcome_mkt_neutral_excess", sa.Float()),
    ("outcome_mkt_neutral_hit", sa.Integer()),
    ("outcome_matured_at", sa.DateTime(timezone=True)),
]

_DIREZIONALI = ("bull", "bear")


def _giorno(v: object) -> date | None:
    """Una data da una colonna letta in SQL grezzo: `date`/`datetime` su
    Postgres, stringa ISO su SQLite."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _snapshot(raw: object) -> dict:
    try:
        s = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}
    return s if isinstance(s, dict) else {}


def upgrade() -> None:
    with op.batch_alter_table("stock_setups") as batch:
        for nome, tipo in _COLONNE:
            batch.add_column(sa.Column(nome, tipo, nullable=True))

    conn = op.get_bind()

    # 1-3. Conversioni esistenti: storiche, datate solo dove e' certo, o sbagliate.
    convertiti = conn.execute(sa.text(
        "SELECT s.id, s.tone, a.signal_date, a.trigger_price, a.snapshot "
        "FROM stock_setups s LEFT JOIN alerts a ON a.id = s.converted_alert_id "
        "WHERE s.status = 'converted'"
    )).all()
    n_legacy = n_datati = n_sbagliati = 0
    for sid, tono_setup, sig_date, prezzo, raw in convertiti:
        snap = _snapshot(raw)
        tono_alert = snap.get("tone")
        if tono_setup in _DIREZIONALI and tono_alert in _DIREZIONALI \
                and tono_setup != tono_alert:
            conn.execute(sa.text(
                "UPDATE stock_setups SET status = 'expired', "
                "closed_reason = 'mislinked', conversion_source = 'legacy' "
                "WHERE id = :i"
            ), {"i": sid})
            n_sbagliati += 1
            continue
        n_legacy += 1
        mai_rivisto = not int(snap.get("amend_count") or 0)
        compatibile = tono_alert in _DIREZIONALI and (
            tono_setup == tono_alert or tono_setup not in _DIREZIONALI
        )
        if mai_rivisto and compatibile and _giorno(sig_date) is not None:
            conn.execute(sa.text(
                "UPDATE stock_setups SET conversion_source = 'legacy', "
                "converted_signal_date = :d, converted_price = :p, converted_tone = :t "
                "WHERE id = :i"
            ), {"i": sid, "d": _giorno(sig_date), "p": prezzo, "t": tono_alert})
            n_datati += 1
        else:
            conn.execute(sa.text(
                "UPDATE stock_setups SET conversion_source = 'legacy' WHERE id = :i"
            ), {"i": sid})

    # 4. Attivi la cui condizione e' gia' scattata su una barra successiva.
    candidati = conn.execute(sa.text(
        "SELECT s.id, s.tone, s.first_seen_at, a.id, a.signal_date, a.snapshot "
        "FROM stock_setups s JOIN alerts a "
        "ON a.stock_id = s.stock_id AND a.signal_name = s.detector "
        "WHERE s.status = 'active' AND a.signal_date IS NOT NULL"
    )).all()
    scelta: dict[int, tuple[date, int]] = {}
    for sid, tono_setup, aperto, aid, sig_date, raw in candidati:
        tono_alert = _snapshot(raw).get("tone")
        if tono_alert not in _DIREZIONALI:
            continue
        if tono_setup in _DIREZIONALI and tono_setup != tono_alert:
            continue
        giorno_apertura, giorno_evento = _giorno(aperto), _giorno(sig_date)
        if giorno_apertura is None or giorno_evento is None:
            continue
        if giorno_evento <= giorno_apertura:
            continue
        # Piu' alert compatibili: si punta al piu' recente, che e' quello che la
        # scansione aggiorna. La data non si scrive comunque.
        if sid not in scelta or giorno_evento > scelta[sid][0]:
            scelta[sid] = (giorno_evento, aid)
    ora = datetime.now(UTC)
    for sid, (_, aid) in scelta.items():
        conn.execute(sa.text(
            "UPDATE stock_setups SET status = 'converted', "
            "conversion_source = 'reconciled', converted_alert_id = :a, "
            "resolved_at = :r, lead_days = NULL WHERE id = :i"
        ), {"i": sid, "a": aid, "r": ora})

    print(
        f"[c4f1a7d20e93] conversioni storiche {n_legacy} (data evento certa: "
        f"{n_datati}), verso opposto chiuse come mislinked {n_sbagliati}, "
        f"attivi riconciliati {len(scelta)}"
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Le riconciliate tornano attive dove non si e' aperto nel frattempo un
    # altro episodio della stessa coppia: l'indice parziale ne ammette uno solo.
    # Le altre restano convertite, e lo si DICHIARA invece di perderle in
    # silenzio.
    riconciliate = conn.execute(sa.text(
        "SELECT s.id, s.stock_id, s.detector FROM stock_setups s "
        "WHERE s.conversion_source = 'reconciled'"
    )).all()
    riaperte = rimaste = 0
    for sid, stock_id, detector in riconciliate:
        aperto = conn.execute(sa.text(
            "SELECT 1 FROM stock_setups WHERE stock_id = :s AND detector = :d "
            "AND status = 'active'"
        ), {"s": stock_id, "d": detector}).first()
        if aperto is not None:
            rimaste += 1
            continue
        conn.execute(sa.text(
            "UPDATE stock_setups SET status = 'active', converted_alert_id = NULL, "
            "resolved_at = NULL WHERE id = :i"
        ), {"i": sid})
        riaperte += 1
    conn.execute(sa.text(
        "UPDATE stock_setups SET status = 'converted', closed_reason = NULL "
        "WHERE closed_reason = 'mislinked'"
    ))
    print(
        f"[c4f1a7d20e93 downgrade] riconciliate riaperte {riaperte}, "
        f"rimaste convertite (episodio gia' aperto) {rimaste}"
    )
    with op.batch_alter_table("stock_setups") as batch:
        for nome, _ in reversed(_COLONNE):
            batch.drop_column(nome)
