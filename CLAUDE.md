# Finance-Alert: Project notes for the agent

Persistent notes accumulated across sessions so we don't waste time
re-discovering recurring problems and patterns. **Read this before doing
anything else in this repo.**

---

## ✅ Commit & push automatically (standing user instruction, 2026-05)

**The user has explicitly opted in to auto-commit + auto-push.** After
completing a coherent unit of work (a feature, fix, refactor, or doc update),
**commit it and push to `origin/cloud` without being asked** — this overrides
the generic "only commit when explicitly asked" default.

⚠️ It said `origin/master` until 2026-09-02. **`cloud` is the deployed branch**:
CI only builds an image and bumps the GitOps tag on a push to `refs/heads/cloud`
(see the `workflow_dispatch` note below), so a push to `master` verifies nothing
and reaches no cluster.

Expect `origin/cloud` to have moved every time you go to push: CI writes the new
image tag back into `charts/finance-alert/values-oci.yaml` on the same branch
(`chore(cd): image <sha> [skip ci]`), so the GitOps loop advances the branch on
its own after every deploy. `git fetch && git rebase origin/cloud` then push —
never force.

### ⚠️ Non citare uno SHA nello stesso push del commit che nomina (2026-09-14)

Conseguenza diretta della riga sopra, e costata due correzioni in un'ora. Le
voci di `PROJECT-BACKLOG.md` citano il commit che le chiude — «Commit `2938707`»
— ma **il rebase riscrive ogni commit locale DOPO che il riferimento e' gia'
stato scritto dentro uno di essi**. Scritto `9be0c3b`, spinto `0c8ab3c`: la
voce punta a un commit che sul ramo non esiste, e `git merge-base
--is-ancestor` lo conferma in un secondo.

Uno SHA e' stabile solo DOPO il push. Quindi la voce di backlog che cita il
commit va scritta in un push **successivo** a quello del codice — mai nello
stesso. La variante peggiore e' indovinarlo prima che il commit esista, che e'
il modo in cui questo e' cominciato.

⚠️ E' la stessa famiglia del `_RANGE_PERIODS` morto: un riferimento sbagliato e'
credibile, verificabile solo da chi lo controlla, e corrobora la convinzione che
qualcuno abbia gia' guardato.

Guidelines:
- Commit at natural completion points (work builds + tests pass), not mid-edit.
- Group related changes into one logical commit with a descriptive message;
  split unrelated work into separate commits.
- Follow the existing message style and the `Co-Authored-By` trailer.
- After any `frontend/` change: rebuild `dist` per the post-commit hygiene
  checklist below BEFORE telling the user it's ready.
- Still NEVER force-push, skip hooks, amend shared history, or commit secrets.
- If something genuinely shouldn't be committed yet (broken/experimental),
  say so explicitly rather than committing it.

---

## ⚠️ Backend restart: ignore the OLD task's "failed" notification

**The most common time-waster.** Every backend restart produces a misleading
"Background command failed" notification. Internalize once and stop chasing it.

### What happens
1. I `taskkill //PID <old> //F` to kill the previous uvicorn
2. I start a fresh uvicorn with `run_in_background: true` (new task id)
3. ~10–30s later a notification arrives:
   ```
   <task-id>OLD_ID</task-id>
   <status>failed</status>
   <summary>Background command "Restart backend" failed with exit code 1</summary>
   ```

### What it actually means
The notification's `task-id` is the **OLD** task — the one whose process I just
killed. Uvicorn exiting because of `taskkill /F` returns a non-zero exit code,
so the background-task wrapper marks the OLD task "failed". This is the kill
ack, not a problem with the NEW backend.

### What to do
**Ignore the notification.** Verify the new backend is up via:
```bash
until curl -sf http://127.0.0.1:8000/api/health 2>nul | grep -q "ok"; do sleep 1; done
```
If health returns OK, everything is fine. The kill-and-restart sequence is
working as intended.

### What NOT to do
- Don't read the failure output as if it's the new backend's startup error
- Don't try to "fix" it
- Don't restart again on the assumption that the start failed
- Don't apologize to the user about the failure — it's expected

### Canonical restart sequence
```
1. netstat -ano | findstr :8000 | findstr LISTENING   # get PID
2. taskkill //PID <PID> //F                            # ignore old-task fail
3. uvicorn ... (run_in_background: true)               # new task
4. curl /api/health until 200                          # confirm new task up
```

### Watch out: orphaned uvicorn workers (the "fix doesn't work" trap)

`uvicorn --reload` forks two processes: the *reloader* (parent, listed
by `tasklist`) and the *worker* (child, spawned via
`multiprocessing.spawn`). Killing only the reloader's PID leaves the
worker alive on Windows — it keeps the listening socket bound and
serves requests with **stale code**. Symptoms:
- You fix a bug, restart backend, request still returns the pre-fix
  500 / wrong response.
- `netstat -ano | findstr :8000` shows 2-3 LISTENING entries (Windows
  allows multiple binders via `SO_REUSEADDR`).
- `tasklist | findstr <old-pid>` says the PID doesn't exist (it's the
  dead reloader).
- TestClient via Python (in-process) works fine — proves the fixed
  code is correct, but uvicorn isn't running it.

If you suspect this, find orphan workers via:
```bash
wmic process where "Name='python.exe'" get ProcessId,ParentProcessId,CommandLine
```
The orphans look like `python.exe -c "from multiprocessing.spawn import
spawn_main; spawn_main(parent_pid=<dead-reloader-pid>, ...)"`. Kill
each by its `ProcessId` (the worker's, not the parent's).

Then re-verify with `netstat`: a healthy state has exactly ONE LISTENING
entry on 8000.

### `git pull` does NOT trigger `uvicorn --reload` on Windows

