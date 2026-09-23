"""Modelli minimi in numpy: logistica L2 e gradient boosting a istogrammi.

Niente scikit-learn nel progetto, e non serve: per una domanda di fattibilita'
bastano una lineare regolarizzata e un GBM stile LightGBM (binning a quantili,
alberi poco profondi, shrinkage, sottocampionamento).
"""
import numpy as np


# ─── metriche ──────────────────────────────────────────────────────────────
def auc(y, s):
    y = np.asarray(y, bool); s = np.asarray(s, float)
    ok = np.isfinite(s)
    y, s = y[ok], s[ok]
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = _rank(s)
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def _rank(x):
    o = np.argsort(x, kind="mergesort")
    r = np.empty(len(x), float)
    r[o] = np.arange(1, len(x) + 1)
    # pareggi: media dei ranghi
    xs = x[o]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        if j > i:
            r[o[i:j + 1]] = (i + j + 2) / 2
        i = j + 1
    return r


def spearman(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 10:
        return np.nan
    ra, rb = _rank(a[ok]), _rank(b[ok])
    return np.corrcoef(ra, rb)[0, 1]


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))


# ─── logistica L2 ──────────────────────────────────────────────────────────
class Logistica:
    def __init__(self, l2=1.0):
        self.l2 = l2

    def _prep(self, X, fit=False):
        X = np.asarray(X, float)
        if fit:
            self.med = np.nanmedian(X, axis=0)
            self.med = np.where(np.isfinite(self.med), self.med, 0.0)
            Xi = np.where(np.isnan(X), self.med, X)
            self.lo = np.nanpercentile(Xi, 1, axis=0); self.hi = np.nanpercentile(Xi, 99, axis=0)
            Xi = np.clip(Xi, self.lo, self.hi)
            self.mu = Xi.mean(0); self.sd = Xi.std(0); self.sd[self.sd == 0] = 1
        Xi = np.clip(np.where(np.isnan(X), self.med, X), self.lo, self.hi)
        Z = (Xi - self.mu) / self.sd
        M = np.isnan(X).astype(float)
        return np.hstack([np.ones((len(X), 1)), Z, M])

    def fit(self, X, y):
        A = self._prep(X, fit=True)
        y = np.asarray(y, float)
        w = np.zeros(A.shape[1])
        R = np.eye(A.shape[1]) * self.l2; R[0, 0] = 0
        for _ in range(25):
            p = 1 / (1 + np.exp(-A @ w))
            g = A.T @ (p - y) + R @ w
            Hs = (A * (p * (1 - p))[:, None]).T @ A + R
            step = np.linalg.solve(Hs + 1e-8 * np.eye(len(w)), g)
            w -= step
            if np.abs(step).max() < 1e-6:
                break
        self.w = w
        return self

    def predict(self, X):
        return 1 / (1 + np.exp(-self._prep(X) @ self.w))


# ─── gradient boosting a istogrammi ────────────────────────────────────────
class GBM:
    """Perdita logistica (loss='log') o quadratica (loss='l2')."""

    def __init__(self, n_trees=300, depth=3, lr=0.03, n_bins=32, min_leaf=300,
                 l2=10.0, subsample=0.7, colsample=0.7, seed=0, loss="log"):
        self.__dict__.update(locals()); del self.__dict__["self"]

    def _bin(self, X, fit=False):
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

    def fit(self, X, y):
        rng = np.random.default_rng(self.seed)
        B = self._bin(X, fit=True)
        n, F = B.shape
        self.nb = self.n_bins + 1
        y = np.asarray(y, float)
        if self.loss == "log":
            p0 = np.clip(y.mean(), 1e-4, 1 - 1e-4)
            self.base = np.log(p0 / (1 - p0))
        else:
            self.base = y.mean()
        f = np.full(n, self.base)
        self.trees = []
        off = (np.arange(F) * self.nb)[None, :]
        for _ in range(self.n_trees):
            if self.loss == "log":
                p = 1 / (1 + np.exp(-f)); g = p - y; h = np.maximum(p * (1 - p), 1e-6)
            else:
                g = f - y; h = np.ones(n)
            rows = np.where(rng.random(n) < self.subsample)[0]
            cols = np.where(rng.random(F) < self.colsample)[0]
            if len(cols) == 0:
                cols = np.arange(F)
            tree = self._grow(B, g, h, rows, cols, off)
            self.trees.append(tree)
            f += self.lr * self._apply(tree, B)
        return self

    def _grow(self, B, g, h, rows, cols, off):
        # albero come lista di nodi: (feat, soglia, sx, dx) o ('foglia', valore)
        nodes = []

        def build(idx, d):
            G, Hh = g[idx].sum(), h[idx].sum()
            if d == self.depth or len(idx) < 2 * self.min_leaf:
                nodes.append(("L", -G / (Hh + self.l2)))
                return len(nodes) - 1
            sub = B[idx][:, cols]
            flat = (sub + (np.arange(len(cols)) * self.nb)[None, :]).ravel()
            Gh = np.bincount(flat, weights=np.repeat(g[idx], len(cols)), minlength=len(cols) * self.nb).reshape(len(cols), self.nb)
            Hh_ = np.bincount(flat, weights=np.repeat(h[idx], len(cols)), minlength=len(cols) * self.nb).reshape(len(cols), self.nb)
            Cn = np.bincount(flat, minlength=len(cols) * self.nb).reshape(len(cols), self.nb)
            GL, HL, CL = Gh.cumsum(1), Hh_.cumsum(1), Cn.cumsum(1)
            GR, HR, CR = G - GL, Hh - HL, len(idx) - CL
            gain = GL ** 2 / (HL + self.l2) + GR ** 2 / (HR + self.l2) - G ** 2 / (Hh + self.l2)
            gain[(CL < self.min_leaf) | (CR < self.min_leaf)] = -np.inf
            gain[:, -1] = -np.inf
            j, t = np.unravel_index(np.argmax(gain), gain.shape)
            if not np.isfinite(gain[j, t]) or gain[j, t] <= 0:
                nodes.append(("L", -G / (Hh + self.l2)))
                return len(nodes) - 1
            feat = cols[j]
            me = len(nodes); nodes.append(None)
            left = idx[B[idx, feat] <= t]
            right = idx[B[idx, feat] > t]
            sx = build(left, d + 1); dx = build(right, d + 1)
            nodes[me] = (feat, t, sx, dx)
            return me

        build(rows, 0)
        return nodes

    def _apply(self, tree, B):
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
            stack.append((sx, idx[m])); stack.append((dx, idx[~m]))
        return out

    def raw(self, X):
        B = self._bin(X)
        f = np.full(len(B), self.base)
        for t in self.trees:
            f += self.lr * self._apply(t, B)
        return f

    def predict(self, X):
        f = self.raw(X)
        return 1 / (1 + np.exp(-f)) if self.loss == "log" else f

    def importanza(self, F):
        imp = np.zeros(F)
        for t in self.trees:
            for nd in t:
                if nd[0] != "L":
                    imp[nd[0]] += 1
        return imp / max(imp.sum(), 1)
