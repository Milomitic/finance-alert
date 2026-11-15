"""La completezza dei fondamentali: gemella di confidenza.ts (FA-156)."""
import json
from pathlib import Path
from types import SimpleNamespace

from app.services import completezza_service as cs

VETTORI = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "completezzaVectors.json"


def test_i_vettori_condivisi_col_frontend():
    d = json.loads(VETTORI.read_text(encoding="utf-8"))
    ns = lambda xs: [SimpleNamespace(**x) for x in xs]  # noqa: E731
    for caso in d["casi"]:
        v = cs.completezza(ns(caso["annual"]), ns(caso["quarterly"]), ns(caso["earnings"]), d["oggi"])
        assert v == caso["atteso"], caso["perche"]
