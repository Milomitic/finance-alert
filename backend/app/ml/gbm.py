# ruff: noqa: N803, N806 — X, B, F, G, H: la notazione del boosting, come nello studio
"""Gradient boosting a istogrammi in numpy, serializzabile in JSON.

Portato da `backend/scripts/studio_taratura/ml.py`, dove ha prodotto i due
risultati che la fase 3 mette in prova (volatilita' prevista, selezione dei
match). Il progetto non ha scikit-learn e non serve: binning a quantili, alberi
poco profondi, shrinkage, sottocampionamento di righe e colonne.

Modulo FOGLIA: solo numpy. Lo importano lo scan (per i punteggi) e il job di
addestramento; una dipendenza in piu' qui la trascinerebbe in entrambi.

Differenze dall'originale, tutte senza effetto sui numeri:
  - `to_dict` / `from_dict`, perche' il modello vive in una riga del database;
  - i nodi sono liste e non tuple, cosi' il giro JSON e' l'identita'.
"""
from __future__ import annotations

import numpy as np


class GBM:
    """Perdita logistica (`loss="log"`) o quadratica (`loss="l2"`)."""

    def __init__(self, n_trees: int = 300, depth: int = 3, lr: float = 0.03,
                 n_bins: int = 32, min_leaf: int = 300, l2: float = 10.0,
                 subsample: float = 0.7, colsample: float = 0.7, seed: int = 0,
                 loss: str = "log") -> None:
        self.n_trees, self.depth, self.lr, self.n_bins = n_trees, depth, lr, n_bins
        self.min_leaf, self.l2, self.subsample, self.colsample = min_leaf, l2, subsample, colsample
        self.seed, self.loss = seed, loss
        self.edges: list[np.ndarray] = []
        self.trees: list[list] = []
        self.base = 0.0

    # ── binning ────────────────────────────────────────────────────────────
    def _bin(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        X = np.asarray(X, float)
        if fit:
            self.edges = []
            for j in range(X.shape[1]):
                col = X[:, j][np.isfinite(X[:, j])]
                if len(col) == 0:
                    self.edges.append(np.array([]))
                    continue
                q = np.unique(np.quantile(col, np.linspace(0, 1, self.n_bins)[1:-1]))
                self.edges.append(q)
        B = np.zeros(X.shape, np.int32)
        for j, e in enumerate(self.edges):
            col = X[:, j]
            b = np.searchsorted(e, col, side="right") + 1   # 1..len(e)+1
            b[~np.isfinite(col)] = 0                         # NaN: bin 0
            B[:, j] = b
        return B

    # ── addestramento ──────────────────────────────────────────────────────
    def fit(self, X: np.ndarray, y: np.ndarray) -> GBM:
        rng = np.random.default_rng(self.seed)
        B = self._bin(X, fit=True)
        n, F = B.shape
        self.nb = self.n_bins + 1
        y = np.asarray(y, float)
        if self.loss == "log":
            p0 = float(np.clip(y.mean(), 1e-4, 1 - 1e-4))
            self.base = float(np.log(p0 / (1 - p0)))
        else:
            self.base = float(y.mean())
        f = np.full(n, self.base)
        self.trees = []
        for _ in range(self.n_trees):
            if self.loss == "log":
                p = 1 / (1 + np.exp(-f))
                g = p - y
                h = np.maximum(p * (1 - p), 1e-6)
            else:
                g = f - y
                h = np.ones(n)
            rows = np.where(rng.random(n) < self.subsample)[0]
            cols = np.where(rng.random(F) < self.colsample)[0]
            if len(cols) == 0:
                cols = np.arange(F)
            tree = self._grow(B, g, h, rows, cols)
            self.trees.append(tree)
            f += self.lr * self._apply(tree, B)
        return self

    def _grow(self, B, g, h, rows, cols) -> list:
        nodes: list = []

        def build(idx, d):
            G, Hh = g[idx].sum(), h[idx].sum()
            if d == self.depth or len(idx) < 2 * self.min_leaf:
                nodes.append(["L", float(-G / (Hh + self.l2))])
                return len(nodes) - 1
            sub = B[idx][:, cols]
            flat = (sub + (np.arange(len(cols)) * self.nb)[None, :]).ravel()
            size = len(cols) * self.nb
            Gh = np.bincount(flat, weights=np.repeat(g[idx], len(cols)), minlength=size).reshape(len(cols), self.nb)
            Hb = np.bincount(flat, weights=np.repeat(h[idx], len(cols)), minlength=size).reshape(len(cols), self.nb)
            Cn = np.bincount(flat, minlength=size).reshape(len(cols), self.nb)
            GL, HL, CL = Gh.cumsum(1), Hb.cumsum(1), Cn.cumsum(1)
            GR, HR, CR = G - GL, Hh - HL, len(idx) - CL
            gain = GL ** 2 / (HL + self.l2) + GR ** 2 / (HR + self.l2) - G ** 2 / (Hh + self.l2)
            gain[(self.min_leaf > CL) | (self.min_leaf > CR)] = -np.inf
            gain[:, -1] = -np.inf
            j, t = np.unravel_index(np.argmax(gain), gain.shape)
            if not np.isfinite(gain[j, t]) or gain[j, t] <= 0:
                nodes.append(["L", float(-G / (Hh + self.l2))])
                return len(nodes) - 1
            feat = int(cols[j])
            me = len(nodes)
            nodes.append(None)
            left = idx[B[idx, feat] <= t]
            right = idx[B[idx, feat] > t]
            sx = build(left, d + 1)
            dx = build(right, d + 1)
            nodes[me] = [feat, int(t), sx, dx]
            return me

        build(rows, 0)
        return nodes

    @staticmethod
    def _apply(tree: list, B: np.ndarray) -> np.ndarray:
        out = np.empty(len(B))
        stack = [(0, np.arange(len(B)))]
        while stack:
            k, idx = stack.pop()
            nd = tree[k]
            if nd[0] == "L":
                out[idx] = nd[1]
                continue
            feat, t, sx, dx = nd
            m = B[idx, feat] <= t
            stack.append((sx, idx[m]))
            stack.append((dx, idx[~m]))
        return out

    # ── previsione ─────────────────────────────────────────────────────────
    def raw(self, X: np.ndarray) -> np.ndarray:
        B = self._bin(X)
        f = np.full(len(B), self.base)
        for t in self.trees:
            f += self.lr * self._apply(t, B)
        return f

    def predict(self, X: np.ndarray) -> np.ndarray:
        f = self.raw(X)
        return 1 / (1 + np.exp(-f)) if self.loss == "log" else f

    def importanza(self, F: int) -> np.ndarray:
        imp = np.zeros(F)
        for t in self.trees:
            for nd in t:
                if nd[0] != "L":
                    imp[nd[0]] += 1
        return imp / max(imp.sum(), 1)

    # ── persistenza ────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "loss": self.loss, "lr": self.lr, "base": self.base,
            "edges": [e.tolist() for e in self.edges],
            "trees": self.trees,
        }

    @classmethod
    def from_dict(cls, d: dict) -> GBM:
        g = cls(lr=float(d["lr"]), loss=str(d["loss"]))
        g.base = float(d["base"])
        g.edges = [np.asarray(e, float) for e in d["edges"]]
        g.trees = [list(t) for t in d["trees"]]
        return g
