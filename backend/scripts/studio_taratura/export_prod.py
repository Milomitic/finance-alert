# Esporta da produzione, in sola lettura, il materiale dello studio (poche
# migliaia di righe: le serie COMPLETE si leggono col \copy di Postgres, vedi
# percorsi.py — dal container dell'app finiscono in OOM).
# Esporta da produzione, in sola lettura, il materiale dello studio.
# Uso: ... python - <tabella>   (argv[1] via env TABELLA)
import csv, json, os, sys, gzip, io, base64
from sqlalchemy import text
from app.core.db import SessionLocal
T = os.environ.get("TABELLA") or sys.argv[1]
db = SessionLocal()
buf = io.StringIO()
w = csv.writer(buf)
if T == "alerts":
    rows = db.execute(text("""
        select a.id, a.stock_id, s.ticker, a.signal_name, a.signal_date, a.triggered_at,
               a.trigger_price, a.archived_at is not null, a.snapshot
        from alerts a join stocks s on s.id=a.stock_id
        where a.signal_name is not null order by a.id""")).all()
    w.writerow(["id","stock_id","ticker","detector","signal_date","triggered_at","trigger_price",
                "archived","tone","strength","probability","regime","horizon","first_horizon",
                "first_emitted_at","first_price","first_atr","atr","first_inval","inval",
                "amend_count","factors"])
    for r in rows:
        try: sn = json.loads(r[8]) if r[8] else {}
        except Exception: sn = {}
        def lv(x):
            return x.get("level") if isinstance(x, dict) else None
        w.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], int(bool(r[7])),
                    sn.get("tone"), sn.get("strength"), sn.get("probability"), sn.get("regime"),
                    sn.get("horizon"), sn.get("first_horizon"), sn.get("first_emitted_at"),
                    sn.get("first_price"), sn.get("first_atr"), sn.get("atr"),
                    lv(sn.get("first_invalidation")), lv(sn.get("invalidation")),
                    sn.get("amend_count"), json.dumps(sn.get("factors") or {}, separators=(",",":"))])
elif T in ("plan_outcomes", "signal_outcomes"):
    res = db.execute(text(f"select * from {T} order by id"))
    w.writerow(list(res.keys()))
    for r in res: w.writerow(list(r))
elif T == "stocks":
    res = db.execute(text("select id, ticker, exchange, sector, industry, country, currency, market_cap from stocks order by id"))
    w.writerow(list(res.keys()))
    for r in res: w.writerow(list(r))
elif T == "ohlcv":
    res = db.execute(text("select stock_id, date, open, high, low, close, volume from ohlcv_daily where date >= '2024-09-01' order by stock_id, date"))
    w.writerow(["stock_id","date","open","high","low","close","volume"])
    for r in res: w.writerow(list(r))
db.close()
sys.stdout.write(base64.b64encode(gzip.compress(buf.getvalue().encode())).decode())