`uvicorn --reload` uses `watchfiles` (inotify-equivalent). On Windows
when files are touched by an external process — `git pull`, `git
checkout`, an editor like VSCode swapping the file via temp+rename —
the change events are **frequently missed**. The file mtime updates
on disk but the worker keeps serving the old in-memory bytecode.
Symptom that just bit us: pull lands a fix, browser polls /quote,
flashes the right value once (cached layer), then reverts to the
pre-fix value (worker's stale code).

**Quick check:**
```bash
# File mtime
stat -c '%y' backend/app/services/<file>.py
# Worker creation time
wmic process where "Name='python.exe'" get ProcessId,CreationDate,CommandLine
```
If the worker (the `spawn_main` row) is OLDER than the file, the
auto-reload missed the event. Solution: run the canonical restart
sequence above. Do NOT trust `--reload` after a pull — it's not free
to verify and the failure is silent.

### Agent operating rule: restart backend always, frontend only if stale after F5

**The asymmetry is real.** Both `uvicorn --reload` (watchfiles) and Vite
(chokidar) can drop file-change events on Windows — but the failure
modes are nothing alike:

| | Detection on miss | Recovery |
|---|---|---|
| Vite | User notices stale page | **F5 → fresh bundle from disk, free** |
| uvicorn | API still returns stale data, user thinks "fix didn't work" | None — module bytecode is in worker memory, MUST kill the worker |

So the agent's restart discipline is asymmetric:

1. **Backend Python edit (`backend/app/**`)** — ALWAYS restart uvicorn
   with the canonical kill-tree + spawn sequence above, immediately
   after the edit. There is no F5 for the backend; a missed reload
   means hours of debugging a phantom.

2. **Frontend file edit (`frontend/src/**`, `vite.config.ts`, etc.)** —
   trust Vite HMR by default. If the user reports the change not
   showing AFTER an F5, then restart Vite (port 5173). HMR + F5
   covers ~99% of cases; the explicit restart is the rare fallback.

Backend restart sequence (already documented above; applies verbatim
to in-session Edit tool changes, not just `git pull`).

Frontend restart sequence (only when F5 doesn't cut it):
```bash
netstat -ano | findstr :5173 | findstr LISTENING
taskkill //PID <PID> //T //F
cd frontend && npm run dev   # run_in_background: true
# Vite prints "Local: http://localhost:5173" + binds to ::1 (IPv6)
# Smoke-test via http://localhost:5173/ NOT http://127.0.0.1:5173/
```

Why this rule is conservative on the backend, relaxed on the frontend:
restart cost is the same ~1-3s either way, but the COST OF NOT RESTARTING
is asymmetric — silent stale-code on backend, visible-stale-page on
frontend (user notices instantly, F5s, problem solved).

### ⚠️ FastAPI serves a pre-built frontend bundle on :8000 — rebuild after every FE commit

`backend/app/main.py` mounts `frontend/dist/` and serves it as the SPA shell
when present. So the same app exists at TWO URLs simultaneously:

| URL | Source | Picks up source edits? | When the user reports "non funziona" |
|---|---|---|---|
| http://localhost:**5173**/ | Vite dev server (`npm run dev`) | ✅ via HMR | F5 |
| http://localhost:**8000**/ | FastAPI serving `frontend/dist/` static files | ❌ NEVER — needs `npm run build` | **REBUILD DIST FIRST**, then hard-reload |

**The user defaults to testing on :8000 in this repo.** Two losses on this in
recent sessions (recompute button + scan-toast sub-phases): edits land,
backend reloads, agent says "F5 to see it", user says "still old". Root
cause every time: dist wasn't rebuilt.

#### Post-commit hygiene checklist (run after EVERY commit that touches `frontend/`)

Treat this as a hard pre-condition for telling the user "ready". Skip it →
the user wastes a round-trip telling you the page is still old.

```bash
# 1. Did this commit touch any frontend source?
git diff --name-only HEAD~1 HEAD | grep -qE '^frontend/(src|public|index\.html|vite\.config|package(-lock)?\.json|tsconfig)' && echo "FE touched — must rebuild" || echo "FE untouched — skip rebuild"

# 2. If touched, compare dist freshness vs the most-recently-edited FE source:
stat -c '%y' frontend/dist/index.html
stat -c '%y' $(git diff --name-only HEAD~1 HEAD | grep '^frontend/src/' | head -1)

# 3. Rebuild if dist is older:
cd frontend && npm run build
# Expected: "✓ built in ~1s" + new index.html + new hashed assets.

# 4. Sanity-check that the new strings actually landed in the bundle. Vite
#    minifies, so grep individual string literals (not full sentences):
grep -c "<distinctive-string-from-your-change>" frontend/dist/assets/index-*.js
# Expect 1+ matches. Zero = the change isn't in the bundle and you have a
# stale build.

# 5. Tell the user to hard-refresh (Ctrl+Shift+R / Cmd+Shift+R), NOT plain F5.
#    Browsers cache hashed assets aggressively; soft reload may keep the old
#    bundle. The hash in the filename changes on each build, so a hard
#    reload always pulls the new one.
```

#### Worktree pitfall: `frontend/node_modules/.bin/` may be broken in a worktree

The git worktree's `node_modules` often has the package directories but
missing `.bin/` symlinks (Windows + worktree edge case). Symptom:

```bash
$ npm run build
> tsc -b && vite build
"tsc" non è riconosciuto come comando interno o esterno...

$ ls node_modules/.bin/
ls: cannot access 'node_modules/.bin/': No such file or directory
```

`tsc` lives at `node_modules/typescript/bin/tsc` — the package is there, just
the .bin shim is missing. Fix: `npm install` from the frontend dir. It's
fast (~10s on warm cache) and only needs to run once per worktree session.

```bash
cd frontend && npm install     # restores .bin/ symlinks
cd frontend && npm run build   # now works
```

#### Why "just run `npm run build`" isn't enough — typical agent failure modes

| Agent shortcut | What goes wrong | Fix |
|---|---|---|
| "Source edited, F5 should work" | User is on :8000 → bundle is from last build → no F5 helps | Always rebuild after FE edits |
| `npm run build` in worktree → tsc not found | `.bin/` broken | `npm install` first |
| Build "succeeds" with TS errors | `npm run build` = `tsc -b && vite build`. tsc errors stop the build entirely | Read the tail; if there are TS errors NOT from your change, they're pre-existing — but a build error from YOUR change must be fixed before declaring done |
| User refreshes with F5, still sees old | Browser cached the hashed asset. Each `npm run build` mints a new hash; the index.html points to the new file, but the F5'd page may have already had the old index in memory | Tell the user "hard reload" (Ctrl+Shift+R) not "F5" |

#### TL;DR rule

Anything touching `frontend/` → **commit → rebuild dist → verify strings are in bundle → THEN tell user to hard-reload**.
Anything touching `backend/app/**` → **commit → restart uvicorn → verify /api/health → THEN tell user**.
Both? Do both.

---

## ⚠️ `npm audit fix` / `npm install` on Windows breaks `npm ci` on Linux

**This has now bitten FIVE times**, three of them on 2026-09-09 alone — see
the postscripts below. `frontend/package-lock.json` must be a
**cross-platform SUPERSET**: it needs the optional platform binaries for BOTH
Windows (dev) and Linux (Docker/CI). Any `npm install` / `npm audit fix` run on
Windows rewrites the lock with **only** the Windows set, and CI dies with:

```
npm ci can only install packages when your package.json and package-lock.json
are in sync … Missing: @emnapi/core@… from lock file
```

It is invisible locally — `npm run build` and even `npm ci` pass on Windows. Only
a clean `npm ci` on Linux shows it. And because the `frontend` job gates `image`,
a broken lock silently stops the deploy (image + bump get skipped).

**The recipe (from a594b29, re-applied 2026-07-17):**

```bash
cd frontend
npm install            # or npm audit fix — the Windows half
# add the linux half (needs Docker running):
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/app" -w /app node:20-alpine   npm install --package-lock-only --no-audit --no-fund
# verify BOTH — this is the whole point of a superset:
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/app" -w /app node:20-alpine npm ci
npm ci                 # windows side
```

Commit the lock only when both pass.

### Third occurrence, and what it costs when Docker is not available (2026-09-09)

Worth recording because the agent that hit it had read this file, and the
failure still looked like success locally. Windows `npm ci`, `npm run build`
and the full vitest suite all passed; Docker Desktop was not running, so the
Linux half of the recipe above was skipped and the superset was never checked.

The push produced **two red pipelines in a row** with the exact error quoted
above:

    npm error Missing: @emnapi/core@1.11.3 from lock file
    npm error Missing: @emnapi/runtime@1.11.3 from lock file
    npm error Missing: @emnapi/wasi-threads@1.2.3 from lock file

Note the third line. The first repair commit restored the two packages this
file names and was STILL red, because `@emnapi/core` carries a nested
`@emnapi/wasi-threads` of its own. **Fixing the packages listed here is not the
same as fixing the lock** — read the actual error each time.

On both red runs `backend`, `postgres` and `dependency audit` were green while
`image`, `trivy` and `gitops` were **skipped**. That is the documented shape:
six of seven jobs look fine and nothing deploys.

**If Docker is unavailable, CI is a valid substitute detector** — it runs a
clean `npm ci` on Linux, which is the only check that matters. It is noisier
(a red run per attempt, and no deploy until green) but it is not guesswork.
Push, then read the `frontend` job. Do NOT declare a lock change safe on a
green Windows run alone; that is what produced all three occurrences.

The net diff is what to verify before merging any lock change: **zero
`node_modules/*` keys removed.** The trap always REMOVES Linux entries, so a
removal count above zero is the signature, and it is one command:

```bash
git diff <base>..<head> -- frontend/package-lock.json | grep -E '^-\s+"node_modules/' | sort > /tmp/r
git diff <base>..<head> -- frontend/package-lock.json | grep -E '^\+\s+"node_modules/' | sort > /tmp/a
comm -23 /tmp/r /tmp/a   # must be EMPTY
```

### Fifth occurrence, caught BEFORE the push (2026-09-09)

The check above is worth running because it works. Adding a single dev
dependency — `npm install --save-dev axe-core` on Windows — removed
`@emnapi/runtime` in the same breath. That is the exact package a commit two
hours earlier (`c1d3d2e fix(ci): keep optional linux dependency in lockfile`)
had just put back after occurrence four.

    RIMOSSE: "node_modules/@emnapi/runtime"
    AGGIUNTE: "node_modules/axe-core"

So the rule is stronger than "be careful with `npm audit fix`": **any** npm
write on Windows can drop the Linux half, including a routine
`install --save-dev` of one unrelated package. Run the removal check after
every one of them.

**The repair, when Docker is unavailable and only one entry was lost.** Do not
regenerate the lock. Take the removed block verbatim out of `git show
HEAD:frontend/package-lock.json`, re-insert it in alphabetical position, assert
the file still parses as JSON, then re-run the removal check and `npm ci`. The
net diff is then the one package you meant to add and nothing else, which is
the only shape that cannot regress CI.


### Better, when it is ONE transitive package: edit the three fields

The recipe above regenerates the whole lock and needs Docker running. For a
single advisory on a transitive dependency there is a smaller move that cannot
break the superset, because it never touches it:

1. Let npm compute the new entry somewhere disposable —
   `npm update <pkg> --package-lock-only` — and copy the `version` /
   `resolved` / `integrity` it produced.
2. `git checkout -- frontend/package-lock.json` to get the known-good lock
   back.
3. Write those three fields into that package's entry and nothing else.
4. `npm ci` + `npm run build` + `npm run test:run` on Windows, and run the
   gate the way CI does:
   `npm audit --json --omit=dev > /tmp/a.json; node security/audit-gate.mjs /tmp/a.json`

The diff is three lines and every other byte is the lock CI already passes
with, so `npm ci` on Linux cannot regress. Applied for nanoid 3.3.16 -> 3.3.18
on 2026-08-20; the ordinary `npm update` on Windows had dropped
`@emnapi/core` and `@emnapi/runtime` (the exact packages in the failure
message above), and `--os=linux --cpu=x64` restored only the first.

Only valid when the bump stays INSIDE the existing semver range — nanoid was
`^3.3.12` under postcss, so nothing else in the tree had to move. If the fix
needs a range change in package.json, use the full Docker recipe.

---

## ⚠️ Checking CI: `gh run list` serves stale results

Cost time twice in one session (2026-08-26). `gh run list --branch cloud` kept
returning runs from six days earlier while a fresh run was already finished,
and once returned a run id from a completely different day. Do not trust it.

Ask the API instead — it has been correct every time:

```bash
gh api "repos/Milomitic/finance-alert/actions/runs?per_page=5"   --jq '.workflow_runs[] | "\(.created_at)  \(.head_sha[0:8])  \(.event)  \(.status)/\(.conclusion)"'
# or for one commit:
gh api "repos/Milomitic/finance-alert/actions/runs?head_sha=$(git rev-parse HEAD)" --jq .total_count
```

⚠️ **`gh run watch --exit-status` non e' un'alternativa: ha restituito 0 su una
run FALLITA** (2026-09-12, run 34698869490, `conclusion: failure` su trivy).
Blocca fino alla fine, il che e' utile, ma il suo codice di uscita non va letto
come l'esito. L'unica lettura affidabile e' la lista dei job, che dice anche
QUALI sono stati saltati — e `gitops` saltato significa che non e' stato
rilasciato niente:

```bash
gh api "repos/Milomitic/finance-alert/actions/runs/<id>/jobs"   --jq '.jobs[] | "\(.conclusion // .status)\t\(.name)"'
```

### ⚠️ "Synced + Healthy" does NOT mean your change is on screen

Cost a round-trip on 2026-09-04 ("non vedo le modifiche"). Everything looked
right and nothing was wrong:

    CI su d8ab4c6            green, all 7 jobs including image + gitops
    ArgoCD                   sync=Synced  health=Healthy  rev=d8ab4c6
    pod                      running image 025362e3   <-- the PREVIOUS one

The image tag bump is a SEPARATE COMMIT that lands AFTER the code commit — CI
can only write it once the image exists (`chore(cd): image <sha> [skip ci]`,
here `58588e5` after `d8ab4c6`). So ArgoCD reporting `Synced` at your commit
means it applied the manifests **as they were at that commit**, whose
`values-oci.yaml` still carried the PREVIOUS tag. There is always a window
where every dashboard is green and the pod runs the old image.

It resolves itself on the next poll (~3 min). To confirm or force it:

```bash
# what is ACTUALLY running — this is the check that matters
kubectl get pod -n finance-alert finance-alert-finance-alert-0   -o jsonpath='{.spec.containers[0].image}'

# force the poll instead of waiting
kubectl annotate application -n argocd finance-alert   argocd.argoproj.io/refresh=hard --overwrite
```

**Never tell the user "it is deployed" on the strength of a green CI run or an
ArgoCD status.** Compare the running image tag against the commit. The rule is
the same one as `workflow_dispatch` below: green is not deployed.

### `workflow_dispatch` verifies but does NOT deploy

`image`, `trivy` and `gitops` all carry
`if: github.event_name == 'push' && github.ref == 'refs/heads/cloud'`. A run
started with `gh workflow run ci` therefore goes green with those three
**skipped** — tests and audits pass, no image is built and no tag is bumped,
so nothing reaches the cluster. Green is not deployed; check the job list.

If a push somehow fails to trigger CI (observed once, cause not established —
the ref had moved and no run was ever created), dispatching will not fix it.
Only another push event will build and deploy.

### ⚠️ Due chiavi `env` uguali a meno delle maiuscole: il workflow NON PARTE (2026-09-15)

`HTTPS_PROXY` e `https_proxy` nella stessa mappa `env` di un passo. GitHub
confronta i nomi senza maiuscole, rifiuta il file e non crea nessun job: la run
compare col PERCORSO del file al posto del nome del workflow, zero job,
`conclusion: failure`. Un parser YAML lo dichiara valido, perche' per YAML sono
due chiavi diverse. Se servono entrambe le forme, una sola sta nella mappa e
l'altra si esporta nello script: `export https_proxy="$HTTPS_PROXY"`.

## ⚠️ Un passo periodico NON puo' essere un livello Docker senza un ingresso che cambi (2026-09-12)

Il livello che scarica le patch di sicurezza Debian **non e' stato eseguito per
24 giorni** ed era scritto bene. Terza istanza della forma «presente,
documentato, creduto efficace, inerte», dopo l'unit k3s e il `_RANGE_PERIODS`
morto — e la prima che ha fermato un rilascio.

### Come si e' presentata

Il 12 settembre trivy ha rotto la pipeline con **12 CVE (3 CRITICAL)** su
`perl-base`, `libsqlite3-0`, `libpcre2-8-0` e `gzip`. Tutte con la correzione
gia' pubblicata da Debian, tutte nell'immagine base, **nessuna introdotta dal
commit che stava passando** (era solo TSX, senza nuove dipendenze). `gitops` e'
stato saltato, quindi il lavoro e' rimasto fuori dalla produzione.

Il primo istinto — cercare quale dipendenza ho aggiunto — e' sbagliato e costa
tempo. La domanda giusta e' perche' l'`apt-get upgrade` che il Dockerfile gia'
faceva non le avesse prese.

### La causa, dal log della build e non per ipotesi

    #19 [runtime 2/13] RUN apt-get update && apt-get upgrade -y ...
    #19 CACHED

CI costruisce con `cache-from: type=gha`, e buildkit riusa un livello finche' il
suo comando e i livelli sopra sono identici. Quel `RUN` **non nominava nulla di
variabile**: costruito il 19 agosto (per chiudere un fallimento trivy identico
su util-linux), e' stato riusato a ogni build successiva. L'archivio di
sicurezza e' stato letto una volta e mai piu'.

⚠️ **La cache non distingue «identico» da «ancora valido»**, e un livello di
patch di sicurezza e' l'unico posto dove i due non coincidono: il comando e'
identico per definizione, il suo risultato no. Vale per qualunque passo che
debba girare PERIODICAMENTE — aggiornamenti di pacchetti, fetch di liste di
revoca, rigenerazione di artefatti datati.

### La correzione

`ARG APT_SECURITY_DATE`, a cui il workflow passa `date -u +%Y-%m-%d`. Tre
dettagli che sembrano pignoleria e sono il motivo per cui funziona:

1. **L'ARG sta subito SOPRA il `RUN` che lo consuma.** Piu' in alto
   invaliderebbe anche i livelli precedenti; piu' in basso non toccherebbe la
   chiave di cache di questo.
2. **Va REFERENZIATO dentro il comando** (`RUN echo "... ${APT_SECURITY_DATE}"
   && apt-get update && ...`). Un ARG dichiarato e non usato non entra nella
   chiave: si otterrebbe lo stesso identico difetto, con l'aggravante di
   sembrare risolto.
3. **Granularita' giornaliera, non per push.** Il costo e' una build lenta al
   giorno — quel livello e tutti i suoi discendenti, `uv sync` compreso.

⚠️ **NON pinnare i nomi dei pacchetti vulnerabili.** Il commento nel Dockerfile
lo scartava gia' per il motivo giusto e vale la pena ripeterlo: la prossima
advisory cade su pacchetti diversi, e una lista di nomi va aggiornata a mano
esattamente quando conta — cioe' invecchia in silenzio.

### La verifica, che non e' «CI verde»

Quattro criteri espliciti, tutti misurati sul rilascio di `9458682`:

1. nel log del job immagine il passo **non** deve leggere `CACHED` — deve
   durare decine di secondi e stampare i pacchetti (`Setting up perl-base
   (5.40.1-6+deb13u1)`);
2. `trivy` passa;
3. `gitops` gira e bumpa il tag;
4. il pod serve il tag nuovo, e `GIT_SHA` letto DA DENTRO il container lo
   conferma (`kubectl exec ... printenv GIT_SHA`).

⚠️ Un quinto controllo vale la pena quando la modifica e' frontend: **il tag
giusto non garantisce il bundle giusto**. Si verifica direttamente —
`kubectl exec ... grep -l "<stringa della modifica>" /app/frontend/dist/assets/*.js`.

## I presidi di verifica: che cosa c'e', e che cosa NON prova (2026-09-12)

Il divario piu' grande di questo progetto non e' fra codice scritto e codice
corretto — quello e' gia' presidiato bene. E' fra **codice corretto e codice che
ha effettivamente girato**, e ne esistono quattro istanze documentate: l'unit
k3s, il `_RANGE_PERIODS` morto, il livello `apt` inerte 24 giorni, e otto
traboccamenti mobile invisibili a 590 test verdi. Otto presidi li chiudono.
Ognuno ha un limite, e i limiti contano quanto i presidi.

| Presidio | Dove | Che cosa intercetta | Che cosa NON vede |
|---|---|---|---|
| Gate UI (Playwright) | `ui-gate`, su push | Traboccamento a 375/768/1440, a11y con stili veri, focus, bersagli tattili | **Un solo motore (chromium)**: un difetto solo-WebKit passa |
| Provenienza immagine | `image`, su push | Il livello patch non e' girato | Niente, se il file non c'e': dice NON SO |
| Notturno trivy | `nightly.yml` | CVE sull'immagine DISPIEGATA | Solo una volta al giorno |
| Codice mai eseguito | `backend`, su push | Funzioni nuove che nessun test chiama | Righe eseguite ma non verificate |
| Censimento istogrammi | `backend`, su push | Una serie nuova con un tetto non scelto | Se il tetto e' scelto male ma dichiarato |
| Mutazione | `nightly.yml` | Righe eseguite la cui correttezza nessuno verifica | Dodici moduli su ~200; e l'operatore numerico INCREMENTA soltanto |
| Parita' immagine | CronJob nel cluster | Il pod non esegue il tag desiderato, da oltre 20 min | Nulla prima dei 20 min (finestra GitOps). ⚠️ Ha letto il pod SBAGLIATO per sette ore — vedi sotto |
| Deriva del nodo | script a mano | Configurazione dichiarata e mai eseguita | Gira solo quando lo si lancia |
| **Drill di ripristino** | CronJob nel cluster, lunedi' 04:00 | Che il backup si RILEGGA: schema, privilegi, conteggi contro il vivo, e la FRESCHEZZA del dato | Si salta da solo se il nodo ha meno di 3Gi liberi — e allora non verifica niente |

### ⚠️ Il presidio di parita' leggeva il pod sbagliato, e allarmava sempre (2026-09-13)

La quinta istanza di «una risposta pulita e falsa da uno strumento guasto», ed
e' la piu' istruttiva perche' il presidio funzionava da mesi e si e' rotto senza
che nessuno toccasse il suo codice.

Il CronJob leggeva
`kubectl get pod -l app.kubernetes.io/name=finance-alert -o jsonpath='{.items[0]...}'`.
**Quell'etichetta ce l'ha OGNI pod del chart**, compresi i Job che il chart
stesso crea: il drill di ripristino e i pod della sonda medesima. `.items[0]`
prende il primo in ordine ALFABETICO, e `drill-...` viene prima di
`finance-alert-...` perche' d < f.

Bastato eseguire un drill a mano. Il suo pod e' rimasto `Completed`, la sonda
ha letto la SUA immagine (`alpine/k8s:1.31.3`), e per sette ore ha ripetuto
ogni quindici minuti «il pod NON esegue l'immagine desiderata da 409 min» —
409 minuti essendo l'eta' del pod del DRILL. L'applicazione era sana e in pari
per tutto il tempo.

⚠️ **Il danno peggiore non e' l'avviso sbagliato.** Sono due cose:

1. Un allarme che suona sempre insegna a ignorarlo — la stessa fatica da
   allarme per cui la soglia della pastiglia «in ritardo» e' passata da 1 a 4
   giorni.
2. **ArgoCD riportava `Degraded` in permanenza**, perche' un Job fallito rende
   degradata l'intera Application. Cioe' il presidio aveva reso cieco il
   cruscotto che serve a vedere i degradi VERI.

**La regola: un pod di StatefulSet si NOMINA, non si cerca.** `<sts>-<ordinale>`
e' garantito dalla specifica, nessun Job puo' chiamarsi cosi', e non e' una
ricerca ma un indirizzo. Dove un selettore serve davvero, deve fallire se
trova piu' di una corrispondenza invece di prendere la prima.

E accanto: una lettura VUOTA non e' «uguale a niente». Senza una guardia
esplicita, due stringhe vuote si confrontano uguali e la sonda dichiara
«parita' OK» mentre il pod non esiste — lo stesso difetto con il segno
invertito.

**Verificato sul cluster vivo prima di spedire la correzione**, che e' la parte
che chiude il cerchio: col comando nuovo desiderato == in esecuzione == il
commit spinto e pronto true, cioe' «parita' OK». La prova che il guasto
riportato non esisteva.

### Il backup era sorvegliato in quattro modi e non era verificato (2026-09-13)

Backup base giornaliero su object storage OCI, WAL continuo, retention 30d,
piu' gli allarmi `PostgresBackupStale` e `PostgresBackupFailing`. Quattro
presidi, tutti sul CATALOGO: che il backup parta, finisca, sia recente.

⚠️ **Nessuno dei quattro puo' dire se i dati dentro si rileggono.** Un backup
che completa ogni notte e ripristina un database corrotto li soddisfa tutti,
per sempre. E il runbook — che la procedura ce l'ha, provata a mano una volta a
luglio — chiudeva con «re-run the drill ... periodically otherwise»: **una
cadenza che dipende da chi se la ricorda non e' una cadenza.**

Il drill ora gira da solo. Quattro cose che non sono dettagli:

1. **Il cluster di prova NON archivia** — nessun blocco `plugins`. Uno che
   eredita la configurazione di Barman scrive WAL nella STESSA destinazione
   della produzione: il drill corromperebbe il backup che esiste per
   verificare. ⚠️ La garanzia e' un blocco ASSENTE, cioe' la forma che una
   modifica distratta reintroduce senza accorgersene.
2. **Il drill non deve causare il guasto da cui protegge.** Nodo singolo, disco
   all'86%, ogni PVC `local-path` e' una directory li' sopra. Sotto soglia si
   SALTA dichiarandolo: un drill saltato e visibile batte un nodo pieno.
3. **La pulizia sta in un `trap`**, non in coda: un fallimento a meta'
   lascerebbe il PVC e il guasto diventerebbe progressivo.
4. **La freschezza e' la verifica che i quattro presidi non potevano fare** —
   `max(ohlcv_daily.date)` entro N giorni. Una pipeline puo' riuscire per mesi
   archiviando sempre lo stesso dato fermo, e da fuori e' identica a una che
   funziona.

⚠️ E i conteggi si confrontano con la produzione VIVA, non con soglie scritte a
mano: una soglia fissa invecchia, e poi o non protegge piu' o fa arrossare
qualcosa che nessuno ha rotto.

**Prima esecuzione automatica: 2026-09-13, passata** — 29 tabelle, `fa_app`
non-superuser, ultima barra a 2 giorni, 2.479.695 righe su 2.479.695, teardown
pulito.

⚠️ Nota di metodo, ed e' la terza istanza in questa sessione. Prima di scrivere
gli allarmi ho verificato che le metriche esistessero, e la sonda ha risposto
che mancavano TUTTE E QUATTRO — compresa una che un allarme esistente gia'
usa. Era rotta la sonda: **`wget` non esiste nel container di Prometheus**.
Interrogando dal proxy dell'API ci sono tutte. Una risposta pulita e falsa da
uno strumento guasto e' il difetto piu' ricorrente di questo progetto: prima di
credere a un «non c'e'», verificare che lo strumento sappia dire «c'e'».

### ⚠️ Una linea di base va generata DOVE viene applicata

Costato due giri di CI, su due presidi diversi, per la stessa ragione.

`dead_code_baseline.json` generata su Windows dichiarava sei funzioni in meno
delle morte in CI — `spa_fallback` perche' senza `frontend/dist` il fallback SPA
non viene montato, le altre per configurazione locale che accende rami spenti in
CI. `a11y_baseline.json` aveva lo stesso problema al contrario: `/calendar` in
locale ha dati veri e rende un elemento interattivo in meno.

In entrambi i casi la baseline locale e' piu' STRETTA, quindi fa arrossare la CI
su codice che nessuno ha toccato. **Rigenerarle dai risultati di CI**, e
aspettarsi che in locale qualche voce appaia come «ora coperta»: e' una nota,
non un errore. Entrambi i file lo dicono in un campo `_ambiente`.

### ⚠️ Un cancello che nasce rosso viene spento

Regola che `eslint.hooks.config.js` si era gia' data e che vale per tutti:
**una regola entra nel cancello solo DOPO essere stata misurata a zero**,
altrimenti un rosso non distingue «hai rotto qualcosa adesso» da «esiste un
arretrato». Dove l'arretrato e' reale si congela una linea di base e si
sorveglia il DELTA — a11y 103 violazioni su 10 rotte, codice morto 351 funzioni
su 1.366 — con un test separato che impedisce di svuotare il file per far
passare la CI. Entrambi i numeri sono a schermo nella scheda «Verifica» del
cruscotto: un arretrato che nessuno vede non cala mai.

### ⚠️ Il pavimento di contenuto, di nuovo, e stavolta ha salvato tutto

Il gate UI asserisce che ogni rotta abbia reso un minimo di caratteri PRIMA di
misurarne il layout. Al primo passaggio in CI ogni rotta rendeva **0 caratteri**
— senza sessione valida `ProtectedRoute` rimanda al login — e senza quel
pavimento le dieci asserzioni sul traboccamento sarebbero passate misurando il
nulla. Il gate avrebbe riportato verde per sempre.

Corollario che e' costato un giro in piu': il messaggio diceva il SINTOMO («la
pagina e' vuota»), non la causa. La fixture interroga ora un endpoint PROTETTO
prima di ogni test, e al primo tentativo ha stampato `401 {"detail":"User not
found"}` — il token era firmato ma l'utente non esisteva, perche' in CI il
database nasce da `create_all`. **Un messaggio d'errore che nomina la causa vale
quanto il controllo che lo produce.**

### Il seme e' parte del cancello, non un accessorio

`app.scripts.seed_e2e` semina 12 titoli, 36 segnali, 2.232 barre e l'utente
admin, deterministici e senza rete. I NOMI SONO LUNGHI e le valute non tutte USD
di proposito: sono l'input avversariale, e seminare «Acme Inc» renderebbe il
gate cieco proprio alla compressione dell'identita' che questo progetto ha gia'
sbagliato (audit §4.6, FA-040).

⚠️ E il seme rende il gate RIPETIBILE, che e' l'altra meta'. `/calendar`
sbordava di 19px in CI e non in locale, perche' in locale il calendario aveva
dati e la striscia filtri si disponeva diversamente. Una misura che dipende da
cosa c'e' nel database non e' una misura.

### ⚠️ `flex-wrap` va messo a OGNI livello che puo' diventare una riga lunga

Terza istanza in un giorno — /stocks, /calendar, e i gruppi annidati di
/calendar. Il wrap manda a capo gli ELEMENTI; non spezza un elemento che da solo
supera la riga. Su /calendar `max-w-full` sul contenitore esterno ha portato lo
sbordo da 19px a 14px e non l'ha chiuso: mancava sui due gruppi interni.

### Mutazione: perche' un motore fatto in casa

`mutmut` era la prima scelta, installato e configurato. `mutmut run` risponde
**«To run mutmut on Windows, please use the WSL»**. Configurarlo per la sola CI
avrebbe significato spedire un cancello mai visto girare — la forma esatta che
questo lavoro sta chiudendo — quindi e' stato rimosso (portava tre dipendenze,
fra cui una TUI) e sostituito da `app.scripts.mutation_probe`: meno operatori,
gira ovunque, si legge in una pagina.

⚠️ Rimuovere una dipendenza con `uv remove` ha aggiornato `click` di tre minor
senza che nessuno lo chiedesse. Il lockfile e' stato ripristinato dal backup: un
`uv remove` non e' l'inverso di un `uv add`.

**La passata completa, 2026-09-13: 465 mutanti, 190 uccisi, 255 sopravvissuti
in linea di base** — un punteggio del 41% su DODICI moduli. Era 130 mutanti /
43 uccisi / 33% su quattro. Il numero e' scomodo ed e' quello vero: pretendere
lo zero avrebbe significato o scrivere decine di test in un colpo, o dichiarare
equivalenti centinaia di mutanti che non lo sono, cioe' mentire in un file che
esiste per dire la verita'. Congelato come linea di base con cricchetto sulla
crescita, come a11y e codice morto, e a schermo nella scheda Verifica.

⚠️ **L'arretrato a schermo salta da 63 a 255 e NON e' un peggioramento.** Il
denominatore e' passato da 130 a 465 perche' `BERSAGLI` e' cresciuto da 4 a 12
moduli; il tasso di uccisione SALE dal 33% al 41%. E' esattamente il motivo per
cui `_totale_mutanti` andava recuperato dopo il rename che l'aveva orfanato:
senza denominatore, «255» si legge come decadimento invece che come piu' codice
sorvegliato.

⚠️ **Un elenco di test troppo CORTO in `BERSAGLI` produce falsi sopravvissuti.**
Al primo giro `base.py` riportava 42 su 58 con due file di test elencati,
mentre i test veri sono 45 file in `tests/signals/`: stavo per riportare «lo
scorer della Forza non e' verificato», che era falso. Vale anche all'indietro —
**18 dei 63 sopravvissuti della vecchia linea di base (≈29%) erano falsi.** Un
conteggio alto di sopravvissuti SI LEGGE COME RIGORE, ed e' la ragione per cui
questo errore non si denuncia da solo.

I moduli dove un difetto silenzioso produce un numero plausibile invece di un
errore sono stati lavorati per primi. Il prossimo candidato e'
`confluence_service` (38 mutanti).

### La sonda non trova bug: trova ACCOPPIAMENTI NON DICHIARATI (2026-09-14)

E' il filo di tutti i rilievi usciti dall'estensione della mutazione, e cambia
cosa aspettarsi da questo strumento. In NESSUNO di questi casi il codice era
sbagliato quel giorno; in tutti era sbagliato il CONTRATTO, e il mutante e'
semplicemente il primo lettore che lo mette alla prova.

| Rilievo | Il contratto non detto |
|---|---|
| 14 periodi cablati | la fonte unica stava dove chi ne aveva bisogno non poteva importarla |
| postura duplicata | due copie identiche finche' qualcuno ne tocca una — ed era gia' successo, con un 500 |
| `_median` senza `sorted` | la correttezza dipendeva dal chiamante, e niente lo diceva |
| parita' immagine su `.items[0]` | «il primo pod con questa etichetta» vale finche' nessuno crea un Job |

⚠️ Il corollario operativo: quando un mutante sopravvive, la domanda utile non
e' «quale test manca» ma **«quale invariante sto dando per scontata»**. Le
quattro volte in cui ho risposto alla prima domanda ho scritto un test; le
quattro in cui ho risposto alla seconda ho tolto la condizione che lo rendeva
necessario.

### ⚠️ Due mutanti sulla STESSA RIGA vanno decisi separatamente

Successo quattro volte in una notte, ed e' la ragione per cui la chiave di
linea di base porta l'ordinale `#N`.

- `if x <= 0 or ref <= 0` in `soft01`: il termine su `x` e' equivalente (zero
  rende zero comunque), quello su `ref` rende **1.0** — il fattore piu' forte
  possibile, restituito proprio quando la scala non esiste.
- `if peak > 0` nella curva di equity: `>= 0` e' equivalente (il picco parte da
  1.0 ed e' un massimo), `> 1` no — una curva che perde dalla prima operazione
  terrebbe il picco a 1.0 e perderebbe il drawdown.
- `if x <= a75 and a75 > a45` in `concave`: il primo termine e' un bordo di
  continuita', il secondo una guardia IRRAGGIUNGIBILE — e capirlo richiede di
  leggere il ramo PRECEDENTE, non quello in esame.

Con la vecchia chiave `file:riga` questi collassavano in una voce sola: si
sarebbe letto «un sopravvissuto sulla riga 93», e dichiararlo equivalente
avrebbe SEPOLTO il difetto vero sotto la ragione giusta per l'altro.

### ⚠️ Le cinque famiglie di sopravvissuto che non sono lacune

Riconoscerle a vista risparmia il triage, e ricompaiono in ogni modulo di
calcolo. `detectors/base` chiude a 43 su 58 e i quindici superstiti sono TUTTI
di queste forme:

1. **Il termine `x <= 0`** di una guardia dove la formula rende comunque 0 in
   x = 0.
2. **I bordi di una curva CONTINUA.** `concave` e' definita a tratti e il suo
   docstring lo dichiara: al nodo esatto il tratto successivo calcola lo stesso
   numero. Non sono lacune — sono la PROVA che la curva non ha salti. La mossa
   giusta non e' ucciderli ma asserire la continuita', che e' la proprieta' che
   li rende equivalenti.
3. **Guardie irraggiungibili** perche' un ramo precedente ha gia' restituito.
4. **Un `return` difensivo** che nessun cammino raggiunge.
5. **`frozen=True`** senza un consumatore che eserciti l'immutabilita'.

### ⚠️ Tre modi in cui un test di mutazione e' «vero di niente»

Tutti e tre trovati scrivendoli, quella notte:

- `monkeypatch.setattr(mod, "NOME_SBAGLIATO", x, raising=False)` **crea** un
  attributo nuovo invece di sostituire quello vero. `raising=False` spegne
  l'unico controllo che verifica di aver scritto il nome giusto.
- Un caso di prova che non DISTINGUE: il detector senza totale, messo accanto a
  vicini da 5 e 99, finiva ultimo sia col ripiego a 0 sia con quello a 1.
  Serve un vicino al valore che il ripiego assume.
- Un inserimento in `BERSAGLI` ancorato su una riga che compare in DUE elenchi
  (`test_equity_curve_direction.py` sta di proposito in entrambi): il test
  sarebbe girato contro i mutanti del modulo sbagliato, lasciando quello giusto
  scoperto **col numero che migliora altrove**. Si ancora sul nome del MODULO.

⚠️ E l'output di uno strumento letto mentre un altro riscrive i sorgenti non e'
un risultato: ruff ha segnalato quattro errori di formattazione su un file che
la sonda stava tenendo in forma `ast.unparse`.

### ⚠️ Un residuo alto non vuol dire la stessa cosa in due moduli diversi

`signal_outcome_service` chiude a **47 su 57** e `technical_score_service` a
**39 su 93**, e la differenza NON e' quanto lavoro ci e' stato messo.

Il magazzino degli esiti e' fatto di CONTRATTI: un colpo e' un colpo, il segno
dell'eccesso segue il tono, una riga nasce solo se la barra futura esiste. Ogni
mutante li' o rompe una regola o e' irraggiungibile, quindi il residuo scende
quasi a zero e i dieci superstiti stanno tutti in `EQUIVALENTI` con la ragione.

La lente Tecnico e' fatta di TARATURE: le finestre (50/200/252/63/126/20/10),
i periodi di ADX e RSI, il divisore 40, la miscela 0,6+0,4·adx_w,
l'arrotondamento, il tetto di 260 barre. **Fissarle con un test significa
rendere rossa ogni ritaratura legittima**, cioe' il contrario di cio' per cui
questi presidi esistono. Le ~46 che restano sono in linea di base, misurate e
visibili, e non sono un arretrato da smaltire.

⚠️ La regola che ha guidato il triage, e vale oltre la mutazione: **il criterio
non e' «quanto e' importante» ma «cosa succede a chi ritara».** Fissare
`adx(ohlcv, 14)` lascia il prossimo davanti a un rosso che non distingue «hai
rotto qualcosa» da «hai cambiato idea». Fissare che una serie ferma non legga
come trend non impedisce nessuna ritaratura: nessuno vuole quel
comportamento. Due asserzioni sulla stessa riga possono cadere da parti
diverse — su `pos = (price-lo)/rng if rng > 0 else 0.5` il VALORE 0,5 e'
taratura, il fatto che il denominatore sia protetto e che il ripiego stia a
meta' scala invece che a un estremo e' contratto.

### Due difetti veri trovati scrivendo quei test (2026-09-13)

Nessuno dei due e' stato trovato leggendo il codice.

1. **Un titolo fermo spariva dalla lente Tecnico.** `_momentum` guardava
   `if n > 15 else 50.0`, cioe' il numero di BARRE. Doppiamente sbagliato:
   `_momentum` e' chiamata solo da `partial_for`, che sbarra sotto le trenta,
   quindi quel ramo era CODICE MORTO; e il caso reale non e' «poche barre» ma
   una serie PIATTA, dove guadagni e perdite sono entrambi zero, l'RSI e' tutto
   NaN e `.iloc[-1]` su una serie vuota solleva IndexError — raccolto dal
   `except Exception` di `partial_for`, che rende None. La riga del MACD due
   sotto lo faceva gia' nel modo giusto (`if hd.size`). ⚠️ Stessa forma del
   `_RANGE_PERIODS` morto: un ramo inerte che sembra coprire il caso e' peggio
   di nessun ramo, perche' corrobora la convinzione che sia coperto.

2. **La costruzione della riga persistita era duplicata** fra `finalize` e
   `recompute_one`, postura e arrotondamenti compresi — e quella duplicazione
   aveva GIA' prodotto un 500 in produzione quando `_recent_signal_facets`
   passo' da "confidence" a "strength" e solo una copia fu aggiornata. La
   correzione di allora sistemo' la copia. Ora `_posture` e `_riga_tecnica`
   sono proprietari unici. ⚠️ La sonda l'aveva reso visibile segnalando gli
   STESSI mutanti due volte, alle righe 236 e 322: non due lacune, la stessa
   logica non verificata in due posti. **Mutanti in coppia sono un indizio di
   duplicazione, non di doppio lavoro** — e togliere la copia ha portato il
   modulo da 107 a 93 mutanti, cioe' meno codice non verificato invece di piu'
   test.

### La chiave della linea di base NON contiene il numero di riga (2026-09-13)

`modulo::funzione#N  prima -> dopo`. Sembra un dettaglio di formato ed era un
cancello rotto.

**Il difetto.** `mutation_probe` gira in `nightly.yml` senza
`continue-on-error` e rende 1 quando trova sopravvissuti nuovi. Con la vecchia
chiave `file:riga  prima -> dopo`, aggiungere un COMMENTO a uno dei dodici
moduli sorvegliati spostava ogni voce sotto di esso e tutti i suoi mutanti
diventavano «NUOVI»: la notturna arrossiva su codice che nessuno aveva toccato
— la forma che questo file registra tre volte come fatale a un cancello, dopo
le baseline di a11y e codice morto generate nell'ambiente sbagliato.

Misurato mentre succedeva: nove righe di commento in `signal_outcome_service`
hanno prodotto quattro falsi sopravvissuti, e il riassetto di
`technical_score_service` ne avrebbe prodotti 85.

⚠️ **Il numero di riga non e' una proprieta' del mutante: e' una proprieta' del
file che lo contiene.** E' la stessa distinzione che questo file fa altrove fra
identita' e posizione — un token di revoca si indicizza sul digest, non su dove
sta la riga.

**Cosa si guadagna oltre alla stabilita'.** L'ordinale `#N` conserva la
risoluzione che la vecchia chiave perdeva: due mutazioni IDENTICHE sulla stessa
riga condividevano una voce, quindi ucciderne una sola non si vedeva. I tre
confronti di `pts` in `_trend` erano un caso reale — una voce sola per tre
mutanti.

**Cosa la sposta ancora, ed e' voluto:** modificare la funzione che contiene il
mutante. Che e' esattamente quando ri-misurare e' giusto.

**Quattro test la difendono**, e uno e' un CONTROLLO NEGATIVO che fissa
l'instabilita' della vecchia forma — senza, il test sulla stabilita' sarebbe
vero anche di una `genera()` che rende una lista vuota. Piu' due pavimenti:
ogni chiave in linea di base e ogni EQUIVALENTE devono avere la forma nuova, e
ogni EQUIVALENTE deve corrispondere a un mutante che ESISTE. ⚠️ Quest'ultimo
chiude un fallimento silenzioso: una voce orfana non protegge piu' niente, il
mutante che dichiarava ricompare come nuovo, e la voce resta nel file a sembrare
una spiegazione. Costa due secondi, perche' generare i mutanti non esegue un
solo test.

### `app/core/security.py`: da 0 su 9 a 7 su 9 (2026-09-13)

Il modulo delle sessioni uccideva **ZERO** dei suoi nove mutanti. Non
significava che fosse sbagliato — significava che nessuna delle sue difese era
verificata, e una difesa non verificata e' indistinguibile da una assente
finche' non serve. Due erano lacune vere e gravi:

- `verify_password`, `except ValueError: return False` -> `True`: `checkpw`
  solleva `ValueError` su un hash MALFORMATO, quindi col mutante una colonna
  troncata o una migrazione storta autentica CHIUNQUE. I test esistenti
  provavano solo la coppia giusta e quella sbagliata, cioe' due hash validi.
- `isinstance(username, str) and 0 < len(username) <= 64` -> `or`: uno username
  vuoto o da duecento caratteri veniva accettato, e un valore non-stringa
  faceva esplodere `len()` — un rifiuto pulito diventava un 500.

⚠️ **Avevo previsto 7 uccisi su 9 e ne sono morti 4**, e l'aritmetica era sullo
schermo prima della previsione: la linea di base diceva `uccisi: 0`, i test
nuovi coprivano due righe per un totale di quattro mutanti, 0+4=4. Avevo
assunto che la suite preesistente coprisse il resto proprio mentre leggevo il
numero che diceva il contrario.

Gli altri tre (riga 45 `<=` -> `<`, righe 62 e 98 `86400` -> `86401`) erano
lacune piu' quiete: il mutante «+1» e' innocuo, ma quello che dimostra e' che
**nessuno sorvegliava quelle moltiplicazioni** — `8640` al posto di `86400`
accorcia ogni sessione a due ore e mezza in silenzio. Chiusi. ⚠️ L'asserzione e'
scritta `24 * 60 * 60` e non `86400`: copiare la costante renderebbe il test
una tautologia che cambia insieme alla riga che deve sorvegliare.

⚠️ **E l'operatore numerico della sonda INCREMENTA soltanto**, quindi su un
parametro di sicurezza puo' esplorare solo la direzione innocua. `rounds=12 ->
13` e `token_urlsafe(16) -> 17` sopravvivono perche' sono piu' FORTI
dell'originale — stanno in `EQUIVALENTI` — ma i mutanti che conterebbero,
`12 -> 11` e `16 -> 15`, la sonda non li genera e sarebbero sopravvissuti nello
stesso identico modo. Due test fissano quindi un PAVIMENTO senza uccidere
nessun mutante: e' il buco che lo strumento non sa nominare. **Un punteggio di
mutazione perfetto su questo modulo non direbbe niente sul costo di bcrypt.**

Al primo giro su `image_provenance` ha trovato **quattro sopravvissuti, due dei
quali lacune vere**: il bordo esclusivo della soglia (`>` contro `>=`, il
fuori-di-uno piu' comune che esista) e il taglio a dieci caratteri di una data
con orario. Entrambi su righe COPERTE dai test. Gli altri due sono equivalenti e
stanno in `EQUIVALENTI` con la ragione scritta — **una lista di sopravvissuti
senza spiegazione e' indistinguibile da una lista di difetti.**

## ⚠️ Do NOT `chmod 600` the node's kubeconfig (2026-09-09)

It reads like elementary hygiene and it **locks you out of the cluster**. Cost
a recovery via `sudo` when I did exactly this, and an external audit's backlog
recommends it in those words, so it will be proposed again.

On the node `kubectl` is a **symlink to `k3s`**, and k3s ignores
`~/.kube/config`: it reads `/etc/rancher/k3s/k3s.yaml`, which is owned by root.
Tightening that file to `600` leaves every `kubectl` the `opc` user runs — the
SSH path this repo operates through — with no readable credentials, and the
error names a missing config rather than a permission problem.

The file DID need fixing: it was world-readable, and it holds cluster-admin.
The shape that is both closed and usable is a group, already in
`infra/terraform/cloud-init/k3s.yaml`:

    EXEC="--write-kubeconfig-mode 640 --write-kubeconfig-group k3s"
    groupadd -f k3s && usermod -aG k3s opc

Mode `640` with group `k3s` removes world access and keeps `opc` working.
**A permissions recommendation for a k3s node must name the k3s.yaml path and
the group, or it is a lockout.**

**Exercised on the live node 2026-09-09, and it needed to be.** The unit had
carried the flags since 2026-09-08 while the running k3s had been up since
17 July with a bare `k3s server` argv, so the correct permissions on disk came
from a manual `chmod`/`chgrp` and the unit had never once been executed. A
staged-but-unexercised unit on the single node that runs everything is a
reboot hazard, not a fix. `systemctl restart k3s` proved it: k3s rewrote
`k3s.yaml` itself at `640 root:k3s`, whose default is `600 root:root`, so only
the flags can produce it. API ready in ~3s, all 28 pods stayed Running with
zero restarts, ingress 200. Note `/proc/<pid>/cmdline` shows a bare
`k3s server` because k3s rewrites its own proctitle — read the FILE it
produced, not the argv, to tell whether the flags applied.

## Telegram: the app and Alertmanager share ONE bot (2026-09-09)

Infra alerting was working the whole time and the app's was not, which is the
kind of asymmetry that hides because both are "Telegram".

Measured on the live Alertmanager: `alertmanager_notifications_total{
integration="telegram"} = 306` with **zero** failures across every reason. Its
route has had a real bot_token/chat_id since setup. The APP's Secret had
neither, and the chart did not even reference them — see the F03 note in
`statefulset.yaml`, the third instance of that shape after Finnhub and FRED.

The app's keys were copied FROM the Alertmanager Secret on 2026-09-09 (same
bot, same chat), verified identical by hash, and proven end to end by sending
through `notifier_service._send_telegram` rather than a bare curl — configured
is not delivers, which is exactly what the 306/0 counter established for the
other side.

⚠️ **They are now coupled.** Rotating the bot token in one place breaks the
other silently: the app would log a send failure nobody reads, and Alertmanager
would increment `notifications_failed_total`, which nothing watches. If you
rotate, update BOTH `alertmanager-kps-alertmanager` (via the kube-prometheus
values) and `finance-alert-prod`.

**What turning it on starts:** the daily digest at 08:00 (`digest_hour`), the
per-signal push if `telegram_push_signals` is enabled, and health-transition
alerts (`telegram_notify_health`, default True, max one per state per 6h). To
stop them, remove the two keys from `finance-alert-prod` and restart the pod.

## axe runs in CI, and what a green run does NOT mean (2026-09-09)

`axe-core` now runs inside the ordinary vitest suite, so it is gated by the
existing `frontend` job with **no workflow change** — `npm run test:run`
already picks up `*.axe.test.tsx`. Helper and rationale in
`src/test/axe.ts`; surfaces covered are the shared shell (`Layout`) and the
densest form (`StockFiltersCard`), both at zero.

⚠️ **jsdom loads no stylesheet, so an entire class of real defect is invisible
to it.** Tailwind classes are inert strings there. That means axe here cannot
see colour contrast, touch target size, focus visibility, or anything decided
by `display:none` versus `sr-only` — and that last one is precisely how the
logout button lost its accessible name on phones the same day. Two of the four
defects found by hand that morning could NOT have been caught by this suite.

What it does catch is the structural half: controls with no accessible name,
invalid or orphaned ARIA, duplicate ids, unlabelled form fields, broken
heading order. Treat a green run as a floor, never as WCAG AA.

Two rules are disabled with a reason, and neither is to make the report green.
`color-contrast` cannot run without computed styles and returns "incomplete"
rather than a violation, which is noise that teaches people to skim. `region`
is a property of a whole page and fails for a component mounted in a bare div.

**Two traps the tests had to avoid, both already documented here in other
forms.** The filters card opens three of its four areas only on click, so
scanning a bare mount would report zero violations about an almost empty card —
the field count is asserted from below first. And a negative control asserts
that axe DOES flag a button with no name, because otherwise every green
assertion could be a misconfigured scanner reporting nothing.

## Endpoint latency: what it actually is, and why it was unreadable (2026-09-09)

The audit's "other slow paths" item guessed at SQL sessions around fundamentals
and repeated ETF sparkline queries. Measuring first gave a different answer,
and the first thing it found was that the measurement was broken.

**Every p95 read exactly 1.000, for nine different handlers.** That is not a
latency. `http_request_duration_seconds` — the only latency series carrying a
`handler` label — shipped with the library's default buckets `(0.1, 0.5, 1)`,
so any quantile above one second falls in `+Inf` and `histogram_quantile`
returns the highest finite edge. It looks like a number and it is a ceiling.

The real figures, from `sum/count` over 24h, which no bucket can distort:

| handler | media |
|---|---|
| /api/stocks/quotes | 4.57 s |
| /api/stocks/{ticker}/multi-tf-kpis | 2.57 s |
| /api/stocks/{ticker}/fundamentals | 2.10 s |
| /api/dashboard/live-assets | 1.68 s |
| /api/stocks/{ticker}/quote | 1.17 s |
| /api/stocks/{ticker}/detail | 0.56 s |

So the slow paths are the QUOTE paths, dominated by the upstream this file
already documents at 43-50s under Yahoo rate limiting — not the SQL sessions
the audit expected. The buckets are now `(0.1, 0.5, 1, 2.5, 5, 10, 30, 60)` and
`tests/test_latency_buckets.py` pins the ceiling.

⚠️ **The sibling metric is a decoy.** `http_request_duration_highr_seconds` has
had fine buckets out to 60s all along, which is why nothing looked wrong at a
glance — but it carries NO handler label, so it can say the app is slow and
never which endpoint. Splitting resolution that way is the helper's design.
Read `..._seconds` for per-endpoint work and `..._highr_seconds` for the whole
app, and never assume the fine buckets you found belong to the series you are
grouping by.

Two readings that are correct and look alarming: the SSE handlers average 432 s
because that is a connection's LIFETIME, not a wait; and `/api/health` is 18k
of the ~20k daily requests because it is the liveness probe.

### ⚠️ `increase()` perde la prima raffica di ogni vita del pod (2026-09-16)

La sesta istanza di «uno strumento risponde pulito e falso», trovata rimisurando
FA-006. `increase(http_request_duration_seconds_count{handler="/api/stocks/quotes"}[8h])`
rispondeva **~0 richieste**; erano 7. La base del giorno prima ne dava **121**;
erano **175**.

**Perche'.** L'instrumentator crea la serie di una rotta alla PRIMA richiesta che
il processo riceve, quindi il primo campione raccolto vale gia' N; `increase()`
misura differenze e non ha uno zero da cui partire, quindi quelle N non esistono.
Qui fa danno piu' che altrove per due ragioni che si sommano: **ogni rilascio
riavvia il pod** (dieci il 16 settembre), e una pagina fa le sue richieste
tutte insieme all'apertura, quindi la prima raffica e' spesso TUTTO il traffico
di una vita. Vale per `rate()`, per ogni pannello e per ogni allarme costruiti
cosi' su una rotta poco usata.

⚠️ **E l'errore non e' neutro:** le richieste perse sono quelle subito dopo un
avvio, cioe' a cache FREDDE e LENTE. La base di FA-006 sembrava migliore del
vero (mediana 5,5 s dichiarata; sui grezzi il 61% oltre 5 s). Le medie della
tabella qui sopra sono state lette nello stesso modo e vanno considerate
ottimiste.

**Il metodo:** `backend/scripts/latenza_per_vita.py`. Legge i campioni grezzi,
conta ogni vita del processo (`process_start_time_seconds`) da zero, somma sulle
serie di stato, e riporta le **raffiche** accanto alle richieste — sette
richieste nello stesso minuto sono UNA pagina aperta, cioe' un'osservazione.
Si passa da stdin al pod, perche' Prometheus e Loki si raggiungono solo nel
cluster; l'uso e' nel docstring.

⚠️ Scrivendolo ho sbagliato due volte nello stesso modo, e vale la pena
saperlo: sovrascrivere invece di SOMMARE le serie di stato, e contare una vita
cominciata prima della finestra dal suo primo campione anche quando la serie e'
nata DENTRO la finestra — che e' di nuovo l'errore di `increase()`. La seconda
bozza diceva 161; il numero giusto e' 175.

## Ingress rate limit: 50/s, burst 100 — and how to test one (2026-09-09)

Until this date `kubectl get middleware -A` returned **No resources found**:
the app was on a public address with nothing in front of it, on a node it
shares with Postgres, Prometheus, Loki and Grafana. `rateLimit` is now a
Traefik Middleware in the chart, on only in `values-oci.yaml`.

**The numbers, and why not stricter.** A stock detail page fans out to ~20 API
calls on load, so `burst: 100` absorbs a page open. `average: 50` per second is
about two orders of magnitude above real browsing and two below a flood, which
is the only band worth defending on one node. No `inFlightReq` beside it on
purpose: the health page holds an SSE connection open for its whole life, so a
concurrency cap counts every open tab as a permanent occupant and locks the
owner out of their own dashboard.

⚠️ **A burst test that comes back all-200 usually means your TEST is too slow,
not that the limiter is off.** This cost two rounds. From a browser-like client
over the internet, 300 requests at 40-way parallelism measured **45.7 req/s** —
*below the 50/s limit*, so zero 429s was the correct answer and proved nothing.
Repeating it from INSIDE the cluster changed nothing (46.1 req/s), because the
script joined each batch before starting the next, so throughput was
`parallelism / batch latency` and a fresh TLS handshake dominated every request.

What actually generates load: **persistent connections and continuous workers**.
24 sockets, keep-alive, 40 sequential requests each — 276 req/s, and the limiter
answered:

    960 richieste in 3.48s     200: 276     429: 684

Those 276 are not arbitrary. A token bucket permits `burst + average x elapsed`
= 100 + 50 x 3.48 = **274**, against 276 measured. The limiter is doing exactly
what it is configured to do, and that arithmetic is the check to repeat if the
numbers are ever changed.

**Corollary worth keeping:** a single remote client on an ordinary connection
tops out around 46 req/s against this endpoint and therefore *cannot* trip the
limit. It only ever engages against something genuinely abusive, so a spurious
429 for the owner is not a realistic failure mode at these settings.

## Node disk: 82% full, and that is monitored (2026-09-09)

Worth not re-investigating. The node's root filesystem is 30G with ~5.6G free,
and every `local-path` PVC is a directory on it — app, Postgres, Prometheus,
Loki, Grafana, Alertmanager all share that headroom, and local-path does NOT
enforce the sizes the PVCs declare.

There is no runaway consumer: containerd holds 7.4G for 28 images (k3s GCs them
itself), the PVCs 4.1G (Prometheus 2.5G is the largest), the OS ~4.8G. The 7G
under `/var/lib/kubelet/pods` is mostly the same PVC content seen through its
bind mounts, counted twice by `du`.

`kps-node-exporter` already ships `NodeFilesystemAlmostOutOfSpace` (fires under
5% free) and `NodeFilesystemSpaceFillingUp` (predictive, 24h), and the delivery
path is the proven one above. So this is watched, not urgent — but the fix when
it fires is a bigger disk or shorter Prometheus retention, not a prune.

### Both time-series stores are already CAPPED (measured 2026-09-09)

Checked rather than assumed, and it closes the question. Neither store can run
away:

| Store | Bound | PVC |
|---|---|---|
| Prometheus | `retentionSize: 2500MB` — a hard SIZE cap | 3Gi |
| Loki | `retention_period: 720h` with the compactor on a 10m interval | 2Gi |

Prometheus drops the oldest blocks before exceeding 2.5 GB, so its 30d
retention is an upper bound it will not reach. Loki is capped on TIME, not
size — the one theoretical gap, since `local-path` does not enforce a PVC's
declared size — but 30 days of this cluster's log volume is well inside 2 GB,
and the oldest line actually retained measured 23 days.

**And containerd garbage-collects itself, with evidence.** Over one morning it
went 8.1G -> 6.8G and the retained app images 6 -> 2, with no intervention. Do
not prune images by hand; the earlier reading of "7.4G for 28 images" was a
snapshot of that cycle, not a leak. Disk over the same morning: 82% -> 89%
during a restore drill -> 79% after. The drill's ~2 GB is the only transient
worth planning for.

### ✅ 2026-09-15, later: boot volume grown 50 -> 100 GB, root 86% -> 31% (FA-076)

**The paragraph below is history.** Option 2 was applied: `boot_volume_gbs`
default 100 in `infra/terraform/variables.tf`, `terraform apply
-target=oci_core_instance.k3s` (update in-place, 26 s, no reboot — node uptime
unchanged), then `/usr/libexec/oci-growfs -y` on the node, which grew
partition sda3, the PV, the root LV and XFS in one go: `/` 30 G -> 83 G, 58 G
free. Terraform then reports "No changes".

How to repeat it, because every step has a trap:

- **Terraform runs in a container** (`hashicorp/terraform:1.9`, see
  `infra/oci/a1-retry.sh`): mount the tf dir on `/wd` and `~/.oci` read-only on
  `/root/.oci`, with `MSYS_NO_PATHCONV=1` on Git-Bash. There is no local binary
  and no local `oci` CLI. Back up `terraform.tfstate` first; plan with
  `-target` and apply only if it says update in-place with 0 to destroy.
- **The disk was 50 GB all along**, not 30: Oracle Linux splits the LVM PV into
  `root` (29.5 G) and `/var/oled` (15 G, ~300 MB used). XFS cannot shrink, so
  that 15 G stays where it is; growing the volume is the only way to give `/`
  more room.
- **OCI grows a boot volume online but never shrinks it.** Lowering
  `boot_volume_gbs` below the real size makes the plan fail, it does not shrink.
- The kernel only sees the new size after a rescan
  (`echo 1 > /sys/class/block/sda/device/rescan`); `oci-growfs` refuses nothing
  and grows whatever the LV of `/` is, so check `lsblk` first.

### ⚠️ 2026-09-15: 86%, and the critical alert has been firing for days (FA-076)

The section above was true on 09-09 and is not any more. Measured: 26.9 GB of
31.6 GB, `FinanceAlertNodeRootFilling` **399 samples firing in 7 days**, 63
notifications delivered. The breakdown that the 09-09 note missed is a **4 GB
`/.swapfile`** (323 MB used) — `du /*` skips dotfiles, so it is invisible to
the obvious command. The growth since then is containerd (7.4 -> 8.66 GB).
Prometheus is at its 2.5 GB cap and cannot grow. The fix is a decision, not a
prune: shrink swap, grow the boot volume, or cut Prometheus retention.

### ⚠️ On `local-path`, `kubelet_volume_stats_*` is the NODE disk, not the volume

Every PVC in this cluster reports the same `used_bytes` / `capacity_bytes` —
26.83 GB / 31.6 GB, identical to `df /` — because a local-path PVC is a
directory on the root filesystem and the kubelet reports that filesystem.
Loki's PVC really holds 122 MB. So a per-PVC "filling up" rule measures the node
under a volume's name and prescribes the wrong remedy.

The Loki rule that existed (FA-015) never fired anyway, and the backlog blamed
the kubelet for it: the selector was `persistentvolumeclaim=~"loki.*"`, and
**PromQL regexes are fully anchored**, so it never matched `storage-loki-0`.
A rule that is loaded, healthy and permanently `inactive` looks exactly like a
rule with nothing to report — check that its selector returns a series before
believing either. Removed in `05de476`; `tests/test_regole_allarme_local_path.py`
keeps `kubelet_volume_stats` out of `infra/observability/`. Rules there are
applied BY HAND (`ssh ... 'kubectl apply -f -' < <absolute path>`), not by
GitOps — and a relative path from the wrong working directory applies nothing
while the shell reports only a missing file.

## Database migrations (alembic)

### ⚠️ `env.py` IGNORA l'url che passi a `Config` (2026-09-14)

`alembic/env.py` fa `config.set_main_option("sqlalchemy.url",
settings.database_url)` **incondizionatamente**, e `alembic.ini` lascia
`sqlalchemy.url` vuota di proposito: la configurazione del database ha un
proprietario solo. E' deliberato e va lasciato com'e'.

Ne segue la cosa che costa tempo: **per far girare una migrazione contro un
ALTRO database non serve a niente passare l'url a `Config`.** Bisogna cambiare
`settings.database_url` (in un test, `monkeypatch.setattr(settings,
"database_url", url)`).

⚠️ E il modo in cui e' venuto fuori vale piu' della regola. Il primo giro di
migrazioni su Postgres di `test_postgres_integration.py` impostava l'url sul
`Config`, quindi girava contro il database predefinito e **il Postgres non
veniva toccato**. Il test PASSAVA. A smascherarlo e' stata l'unica asserzione
che guardava il RISULTATO — l'indice parziale deve esistere, e con la sua
clausola `WHERE` — invece della semplice assenza di eccezioni. Senza quella
riga sarebbe rimasto verde per sempre misurando niente: la quinta istanza di
«un test puo' essere vero di niente», e la prima trovata da un'asserzione che
avevo aggiunto per un altro motivo.

### ⚠️ SQLite ignora `VARCHAR(n)` e ordina i NULL in fondo: due guasti di produzione (2026-09-15)

La suite gira su SQLite, la produzione su Postgres, e su due punti i dialetti
danno risposte diverse **senza nessun errore dalla parte di SQLite**. Lo stesso
giorno hanno prodotto due guasti, e il primo ha fermato ogni scansione per ~19
ore.

**1. La lunghezza di un `VARCHAR` su SQLite e' decorativa.** FA-061 (`8e6b035`)
ha aggiunto il tono `undetermined` (12 caratteri) in `stock_setups.tone`,
dichiarata `String(8)`. Rilascio alle 19:51 UTC, prima scansione fallita alle
19:53, poi undici di fila compresa la notturna: Postgres rifiuta il valore con
`StringDataRightTruncation`, la sessione resta abortita e il ciclo non avanza
piu'. In produzione non esisteva UNA riga con quel tono. 2.456 test verdi.
Correzione `33ad6a7` (colonna a 16, migrazione `5e2f0b7c9d41`).

⚠️ **La regola: una costante nuova scritta in una colonna di lunghezza fissa va
confrontata con quella lunghezza.** `tests/test_setup_tone_entra_nella_colonna.py`
e' la forma: importa le COSTANTI (non copie) e le confronta con
`Model.__table__.c[col].type.length`, quindi gira su SQLite e fallisce lo stesso.
**Dal 2026-09-16 la suite lo fa rispettare a TUTTE le colonne**:
`conftest.enforce_varchar_lengths` crea su SQLite un trigger `BEFORE
INSERT/UPDATE` per ogni `String(n)` (128 trigger, ~3 ms a test, copre anche gli
`insert()` Core che il flush ORM non vede), e
`tests/test_varchar_rispettato_in_sqlite.py` lo sorveglia con un controllo
negativo. Acceso, la suite intera e' rimasta verde; in produzione la colonna
piu' vicina al tetto e' `scan_runs.phase` (28 su 32, insieme chiuso di fasi).
⚠️ Vale solo per i test che passano dalla fixture `db`: un engine creato a mano
in un test non ha i trigger.

**2. In un ordinamento decrescente Postgres mette i NULL PER PRIMI.** Due punti
chiedevano `ORDER BY completed_at DESC LIMIT 1` per «l'ultima scansione
riuscita», e in produzione ci sono 18 esecuzioni `success` di maggio senza
`completed_at`. Restituivano la #19 del 5 maggio con data nulla:

- il recupero all'avvio lanciava una scansione completa (~10 minuti) a OGNI
  ricreazione del pod — **83 ricreazioni in 7 giorni, da 5 a 22 scansioni al
  giorno invece di 1-2**, e parte delle «fallite» erano scansioni interrotte
  dal rilascio successivo;
- `effective_max_age_days` non allargava mai la finestra di recenza.

Correzione `9301f5d`: `last_successful_completed_at` in `app/models/scan_run.py`,
con `MAX(...)` e `IS NOT NULL` — la forma che `app_metrics.hydrate_from_db` usava
gia', ed e' per questo che l'allarme sulle scansioni ferme leggeva giusto
mentre il recupero all'avvio sbagliava sulla stessa tabella.

⚠️ **Per «il piu' recente» su una colonna nullable si usa `MAX`, non
`ORDER BY ... DESC LIMIT 1`.** Se serve la riga intera, `nulls_last()` o un
filtro `IS NOT NULL` esplicito. Un test di comportamento su SQLite NON puo'
vedere la differenza: il test vero sta nella corsia Postgres ed esegue la forma
sbagliata pretendendo che sbagli.

**3. E il gestore d'errore crollava sopra il guasto.** Il ramo `except` di
`run_tracked_scan` leggeva `run.id` prima del rollback; su una sessione abortita
quella lettura solleva `PendingRollbackError`, la riga restava `running` e la
pulizia la chiudeva con «heartbeat fermo da ~5min». Undici scansioni fallite
portavano quel messaggio e la causa vera stava solo nei log del pod. Correzione
`8a0b25f`. ⚠️ **In un `except` che segue un errore del database, niente letture
dell'ORM prima del rollback** — gli id si catturano a sessione sana.

⚠️ Nota di metodo, ed e' la ragione per cui questo e' stato trovato: cercavo i
job batch da ottimizzare, non un guasto. `scan_runs` raggruppato per giorno ha
detto due cose che nessun allarme diceva — undici fallite di fila, e un numero
di scansioni al giorno dieci volte il calendario. **Contare le esecuzioni di un
job contro il suo calendario e' un controllo di cinque secondi.**

### ⚠️ `BackgroundScheduler(timezone=...)` NON vale per un `CronTrigger` costruito a mano (2026-09-15)

`app/scheduler/__init__.py` diceva `BackgroundScheduler(timezone="Europe/Rome")`
e scriveva ogni orario in ora di Roma. Ma quel fuso vale solo per i job aggiunti
con la stringa `"cron"`: i 17 `CronTrigger(...)` costruiti a mano prendevano
`tzlocal.get_localzone()`, il fuso della MACCHINA. Sul desktop era Roma e tutto
tornava; nel pod e' `Etc/UTC`. **Da quando l'app e' sul cloud ogni job girava
due ore dopo l'orario scritto** — scansioni alle 18:30 e 23:30 UTC, digest alle
10:00 di Roma — e nessuno se n'e' accorto perche' due ore non rompono niente di
visibile.

Scoperto perche' un test sulle finestre di FRED era verde su Windows e rosso in
CI. Corretto con `_cron()`, che passa il fuso esplicitamente.

⚠️ **Un test sul fuso deve SIMULARE una macchina UTC** (monkeypatch di
`apscheduler.triggers.cron.get_localzone`). Su una macchina a Roma leggere il
fuso del trigger da' «Europe/Rome» anche col difetto dentro — che e' come il
difetto e' sopravvissuto: verde in locale, rosso solo dove gira. E' la stessa
famiglia di «SQLite ignora `VARCHAR(n)`» qui sopra: **la macchina di sviluppo
nasconde proprio le proprieta' che la produzione ha di diverso** (dialetto,
fuso). Quando un test tocca una di queste, va eseguito nelle condizioni della
produzione, non in quelle del portatile.

Verificare in produzione: `kubectl exec ... -- date` dice `UTC`, e i
`started_at` di `scan_runs` sono l'orario reale a cui un job e' partito.

### ⚠️ Le migrazioni non giravano MAI su Postgres

Il job M7 prova che i MODELLI mappano su DDL Postgres (`create_all`), che e'
un'altra cosa: `alembic upgrade` e' DDL scritta a mano, batch mode, indici
parziali con clausole per dialetto. Su SQLite girava a ogni sviluppo; su
Postgres, mai.

Il difetto che ha scoperto appena acceso: un `try/except` attorno a una
`DROP CONSTRAINT` che puo' legittimamente non esistere. Su SQLite funziona; su
Postgres **una DDL fallita ABORTA la transazione**, quindi l'eccezione viene
ingoiata e ogni istruzione successiva muore con «current transaction is
aborted». Si CONTROLLA l'esistenza con l'inspector, non si cattura.

E si prova anche il RITORNO. Una migrazione che non si ripercorre all'indietro
va scoperta adesso, non durante un ripristino — il drill del lunedi' esiste
esattamente per questa ragione. Quando lo schema di destinazione non puo'
contenere i dati (FA-061: piu' episodi per coppia), il `downgrade` o fallisce o
perde righe, e non esiste una terza possibilita': **sceglie di perderle e lo
DICHIARA con un conteggio.** Un ripristino che cancella in silenzio e' peggio
di uno che rifiuta.


### Iterare su Postgres quando Docker Desktop non parte (2026-09-15)

Docker Desktop su questa macchina non si avvia in modo non interattivo, e
`test_la_catena_INTERA_arriva_in_fondo_da_vuoto_su_POSTGRES` vuole un Postgres
vero. Un ramo di prova con un workflow ridotto — il solo servizio `postgres:16`
e quel file di test, `on: push` sul ramo — gira in circa un minuto e ha chiuso
FA-070 in due giri. Cancellare il ramo alla fine. ⚠️ Una catena rossa si ferma
al PRIMO difetto: i controlli negativi vanno fatti per ogni correzione
separatamente, altrimenti la seconda non e' mai stata vista fallire.

- Migration files live in `backend/alembic/versions/`
- Generate with: `./.venv/Scripts/alembic.exe revision -m "<name>"`
  (the file is empty — fill in `upgrade()` and `downgrade()` manually)
- Apply with: `./.venv/Scripts/alembic.exe upgrade head`
- The DB engine is SQLite; use `op.batch_alter_table(...)` for column changes
  (SQLite doesn't support `ALTER COLUMN` natively)

---

## Universe pruned 1494 → 1000 (2026-06-18)

The stock universe was trimmed to **1000** to cut recurring fetch/scan load
(per-stock cost is ~O(#stocks); the universe was over-broad for the user's
needs). Method:

- **Kept (mandatory):** all 811 index members (`stock_indices`), the eToro
  hand-picks, and any `price_alerts` name.
- **Trimmable pool:** the 655 non-index-but-already-alerted names. Ranked by a
  **liquidity-weighted composite** = 0.55·(avg-30-bar dollar turnover, FX→USD)
  + 0.30·(engine = avg of `stock_scores.composite` + `technical_scores.composite`)
  + 0.15·(data-completeness: market_cap/sector/industry/country/fundamentals-cache).
  Kept the top 161, **cut the bottom 494**.
- **Cascade-deleted** across `ohlcv_daily` (~1.08M rows), `alerts`,
  `signal_outcomes`, `stock_scores`, `technical_scores`, `score_history`,
  `fetch_cache` (by ticker, with a dual-listing collision guard),
  `institutional_holdings`. `VACUUM` reclaimed ~155 MB (DB 496 → 341 MB).
- **Pre-prune backup:** `backend/data/app.db.pre-prune-2026-06-18.bak` (full
  496 MB snapshot — delete once you're confident the prune is good).
- Composite percentiles / breadth recompute on the next scan; nothing else
  needed. To prune again, the approach is reproducible from this note.

### Dot-ticker fix + Berkshire dedup → 999 (2026-06-19)

Three index members had **no OHLCV** because their `ticker` (used directly as
the yfinance download symbol) was in dot format yfinance rejects. Renamed to the
correct symbols and 10y-backfilled: **BRK.B→BRK-B, BF.B→BF-B, BT.A→BT-A.L**
(LSE needs the `.L` suffix + dash). The BRK rename revealed Berkshire was
**double-listed** — a working `BRK-B` already existed on NYSE (id 8, the correct
exchange, with alert history). Consolidated onto id 8 (moved its S&P 500
membership over, deleted the redundant NASDAQ dup). So the universe is now
**999 unique** stocks (the 1000th was the Berkshire duplicate), all with OHLCV.
Breadth `stocks_with_data` shows ~996 because 3 recent NASDAQ listings (PURR/Q/
LBRX) have <200 bars — `has_full_data` needs ≥200 for a meaningful EMA200; this
small gap is normal, not a bug.

---

## Unrepaired splits inside the stored history (tooling EXISTS — 2026-09)

`ohlcv_service._check_price_basis` compares the incoming overlap bar against the
stored one, so it only ever sees a discontinuity at the EDGE of a fetch window.
A break already INSIDE the stored history is invisible to it by construction:
from the next day on, stored and incoming are both on the new basis, the ratio
is 1.0, and it reports "basis OK" forever. It was added 2026-07-04, so every
split spliced before that date went unrepaired.

The damage was not cosmetic — measured on the live catalogue 2026-09-01:

    TIT.MI  reverse 1:10, 15 May  ->  rel_strength 100.0, the HIGHEST in the
                                      whole universe, posture "Forte"
    KLAC    10:1, 18 May          ->  rel_strength 0.1
    CRWD    4:1, 29 Jun           ->  rel_strength 0.3
    SOXS    20:1, 26 May          ->  rel_strength 0.0

Three real companies at the bottom of the technical ranking and one artifact at
the very top. It contaminates breadth, ATR, the 52-week range, the Tecnico lens
and every detector whose lookback crosses the date.

**Built, do not rebuild:** `ohlcv_service.find_basis_breaks` (detector) and
`app.scripts.repair_price_basis` (report + repair, read-only by default,
`--ticker` to scope).

### The detector is deliberately blind to 2:1 splits

Calibrated by sweeping min-ratio x tolerance against real data: `min=3.0`,
`tol=0.08` gives 14 hits, zero of them the COVID crash, and 5/5 known real
splits. A first attempt started the ratio list at 1.5 and returned **239 false
positives**, dozens dated 9-18 March 2020 — any ~30% single-day fall matches a
1.5 ratio. The volume discriminator (`(ratio < 1) != (vol_ratio > 1)`) is what
separates a split from a crash: a split conserves dollar volume, a crash does
not. **A 2:1 split is therefore NOT detected. That is the accepted cost.**

### Two repair modes, and picking the wrong one destroys data

- `--apply` wipes the series and re-downloads it. Correct ONLY when a fresh
  download is clean, i.e. our stored copy drifted from a healthy source.
- `--truncate` drops every bar BEFORE the break. For when the source itself
  reproduces the break.

**Check which case you are in before running either.** Download the ticker
fresh and re-run the detector on it. SOXS (2026-09-02) is the worked example:
one break at 2026-05-26 that a fresh 10y download reproduces to the cent, so
`--apply` would have destroyed 2,514 bars and rebuilt them identically broken.

And do not "just rescale by the ratio". yfinance DECLARES SOXS splits on
2026-03-05 (1:20) and 2026-07-15 (1:10) — both correctly adjusted, no
discontinuity on either date — so the May break matches no declared corporate
action and the `20:1` the detector prints is a pattern match, not a fact. A
ratio you inferred, applied to ten years of prices, looks perfectly healthy and
is silently wrong if the truth is 18 or 25. (The residual is real, too:
1159.50/20 = 57.98 against an actual 62.90 is a genuine +8.5% day for a 3x
leveraged ETF, so the arithmetic cannot be checked against itself.)

Truncating invents nothing, and a ticker left under 200 bars simply fails
`has_full_data` — which already keeps it out of EMA200 signals and breadth —
then self-heals as real bars accrue.

### Run the scan against PROD, not the dev DB (2026-09-03)

The local `backend/data/app.db` showed exactly ONE break (SOXS). Production had
**seven, across six tickers**. The dev copy is not a sample of production — it
is a different, staler dataset. Always run the read-only pass in the pod:

    kubectl exec -n finance-alert finance-alert-finance-alert-0 --         python -m app.scripts.repair_price_basis

Triage that worked, and it is mechanical: download each ticker fresh and re-run
the detector on the DOWNLOAD. Fresh clean -> `--apply`. Fresh reproduces the
break -> `--truncate`, or leave it. Result on 2026-09-03:

    DD      fresh clean (declares a 1:3 on 2026-06-24)  -> --apply,    2512 bars
    FCIT.L  fresh clean (declares a 4:1 on 2026-05-11)  -> --apply,    2525 bars
    ARWR    fresh reproduces, no declared split          -> --truncate,  -129
    KDP     fresh reproduces, no declared split          -> --truncate,  -548
    SOXS    fresh reproduces, no declared split          -> --truncate, -2444

Six down to two. Always back the rows up first — `\copy (...) TO STDOUT` piped
to a local file; the pg pod's filesystem is read-only, so a server-side path
fails.

### INDV: RESOLVED — 1,765 bars that were never traded (2026-09-08)

The note here read: two opposite breaks close together are a data defect in the
window between them, wanting a bar-level repair that does not exist yet. The
first half is right. The second was wrong about the SIZE, and building the
repair is what showed it.

    2016-2023   1,911 bars   36-89% with o==h==l==c   14-52% at zero volume
    2024-2026     672 bars              0%                       0%

Indivior moved its primary listing to Nasdaq. Everything before is a thin
secondary line where the price was CARRIED rather than observed, and the
November 2022 pair is that line's most visible artifact, not the defect.
Deleting three days would have left 1,908 bars of the same provenance.

Truncated at 2023-06-02, the start of the trailing run with no untraded bars:
-1,765 rows, 818 left (above the 200 `has_full_data` floor). Both detectors
now report INDV clean. Backup:
`backend/data/basis-repair-backups/INDV_pre_2023-06-02.csv`.

**The general rule this leaves behind: bar COUNT is the wrong objective.**
Dropping INDV's untraded bars costs 562 and truncating costs 1,765 — the
cheaper option loses three times fewer bars and leaves 1,203 of them 61% flat.
What matters is whether what remains is a coherent record.

`assess_bar_quality` + `app.scripts.repair_bar_quality` (read-only by default,
`--drop-untraded` for scattered damage, `--truncate-to-clean` for a bad
prefix). The marker is zero VOLUME, never a flat bar: a real illiquid session
can print o==h==l==c honestly, and 524 of INDV's flat bars carry genuine
volume.

### The catalogue-wide sweep: 13 done, 254 deliberately left (2026-09-08)

The scan `repair_bar_quality` made possible found **267 tickers holding 9,216
untraded bars** — a quarter of the universe, invisible until then because
`find_basis_breaks` only fires on ~3x jumps and a carried-over price rarely
makes one.

**The 13 that look like INDV are done.** Their prefix is a different DATA
REGIME, not scattered damage, and the plausibility check run before applying
is what confirms the tool was not guessing: the cut dates land on real
corporate events. AMCR 2019-06-11 is its NYSE listing after the Bemis merger;
SW 2024-07-08 is the birth of Smurfit Westrock; FER 2024-05-03 is Ferrovial
moving its primary listing; DKNG, ASTS and HIMS cut at the end of their SPAC
shells' histories. 8,132 rows, every count matching both the tool's prediction
and the CSV exported before the delete. All keep 200+ bars (SW is shortest at
544). Backups in `backend/data/basis-repair-backups/`.

**The remaining 254, holding 4,151 bars, are NOT a defect to repair.** They are
LOCAL MARKET HOLIDAYS that yfinance fills with a carried price, and the
evidence is that DB1.DE and MUV2.DE have an IDENTICAL date list — 60 bars each,
including 3 October, German Unity Day. Two different stocks sharing exact dates
means it is the Frankfurt calendar, not the stocks. BMPS.MI clusters on the
Milan year-end. The worst offenders are almost all non-US lines (.MI, .HK, .DE)
for the same reason: yfinance's calendar follows the NYSE.

Dropping them is defensible — a day with no market should not be a bar — but
the median ticker loses 0.65% of its series and 91 of the 254 have exactly ONE
bad bar. **Deliberately not applied.** Reach for `--drop-untraded` when
something downstream actually misreads a carried price, not as housekeeping.

### EYPT: RESOLVED — there was never anything to repair (2026-09-08)

It waited a month for Yahoo to apply a late split adjustment. Yahoo never did,
because there was no split.

**The decisive test, and it is not the one the triage above prescribes.**
yfinance applies declared splits to the price series *even with*
`auto_adjust=False`. Verified on EYPT's own declared 1:10 of 2020-12-09, where
the series is continuous across the date (x0.871 — ordinary daily noise) while
2026-08-17 shows x0.330. It follows that **a break which SURVIVES a fresh
download cannot be an unadjusted split**: if it were, the source would already
have absorbed it.

**The second discriminator is the MONEY, not the shares.** A split divides the
same turnover into more shares, so dollar volume on the day is ordinary. EYPT
traded $254M against a $20.7M median over the prior six months — sixteen times
normal, with +12% / +15% / -14% daily swings after it. That is a biotech news
event, and the stored history is CORRECT. Truncating would have destroyed 2,501
good bars to fix a defect that does not exist.

`find_basis_breaks` cannot make this call: it sees SHARE volume, where a split
and a panic both go up. Turnover separates them.

**Both checks are now in `repair_price_basis` and print on every read-only
run** — `_source_verdict`, one download per flagged break, `--no-source-check`
to skip. It reproduces the hand triage recorded above (DD/FCIT.L "fresh clean
-> --apply"; ARWR/KDP/INDV "source reproduces"). Three lessons are baked into
it, each from a wrong first version:

1. **Magnitude gates the verdict.** SOXS shows x0.054 with elevated turnover,
   and the first version called it a real move. A 3x leveraged ETF that resets
   daily cannot fall 94.6% in a session — it would need -31.5% on the
   underlying. Below `_MIN_REAL_RATIO` (0.20) no automatic verdict is issued at
   all. -67% happens; -95% does not.
2. **The turnover baseline must be the sedute BEFORE the break, not the whole
   history.** Against a 10-year median EYPT reads x186 and SOXS x19.2; against
   the prior six months, x15.9 and **x1.6**. That reclassified SOXS from a
   wrong "real move" to "investigate" — the baseline was not cosmetic.
3. **Only the network call is caught.** The first version wrapped the
   arithmetic too, and reported a `TypeError` in its own code as "source
   unreachable". The bug: the break date is a `date` from Postgres and a
   **string** from SQLite, so it was invisible in production and only broke on
   the dev DB — the reverse of the usual trap. `_as_date` normalises it.

INDV is unchanged by this and its verdict stands: two opposite breaks three
sessions apart, x0.0 turnover on the first. Not a split, not a price move —
corrupt bars, wanting a bar-level repair that does not exist.

### ⚠️ Ogni rebase lascia gli ALERT sulla base vecchia (FA-069, 2026-09-15)

Tutto sopra ripara la SERIE. `alerts.trigger_price` resta dov'era, quindi dopo
un rebase l'alert prezza l'ingresso su una base che il suo stesso grafico non
usa piu'. Misurato: **39 alert su 8 titoli, 11 visibili — e 20 li ha lasciati il
rebase AUTOMATICO del fetch**, non questo script: APH e MNST a x2.000 (i 2:1 che
`find_basis_breaks` per scelta non vede), AVB a 2.793.

`ohlcv_service.find_alerts_off_basis` li trova, `repair_price_basis` li stampa a
OGNI corsa — anche con «nessuna discontinuita'», che e' esattamente il caso dopo
una riparazione — e `_rebase_full_history` avverte nel log quanti ne lascia.
Due scelte che sembrano dettagli:

- **La finestra, non la barra del segnale.** Il trigger e' l'ultima chiusura che
  lo scan aveva: una rilevazione tardiva dopo un movimento vero (MRNA, x2.29
  sulla barra del segnale) combacia al centesimo con una chiusura successiva.
- **La banda e' quella dell'ingest** (`_BASIS_RATIO_*`), non un numero nuovo.
  Sopra il 25% di scarto ogni alert e' anche sopra il 50%; fra l'1 e il 22%
  stanno chiusure di Hong Kong assestate e scorpori (FDX x1.22).

**Non si correggono.** Lo snapshot porta livelli propri sulla stessa base
vecchia, che il playbook legge insieme al trigger; il fattore sarebbe NOSTRO
(la lezione SOXS); e gli esiti sono gia' giusti, perche' entrambe le chiusure
vengono dalla serie riparata.

## Catalog ticker rows — duplicates RESOLVED (2026-05)

**Historical note:** 59 tickers (AAPL, AMZN, UCG.MI, etc.) used to have **two
rows** in the `stocks` table because two ingestion paths inserted the same
logical ticker. **These duplicates have since been deduped** — as of 2026-05
the live DB has 1049 stock rows / 1049 distinct `(ticker, exchange)` groups
(verified read-only), and a `UniqueConstraint("ticker", "exchange")` on the
table now prevents the problem from recurring.

The defensive read-path pattern below is no longer strictly necessary, but it
remains **harmless and recommended** as belt-and-suspenders — keep using it on
read paths so a future ingestion bug can't resurface `MultipleResultsFound`:

```python
# WRONG — would raise MultipleResultsFound if a dup ever sneaks back in
stock = db.execute(select(Stock).where(Stock.ticker == ticker)).scalar_one_or_none()

# RIGHT — picks any matching row, all equivalent for read-only paths
stock = db.execute(
    select(Stock).where(Stock.ticker == ticker).limit(1)
).scalars().first()
```

A defensive, idempotent dedup migration (`128c69e4701a_dedup_stock_rows`,
no-op on the current clean DB) was authored on branch
`worktree-agent-a75ca023d8660c670` but **not merged** — it's redundant with the
unique constraint. Resurrect that branch only if duplicates ever reappear.

---

## One palette per meaning: rose/emerald = direction, red = broken (2026-09-08)

The app carried TWO complete up/down palettes — `green`/`red` and
`emerald`/`rose` — each self-consistent inside a given file, which is why a
file-level check said everything was fine. It was not: following each page's
IMPORT CLOSURE showed **9 of 17 pages rendering both on one screen**, and
`MarketMoodStrip` had them in a single declaration
(`from-red-50 to-rose-50`). Two colours for one meaning, side by side.

Measured before deciding, since `red` could legitimately have meant "error":
66% of `red-*` uses sat beside a green or a directional identifier
(change/up/down/gain/loss), 17% were error-semantic, and most of the remaining
17% were directional too (bearish mood, "Sold out", RSI overbought). About
four fifths of `red` meant "down" — the same thing `rose` meant.

**The rule now, and the reason it can be checked:**

- `rose` / `emerald` — market direction. Down and up.
- `red` / `green` — something is broken. Errors, failed scans, CRITICAL log
  levels, "not found".

80 lines converted, 13 deliberately left. Afterwards 2 pages still show both,
and both are CORRECT: PlatformHealthPage renders ERROR/CRITICAL levels and
failed scans beside directional data, SectorDetailPage an error message. 22
`red-*` tokens remain, all error-semantic. **If that count grows, someone has
coloured a price move red.**

Every swap was checked against WCAG AA on both card backgrounds before it was
made — the shades map 1:1 and all pairs hold. The tightest is `red-600` ->
`rose-600` on white, 4.83 -> 4.70, still above the 4.5 threshold but with less
room; do not darken the background behind it.

⚠️ **A rename makes comments lie.** `MicroDataCard`'s constants were
`GREEN`/`RED`/`AMBER` holding emerald/rose values, directly beneath a comment
documenting the contrast of `green-800` and `red-600` — numbers for classes the
file no longer used. Renamed to `GOOD`/`BAD`/`WARN`, which is what they always
meant, and the measurements re-stated. Same failure mode as the dead
`_RANGE_PERIODS` table below: the stale note is believable precisely because
something next to it corroborates it.

## Money on screen: one owner, and the two ways to get it wrong (2026-09-10)

312 of the 1010 catalogued stocks are not quoted in dollars — 97 GBP, 87 EUR,
59 HKD, 40 JPY, 20 KRW and a tail — and the stock detail page hard-coded `$`
beside every price. Not ambiguous for a third of the universe: **wrong**.

There were THREE formatters and they disagreed. The screener had a symbol map
and got it right; PositionsPage had an `Intl` helper; the detail page had
neither. `lib/money.ts` is now the single owner, the frontend twin of
`currency_units` on the backend — which consolidated the same problem after
finding the pence logic quintuplicated across five services.

⚠️ **Do NOT reach for `Intl` + `currencyDisplay: "narrowSymbol"`.** It reads
like the obvious way to get `$` instead of `USD`, and it renders USD, HKD and
AUD as the SAME `$`, recreating the whole defect on the 59 Hong Kong names.
`it-IT` without it renders USD as the string "USD", which is why the app had a
hand map in the first place. The map is the answer; `money.test.ts` pins the
four dollars apart and pins `¥` apart from `CN¥` (the screener's map had one
glyph for both).

⚠️ **A missing currency must never become USD.** The old helper read
`currency && /^[A-Z]{3}$/.test(currency) ? currency : "USD"`, which prints
dollars for a stock whose currency did not load AND — since the regex demands
uppercase — rejects yfinance's `GBp` and prints dollars for a London stock
specifically. `fx_service` settled this in its own docstring: an unresolvable
currency is UNKNOWN and the caller shows nothing. Market assets (indices, FX,
crypto) rely on it — an index level is not money.

### `Stock.currency` had six stale `GBp` rows, and the prices were FINE

Worth reading before "fixing" anything that looks like a pence bug. All 99
`.L` stocks have `ohlcv_in_pounds = true`: the migration divided by 100 at
ingest and the NUMBERS are correct. Six rows (BA.L, BP.L, BRBY.L, GLEN.L,
RR.L, SHEL.L) kept yfinance's raw `GBp` LABEL beside a pounds value.

The check that settles it without any outside price knowledge: the six sit at
5.57-35.04, inside the 0.80-175.70 range of the 93 rows already labelled GBP.
Pence would be a hundred times larger. Shell's own market cap confirms it
independently — 196 billion against a 35.04 price is only arithmetic in
pounds.

`currency_units.major_unit_currency` owns the LABEL rule (idempotent, safe on
any display path); `scale_minor_to_major` owns the VALUE rule (runs exactly
once, at ingest). **They are not interchangeable and running the second one
twice is the ×100 bug in reverse.** Migration `8fc285de13e2` repaired the rows
and `seed_service` normalizes at the boundary, the way `canonical_country`
does — repairing without closing the door lets the next CSV import undo it.

### ⚠️ `stock.market_cap` is in the LISTING currency, and the screener sorts on it

NOT fixed, and it is a real defect, so do not re-discover it. `risk.py` hit
this exact trap and its test records the damage: 158 names cleared the 200e9
mega-cap bar in native currency against only 83 in USD, so **75 stocks were
scored as stable mega-caps without being anything of the kind** (7270.T at
$10.9bn, 033780.KS at $14.4bn). It now calls `to_usd` first.

The screener's market-cap column and NavbarSearch still print `$` on the raw
figure AND the column is SORTABLE, so a 19,812bn KRW cap outranks a 3,500bn
USD one. Fixing it is a decision, not a relabel: converting to USD keeps the
sort meaningful and changes the numbers on screen; labelling each cap with its
own currency is honest and makes the sort meaningless. Do not slap
`formatMoney` on it — that picks the second option by accident.

## Units are the third recurring defect class, after palettes and rates (2026-09-10)

The honesty rules in this file are applied to STATISTICS and not to
ARITHMETIC. A rate must carry its denominator and an interval must be sized on
independent windows -- meanwhile a full UI audit found four values on screen
wearing the wrong unit, three of them off by a large factor.

| Where | What is shown | What it is |
|---|---|---|
| Macro detail | `159.1K` | a value already in thousands, so 1000x |
| Institutional panel | `+7663.7PP` | a SHARE-count % change, not weight points |
| Screener | `$2.86T` beside `HK$165.60` | a HKD figure under a USD symbol |
| Market detail | `52W LOW 4.40` | the all-time low, on 5 of 6 timeframes |

**Three checks that need no code reading and would have caught three of four:**

1. **A percentage of a whole cannot change by more than 100 points.**
   `|delta_pp| <= 100`, always. Three values above it sat on one screen.
2. **Two boxes with different labels must not print the same number.**
   `52W high` equalled `Range high` to the cent -- one measurement wearing two
   names.
3. **A compact suffix must know the stored scale.** The macro card literally
   renders `Total Non-Farm Payrolls (thousands)` two inches from `159.1K`. The
   unit was in the payload and the formatter ignored it.

⚠️ **The dangerous half is never the absurd value.** An S&P 500 low of 4.40
denounces itself. The same bug on 5m/30m produces a 60-day low labelled "52
weeks", which is PLAUSIBLE and therefore believed. When a window bug is found,
fix every timeframe, not the one that looked wrong -- and note that the 52W
block had NO test, so the regression was invisible from `2faee27` onward.

Full audit with causes and file refs:
[docs/frontend-audit-2026-09-10.md](docs/frontend-audit-2026-09-10.md).
Backlog IDs FA-030 to FA-039.

## When space runs out, the IDENTITY gives way and the decoration survives (2026-09-10)

Found three times in one afternoon, in three unrelated components, always the
same shape: the flexible track is the one that says WHAT you are looking at,
and everything beside it is `shrink-0`.

| Component | What compressed to nothing | What survived intact |
|---|---|---|
| `SectionTitle` | the card's name -> `F` for `FUNDAMENTALS` | timestamp + refresh button |
| `EventChip` (calendar) | the ticker -> `D ▲`, `A…` | logo, arrow, dot |
| `AllocationBars` | the fund/holding name | the percentage and the bar |

Each reads as reasonable in isolation: a chip should not wrap, a timestamp
should not break. But together they mean the LABEL is the only thing that can
absorb a deficit, so it absorbs all of it. A bar at 3.5% with no name is not
partial information, it is noise.

**The rule: identity and measure belong in the same unit of reading.** When
they do not both fit, wrap or stack — do not let the name go to zero. Concrete
shapes used here: `flex-wrap` so the trailing slot drops below (SectionTitle),
one item per row instead of two columns (calendar), a two-row grid under `sm`
(AllocationBars).

⚠️ **All of these are LITERAL class strings.** A responsive template composed
at runtime (`` `sm:grid-cols-[${cols.join("_")}]` ``) is dropped by the
Tailwind purger and the bug is invisible in dev — the rule the tone-class
section below already states, in a second disguise. Where a grid needs several
shapes, write each one out; four literals beat one template.

### The corollary that cost the most time: a partial fix HIDES the defect

Two of the three had already been found, already been "fixed", and the fix had
the wrong threshold. Worse, the comment beside the code described the defect
in detail, with measurements, and declared it closed:

- `StockDetailPage` — *"side by side these two got ~170px each... the Qualità
  gauge collided with its risk badge"*. Fixed under `sm`; the column is narrow
  from `lg` UP, where it becomes the `1fr` of `[2fr_1fr]` and yields ~133px.
- `DayCell` — *"Two columns is what made the tickers vanish... thirty-one
  labels were invisible"*. Moved to `dense-3` (1400px) on a "two 85px chips"
  calculation. 85px does not hold a ticker, and the screenshot that reopened
  the case is at **1440px** — inside the two-column branch.

This is the `_RANGE_PERIODS` failure in another form: dead code corroborates a
stale note, and a partial fix corroborates a closed case. **When a comment says
something was fixed, redo the arithmetic — it costs less than trusting it.**

## Un seme SEMINATO non basta: conta il NUMERO di estrazioni (2026-09-13)

Il gate UI e' diventato rosso su `/alerts` e `/sectors` per un commit che non
aveva toccato ne' l'una ne' l'altra (le sue modifiche frontend erano solo
`InfraCard` e `platformHealth`, cioe' /diagnostics). Cercare il difetto nel
codice in esame e' stato tempo perso: non era li'.

`seed_e2e` usa `random.Random(20260912)` e sembrava quindi gia' conforme alla
regola che questo file impone — «una misura che dipende da cosa c'e' nel
database non e' una misura». La dipendenza non era dai DATI. Era dal TEMPO, su
due canali distinti, ed entrambi meritano di essere riconosciuti a vista.

### 1. Un `continue` dentro il ciclo cambia quante estrazioni si consumano

    for i in range(BARRE, 0, -1):
        giorno = oggi - timedelta(days=i)
        if giorno.weekday() >= 5:
            continue              # <- salta PRIMA di estrarre
        prezzo *= 1 + rng.uniform(...)

Questo conta i feriali DENTRO un intervallo fisso di giorni, che non e' un
numero fisso di feriali: misurato, **215 il sabato e la domenica, 214 il
lunedi'**. Ogni barra consuma un'estrazione, quindi una barra in meno sposta
l'INTERA sequenza successiva: tutti i prezzi cambiano, con essi le percentuali
a schermo, e con esse i colori che le vestono.

⚠️ **Un generatore seminato rende riproducibili i VALORI, non il NUMERO di
estrazioni.** Se il conteggio dipende da qualcosa di esterno — il giorno della
settimana, un filtro sui dati, una condizione di rete — il seme non serve a
niente e il codice sembra deterministico. La forma da cercare e' un `continue`,
un `if` o un `break` fra l'inizio del ciclo e la prima estrazione.

La correzione: `_giorni_feriali(oggi, N)` rende sempre esattamente N feriali.

### 2. `datetime.now()` in un seme e' l'ora della corsa

    triggered_at = datetime.now(UTC) - timedelta(hours=6 * (i + j))

Gli scarti valgono fino a 78 ore, e la UI legge lo scarto in GIORNI DI
CALENDARIO fra `signal_date` e `triggered_at` (soglia 4 giorni -> pastiglia «in
ritardo»). Quello scarto cambia con l'ORA in cui parte il job: **la corsa che
ha fallito girava alle 00:18 UTC**, dove `now - 6h*k` scivola nel giorno prima
per i k piccoli. Numero di elementi resi diverso, conteggio axe diverso.

Ancora a **mezzogiorno UTC** (`_ancora(oggi)`): lontano da entrambi i bordi del
giorno, quindi nessuna ora di partenza puo' spostarlo oltre la mezzanotte.

Diciotto test in `test_seed_e2e_deterministico.py`, col controllo negativo che
fissa l'INSTABILITA' della vecchia forma — senza, il test nuovo sembra una
formalita' e qualcuno lo «semplifica» all'indietro.

### 3. ⚠️ E la data del SEGNALE non era agganciata ai feriali (2026-09-14)

**La stessa lezione, applicata a meta', e l'ho scoperto il giorno dopo averla
scritta.** I due canali sopra erano chiusi — `_giorni_feriali` rende sempre N
barre, `_ancora` e' mezzogiorno UTC — ma `signal_date` era rimasto
`oggi - N giorni di CALENDARIO`, mentre le barre esistono SOLO nei feriali.

Quindi quanti segnali cadono su un giorno che HA una barra dipendeva ancora dal
giorno della settimana in cui gira il job. Misurato:

    domenica 13/09:  29 segnali su 36 hanno una barra
    lunedi'  14/09:  21 segnali su 36

⚠️ **E' bastato che la CI attraversasse la mezzanotte.** Il gate a11y e'
diventato rosso su `/alerts` (`button-name: 48 -> 49`) per un commit che non
toccava ne' il seme ne' il frontend: la corsa delle 18:57 UTC passava, quella
delle 00:24 no. Identico all'incidente precedente, che girava alle 00:18.

La correzione: `signal_date` si PRENDE dal calendario dei feriali, lo stesso che
genera le barre, quindi ogni segnale ne ha una per costruzione. E `triggered_at`
si conta **dal segnale, non da oggi** — la pastiglia «in ritardo» misura giorni
di CALENDARIO, quindi ancorandolo a `oggi` lo scarto cambiava con i fine
settimana di mezzo e il conteggio restava legato all'orologio anche dopo aver
sistemato le barre.

Verificato su QUATTORDICI giorni consecutivi: una sola combinazione distinta
(36 segnali su 36 con la loro barra, 7 con la pastiglia, 0 nel futuro), dove
prima erano tre. Col controllo negativo che ricostruisce la forma vecchia e
pretende che domenica e lunedi' divergano.

**La regola generale, dopo tre canali:** in un seme, ogni grandezza che la UI
legge va derivata dal CALENDARIO DEL SEME, non dall'orologio. «Oggi meno N
giorni» sembra deterministico e non lo e' appena qualcos'altro nel seme vive su
una griglia diversa — qui i feriali.

### 4. ⚠️ Il backend del gate aveva la RETE, e l'avvio la usava (2026-09-15)

Il quarto canale e il piu' largo: non l'orologio del seme, ma cosa Yahoo e
Dataroma rispondevano quel giorno. Due percorsi d'avvio:

- `_catch_up_scan_on_boot` (soglia `SCAN_STARTUP_STALE_HOURS`) scaricava barre
  VERE per i ticker del seme e le incollava sopra la storia sintetica. Su
  /stocks la chiusura vera di 0016.HK sopra una serie da 146 dava RSI 18,8, e il
  gate a11y e' diventato rosso (`button-name: 46 -> 49`) su un commit di sole
  migrazioni.
- `_catch_up_institutionals_on_boot` lancia gli scraper 13F quando
  `filings_refresh_is_stale`, che risponde vero anche quando NON ESISTE nessun
  filing — cioe' sempre, su un database nato vuoto.

La chiusura ha tre pezzi e nessuno basta da solo: il seme semina i filing ed
esegue la meta' dello scan che non scarica (`run_tracked_scan` + contabilita');
il job da' al backend un proxy su una porta chiusa; e
`SCAN_STARTUP_STALE_HOURS=0` e' esplicito. ⚠️ `app/core/public_http.py` usa
`urllib3` diretto, che le variabili di proxy NON le legge: residuo dichiarato,
innocuo finche' il seme non ha notizie.

⚠️ Per riprodurre il gate senza rete su Windows il proxy va su
`http://0.0.0.0:9`: una connessione a una porta chiusa di `127.0.0.1` impiega
~2s a essere rifiutata (su Linux e' istantanea), e tre test scadono per il
tempo, non per un difetto.

### Stringere una linea di base vuole DUE osservazioni

Col seme corretto `/alerts` e' scesa a 46, e il gate stesso suggerisce
`E2E_UPDATE_BASELINE=1`. Due cautele, entrambe gia' pagate:

1. **Non si rigenera in locale.** Questa linea di base e' quella di CI e il file
   lo dice in `_ambiente`: in locale il calendario ha dati veri e rende un
   elemento in meno, quindi si otterrebbe un file piu' STRETTO che fa arrossire
   la CI su codice intatto.
2. **Non si stringe su una corsa sola.** `/calendar` fu stretta da 3 a 2 su una
   verde e la successiva lesse 3. Qui il 46 e' stato letto da DUE corse
   indipendenti (un push e un `workflow_dispatch`) prima di scendere, e si e'
   cambiato UN SOLO valore a mano invece di adottare una candidata non
   leggibile — adottarla in blocco stringerebbe anche rotte viste una volta.

### Il corollario: un cancello deve NOMINARE il colpevole

«button-name: 53 -> 54» su un arretrato di 53 non dice quale nodo, ne' se la
colpa e' del commit. La diagnosi e' costata scaricare gli artefatti di CI e
leggere uno screenshot. Il gate stampa ora i SELETTORI dei criteri cresciuti, e
la prima esecuzione con quella stampa ha risolto in un colpo due domande
diverse: su `/alerts` i nodi erano caselle di riga (seme), su `/sectors` erano
**undici volte lo stesso token `text-sky-600`** — cioe' un difetto unico, non
undici.

### E il difetto vero che tutto questo ha portato a galla

`amber-600` vale **3,19 : 1** e `sky-600` **4,10 : 1** su fondo scheda, contro
la soglia AA di 4,5. **Diciassette nodi** in due rotte — 6 su /stocks/AAPL e 11
su /sectors, di cui 10 gia' in linea di base — tutti da un token solo
(`SCORE_TEXT_TONE`, proprietario unico di dieci componenti). Sette sono
comparsi col seme corretto; gli altri dieci erano li' da sempre, accettati come
arretrato senza che nessuno avesse notato che erano LA STESSA COSA.

⚠️ **Erano invisibili a TUTTI i presidi, e non per una svista.** axe in jsdom
non carica fogli di stile, quindi non misura contrasto — gia' scritto qui. Il
gate e2e gli stili ce li ha, ma vede solo i colori che i DATI di quella corsa
fanno comparire, e col vecchio seme nessun punteggio cadeva nelle fasce
«mediocre» e «buono». Un difetto di mesi, scoperto da una correzione che
riguardava altro.

La lezione operativa: **dove un colore dipende da una soglia sui dati, il
contrasto va calcolato sui TOKEN, non cercato nel DOM.**
`scoreMeta.contrasto.test.ts` fa aritmetica WCAG sulla tabella dei toni — non
dipende da quali dati ci sono, quindi non puo' essere vero per caso. Porta un
controllo negativo (la formula DEVE bocciare i due colori tolti) e una deroga
dichiarata con la ragione scritta, nella forma di `EQUIVALENTI`.

⚠️ `sky-600` a 4,10 e' il motivo per cui va CALCOLATO: sembra scuro abbastanza.
E la formula va verificata contro un numero indipendente — questo file
registrava gia' `rose-600` su bianco a 4,70, e il calcolo nuovo rende 4,70.

⚠️ Le varianti scure NON si scuriscono insieme alle chiare: `amber-400` su
fondo scuro e' gia' molto sopra soglia e scurirlo lo porterebbe SOTTO. Le due
meta' di un token si muovono in direzioni opposte.

⚠️ E gli sfondi vanno presi dai token, non a occhio: il fondo muto vero e'
`#f1f5f9` (`hsl(210 40% 96.1%)`), non il `#f8fafc` che il primo tentativo aveva
indovinato — piu' SCURO, cioe' la stima era ottimista, sbagliata nella
direzione che nasconde i difetti. `index.css` non e' leggibile da vitest
(neutralizza gli import di fogli di stile: sia `import.meta.glob(...?raw)` sia
l'import statico `?raw` tornano stringa vuota), quindi i valori sono trascritti
e la trascrizione e' verificata rifacendo la conversione dall'HSL.

### Il quarto viewport, e perche' e' ristretto a una specifica

La pagina dettaglio titolo si riassetta oltre i 1920px. I tre viewport del gate
— 375, 768, 1440 — sono TUTTI sotto quella soglia, quindi misuravano solo il
ramo vecchio; e jsdom non fa layout, quindi «affiancate» e «sotto» non sono
nemmeno esprimibili in vitest. Progetto `over-fhd` a 2560x1440.

⚠️ Gira SOLO su `stock-detail-riassetto.spec.ts`, non su `layout.spec.ts`: il
traboccamento a 2560px sulle altre nove rotte non e' mai stato misurato, e
**un cancello che nasce rosso viene spento**. Allargarlo e' una riga, dopo la
misura.

⚠️ Quando un riassetto cambia CHI sta DOVE (non come appare), il ramo va in JS:
con `hidden` resterebbero montate due copie — due query, due alberi — e quella
nascosta verrebbe comunque misurata e letta dagli assistivi. Ne segue che
esistono DUE soglie, una in `tailwind.config.js` e una nel componente, e vanno
PINNATE INSIEME: la banda di larghezze fra due soglie divergenti e' il peggio
delle due disposizioni. Il test che conta di piu' li' e' il CONTEGGIO delle
copie, perche' una doppia montatura e' invisibile a occhio.

## Larghezza su mobile: il difetto c'e, ma il CONTROLLO ovvio non lo vede (2026-09-12)

Otto rotte traboccavano a 375px e nessuna barra di scorrimento orizzontale
compariva. Cercarle con il controllo che viene in mente per primo —
`document.documentElement.scrollWidth > clientWidth` — restituisce **sempre
zero**, su ogni pagina, anche mentre il contenuto esce dallo schermo.

**Perche.** `html` e `body` sono `overflow-x: clip`, quindi il documento non
puo scorrere di lato: taglia e basta. E `<main>` porta
`flex-1 min-w-0 overflow-y-auto p-3`, dove `overflow-y: auto` **forza per
specifica** `overflow-x` da `visible` ad `auto` (i due assi non possono essere
uno visibile e uno scorrevole). Quindi:

- il traboccamento diventa una barra DENTRO `<main>`, non a livello di pagina;
- qualunque rilevatore che salta i discendenti di un contenitore che scorre —
  cioe la regola giusta, perche una tabella in `overflow-x-auto` scorre di
  proposito — **scarta l'intera applicazione**, perche `<main>` e la radice di
  tutto.

Il primo rilevatore scritto qui ha riportato «zero offensori» su ogni rotta ed
era una risposta falsa, la stessa forma di «un test puo essere vero di niente»
gia registrata tre volte in questo file. **Il controllo negativo l'ha mancata**:
la sonda larga 900px era appesa a `document.body`, cioe FUORI da `<main>`, e
veniva vista. Spostata dentro `<main>`, il rilevatore taceva.

**La ricetta che funziona**, e il riquadro da usare e quello di `<main>`:

```js
const main = document.querySelector("main");
const limite = main.getBoundingClientRect().left + main.clientWidth;
// offensore = right > limite+1, nessun antenato (fino a main ESCLUSO)
// con overflow-x auto|scroll|hidden|clip, elemento visibile
// poi si tengono solo i piu ESTERNI, altrimenti si legge la stessa riga 12 volte
```

E si misura con `resize_window` preset **mobile**: una larghezza CUSTOM
(390x844) e stata accettata dallo strumento e **non ha cambiato il layout** —
la pagina continuava a leggere 533px, con `maxTouchPoints: 0`. Il preset porta
375px, UA Android e 5 punti di tocco. Leggere sempre `window.innerWidth` dalla
pagina prima di credere a un viewport.

### Le due cause vere, che non sono larghezze scritte a mano

Un grep di `w-[NNNpx]` non trova niente: gli otto siti erano tutti **contenuto
che non sa stringersi**.

1. **`flex-wrap` sul contenitore non spezza un ELEMENTO troppo largo.** Manda a
   capo gli item; se un singolo item ha min-content maggiore della riga, esce
   lo stesso e si porta dietro il genitore. Su `/calendar` e `/stocks` il wrap
   c'era gia ed era inutile: serviva scendere al gruppo interno
   (`min-w-[13.5rem]` sull'etichetta del mese, 412px di riga; la barra
   «Righe per pagina…» da 445px).

2. **`truncate` su un flex item non entra in funzione senza `min-w-0`.** Un
   flex item ha `min-width: auto`, cioe si rifiuta di scendere sotto la propria
   min-content: con un'etichetta lunga la min-content e l'etichetta INTERA, il
   contenitore viene sfondato e il troncamento non scatta mai perche lo spazio
   «c'e». `SectionTitle` — il titolo canonico di OGNI scheda — ne era privo, e
   il commento accanto descriveva in dettaglio un difetto simile dichiarandolo
   chiuso. Stessa forma del `_RANGE_PERIODS` morto: **quando un commento dice
   che una cosa e risolta, rifare l'aritmetica**.

Un `<select>` merita una nota a parte: si dimensiona sull'**opzione piu lunga**,
non sul contenitore, e ignora il genitore finche non gli si mette
`min-w-0 max-w-full`.

## `title=` e una spiegazione che su un telefono NON esiste (2026-09-12)

Misurato: **112 attributi `title`** con prosa lunga, quasi tutti su
intestazioni di tabella. Su un dispositivo touch `title` non si apre mai — non
c'e un hover da produrre e il long-press apre il menu contestuale del sistema.
Erano spiegazioni scritte, spedite nel bundle, e invisibili a meta degli
utenti. Il difetto e di ACCESSO, non di spazio, ed e per questo che non si
vedeva: su desktop funzionava tutto.

`components/ui/info-hint.tsx` e l'unico proprietario del rimpiazzo, e
`TableHead` accetta `hint=` che lo monta da solo. Tre cose che sembrano
dettagli e non lo sono:

- **Radix Tooltip e la scelta sbagliata.** Si chiude su `pointerdown`, che e
  esattamente il gesto di un tap: sarebbe lo stesso difetto con un'altra
  libreria. Popover apre al click, che touch e mouse producono entrambi.
- **Il click deve APRIRE, non commutare.** Col mouse `pointerenter` ha gia
  aperto, quindi un toggle richiude subito e **col mouse il pannello non si
  apre mai al click**. Si disinnesca il toggle interno di Radix con
  `preventDefault()`, che `composeEventHandlers` rispetta.
- **Serve il portale e serve `collisionPadding`.** Il grilletto vive dentro
  `overflow-x-auto`, quindi un figlio posizionato verrebbe tagliato; e il
  default `collisionPadding: 0` incolla il pannello al bordo — misurato su
  375px cadeva a 376, un pixel dentro la zona che `overflow-x: clip` taglia.

⚠️ **Non convertire cio che e un DATO.** Le didascalie delle piastrelle
`/setups` portano bande di confidenza, minimi/massimi e «non concludente»:
metterle dietro un tocco significa mostrare un tasso senza il campione che lo
regge, cioe rompere la regola di onesta che questo file impone altrove. Sono
state lasciate a schermo di proposito; e passata nel popup solo la prosa.

Il censimento sta in `components/mobileLayout.test.ts` (jsdom non fa layout,
quindi le classi sono fissate alla sorgente, con un pavimento su ogni conteggio
e un'asserzione che le spiegazioni esistano ancora ALTROVE — senza, cancellarle
tutte passerebbe). **Ha trovato subito nove intestazioni che il grep a mano
aveva mancato**, perche stavano su piu righe.

## Frontend tone classes (Tailwind purger)

Tone-class maps in `lib/alertMeta.ts` and similar files MUST stay as plain
string-literal `Record<Tone, string>` maps. **Do not refactor to template-
string composition** — Tailwind's build-time class purger only sees literals,
and a refactor will silently strip all the tone classes from the prod build.
The bug is invisible in dev.

---

## Tre trappole dell'armamentario, non del prodotto (2026-09-11)

Tutte e tre hanno prodotto un rosso — o un verde — che NON riguardava il codice
in esame, e ognuna e costata tempo perche il primo istinto e stato correggere
il prodotto.

### ⚠️ `vi.fn()` che lancia fa fallire il test anche quando l'errore E gestito

Un mock di vitest che lancia, o che restituisce una promise gia rifiutata,
viene riportato come fallimento del test indipendentemente da chi lo gestisce.
Mettere un `catch` sulla promise originale NON basta: il rifiuto segnalato e
quello DERIVATO che il mock crea per osservare la risoluzione.

Isolato con una sonda di dieci righe, che e la mossa da rifare invece di
tentare varianti: lo stesso `useQuery` con una `queryFn` che lancia
direttamente passa; con un `vi.fn()` di mezzo fallisce. Quindi non e
react-query e non e il componente.

La forma che funziona — **il finto restituisce sempre, a lanciare e il
guscio**:

```ts
vi.mock("@/api/x", async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  fetchThing: async (a: string) => {
    const r = fetchMock(a);
    if (r instanceof Error) throw r;   // il lancio non esce dal vi.fn()
    return r;
  },
}));
// nel test:  fetchMock.mockReturnValue(new Error("boom"))
```

Va commentata sul posto, altrimenti il prossimo lettore la legge come una
complicazione inutile e la semplifica, riaprendo un rosso che non riguarda il
prodotto. Esempio vivo in `SourceDegradedNote.test.tsx`.

Corollario: quando aspetti che una query in ERRORE si sia risolta, aspetta lo
stato (`qc.getQueryState(key)?.status === "error"`), non che il mock sia stato
chiamato. La chiamata e sincrona, quindi quell'attesa passa subito e il test
finisce prima che react-query agganci il proprio handler.

### ⚠️ Un test sui giorni fra due date e VACUO in UTC — cioe in CI

Terza istanza di «un test puo essere vero di niente», dopo `toEqual` sui nodi
DOM e la scheda filtri con tre aree chiuse.

`Date.parse("2026-09-18")` e mezzanotte **UTC**; «oggi» calcolato con
`setHours(0,0,0,0)` e mezzanotte **locale**. La differenza vale `n + offset`:

| Fuso | Differenza | `floor` vs `round` |
|---|---|---|
| Roma (UTC+2) | `n + 0,083` | identici |
| **CI (UTC)** | `n` | **identici** |
| New York (UTC-4) | `n − 0,208` | divergono |

Un test che asserisce l'arrotondamento passa quindi anche sostituendo
`Math.round` con `Math.floor`, sia in locale sia dove conta. Il fuso va
IMPOSTO — `process.env.TZ` e rileggibile a runtime da Node, anche dopo che una
`Date` e gia stata costruita, ed e reversibile:

```ts
const env = nodeEnv(); const tz = env.TZ;
try { env.TZ = "America/New_York"; vi.setSystemTime(...); /* asserzioni */ }
finally { env.TZ = tz; }
```

Reso capace di fallire, il test ha trovato subito un difetto vero:
`Math.round` di un valore in (-0.5, 0) vale `-0`, e `Object.is(-0, 0)` e falso.

⚠️ Non installare `@types/node` per tipare `process`: qualunque scrittura npm
su Windows puo togliere il ramo Linux dal lockfile. Tre righe di dichiarazione
con un cast su `globalThis` fanno lo stesso lavoro — vedi
`earningsProximity.test.ts`.

### ⚠️ Una funzione SOSTITUITA ovunque non e' verificata da nessuno (2026-09-14)

Il cancello del codice mai eseguito ha segnalato
`live_quote_service::_is_premarket` come nuova funzione morta su un commit che
toccava **solo il frontend**. E la riga sopra, nello stesso rapporto,
dichiarava `_today_session_open_epoch` «ora coperta»: due funzioni dello stesso
modulo che si scambiano lo stato di copertura fra due corse.

**La causa, misurata sui test e non dedotta: OGNI riferimento esistente le
sostituiva.** Otto fra `monkeypatch.setattr` e `patch(...)`, nessuna chiamata
reale. La loro copertura veniva solo dall'esecuzione incidentale dentro
qualche altro test — e quella dipende dall'ORA, perche'
`allow_remote_today_fetch and _is_premarket(ticker)` corto-circuita e la
condizione a valle legge l'orologio.

⚠️ Stessa famiglia del `raising=False` che crea un attributo nuovo invece di
sostituire quello vero: **il finto nasconde che l'originale non gira mai.** Un
modulo puo' avere venti test che lo nominano e zero che lo eseguono, e il
sintomo non e' un rosso — e' un cancello che sfarfalla.

La forma della correzione conta: **il tempo si INIETTA dove la firma lo
permette** (`_is_premarket(ticker, now_utc)`), e dove non lo permette si
asserisce una proprieta' vera a QUALUNQUE ora — l'epoch reso, riconvertito nel
fuso della borsa, e' l'apertura di oggi — invece di congelare l'orologio. Un
test che gira solo col tempo fermo e' esattamente cio' che ha reso queste due
funzioni invisibili.

⚠️ E uno dei tredici test ha corretto CHI LO SCRIVEVA. Avevo asserito che un
suffisso sconosciuto rendesse `None`; `_exchange_region` fa cadere ogni
suffisso ignoto su `"US"` e il suo docstring dichiara che non e' cosmetico.
Ne segue che il `return None` di `_today_session_open_epoch` e' un ramo
difensivo irraggiungibile per quella via — una delle cinque famiglie. Si fissa
il comportamento VERO, non quello che sembrava ragionevole.

### ⚠️ axe tollera un `aria-controls` pendente solo con `aria-expanded` (2026-09-14)

Costato due corse rosse del gate UI. Un controllo «Recenti / Storico» reso con
Radix `Tabs`: `TabsTrigger` emette `aria-controls` verso il `TabsContent`
corrispondente, che non veniva reso perche' il contenuto era un fratello piu' in
basso. Riferimento a un id INESISTENTE -> `aria-valid-attr-value: 0 -> 1`.

**La parte non ovvia: axe ne ha segnalato UNO, non sette.** Nella stessa scheda
sei popover `InfoHint` portano lo stesso attributo pendente e sono VALIDI,
perche' axe tollera un riferimento non risolto quando l'elemento ha
`aria-expanded="false"` — un pannello non ancora montato e' legittimo. Radix
Popover mette `aria-expanded`; `TabsTrigger` no, perche' un tab non ha uno stato
aperto/chiuso.

Due conseguenze operative:

1. **Un gruppo di tab senza tabpanel non e' un gruppo di tab.** Due bottoni con
   `aria-pressed` sono la forma corretta di un controllo segmentato e non
   promettono un pannello. Un'ARIA che nomina un id che non c'e' e' peggio di
   nessuna ARIA: gli assistivi annunciano una relazione inesistente e il
   difetto e' invisibile a chi guarda lo schermo.
2. **Il test che lo sorveglia va RISTRETTO al proprio controllo.** La prima
   versione cercava ogni `aria-controls` pendente nella scheda e diventava rossa
   sui sei popover corretti di qualcun altro — cioe' un cancello che nasce
   rosso, che poi viene spento.

### ⚠️ Il nome di una scheda e' la sua IDENTITA': non cambia con la vista

Stessa correzione, secondo difetto. Avevo fatto variare il titolo della scheda
con la scheda attiva («Segnali recenti» / «Storico completo») e il gate e2e, che
la localizza per quel testo, non l'ha piu' trovata: *«la scheda dei segnali non
e' stata resa»*.

Il test aveva ragione a rompersi. E' la stessa regola della sezione sullo spazio
che finisce — quando manca, cede la decorazione e non l'etichetta — applicata al
tempo invece che allo spazio: **cio' che identifica il riquadro resta fermo, cio'
che appartiene alla vista varia.** Il titolo e' tornato stabile e il CONTEGGIO
segue la vista, perche' quello alla vista appartiene davvero.

### ⚠️ `git checkout --` NON e un ripristino: e un ritorno a HEAD

Questo file dice gia «si toglie la correzione **su una copia**, si esegue, si
ripristina». Il modo di sbagliarlo e usare `git checkout -- <file>` come
"ripristino": su codice committato i due coincidono, su lavoro in corso
**distrugge tutto cio che non e in indice**. Costato due volte in una sessione,
e la seconda dopo la prima.

```bash
cp <file> "$SCRATCH/$(basename <file>).bak"   # PRIMA di rompere
# ... rompi, esegui, leggi il rosso ...
cp "$SCRATCH/$(basename <file>).bak" <file>   # ripristino vero
```

Il sintomo e ingannevole: la suite torna rossa su TUTTI i test invece che su
uno, il che si legge come «ho rotto qualcos'altro» mentre il codice e
semplicemente sparito.

## Leggere metriche IN-PROCESS dal pod: serve HTTP, non `kubectl exec python` (2026-09-11)

`data_source_metrics` (e ogni contatore in memoria) vive nel worker uvicorn.
`kubectl exec ... python -` avvia un processo NUOVO che non ha mai chiamato
nulla, quindi riporta ogni fonte `idle` — una risposta plausibile e falsa. E la
stessa trappola della cache fondamentali, ma **peggiore**, perche li esiste
`hydrate_l1_from_db()` e qui non esiste alcun hydrate: i contatori non sono
persistiti.

L'unico modo e interrogare il worker vivo dall'interno del pod. Due ostacoli,
entrambi risolti nella ricetta:

```python
# kubectl exec -i -n finance-alert finance-alert-finance-alert-0 -- python -
import json, urllib.request
from app.core.security import create_session_token
from app.core.config import settings
tok  = f"{settings.session_cookie_name}={create_session_token(settings.admin_username)}"
host = settings.allowed_hosts.split(",")[0].strip()          # <- indispensabile
req  = urllib.request.Request("http://127.0.0.1:8000/api/platform/health",
                              headers={"Cookie": tok, "Host": host})
