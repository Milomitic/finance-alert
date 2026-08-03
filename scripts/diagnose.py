#!/usr/bin/env python3
"""Read-only production diagnostics, aggregated into findings.

Written so the agent can answer "what is wrong right now" without asking for a
screenshot. Access alone would not achieve that: a raw log dump is 500 lines
that still need reading. The work this script does is the COLLAPSE — turning
those lines into a ranked handful of signatures, each with a count and a first
/ last seen. Fifty "no data for <TICKER>" lines are one finding about one
upstream, not fifty findings.

HOW IT GETS IN, and why this way.

The app itself authenticates by session cookie only: no API key, no roles, so
there is no read-only credential to hand out and adding one would mean putting
a new auth path on a public host. Grafana is already deployed, already sits
behind the NSG allowlist on :443, and already has exactly the right primitive —
a SERVICE ACCOUNT with the Viewer role, which is read-only by construction and
revocable in one click. It also proxies both Loki and Prometheus, so one
credential covers logs and metrics.

SETUP (once, and the token never passes through the chat):

  1. Grafana → Administration → Service accounts → Add service account
     name: "agent-diagnostics", role: Viewer
  2. Add service account token, copy it
  3. Write it into scripts/.env (that file is gitignored):
        GRAFANA_TOKEN=glsa_xxxxxxxx
  4. Run:  python scripts/diagnose.py

Viewer cannot mutate anything: no dashboards, no datasources, no alert rules.
The worst a leaked token does is read telemetry from a host already restricted
to one IP — and revoking it is one click, with no app redeploy.

    python scripts/diagnose.py [--hours 6] [--limit 3000]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEFAULT_BASE = "https://80-225-80-141.sslip.io/grafana"
ENV_FILE = Path(__file__).with_name(".env")

# Force UTF-8 on stdout. A Windows console defaults to cp1252 and raises
# UnicodeEncodeError on the first non-latin1 byte — and log lines are exactly
# where such bytes turn up, unpredictably. Fixing it at the stream rather than
# sanitising each string means a stray character in someone's stack trace can
# never again abort the whole report; errors="replace" keeps it printing.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Log noise is mostly ONE message repeated with a different subject. Collapsing
# on these turns "PAYX, SJM, LLY, J, SPOT have no data" into a single finding
# that says how many and which — which is the actual shape of the problem.
_NORMALISE = [
    (re.compile(r"\b[A-Z]{1,6}(?:[.-][A-Z]{1,4})?(?=:| )"), "<TICKER>"),
    (re.compile(r"\b\d+\.\d+\b"), "<FLOAT>"),
    (re.compile(r"\b\d{3,}\b"), "<N>"),
    (re.compile(r"0x[0-9a-f]+", re.I), "<ADDR>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][\d:.]+\b"), "<TS>"),
]


def _read_token() -> str:
    """From scripts/.env, or the environment. Never printed, never logged."""
    import os

    tok = os.environ.get("GRAFANA_TOKEN")
    if tok:
        return tok.strip()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GRAFANA_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    # ASCII only: this is the first thing a new user sees, and a Windows
    # console on cp1252 renders an arrow as a mojibake escape.
    print(
        "No GRAFANA_TOKEN found.\n\n"
        "  Grafana -> Administration -> Service accounts -> Add service account\n"
        "    name: agent-diagnostics   role: Viewer   (read-only)\n"
        "  Add a token, then put it in scripts/.env (gitignored):\n"
        "    GRAFANA_TOKEN=glsa_...\n\n"
        "Viewer cannot change anything, and revoking is one click.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _get(base: str, path: str, token: str, params: dict | None = None) -> dict:
    url = f"{base}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:  # noqa: S310 — fixed https base
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read()[:200].decode("utf-8", "replace")
        raise SystemExit(f"{path} → HTTP {e.code}: {body}") from e


def _datasources(base: str, token: str) -> dict[str, str]:
    """{type: uid} for the ones we query. Discovered rather than hard-coded —
    uids change when the stack is reinstalled."""
    out: dict[str, str] = {}
    for ds in _get(base, "/api/datasources", token):
        if ds.get("type") in ("loki", "prometheus") and ds["type"] not in out:
            out[ds["type"]] = ds["uid"]
    return out


def _signature(msg: str) -> str:
    for pat, repl in _NORMALISE:
        msg = pat.sub(repl, msg)
    return msg.strip()[:160]


def _loki_range(base: str, token: str, uid: str, query: str, hours: int, limit: int):
    end = datetime.now(UTC)
    start = end - timedelta(hours=hours)
    return _get(
        base,
        f"/api/datasources/proxy/uid/{uid}/loki/api/v1/query_range",
        token,
        {
            "query": query,
            "start": str(int(start.timestamp() * 1e9)),
            "end": str(int(end.timestamp() * 1e9)),
            "limit": str(limit),
            "direction": "backward",
        },
    )


# Known-benign lines that would otherwise dominate the ranking. The first run
# of this script spent a third of its 3,000-line budget on two CoreDNS warnings
# about optional config files that were never meant to exist — noise loud
# enough to push real findings off the page. Excluded at the QUERY, not after,
# so the budget goes to lines worth reading.
_MUTE = [
    "No files matching import glob pattern",   # coredns optional custom config
]


def report_log_signatures(base: str, token: str, uid: str, hours: int, limit: int) -> None:
    q = '{namespace=~".+"} |~ "(?i)(warning|error|exception|traceback|failed)"'
    for pat in _MUTE:
        q += f' != "{pat}"'
    data = _loki_range(base, token, uid, q, hours, limit)
    groups: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "first": None, "last": None, "example": "", "subjects": set()}
    )
    total = 0
    for stream in data.get("data", {}).get("result", []):
        for ts_ns, line in stream.get("values", []):
            total += 1
            ts = datetime.fromtimestamp(int(ts_ns) / 1e9, UTC)
            sig = _signature(line)
            g = groups[sig]
            g["n"] += 1
            g["last"] = max(g["last"] or ts, ts)
            g["first"] = min(g["first"] or ts, ts)
            if not g["example"]:
                g["example"] = line.strip()[:200]
            for m in re.finditer(r"\b[A-Z]{2,6}(?:[.-][A-Z]{1,4})?\b", line):
                g["subjects"].add(m.group(0))

    print(f"\n{'=' * 92}\nLOG SIGNATURES — last {hours}h ({total:,} matching lines)\n{'=' * 92}")
    if not groups:
        print("  nothing matching warning/error in the window.")
        return
    for sig, g in sorted(groups.items(), key=lambda kv: -kv[1]["n"])[:20]:
        span = f"{g['first']:%H:%M} → {g['last']:%H:%M}"
        print(f"\n  [{g['n']:>5}x]  {span}   {sig}")
        print(f"          e.g. {g['example']}")
        subs = sorted(s for s in g["subjects"] if len(s) <= 6)[:12]
        if len(subs) > 2:
            print(f"          subjects: {', '.join(subs)}")


def report_metrics(base: str, token: str, uid: str, hours: int) -> None:
    """A handful of PromQL questions whose answers are usually the story."""
    checks = [
        ("restarts of the app pod",
         f'changes(process_start_time_seconds[{hours}h])'),
        ("python exceptions/min (if instrumented)",
         'sum(rate(python_exceptions_total[15m])) * 60'),
        ("http 5xx/min",
         'sum(rate(http_requests_total{status=~"5.."}[15m])) * 60'),
        ("resident memory (MB)",
         'process_resident_memory_bytes / 1024 / 1024'),
    ]
    print(f"\n{'=' * 92}\nMETRICS\n{'=' * 92}")
    for label, expr in checks:
        try:
            res = _get(
                base, f"/api/datasources/proxy/uid/{uid}/api/v1/query", token,
                {"query": expr},
            )
            rows = res.get("data", {}).get("result", [])
            if not rows:
                print(f"  {label:<40} (no series — metric not exported)")
                continue
            vals = ", ".join(f"{float(r['value'][1]):.2f}" for r in rows[:4])
            print(f"  {label:<40} {vals}")
        except SystemExit as e:
            print(f"  {label:<40} query failed: {e}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--hours", type=int, default=6)
    p.add_argument("--limit", type=int, default=3000)
    a = p.parse_args()

    token = _read_token()
    ds = _datasources(a.base, token)
    if not ds:
        raise SystemExit("no loki/prometheus datasource visible to this token")
    print(f"datasources: {', '.join(sorted(ds))}")

    if "loki" in ds:
        report_log_signatures(a.base, token, ds["loki"], a.hours, a.limit)
    if "prometheus" in ds:
        report_metrics(a.base, token, ds["prometheus"], a.hours)


if __name__ == "__main__":
    main()
