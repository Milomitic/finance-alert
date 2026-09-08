"""Find — and optionally repair — unrepaired splits in the stored OHLCV.

WHY THIS EXISTS
---------------
`ohlcv_service._check_price_basis` compares the incoming overlap bar against
the stored one, so it only ever sees a discontinuity at the EDGE of a fetch
window. A break already inside the stored history is invisible to it by
construction: from the next day on, stored and incoming are both on the new
basis, the ratio is 1.0, and it reports "basis OK" forever. It was added on
2026-07-04, so every split spliced before that date was never repaired and
never would be.

Measured on the live catalogue on 2026-09-01, the damage was not cosmetic:

    TIT.MI  reverse 1:10, 15 May   ->  rel_strength 100.0, the HIGHEST in the
                                       entire universe, posture "Forte"
    KLAC    10:1, 18 May           ->  rel_strength 0.1, trend 0.9
    CRWD     4:1, 29 June          ->  rel_strength 0.3, trend 0.0
    SOXS    20:1, 26 May           ->  rel_strength 0.0
    8053.T   4:1,  1 June

Three real companies sat at the bottom of the technical ranking and one
artifact sat at the very top. It contaminates breadth, ATR, the 52-week range,
the Tecnico lens, and every detector whose lookback crosses the date.

USAGE
-----
    # report only, safe, read-only
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.repair_price_basis

    # repair: wipes and re-downloads 10y for each affected stock
    ... -m app.scripts.repair_price_basis --apply
    ... -m app.scripts.repair_price_basis --apply --ticker KLAC --ticker CRWD

STOP UVICORN FIRST on SQLite (single writer). `--apply` is destructive per
stock: `_rebase_full_history` deletes the whole series and re-downloads it on
the authoritative basis. That is safe by construction — a failed refetch
raises and the per-stock transaction rolls back, so it never destroys what it
cannot replace — but it is a decision, which is why it is not automatic and
never runs inside a scan.

The detector reports CANDIDATES, not certainties: it is calibrated to catch
3:1 and larger (see `_SPLIT_MIN_RATIO`), and a couple of the older hits are
data glitches rather than splits — INDV falls 6x and recovers 7x five days
later, which is not a corporate action. Read the table before passing
--apply, and use --ticker when in doubt.
"""
from __future__ import annotations

import argparse
from datetime import timedelta

from loguru import logger
from sqlalchemy import text

from app.core.db import SessionLocal
from app.models import OhlcvDaily, Stock
from app.services.ohlcv_service import (
    _rebase_full_history,
    as_date,
    find_basis_breaks,
)

# Sotto questo rapporto di prezzo nessun verdetto automatico viene emesso: un
# -80% in una seduta esiste (EYPT: x0.330), un -95% no. Vedi _source_verdict.
_MIN_REAL_RATIO = 0.20
# Quante volte il controvalore mediano deve salire perche' la giornata sia un
# evento e non una riclassificazione. EYPT: x12.3. Uno split conserva i soldi.
_TURNOVER_SPIKE = 4.0
# Sedute di calendario prima della rottura su cui si calcola il controvalore
# tipico. ~6 mesi: abbastanza da essere stabile, abbastanza vicino da essere
# lo stesso titolo.
_BASELINE_DAYS = 180