d = json.load(urllib.request.urlopen(req, timeout=60))
```

- **`curl` non e nell'immagine.** Usa `urllib` dal Python che c'e gia.
- **Senza l'header `Host` la risposta e HTTP 400.** Il middleware di
  `main.py` valida l'host su ogni path tranne `/api/health` e `/metrics`, e
  `127.0.0.1:8000` non e fra gli host ammessi. Il 400 non dice perche.

## ⚠️ Tre strumenti che rispondono in modo pulito e FALSO (2026-09-14)

Tutti e tre pagati in una sessione, e tutti e tre della famiglia che questo
file ripete piu' di ogni altra. Il costo non e' l'errore: e' che la risposta
sembra un risultato.

### 1. `vitest` TRASPILA senza fare typecheck

**642 test verdi in locale, due job rossi in CI, una sola causa**: un file di
test che non compilava. Vitest passa i `.tsx` per esbuild, che cancella i tipi
senza controllarli — quindi un errore di tipo in un TEST e' invisibile a
`npm run test:run`, per sempre.

Il cancello vero e' **`npm run build`** (`tsc -b && vite build`), ed e' quello
che gira in CI in DUE job (`frontend` e `gate UI`, che costruisce il bundle per
Playwright). Un `npx tsc -b` eseguito PRIMA di aggiungere un file non vale:
`tsc -b` e' incrementale e non puo' controllare cio' che ancora non esiste.

⚠️ E l'errore vero era sepolto: lo stesso log portava decine di righe
`ReferenceError: EventSource is not defined` da jsdom, catturate
dall'ErrorBoundary per progetto, con i 642 test verdi due righe sotto. Cercare
li' e' tempo perso — **si grep il log per `TS[0-9]{4}` e `##[error]`**, non per
«error».

