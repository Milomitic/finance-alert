"""Stampa il confronto dal vivo fra i modelli in ombra e il motore di oggi.

    kubectl exec -n finance-alert finance-alert-finance-alert-0 -- \
        python -m app.scripts.rapporto_modelli_ombra

Sola lettura. Misura, non promuove: il criterio e' in
`docs/superpowers/specs/2026-09-24-modelli-in-ombra.md`.
"""
from __future__ import annotations

import json


def main() -> None:
    from app.core.db import SessionLocal
    from app.ml.valutazione import rapporto

    with SessionLocal() as db:
        print(json.dumps(rapporto(db), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