def _source_verdict(ticker: str, when: object) -> str:
    """Run CLAUDE.md's triage against the SOURCE and print what it found.

    The decisive question is not "does yfinance declare a split" — it is
    **does a fresh download still contain the break**. Verified on EYPT
    (2026-09-08): yfinance applies declared splits to the price series even
    with `auto_adjust=False`, checked against EYPT's own 1:10 of 2020-12-09,
    where the series is continuous across the date (x0.871, ordinary noise)
    while 2026-08-17 shows x0.330. So:

      fresh download is CLEAN      -> our stored copy drifted from a healthy
                                      source                      -> --apply
      fresh REPRODUCES the break   -> the source has it too, and the money
                                      says which kind:
          dollar volume SPIKED     -> a real price move. DO NOT REPAIR; the
                                      stored history is already correct and
                                      --truncate would destroy good bars.
          dollar volume ORDINARY   -> a 90% gap with no money changing hands
                                      is not a price move. Bad data, and
                                      neither repair mode may fit (see INDV).

    That last discriminator is the one `find_basis_breaks` cannot apply: it
    sees SHARE volume, where a split and a panic both go up. Turnover
    separates them, because a split divides the same money into more shares.
    EYPT traded $254M against a $20.7M median over the prior six months —
    twelve times normal, a news event. KLAC's x0.097 came with x0.9 turnover,
    which is a split.

    Only the network call is caught, and a failure returns "?" rather than a
    verdict — an unreachable source means unknown, never clean. Everything
    after the fetch is arithmetic, and a fault there is a BUG that must be
    loud: the first version of this function caught both and reported a
    TypeError in its own code as "source unreachable".
    """
    day = as_date(when)
    try:
        import yfinance as yf

        hist = yf.Ticker(ticker).history(period="10y", auto_adjust=False)
    except Exception as exc:  # noqa: BLE001 - qualunque guasto di rete = non lo sappiamo
        return f"? sorgente non raggiungibile ({str(exc)[:40]})"

    if hist.empty:
        return "? la sorgente non ha restituito storico"

    dates = [as_date(i) for i in hist.index]
    closes = [float(c) for c in hist["Close"]]
    volumes = [float(v) if v == v else None for v in hist["Volume"]]
    fresh = find_basis_breaks(dates, closes, volumes)

    if not any(b.date == day for b in fresh):
        return "download fresco PULITO su questa data -> --apply"

    # La mediana si prende sulle sedute che PRECEDONO la rottura, non su tutti
    # i dieci anni: il controvalore di un titolo cambia molto in un decennio, e
    # un fondo di paragone lontano risponde a un'altra domanda. EYPT segna x12
    # contro le sue ultime 6 sedute-mese e x186 contro la sua storia intera —
    # stessa conclusione qui, ma non sarebbe sempre cosi'.
    window_start = day - timedelta(days=_BASELINE_DAYS)
    prior = [
        c * v
        for d, c, v in zip(dates, closes, volumes, strict=True)
        if v is not None and window_start <= d < day
    ]
    on_day = [
        c * v
        for d, c, v in zip(dates, closes, volumes, strict=True)
        if d == day and v is not None
    ]
    if not on_day or len(prior) < 40:
        return "la sorgente riproduce la rottura; troppo poco storico prima per il test volumi"

    median = sorted(prior)[len(prior) // 2]
    mult = on_day[0] / median if median else 0.0
    ratio = closes[dates.index(day)] / closes[dates.index(day) - 1] if dates.index(day) else 1.0
    tail = f"la sorgente la riproduce; salto x{ratio:.3f}, $ scambiati x{mult:.1f}"

    # Il volume da solo non basta, e SOXS e' il controesempio: x19.2 di
    # controvalore su un salto x0.054. Un ETF a leva 3 che si azzera ogni
    # giorno non puo' perdere il 94.6% in una seduta — servirebbe -31.5% sul
    # sottostante. Sotto _MIN_REAL_RATIO nessun verdetto viene emesso: un
    # salto simile non e' un prezzo, qualunque cosa dica il volume.
    if ratio < _MIN_REAL_RATIO:
        return f"{tail} -> salto troppo grande per un prezzo: indaga a mano"
    if mult >= _TURNOVER_SPIKE:
        return f"{tail} -> MOVIMENTO REALE, non riparare"
    return f"{tail} -> volume ordinario su un salto grande: dati sbagliati, indaga"


def scan(db, only: set[str] | None = None) -> list[tuple[Stock, list]]:
    q = "SELECT id, ticker FROM stocks ORDER BY ticker"
    out: list[tuple[Stock, list]] = []
    for sid, ticker in db.execute(text(q)).all():
        if only and ticker not in only:
            continue
        rows = db.execute(
            text(
                "SELECT date, close, volume FROM ohlcv_daily "
                "WHERE stock_id = :sid ORDER BY date"
            ),
            {"sid": sid},
        ).all()
        if len(rows) < 30:
            continue
        breaks = find_basis_breaks(
            [r[0] for r in rows],
            [float(r[1]) if r[1] is not None else None for r in rows],
            [float(r[2]) if r[2] is not None else None for r in rows],
        )
        if breaks:
            out.append((db.get(Stock, sid), breaks))
    return out


def _truncate(db, found) -> None:
    """Delete every bar strictly before the break, keeping the newer basis.

    WHEN TO USE THIS INSTEAD OF --apply. `--apply` wipes and re-downloads, so it
    only helps when the SOURCE is right and our stored copy drifted. If a fresh
    download reproduces the same break, refetching destroys the series and
    rebuilds it identically broken - strictly worse than doing nothing.

    Why not rescale the old bars by the ratio? Because the ratio would be OURS,
    not the source's. SOXS (established 2026-09-02) is the case this exists for:

      - exactly one discontinuity, 2026-05-26: price x0.054, volume x21.4;
      - yfinance DECLARES splits on 2026-03-05 (1:20) and 2026-07-15 (1:10),
        and both are correctly adjusted - no discontinuity on either date;
      - so the May break matches NO declared corporate action, and the "20:1"
        the detector prints is a pattern match, not a fact;
      - a fresh 10y download reproduces it to the cent, so --apply cannot help.

    Dividing ten years of prices by an inferred 20 would look perfectly healthy
    and be silently wrong if the true ratio were 18 or 25. Truncating invents
    nothing: what remains sits on ONE consistent basis, and a ticker left under
    200 bars simply fails `has_full_data`, which already keeps it out of
    EMA200-dependent signals and out of breadth (CLAUDE.md). It self-heals as
    real bars accrue.

    The cost is explicit and one-way: the pre-break history for that ticker is
    gone. Prefer --apply whenever a fresh download IS clean.
    """
    print()
    print(f"troncamento di {len(found)} titoli (elimina le barre PRIMA della rottura)...")
    for stock, breaks in found:
        cut = min(b.date for b in breaks)
        try:
            n = db.query(OhlcvDaily).filter(
                OhlcvDaily.stock_id == stock.id, OhlcvDaily.date < cut,
            ).delete(synchronize_session=False)
            left = db.query(OhlcvDaily).filter(
                OhlcvDaily.stock_id == stock.id,
            ).count()
            db.commit()
            flag = "  <- sotto 200: fuori dai segnali EMA200" if left < 200 else ""
            print(f"  ok  {stock.ticker:<10} -{n} barre prima del {cut}, restano {left}{flag}")
        except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the rest
            db.rollback()
            logger.warning(f"[repair] {stock.ticker} non troncato: {exc}")
            print(f"  FALLITO {stock.ticker:<10} {str(exc)[:70]}")
    print()
    print("Ricalcola i punteggi tecnici: i vecchi restano sulla base sbagliata.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="repair (destructive refetch)")
    ap.add_argument(
        "--truncate", action="store_true",
        help="drop every bar BEFORE the break instead of refetching - for a "
             "break the source itself reproduces (see SOXS in _truncate)",
    )
    ap.add_argument("--ticker", action="append", help="limit to these tickers")
    ap.add_argument(
        "--no-source-check",
        action="store_true",
        help="skip asking yfinance whether each flagged date is a real split",
    )
    args = ap.parse_args()

    only = set(args.ticker) if args.ticker else None
    db = SessionLocal()
    try:
        found = scan(db, only)
        if not found:
            print("nessuna discontinuita' di base trovata.")
            return

        print(f"{len(found)} titoli con una discontinuita' sospetta:\n")
        print(f"{'ticker':<10}{'data':<12}{'prezzo':>10}{'volume':>10}{'~split':>9}")
        for stock, breaks in found:
            for b in breaks:
                vr = f"x{b.volume_ratio:.2f}" if b.volume_ratio else "n/d"
                print(
                    f"{stock.ticker:<10}{str(b.date):<12}"
                    f"{'x' + format(b.price_ratio, '.3f'):>10}{vr:>10}"
                    f"{format(b.matched_ratio, '.0f') + ':1':>9}"
                )

        if not args.no_source_check:
            print()
            print("verdetto della sorgente (una richiesta per rottura):")
            for stock, breaks in found:
                for b in breaks:
                    print(f"  {stock.ticker:<10}{str(b.date):<12}{_source_verdict(stock.ticker, b.date)}")
            print()
            print("Un movimento reale NON va riparato: la storia archiviata e' gia' corretta,")
            print("e --truncate distruggerebbe barre buone. Vedi la nota EYPT in CLAUDE.md.")

        if args.truncate:
            _truncate(db, found)
            return

        if not args.apply:
            print()
            print("sola lettura.")
            print("  --apply    riscarica da capo - SOLO se un download fresco e' pulito")
            print("  --truncate elimina le barre prima della rottura - quando non lo e'")
            return

        print(f"\nriparazione di {len(found)} titoli (wipe + refetch 10y)...")
        ok = failed = 0
        for stock, _ in found:
            try:
                rows = _rebase_full_history(db, stock)
                db.commit()
                ok += 1
                print(f"  ok      {stock.ticker:<10} {rows} barre riscaricate")
            except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the rest
                db.rollback()
                failed += 1
                logger.warning(f"[repair] {stock.ticker} non riparato: {exc}")
                print(f"  FALLITO {stock.ticker:<10} {str(exc)[:70]}")
        print(f"\nriparati {ok}, falliti {failed}.")
        if ok:
            print("Ricalcola i punteggi tecnici: i vecchi restano sulla base sbagliata.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