**La regola: dopo aver aggiunto o modificato un file di test TSX, `npm run
build`.** Non `tsc -b`, non `test:run`.

### 2. Il repo ha file CRLF e file LF, mescolati

`useSetups.ts`, `SetupsPage.tsx`, `setupGrouping.ts`, `SetupDetailDialog.tsx`
sono CRLF; i loro vicini nella stessa cartella sono LF. Una sostituzione con un
pattern multi-riga che usa `
` **non trova niente** in un file CRLF, e senza
contare le occorrenze il fallimento e' muto.

Qualunque script di modifica multi-riga deve (a) contare le occorrenze e
fermarsi se non sono esattamente quelle attese, e (b) **preservare** i fine riga
del file — normalizzarli produce un diff che riscrive l'intero file e seppellisce
la modifica vera. Git li normalizza al commit da solo, quindi la copia di lavoro
CRLF non e' un problema: lo diventa solo se lo script la riscrive.

### 3. Un test puo' essere FALSO DI TUTTO, non solo vero di niente

Variante nuova di una famiglia gia' registrata tre volte. Un test che asserisce
«questo modulo non tira dentro SQLAlchemy» svuotando `sys.modules` dei soli
`app.*` **fallisce sempre**: dentro pytest `sqlalchemy` e' gia' caricato dal
conftest, e nessuna cancellazione parziale lo toglie.

Una proprieta' sull'IMPORT si misura in un processo nuovo
(`subprocess.run([sys.executable, "-c", ...])`), oppure sulla SORGENTE come fa
`test_periodi_indicatori.py`. Un controllo sull'import sporcato da cio' che gia'
gira non misura l'import. ⚠️ E vale la verifica inversa, che qui ha funzionato:
rimettere la dipendenza su una copia e pretendere il rosso.

## Test commands

- **Backend lint (GATED, and the one that's easy to forget)**:
  `cd backend && ./.venv/Scripts/ruff.exe check app tests`
  CI runs ruff BEFORE pytest and a lint error fails the job without a single
  test running — so a green local pytest tells you nothing about the gate.
  Cost a red CI on 2026-09-02 (`fc3ee7c`): an `import pytest` inserted at line
  1, ahead of `import pandas`. Note the scope is **`app tests`**, not `.` —
  `backend/scripts/` is deliberately outside the gate and has a pre-existing
  I001 that is NOT yours to fix; `ruff check .` will report it and mislead you.
- **Backend**: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q`
  (1756+ tests, runs in ~35s)
- **Frontend tests**: `cd frontend && npm run test:run` (152 tests, ~5s)
- **Frontend hook gate**: `cd frontend && npm run lint:hooks` (see below — clean
  output and exit 0 is the only acceptable result)
- **Frontend build/typecheck**: `cd frontend && npm run build`
  (also: `npx tsc -b` for type-only check)
- **Single test file**: append the file path to the pytest command

⚠️ `npm run lint` (the FULL config) reports **ZERO** findings, misurato
2026-09-13. Era 60 a settembre e 31 stamattina. **Un rosso li' adesso e' una
regressione, non l'arretrato** — la frase «a red result there is expected», che
questo file ha portato per mesi, non vale piu'.

`lint:hooks` gatta SETTE regole: rules-of-hooks, static-components,
set-state-in-effect, exhaustive-deps, refs, purity, immutability.

**set-state-in-effect (14) ed exhaustive-deps (9) sono a ZERO e sono entrate
nel gate** il 2026-09-13. La barra e' quella che `eslint.hooks.config.js` si e'
sempre dato: misurata a zero PRIMA, e una violazione deve rompere qualcosa che
un utente sente. Entrambe l'hanno superata con difetti veri trovati durante la
pulizia — fra gli altri, l'evidenziazione della ricerca che puntava a una riga
di una lista gia' accorciata (Invio apriva il titolo sbagliato), lo spessore
applicato a una sola delle due linee del pannello MACD, e l'orologio dell'asse
che non si accendeva passando a un intervallo intraday.

**only-export-components (25) e' a zero e NON e' gatta, deliberatamente.**
Rompe il Fast Refresh, che costa a chi sviluppa e non a chi usa: la seconda
meta' della barra di `eslint.hooks.config.js` chiede che una violazione rompa
qualcosa che un utente SENTE. Stessa ragione per cui `no-unused-vars` sta
fuori. Le 25 sono state sciolte spostando funzioni e costanti in `lib/` — il
precedente e' `NAV` -> `lib/nav.ts` — perche' un dato non e' un componente.

⚠️ E NON e' stato gatto `npm run lint` per intero, benche' oggi sia a zero: un
gate su una config che segue le `recommended` di un plugin diventa rosso quando
il plugin aggiunge una regola, cioe' su una decisione di qualcun altro e su
codice che nessuno ha toccato. Le regole si nominano una per una.

⚠️ **Nessuna delle due si chiude nel modo ovvio**, ed e' la parte che costa
tempo se non la si sa:

- `exhaustive-deps` NON si chiude aggiungendo l'oggetto mancante. Sui grafici
  avrebbe distrutto e ricostruito l'intero grafico a ogni cambio di colore,
  perdendo zoom e posizione. Si chiude estraendo la FETTA fuori dall'effetto,
  cosi' che il corpo legga esattamente cio' che dichiara.
- `set-state-in-effect` si chiude aggiornando lo stato IN RENDER (il pattern
  che React documenta per «aggiustare lo stato quando cambia una prop»), ma
  solo se il valore e' PURO: il primo tentativo su `DataSourcesCard` leggeva
  `Date.now()` in render e `react-hooks/purity` l'ha respinto. Li' la risposta
  era rimontare il componente con una `key`.

⚠️ E la trappola che ha prodotto l'unico rosso della pulizia, trovata da un
test e non a ragionamento: **un effect gira anche al PRIMO montaggio, un
aggiornamento in render guardato da `prec !== corrente` no** — se si
inizializza `prec` col valore corrente, il primo confronto e' gia' uguale e il
comportamento al montaggio sparisce. Dove il montaggio conta la guardia parte
da una sentinella (`null`/`undefined`): vedi `LogStream` e `PriceAlertDialog`.

⚠️ **The number grew from 47 and the growth was partly MINE**, which is the
thing to check first when this count moves. `Layout.tsx` gained an
`only-export-components` the moment FA-044 exported `NAV` beside the component;
it is fixed by moving the nav data to `lib/nav.ts`, which is better design
anyway — the data is not a component, and the navigation test now reads it
without mounting the app. Before treating this count as a backlog to burn down,
diff it against what the current session added.

The count read 60 on 2026-09-09 (with exhaustive-deps 15, purity 5,
immutability 1). The last two categories are now at zero and were not cleaned
deliberately — they fell out of ordinary work. **Re-count before quoting this
number**; a stale figure here is exactly the failure mode the `_RANGE_PERIODS`
note below describes, where a believable number corroborates a wrong belief.

What was cleaned on 2026-09-09, and why the rest was not: nine
`no-unused-vars` findings were placeholders this codebase already marks with a
leading underscore, so the rule was CONFIGURED to read that convention rather
than the code renamed to satisfy an unconfigured rule. Two `eslint-disable`
directives suppressed rules that are not enabled, so they documented a
constraint that did not exist. One ternary-as-statement became an if/else,
because in that shape a dropped `()` evaluates to a method reference and
silently does nothing. That category is now at zero and is still NOT gated —
`eslint.hooks.config.js` requires a violation to break something a user can
feel, and an unused variable does not.

---

## ⚠️ White screen = a component threw during render. READ THE CONSOLE FIRST.

**Cost so far: two wrong fixes and two reverts of innocent code (2026-08-04).**

React unmounts the ENTIRE tree when a render throws with no error boundary
above it. So a bug in a decorative corner widget presents as "the whole app is
blank" — and whatever was on screen just before the blank looks like the
culprit while being unrelated. The actual cause is always named, precisely, in
the browser console.

**The rule: on a blank page, read the console before forming any hypothesis.**
The error gives the component, the hook index, and the exact transition. Both
wrong fixes were plausible readings of the SYMPTOM; one console read gave the
answer in seconds.

The instance that cost the time: `useIsPhone()` in `RunProgressToast` sat next
to the JSX that used it, which put it after three `return null`s. Hidden render
= 7 hooks, visible render = 8, so React threw the moment a scan started. The
toast IS the progress bar, so "the bar appears then everything disappears"
read as a bug in the bar. Fixed in `76bd68a`.

### Now guarded — three layers

1. **`npm run lint:hooks`** (`frontend/eslint.hooks.config.js`) — ONE rule,
   `react-hooks/rules-of-hooks`, gated in CI. The plugin was installed and the
   rule enabled the whole time; it simply never ran where it could stop a
   merge. Verified empirically by re-introducing the bug on a copy.
2. **`ErrorBoundary` is wired** in `Layout.tsx` — around the route outlet
   (keyed by `location.pathname`, because boundaries never reset themselves)
   and around both global toasts with `fallback={null}`. A crash now costs one
   subtree. It existed as dead code before, imported nowhere.
3. **Frontend tests run in CI.** They did not before — the job was `npm ci` +
   `npm run build` only, so 85 tests could go red and merge anyway.

### Two ways a regression test passes while the bug is present (2026-09-08)

Both cost a round-trip in one session, and both LOOK like a passing test.

**`toEqual` on DOM nodes compares STRUCTURE, not identity.** The LogStream
test asserts that a row survives an append — i.e. that its DOM element is the
SAME OBJECT afterwards. Written with `expect(after).toEqual(before)` it passed
cleanly with the bug reintroduced, because a freshly remounted row is
structurally identical to the one it replaced: same tag, same classes, same
text. `toBe` is the assertion; `toEqual` is the trap, and it is the one that
reads more naturally.

**A test can be true of nothing.** `StockFiltersCard`'s a11y test asserts every
numeric filter has an accessible name — but three of the four filter areas are
CLOSED by default, so a bare mount renders almost none of them and the
assertion holds vacuously. It opens every area first AND asserts the count from
below (`toBeGreaterThanOrEqual(9)`), so a change that stops rendering them goes
red instead of quiet. Any "every X has property P" test needs a floor on the
number of X.

The rule already in this file — confirm the test fails with the fix reverted —
is what caught both. It is two commands and it is not optional.

### ⚠️ Node 25's `localStorage` shadows jsdom's, and it is BROKEN (2026-09-10)

The "`--localstorage-file` was provided without a valid path" warning printed
on every vitest run for a while. It was not noise.

Node 25 ships a global `localStorage`, and under vitest it REPLACES jsdom's:
`globalThis.localStorage === window.localStorage` and neither has a callable
`setItem`, `getItem` or `clear`. Reaching for `window.localStorage` instead of
the bare global does not help — measured, they are the same broken object.

**Why that is worse than a missing feature.** Every storage-backed module here
wraps its access in try/catch, correctly, because a private window or a
browser blocking site data really can throw. So the broken object is swallowed
silently, the code takes its "storage unavailable" branch, and a test asserting
that a preference PERSISTS passes without anything ever having been stored.
That is the "a test can be true of nothing" failure recorded twice above, in a
third disguise — and it applies to every localStorage feature in the app:
saved views, column visibility, the sidebar state, the chart timeframe.

`src/test/setup.ts` now installs an in-memory `Storage` on both `globalThis`
and `window`, cleared in the same `afterEach` as the DOM. Storage is global
and outlives a test file otherwise, so a preference written by one test would
be read as a "remembered" value by the next.

Nothing broke when storage started actually working, so no existing test was
depending on the broken behaviour — but none of them could see a regression in
persistence either. Assertions about what SURVIVES a reload are only
meaningful after this setup.

### `React.memo` does nothing when the key is unstable

Worth knowing before reaching for memo on any list. LogStream keyed rows on
`${r.ts}-${i}` where `i` indexes a list that is REVERSED for display, so one
arriving record shifted every index, every key changed, and React was not
re-rendering 500 rows — it was unmounting and rebuilding them. Memo cannot help
there: a changed key is a different element, not a re-render.

Order matters. Stable identity first, then memo. And identity often cannot be
fixed at the render site — `LogRecord` has no id, so the counter had to go in
`usePlatformHealthStream`, which owns the buffer.

The related trap on the OTHER side: memo is pure overhead when a prop is
rebuilt every render. `StockBrowserTable`'s rows key on `s.id` (stable), but
the row calls `rowChange(item)`, which closes over a map that is replaced on
every quote tick — so memo would compare a fresh function against the old one
and skip nothing. Making it pay means giving each row SCALAR props, i.e.
moving the per-row lookup up into the parent, in both layouts.

**CLOSED on 2026-09-08, not deferred. Do not re-open it as a perf task.**
Stating the objective plainly is what settled it: only the rows whose price
moved would re-render instead of all 200, on a cycle that runs every 15 s
(`FAST_MS` in `useLiveQuote.ts`). That is roughly two dropped frames, four
times a minute, and only when it coincides with the user scrolling or clicking.

⚠️ **The "~32 ms" this note used to quote was INFERRED, not measured.** The real
measurement is 63.0 ms for one changed quote against 66.5 ms for all 200 — taken
BEFORE `31f2002` removed the hidden second layout. Halving it assumes removing
half the DOM halves reconciliation, which is plausible and is not a fact. If
anyone re-opens this, measure first.

And memo does not touch the MOUNT cost (297 ms before `31f2002`, about half
that now) — it only affects re-renders. "The screener is slow to open" and "the
screener stutters" look identical on screen and are different problems; this
work addresses only the second.

The one honest reason to do it anyway is legibility: the row reads ~10 values
out of closures, and explicit props would make it testable in isolation. That
is a maintainability argument, and it should be made as one — not sold as
performance.

### The gated lint config now carries TWO rules

`eslint.hooks.config.js` gained `react-hooks/static-components` on 2026-09-08.
Its bar was the file's own: the rule had to be at ZERO first, so a red result
still always means something is broken. It is not stylistic — a component
declared inside another component's body is a new TYPE every render, React
reconciles by type, and the subtree is destroyed and rebuilt. Both offenders
were toggle groups, so the remount was caused by the very click it punished,
and keyboard focus went to `<body>`.

One documented false positive: `const Icon = getSectorIcon(x)` is a LOOKUP into
a module-level map, so the reference is stable, but the rule sees a capitalized
local const used as JSX. There is exactly one such disable, in
`SectorDetailPage`. Do not add more without checking it really is a lookup.

### Writing tests that can actually see this class of bug

A test that renders a component in ONE state cannot detect a hook-order fault.
Render it across the TRANSITION, both directions — see
`RunProgressToast.test.tsx`. React reports the violation via `console.error`
rather than a throw the test can catch, so assert on a spy.

**Always confirm a regression test fails with the fix reverted.** It is cheap:
patch the fix out on a copy, run, restore.

### Local repro of a logged-in browser session (no password anywhere)

Guessing from the outside is what cost the time. This gets a real browser onto
the real app in about a minute:

```bash
# 1. backend (background)
cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. mint a session cookie with the app's OWN signer and write it to a
#    throwaway page — the token never passes through the chat or a shell echo
cd backend && ./.venv/Scripts/python.exe -c "
import io
from app.core.security import create_session_token
from app.core.config import settings
tok = create_session_token(settings.admin_username)
io.open('../frontend/public/__dev-session.html','w',encoding='utf-8').write(
  \"<script>document.cookie='%s=%s; path=/; SameSite=Lax'</script>\" % (settings.session_cookie_name, tok))"

# 3. vite (proxies /api -> :8000), then visit /__dev-session.html, then /
cd frontend && npm run dev

# 4. ALWAYS delete it afterwards — it contains a valid session token
rm frontend/public/__dev-session.html
```

`frontend/public/` is served at the site root and IS a committed directory —
the file must never be committed. Verify with
`git log --all -- frontend/public/__dev-session.html` (must be empty).

---

## Stock detail card layout (the one that always tries to break)

The 3-card row (Fundamentals · Valuation · News) uses:
- Grid: `lg:grid-cols-3 gap-3` (default `items-stretch`, NOT `items-start`)
- Each card: `h-full overflow-hidden flex flex-col`
- FundamentalsCard sets the row's natural height (no internal scroll on its
  tables — per user constraint)
- MicroDataCard + NewsCard scroll internally via `flex-1 min-h-0 overflow-y-auto`
- **NewsCard is wrapped in `<div className="relative h-full">` with the Card
  positioned `absolute inset-0`** — so its 25-item content doesn't inflate
  the row. Don't undo this.

---

## Indicator periods are FIXED, not adaptive (reversed — read this)

**This section used to say the opposite, and the code that made it look true
was dead.** Corrected 2026-09-02.

Periods do NOT adapt to the range. They are fixed across every timeframe:

| EMA fast/mid/slow | RSI | BB | MACD |
|---|---|---|---|
| 20/50/200 | 14 | 20 (k=2.0) | 12/26/9 |

Single source of truth: `FIXED_*` in **`app/indicators/periods.py`** (era in
`services/timeframe_service.py` fino al 2026-09-14, che ora le ri-esporta). Il
modulo porta la ragione accanto alle costanti — *"Don't adapt these per
timeframe"* — perche' **l'utente l'ha chiesto esplicitamente**: una definizione
di indicatore ovunque, cosi' i valori cambiano con la DURATA DELLA BARRA e non
con una tabella. RSI(14) su barre da 30m copre 7 ore; su barre giornaliere, 14
sedute. (Maggio 2026 ha portato le linee di tendenza da SMA a EMA tenendo
20/50/200.)

### ⚠️ La fonte unica c'era da mesi e NESSUNO la importava (2026-09-14)

Un censimento ha trovato **quattordici** chiamate col periodo scritto a mano su
cinque file — EMA 20/50/200 e RSI 14 riscritti in `market_detail_service`,
`market_stats_service`, `signals/context.py`, `technical_score_service`,
`signal_outcome_service` (`_REGIME_EMA = 200`) e `entry_ic_report`.

**E la causa non era disattenzione: era la COLLOCAZIONE.** Le costanti stavano
dentro `timeframe_service`, che importa SQLAlchemy, i modelli e loguru.
`app/signals/context.py` e' calcolo puro (numpy, pandas, `app.indicators`): per
leggere il numero 200 avrebbe dovuto tirarsi dentro mezzo stack. La costante
NON ERA IMPORTABILE da chi ne aveva bisogno, quindi nessuno la importava,
quindi ognuno la riscriveva.

⚠️ **Una fonte unica che nessuno puo' consumare e' una fonte unica solo nel
commento**, ed e' la stessa forma del `_RANGE_PERIODS` morto: qualcosa di
inerte che corrobora una nota sbagliata. Quando si dichiara un proprietario
unico, la domanda da farsi non e' «dove sta bene» ma **«chi deve poterlo
importare, e cosa si porta dietro se lo fa»**.

Ora vivono in un modulo FOGLIA senza una sola dipendenza.
`tests/test_periodi_indicatori.py` tiene chiuso il difetto con quattro
asserzioni, e due meritano una nota:

- ⚠️ Il censimento guarda la SORGENTE, non il comportamento, e non e' pigrizia:
  `from ... import FIXED_EMA_SLOW` lega il VALORE al momento dell'import, quindi
  sostituire la costante a runtime non cambia niente in chi l'ha gia' importata
  e **nessun test di comportamento puo' distinguere `ema(close, FIXED_EMA_SLOW)`
  da `ema(close, 200)`**. Stessa forma del censimento delle classi mobile.
- Un test pretende che `periods.py` resti senza dipendenze. E' la proprieta' da
  cui dipende tutto il resto: se qualcuno gli aggiunge un import di
  `app.services`, la costante torna non-importabile e il difetto si riapre da
  solo **col censimento ancora verde**, perche' i consumatori attuali
  continuerebbero a funzionare.

⚠️ Due cose deliberatamente NON convertite. I periodi ADATTIVI di
`technical_score._trend` (`ema(close, min(50, max(10, n // 4)))`) sono un'altra
cosa e devono restare; e il `20` in `context.py` (`max(20, len // 2)`) e' un
PAVIMENTO sul ripiego a storia corta, non la EMA veloce — due numeri uguali che
significano cose diverse restano separati.

The bundle keys in the API response (`sma20`/`sma50`/`sma200`, `rsi14`) are
still SLOT NAMES rather than literal periods, and `indicators.periods` is still
the field to read in the UI — that part of the old advice survives. What is
gone is the reason: the periods it reports are now constant.

### Why this note exists at all

The stale version carried a full table of per-range periods (1m → 5/10/20,
3m → 10/20/50, …) and the instruction *"don't hard-code SMA 200 / RSI(14) in
new code"*. Anyone checking would have found `_RANGE_PERIODS` in
`stock_detail_service.py` holding exactly that table, and believed it.

It was dead. `_compute_indicator_series`, its only consumer, had **zero
callers** in `app/` or `tests/` — and it was the sole reason that file imported
pandas, `bollinger`, `ema`, `macd` and `rsi` at all. Both are now deleted (64
lines plus 5 imports), with a note in their place pointing at
`timeframe_service`.

**The general lesson, since this file is read before anything else:** dead code
does not just sit there. It corroborates stale documentation, which is how a
wrong instruction survives a spot-check. When a note here disagrees with the
code, suspect BOTH — and delete the loser rather than leaving it to mislead the
next reader.

## Alert dual-timestamp model

Every alert has two dates (since commit `e22bec5`):
- `signal_date` (Date): bar where the rule's condition matched
- `triggered_at` (DateTime): wall-clock when the row was created

The two diverge meaningfully on backfill / weekend / skipped scans. UI
distinguishes them via `lib/alertDates.ts:isDelayedDetection` (≥ 4 calendar
days delta → orange clock chip + "in ritardo" label; the threshold was
raised from 1 in 2026-07 because weekend + normal scan cadence made ~93%
of alerts wear the chip — alarm fatigue). The exact +Ng delta always stays
in the tooltip.

Legacy alerts predate the column → `signal_date = null`. UI falls back to
`triggered_at` and shows "—" or "n/d · legacy" for the signal slot.

---

## Read/unread alert system was removed

`Alert.read_at` still exists in the DB and API for back-compat, but the UI
doesn't surface it anymore (no badges, no filters, no bulk actions). Don't
re-add it without the user explicitly asking. The `archived_at` axis is
still active.

---

## Typed upstream error hierarchy (`app/core/errors.py`)

Upstream-fetch failures are tagged with one of three subclasses of
`UpstreamError(message, *, source, op)`:

- `UpstreamTimeout` — network timeout (retryable)
- `RateLimitError` — 429 / "too many requests" (retryable with backoff)
- `UpstreamUnavailable` — 5xx / malformed body (NOT retryable — re-fetch would
  just hit the same problem)

Routers catch the base `UpstreamError` for warning-level structured logging
(`logger.warning(f"upstream {e.source}.{e.op} failed: {e}")`), then fall back to
`except Exception` only as a defensive last-resort.

### ⚠️ Only FIVE services actually raise these — check before writing a handler

`stock_fundamentals_service` (via `_normalize_yf_error`) and the four news
services (`stock_news_service`, `finnhub_news_service`, `marketaux_news_service`,
`yahoo_rss_news_service`). Nothing else does.

**The two biggest upstream fetches in the app are NOT among them**, and they
report failures through a different channel on purpose:

| Service | How an upstream failure surfaces |
|---|---|
| `ohlcv_service.fetch_and_upsert` | caught per stock inside the loop; `logger.exception` + `result.failed_tickers` / `stocks_failed` on the returned result |
| `live_quote_service.get_quote` | `q.error` on the RETURNED quote object, plus `market_state="STALE"` for an L2 restore |

A per-item result is richer than an exception here — one bad ticker must not
abort a 999-stock batch — so this is a design choice, not a gap to close.

Two `except UpstreamError` handlers had been written around exactly these two
calls and could never run (removed 2026-09-02). The `ohlcv_service` one was
dead twice over: the service raises no typed error AND catches `Exception` per
stock, so nothing escapes to the router at all. Both sat directly above an
identical `except Exception`, so deleting them changed no behaviour.

The cost of an unreachable handler is not runtime, it is belief: it reads as
"upstream failures on this path are logged with source/op", so anyone grepping
the logs for `[scan] upstream ...` during a yfinance outage finds nothing and
goes looking for the bug somewhere else. **Before adding a handler, confirm the
callee is on the list above.**

When adding a new external fetch:
1. Wrap raw network calls so they raise the appropriate typed exception (see
   `_normalize_yf_error` in `stock_fundamentals_service.py` for the pattern).
2. Apply `@with_backoff(retries=N, base_delay=..., max_delay=..., on=(UpstreamTimeout, RateLimitError))`
   from `app/services/_retry.py` to get exponential backoff with jitter.
3. Catch `UpstreamError` in any consumer router and either return a graceful
   fallback (e.g. cached EOD, secondary provider) or surface a 503 — never let
   it 500.

The retry decorator only retries the typed errors listed in `on=`. Passing
`UpstreamUnavailable` there would waste cycles on non-recoverable failures.

---

## Two-tier cache: in-memory L1 + persistent L2 (`fetch_cache` table)

`stock_fundamentals_service` and `stock_news_service` use a two-layer cache:

- **L1**: in-process dict (`_CACHE`) — microsecond hits.
- **L2**: `fetch_cache` table (one row per `(ticker, kind)`, JSON payload) —
  survives backend restarts. Read by service on L1 miss; written on every
  successful upstream fetch. Hydrated into L1 at app startup (`lifespan`).

The flow on every `get_fundamentals(ticker)` / `get_news(ticker)`:
```
L1 hit + fresh        → return immediately (microseconds)
L1 miss / stale → L2 hit + fresh → hydrate L1 + return (single DB query)
both miss / stale     → upstream fetch → UPSERT L2 + L1 → return
```

**Don't bypass L2.** If you write a new service that reads `_CACHE` directly
(e.g. the calendar aggregator does this — see
`backend/app/services/calendar_service.py`), document it explicitly and be
aware that on a fresh process boot before any consumer has triggered
hydration, `_CACHE` may still be empty for a few seconds — call
`hydrate_l1_from_db()` if you need an immediate-read guarantee.

**`clear_cache()` clears BOTH layers** (it used to clear only L1; that was
test-isolation hostile). Calling it from production code wipes the persisted
rows too. If you really want to discard only the in-memory cache (e.g. to
simulate a process restart in a test), poke `_CACHE.clear()` directly.

**Don't persist error rows.** Both services intentionally skip the L2 write
when the upstream fetch returned an error — a transient yfinance failure
shouldn't poison the cache for 24h across restarts.

`live_quote_service` **IS** now backed by L2 (`live_quote_l2`, `kind="live_quote"`)
— this REVERSES the earlier rule that said it must not be. The old rationale
("TTL is 10s, a 30s-old quote is worse than re-fetching") assumed re-fetching
is fast. On 2026-07-23 we measured quote requests taking **43-50 seconds**
under Yahoo rate-limiting; they saturated the sync threadpool and got the pod
liveness-killed. A 30s-old price beats a 50s wait, and beats a blank page
after a restart. Rules of the layer:

- It is a **floor, never a source of truth** — read only when the live path
  can't answer NOW (breaker open, deadline blown, cold cache after restart).
- Restored quotes are flagged `market_state="STALE"`. **Never** let a restored
  price present itself as live.
- Writes are **batched**: the sweep marks tickers dirty and `flush_l2()` writes
  them in ONE transaction at the end of its pass. Don't add per-quote commits.
- Errors are never persisted (same rule as fundamentals/news).

`get_quotes_batch` also takes `deadline_seconds` (default 6s): user-facing
callers must stay bounded, background callers (the sweep) pass `None`.

---

## Scoring architecture: 3 orthogonal lenses (2026-05 redesign)

Three INDEPENDENT lenses — keep them decoupled (a mid-2026 cleanup removed the
cross-lens leakage; don't re-introduce it):

1. **Qualità** — `score_service.py` composite, now **PURE fundamental** (5
   pillars: profitability/sustainability/growth/value/sentiment, `PILLAR_WEIGHTS`
   sum 1.0). The **Momentum pillar was REMOVED** (price-action belongs to the
   Tecnico lens). `StockScore.momentum` column kept nullable but always `None`;
   `_momentum()` retained-but-unused. Recomputed by `score_service.recompute_all`
   (called inside `run_tracked_scan`, NOT by `scan_universe`).
2. **Tecnico** — `technical_score_service.py`: continuous price-action posture.
   OWNS all momentum/price-action. Do NOT let signals nudge its composite (the
   old ±5pp nudge was removed; the `signals` field is informational only).
3. **Segnali** — the 17 detectors. Each signal carries **Forza** + **Probabilità**
   — NOT `confidence` (that single score was split; the `confidence` field is a
   TRANSITIONAL alias of `strength`, being retired).

### Signal scoring (`app/signals/detectors/base.py`)
- **Forza** = `score_v2(factors, weights, strength_keys)`: weighted mean capped by
  a soft-min over the STRENGTH factors → `min(arith, min(strengths)+0.12, 0.99)`.
  Kills "mediocrity laundering". EXCLUDE context factors (trend_alignment /
  trend_maturity / gates) from `strength_keys`. Ceiling **0.99** — reachable only
  by exceptional signals; 100 never.
- Per-factor curves: `concave(x, anchors)` (bounded) / `log_saturate(x, ceil)`
  (unbounded ratios, e.g. volume). ⚠️ anchors are per-detector and must be in the
  **UNITS OF THE VALUE PASSED TO THE CURVE** — read the factor formula (e.g. a
  `clamp01((ADX-25)/75)` factor takes 0..1, NOT raw ADX).

  ⚠️⚠️ **This rule was already written here and `chart_pattern` still violated
  it for the whole life of the detector** (found and fixed 2026-09-02,
  `fc3ee7c`). Read it as a checklist item, not a maxim, because the failure is
  SILENT and self-congratulatory:

  - Its anchors were `(0.40, 0.65, 0.80, 0.92)` while the factor — a chart
    figure's height as a fraction of price — actually runs p50=0.094 /
    p95=0.234 / max=0.564 over 1,041 measured patterns. The median pattern
    scored Forza 10.6, and exactly ONE pattern in 1,041 could clear the 60
    emission gate.
  - Three of the seven pattern families hard-coded their magnitude (0.6 / 0.6 /
    0.55) instead of measuring it. Since `pattern_amplitude` is that detector's
    ONLY strength factor, a constant magnitude is a constant Forza.
  - Net effect: **every alert the detector ever produced was a triangle**, at
    two Forza values (63.0 and 69.0 — the two constants), while the four
    families that measured themselves honestly were silent. It looked healthy:
    95 alerts in the warehouse.

  **Two checks that would have caught it, and are cheap:**
  1. For any detector, ask how many DISTINCT Forza values it has produced.
     Two, on 95 alerts, is not a score — it is a constant wearing a number.
     (`SELECT COUNT(DISTINCT ROUND((snapshot->>'strength')::numeric,1))
     FROM alerts GROUP BY signal_name`.)
  2. Before trusting anchors, measure the factor's real distribution over
     stored OHLCV and check the anchors bracket it. If a45 sits above the
     p95 of the real data, the factor is dead and the detector is running on
     whatever else is in the weighted mean — or, if it is the only factor, on
     nothing at all.

  A test that only asserts "the pattern is EMITTED" cannot see any of this;
  that is exactly what the existing tests did. Assert on the NUMBER.
- **Probabilità** = `calibration_map.get_calibration().probability(name, factors)`
  → per-detector base rate (+ bounded factor adjustments) from
  `app/data/signal_calibration.json`. Empirical hit-rate "di accadimento" (~45-55:
  single-name technicals are near coin-flips). Degrades to neutral 50 if the
  artifact is missing.
- Snapshot stores `strength` + `probability`; emission gate is on Forza
  (`settings.signal_min_confidence` = the min-Forza bar).

### Calibration data — read-only studies, regenerate when wanted
- `python -m app.scripts.signal_factor_outcomes` — per-FACTOR forward-outcome study.
- `python -m app.scripts.signal_detector_outcomes --emit-map` — per-DETECTOR base
  rates → writes `app/data/signal_calibration.json`. Both no-look-ahead over 10y
  `ohlcv_daily`; the confidence/Forza was validated against these (current
  `confidence` shown ~flat vs realised outcome — the reason for the split).
- Design spec: `docs/superpowers/specs/2026-05-28-signal-strength-probability-split-design.md`.

### ⚠️ The market-neutral benchmark is the universe MEDIAN, everywhere (2026-09-02)

Invariant #3 in the conditional-screen list below is not local to that study.
Every "market-neutral hit" in this repo is *signal beat the universe benchmark
that day*, sign-flipped for bear tone — which only means something if a
zero-skill signal scores 50%. Measured here, 400 stocks / ~1M stock-days:

          h=5      h=21     h=63
    mean  49.29%   48.37%   47.12%
    med   49.94%   49.94%   49.94%

Cross-sectional forward returns are right-skewed, so the mean sits above the
typical stock and charges every bull-tone detector 1.6pp at h=21 / 2.9pp at
h=63, crediting every bear-tone one the same. The live warehouse
(`signal_outcome_service._universe_fwd_medians`) was already on the median;
**four offline studies were still on the mean until 2026-09-02** —
`signal_detector_outcomes`, `multihorizon_outcomes`, `signal_factor_outcomes`,
`backfill_replay_outcomes`. All four now call `_universe_median_fwd`
(`signal_factor_outcomes`), which has the identical return shape.
`regime_conditioned_outcomes` had implemented the median and documented why,
then defaulted to `--benchmark mean`; the default is flipped.

**REGENERATED 2026-09-02** — `signal_calibration.json` is now median-based
(`2026-09-02-977u-median`, 977 stocks, 249,345 signals). `base_rate` is
byte-identical for all 14 detectors, confirming Probabilità never depended on
the benchmark. Three of fourteen honesty tags changed, in both directions:

    high52_momentum   bull   45.7 -> 50.9   negative -> coinflip
    trend_pullback    bull   49.5 -> 50.2   negative -> coinflip
    structure_break   bear   50.2 -> 47.7   coinflip -> negative

The two big movers are the two most one-sided detectors by tone, each moving
the way a right-skewed benchmark predicts. The external check: an independent
study already on the median (`conditional_screen_shorthz`) had high52_momentum
at 50.5; the new value is 50.9, the old was 45.7.

Artifacts now carry `"benchmark": "universe_median"`. **One with no
`benchmark` key predates this and was built on the mean.** `--map-version`
used to default to `"1"` and silently overwrote the informative July string;
it now stamps `<date>-<N>u-median` on its own.

⚠️ **Budget 7-8 HOURS for a full re-run** (`--sample 999 --emit-map` took
7h27m wall-clock, single-core-bound). Scaling linearly from a small `--sample`
underestimates by ~4x — measured, after a 12-stock run predicted 1h50.

`_universe_mean_fwd` still exists ONLY because `confirmation_outcomes` and
`fit_signal_calibration` import it for its `_date_to_idx` calendar map and
compute no market-neutral label at all. In those two the variable is named
`_cal`, not `umean`, so nobody reaches for its values. **Never use its values
as a benchmark.**

Guarded by `tests/test_universe_benchmark_symmetry.py`, on a deliberately
right-skewed fixture, including a test asserting the MEAN is *not* symmetric on
it — so if the fixture ever stops being skewed, the symmetry test stops
silently passing for the wrong reason.

Two things this does NOT change. `base_rate` (→ Probabilità) is
`close_to_close_abs_hit` — ABSOLUTE, never touches the benchmark. And the six
null results stand: a biased benchmark manufactures apparent effects rather
than hiding them, so nulls measured against a harsher baseline stay null. What
moves are the POINT ESTIMATES on display — `mkt_neutral_hit`,
`mkt_neutral_edge_pct`, and the `coinflip`/`negative`/`edge` quality_tag.

**A search that misses this class of bug:** grepping `umean[` finds `umean[h]`
and silently misses `umean.get(h)`. That is exactly how `backfill_replay_outcomes`
was first cleared as "calendar-map only" and had to be corrected a commit later.
Grep the bare identifier and read every hit.

### Chain enrichment + `confirmation_count` is DISPLAY-ONLY by design (2026-06)
`app/signals/chain_enrichment.py` appends co-temporal, same-tone confirmation
events (EMA reject, MACD cross, candle rejection, RSI rollover, volume,
lower-high/higher-low) to a technical detector's Catena, tagged
`kind="confirmation"`, and stamps a bounded `factors["confirmation_count"]`.
Wired in `runner.detect_signals`; runs for the 14 technical detectors in
`ENRICHABLE`; each detector excludes its OWN trigger event (`_OWN_EVENT_TYPES`)
so it never re-counts the event it fired on.

**`confirmation_count` does NOT move Forza/Probabilità — and that's validated,
not an oversight.** The `confirmation_outcomes` study (14.5k signals,
no-look-ahead) showed forward hit-rate is ~flat across 0/1/2/3 confirmations
(49.9/49.9/49.1%) and *worse* for the divergence family. So: it stays out of
every detector's `strength_keys`, `factor_adjustments` has no
`confirmation_count` entry, and there is no per-alert confluence Forza boost.
**Do NOT re-add a confirmation/confluence → score bonus without a NEW study
showing edge** (mirrors the "read/unread removed, don't re-add" rule). Findings:
`docs/superpowers/specs/2026-06-09-confirmation-outcome-study-findings.md`.
**Re-confirmed independently 2026-08-03**: the conditional screen tested
`concurrence` (count of DISTINCT detectors firing on one name on one day) as a
condition and found it null at h=1/2/3/5 — a different metric, horizon set and
statistical treatment than the 2026-06 study, same answer. Two independent
nulls; treat this as settled.

Confluence aggregation (`confluence_service`) IS de-correlated by detector
FAMILY (`_FAMILY` / `_effective_n`): N correlated same-family signals count
~1.3, not N. `ConfluenceCluster.effective_n` is the de-correlated count (≤
`n_signals`). This only ever *lowers* inflated confluence; it makes no
predictive claim. The one cross-signal feature with a prior backtest edge is
`multi_horizon` (~+0.8%/30d, bull only) — the only thing that may justify a
future target tweak. (It used to read "target/conviction tweak"; there is no
conviction any more — see the trade-playbook note below.)

### Engine Quality v1 (2026-06): outcome warehouse + honest surfacing
Spec: `docs/superpowers/specs/2026-06-09-engine-quality-v1-design.md`. All
SURFACING + SUBSTRATE — none of it changes the composite/Probabilità/targets.

- **`signal_outcomes` warehouse** (`app/models/signal_outcome.py`,
  `signal_outcome_service.mature_outcomes`): append-only labeled forward
  outcomes (abs_hit + market-neutral + causal regime), the SINGLE forward-hit
  source of truth. Matured at scan end (best-effort) once a horizon elapses;
  idempotent on `alert_id`. One-off (re)build: stop uvicorn, run
  `app.scripts.backfill_signal_outcomes` (prints a parity report). This is the
  substrate every later validation (walk-forward CV, regime, ranking, score IC,
  recalibration) should query instead of re-replaying OHLCV.
- **Beta-stripped skill + honesty tags** (`calibration_map.skill/edge_pct/
  quality_tag`, `GET /api/alerts/signal-calibration`): the UI shows market-
  neutral `skill` + a `coinflip`/`negative`/`edge` tag (keyed on SKILL not
  base_rate — a high base that's pure beta reads `coinflip`). Probabilità still
  uses base_rate; skill is display/ranking-only.
- **Qualità score percentile + `quality_extras`** (`scores._composite_
  percentiles`, `score_service.quality_extras`): sector/universe percentile +
  governance/analyst signals are INFORMATIONAL (read-time, cache-only). Do NOT
  weight any of these into the composite without the score-IC backtest
  (roadmap #9) over persisted score_history + point-in-time fundamentals.

### ⚠️ The warehouse was measuring 19 of its 4,880 rows (2026-09-05)

`signal_outcomes` is the single source of truth for whether the engine works.
Three consumers joined `alerts` to exclude archived ones — the cube
(`detector_performance_service`), the equity curve, and the drift monitor
(`signal_drift_service`) — on the reading that archival means "user flagged it
irrelevant". Measured against production:

    esiti maturati nel magazzino          4.880
    visibili dopo il filtro archiviati        19

**Archival tracks AGE, not quality.** By month of signal: 99% of May's alerts
archived, 68% June, 61% July, 36% August, 0% September — a clean monotone
gradient, because archiving is an inbox action and old alerts have had time to
be filed. Maturation tracks age too (an outcome is written only once its
forward window has elapsed). So the two conditions select opposite ends of one
axis and their intersection is nearly empty.

The drift monitor exists to say WHEN to retune a detector on evidence. It was
answering "no drift" when the truth was "I can see nineteen rows". Nothing
errored, every panel rendered.

**The general rule: never filter an efficacy measurement on a field the USER
writes.** A number that moves when someone clears their inbox is not measuring
the engine. If a filter must exist, check what fraction of the sample it
removes before trusting anything downstream of it.

### `n` is not the sample size — overlapping windows are one observation

Every consumer treated one warehouse row as one independent draw. They are not.
A signal labeled 21 trading days forward shares 18/21 of its outcome window
with one fired three days later, and shares ALL of it with the twenty other
stocks that tripped the same detector the same morning.

`detector_performance_service.independent_blocks(dates, horizon)` counts
non-overlapping horizon-length time blocks — the same convention as rule A in
the conditional-screen notes above, and for the same reason. `sized_interval`
then puts a Wilson 95% band around the rate using THAT count. The point
estimate still uses every row (it is the best guess available); only the WIDTH
is charged the overlap.

Measured on the live warehouse, this is not a rounding correction:

    detector            righe   finestre   skill        intervallo 95%
    candle_reversal      1884         16   44.4         23.6 - 67.4
    macd_divergence       227          3   78.9         28.0 - 97.3
    trend_pullback        325          1   46.2          4.7 - 93.7

**All 16 detectors read "non concludente", and that is the correct answer, not
a bug.** The warehouse spans ~3.5 months; a 21-day detector fits in it three
times. Resolving a 5pp edge needs a few hundred independent windows, which at
21-day horizons is measured in decades. More stocks do not help — only time
does. This is the same conclusion the six offline studies reached, now visible
on screen instead of buried in a report.

The cell carries `horizon_days` beside `effective_n` because without it the
count is unreadable: 16 windows for a 5-day detector and 1 for a 63-day one
over the identical span looks arbitrary until you can see why.

### The honesty rules are enforced in the UI too, not just in this file (2026-09-02)

The engine's conclusions kept being stated here and contradicted on screen. Four
places were fixed; the pattern is worth recognising because each one *looked*
fine:

- **Trade playbook no longer sizes on Forza.** `frontend/src/lib/tradePlaybook.ts`
  ran the risk budget 0.5% → 1.5% linearly in `strength`, with leverage
  following — the most capital and the most leverage on the highest-Forza
  signals. The warehouse says the opposite: market-neutral hit by Forza band
  over 2,246 matured live signals is 52.0 / 53.0 / 52.1 and then **42.3% for
  90-99**, and the decline holds inside a single detector. That is NOT evidence
  high Forza is worse (one sample, overlapping windows, no multiple-testing
  correction) — it is evidence there was no basis for the ramp, so the ramp went
  and **nothing replaced it**. Inverting it would repeat the mistake with the
  opposite sign. Budget is now one constant; the LEVEL is the user's
  risk-appetite choice, and what must not come back is making it depend on
  Forza. Size still varies through `riskBudget / stopPct` — stop distance is
  MEASURED and the stop/target geometry is the one part with an OOS backtest
  (+0.01/+0.04/+0.09R). `conviction` ("ingresso" / "osserva") is gone: the plan
  describes a geometry, it does not issue an instruction.
- **The home card cannot wear a trophy.** It was `Trophy` + "Top picks"; the
  score-IC study says the Qualità composite is a descriptor, not a predictor.
  Now "Classifica qualità · non prevede i rendimenti". `SuperinvestorPicksCard`
  KEEPS "Top picks" deliberately — those are positions someone filed with the
  SEC, not a claim the app makes.
- **A rate needs a sample.** The Setups tile showed "100%" on six resolved
  setups. Below 20 it now shows the raw fraction; the unresolved case still
  renders "—", never 0%.
- **`chart_pattern`** — see the anchors warning in the Forza section above.

The rule these share: **a number, an icon or a verb that claims more than the
measurement supports is the same defect as a wrong number.** When a study here
concludes "no edge", check what the screen says before considering it shipped.

### Factor-adjustment fitting RUN (2026-07-08) — verdict: Probabilità stays a per-detector base rate
The B4-4 gate was executed (`app.scripts.fit_signal_calibration --sample 999`,
247k replayed signals, two OOS splits: by-stock and temporal old→recent).
Both candidate models FAILED the adoption bar (≥2% Brier improvement on BOTH
splits + no log-loss regression + monotone reliability): isotonic ΔBrier
−0.71%/−0.44% (worse than baseline, non-monotone), logistic +0.04%/−0.16%
(flat, log-loss regression). **`factor_adjustments` stays `{}` — per-factor
Probabilità adjustments demonstrably do not improve out-of-sample prediction
on this data. The UI tooltip (lib/alertMeta.ts PROBABILITA_TOOLTIP) now states
honestly that Probabilità is the detector's base rate, identical for every
signal of the same detector.

**Measured on 2,246 live signals (2026-08-20), and the UI was changed because
of it.** Probabilità takes ONE OR TWO distinct values per detector and spans
47-52 across the whole engine; Forza, beside it, takes 34-39 values per
detector over 60-98. So the two mechanics built on it were not what they
looked like: sorting by Prob. ordered rows BY DETECTOR, and the "Probabilità
minima" filter selected a set of detectors — returning an empty list forever
for any threshold above 52, and filtering nothing below 47. Both were removed
from the UI (the sortable header in AlertsTable, the control + chip in
AlertFilters); `filtersFromSearch` also drops `probability_min` and a
`sort_by=probability` coming from an old bookmark, because a filter with no
control left to clear it is worse than none. The COLUMN stays — the number is
honest context, with its calibration dot — and the backend still accepts both
parameters. Same rule as read/unread: **do not re-add the filter or the sort
without a genuinely per-signal probability behind them.** Do NOT re-run this gate expecting a different
answer without materially new data (e.g. 6-12 months of live outcomes).**

### Score-IC backtest RUN (2026-07-07) — verdict: NO reweighting is justified
The roadmap-#9 gate was executed (`app.scripts.score_ic_backtest`, point-in-time
SEC facts, 552 US stocks, 39 quarterly cross-sections 2010-2026, 20,217 obs;
report: `app/data/score_ic_report.json`). Result: **no pillar shows a
statistically significant IC** on forward returns (21/63/126 bars). Growth is
the only weak positive (IC ~+0.04, t≈1.7 — below significance); profitability
and sustainability ≈ 0; the equal-weight composite ≈ 0 with a NEGATIVE
market-neutral decile spread at longer horizons. Value/sentiment were excluded
honestly (SEC facts are split-unadjusted vs adjusted OHLCV; no filed history of
analyst estimates). **Operational rule: the Qualità composite is a company-
quality DESCRIPTOR, not a return predictor — do not reweight pillars or add
quality_extras weights on alpha grounds, and don't re-run this gate expecting a
different answer without NEW point-in-time data (e.g. matured score_history
after 6-12 months of accrual).** Mirrors the confirmation-count rule: no
score-affecting change without a study showing edge; this study showed none.

### Conditional screen RUN (2026-08-03) — verdict: NO condition changes detector skill
The 6th study, and the one that widened the search instead of deepening it:
729,830 signals, 300 stocks, 8 candidate market states + concurrence, tested
at 5 horizons. **Zero survivors.** Unlike the earlier nulls this one had
power: 0/243 cells were below a 10pp MDE, so "flat" here means "no effect",
not "no sample". **Do NOT re-run expecting a different answer without
materially new data** (the accruing live `signal_outcomes`, which are OOS by
construction). Reports: `app/data/conditional_screen_report{,_h1,_h2,_h3,_h5}.json`.

**Two hard-won methodology rules came out of this run. Both produced a
convincing false result first, and both are now TDD'd.**

**A. Market-wide conditions are counted in TIME BLOCKS, not stock-episodes.**
The first grid reported **9 survivors** — the first non-null in six studies,
and all false. Collapsing rows into per-stock episodes fixes clustering WITHIN
a name, but on 2015-03-12 there is ONE VIX shared by all 300 stocks: a cell
credited with 12,054 "independent episodes" was 4–13 contiguous occurrences of
that state in 10 years. Re-tested per block, all 9 collapsed;
`trend_pullback/credit=mid` **reversed sign** (row −3.2pp → block +1.8pp, a
textbook Simpson's paradox). `_MARKET_WIDE` in the grid holds the classification;
the block test uses a **Student-t** (5–14 obs — a normal tail is far too
generous there), implemented via the regularized incomplete beta since scipy
is not a dependency. ⚠️ **The negative control PASSED in that broken run** — the
flaw inflated confidence uniformly rather than manufacturing a specific effect.
A control only proves the pipeline isn't lying in the way you thought to check.

**B. FDR is applied WITHIN a grid, so testing N horizons multiplies the budget
by N.** h=3 and h=5 each produced one cell at q≈0.09; with 4 horizon families
both go back above threshold. Neither was claimed.

**Beta vs skill, quantified** (`conditional_screen_shorthz`, absolute and
market-neutral side by side): `high52_momentum` (100% bull) reads **54.0 abs /
50.5 mkt-neutral @5d** — of ~4pp above a coin flip, **3.5 is simply being long**.
Pooled across detectors the gap is −0.1pp only because bear-tone signals are
sign-flipped and cancel it; **read the per-detector table, never the pooled row**.

**Concurrence (several detectors, same name, same day) is NULL at 1/2/3/5
days** — the literal "coincidence of events" hypothesis, tested on tens of
thousands of stock-episodes (it varies cross-sectionally, so it has real n).
Largest raw effects sit at q≥0.36.

**The h=1 grid is VOID** and stays that way: the negative control fired,
returning `trend_pullback` bull **+1.4** / bear **−1.4** — a perfect symmetry,
which is the signature of ONE effect seen from two sides, i.e. tone, not
regime. It had an attractive survivor (`macd_divergence/vix=low`, q=0.077);
it was discarded. **Honour the control rule even when it costs you a finding.**

---

The tooling below is BUILT and RUN. **Don't rebuild it — it exists.**

- `app.scripts.backfill_macro_history` — full-history FRED **state** series,
  deliberately separate from `refresh_fred`'s `CURATED_SERIES` (those are
  calendar events on a 3y rolling window; these are state on 10y+ and must
  stay OFF the calendar). VIXCLS (1990), T10Y2Y (1976), **BAA10Y (1986)**.
  ⚠️ Do NOT reach for the ICE BofA OAS series (`BAMLH0A0HYM2`, `BAMLC0A0CM`):
  ICE restricted the licence and FRED serves only a ~3y rolling window —
  measured, 795 obs even with an explicit 1996 start. Moody's Baa-over-10y is
  the deep-history substitute. Idempotent.
- `app.scripts.conditional_screen_replay` — ONE replay, MANY stamps: one row
  per signal with 8 conditions (vix level/Δ5d, curve, credit, breadth,
  sector RS, ATR regime, + `regime` as a **negative control**) → csv.gz. It
  deliberately does NOT aggregate, so new hypotheses/bucketings are re-analysed
  offline without paying for the replay again (the regime study had to re-run 4x).
- `app.scripts.conditional_screen_grid` — Benjamini-Hochberg FDR over the whole
  grid, effective-n by collapsing overlapping windows into episodes (or time
  blocks for `_MARKET_WIDE` conditions — see rule A), per-cell MDE so "no
  effect" stays distinct from "no power".
- `app.scripts.conditional_screen_shorthz` — re-scores the SAME rows at
  h=1/2/3/5 with absolute vs market-neutral side by side, and adds
  `concurrence`. **No replay needed**: the rows kept `stock_id` + `bar_i`, so
  outcomes are recomputed by rejoining stored OHLCV — ~4 min vs ~3.2 h. This is
  the payoff of the "write raw rows, never aggregate" design; reach for it
  before ever re-running the replay.

**Four invariants, all TDD'd in `tests/test_conditional_screen.py` and verified
to fail when removed — a bug in any of them is INVISIBLE in the output:**
1. Tercile boundaries are EXPANDING-WINDOW. A whole-sample cut encodes the
   future in the label; the test asserts an old date's label cannot change
   when later observations are appended.
2. Macro reads are STRICTLY BEFORE the fire date (FRED revises and posts late).
3. The hit uses the universe **MEDIAN**, never the mean — the tone-asymmetry
   that fabricated the trend_pullback regime artifact.
4. Market-wide conditions are sized on time blocks, not stock-episodes (rule A).
   The regression test builds the exact trap: 4,800 rows / 300 stocks showing a
   100pp difference across 3 months, which must NOT survive.

The `regime` condition is a negative control with a KNOWN null (2026-06-10). If
the grid ever reports it as a survivor, **the pipeline is broken and every
other survivor in that run is void** — the script prints this check first.
(2026-08-03: it fired at h=1 and that grid was discarded. It also PASSED a run
that was broken in a different way — see the ⚠️ in rule A.)

A survivor is a CANDIDATE, not a result: adoption still needs the full cascade
(OOS sign+magnitude, adversarial verification starting with the tone↔condition
correlation, wider-universe confirmation) before any `signal_calibration.json`
block. The regime-conditioned Probabilità mechanism is already shipped and
dormant, waiting for exactly that.

**Where the engine stands after six studies.** Confirmation-count, factor-
adjustments, score-IC, regime, multi-horizon and now the conditional screen are
all null. `factor_adjustments` stays `{}`, pillar weights stay put, no
conditional Probabilità block exists. Read the engine as what the evidence
supports: a **descriptor and an attention filter** with a structured entry/exit
geometry — not a return predictor. Probabilità is a per-detector base rate.
The only thing that can still overturn this is time: matured live outcomes in
`signal_outcomes`, out-of-sample by construction because they did not exist
when the detectors were written.

### ⚠️ Run scripts from `backend/`, or you silently query an EMPTY database

There is a gitignored `data/app.db` at the REPO ROOT: 4 KB, **zero tables**.
The real one is `backend/data/app.db` — 28 tables, ~616 MB. The SQLite URL is
relative, so a script started from the repo root connects to the empty decoy
instead of failing, and you get zeros, empty lists, or `no such table: stocks`
— none of which read as "wrong working directory". Hit on 2026-09-02 while
spot-checking a catalogue count.

Always `cd backend` first (the `PYTHONPATH=. ./.venv/Scripts/python.exe ...`
form below already does). If a query returns suspiciously empty results, check
`pwd` before you check your SQL.

### One-off scan / recompute outside the API (e.g. after a scoring change)
Stop uvicorn FIRST (sole SQLite writer → avoids "database is locked"), run with
`cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe <script>`, then restart +
verify `/api/health`. `scan_universe` uses STORED OHLCV (fast, no network) and
fires signals only — it does NOT recompute the composite; `recompute_all` does
(reads fundamentals from the L2 cache, ~minutes for the ~1000-stock universe).
