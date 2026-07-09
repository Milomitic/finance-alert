# OCI Always-Free account setup — for the M3 `terraform apply`

A practical, ordered checklist to create the OCI account and make it
Terraform-ready with the sizing our `infra/terraform/` expects. Follow top to
bottom; the ⚠️ steps are the ones that bite people.

> Facts here reflect Oracle's Always-Free program at time of writing. Oracle
> changes limits/UI — verify anything money- or quota-related on the console.

---

## Decision 1 — Home region ⚠️ PERMANENT

The **home region** is chosen at signup and **cannot be changed**. It's where
your Always-Free resources (incl. the A1 quota) live.

- Pick one **geographically close** for latency. From Italy: **Milan
  (eu-milan-1)**, Frankfurt (eu-frankfurt-1), Zurich, Paris, Marseille.
- ⚠️ **Ampere A1 capacity is the catch.** The biggest regions (Frankfurt,
  Amsterdam, Ashburn) are the most *contended* — "Out of host capacity" on A1
  is common there. Milan is close to Italy and often less contended.
- **Recommendation:** Milan if available at signup, else Frankfurt.

## Decision 2 — Stay Always-Free, or upgrade to Pay-As-You-Go?

- New accounts get **trial credits (~$300 / 30 days)** *plus* Always Free.
  After 30 days only Always Free persists (paid resources get reclaimed).
- ⚠️ **A1 availability nuance (widely reported):** pure Always-Free accounts
  are *deprioritised* for scarce A1 capacity; accounts **upgraded to
  Pay-As-You-Go** get A1 much more reliably — and **cost nothing** as long as
  you only run Always-Free-eligible resources.
- **Trade-off:** PAYG removes the A1 headache but means a misconfigured
  resource *can* bill you. Our Terraform is sized to stay inside Always Free,
  so the risk is low if you don't hand-create paid resources.
- **Recommendation:** start Always-Free; if `apply` keeps failing on A1
  capacity, upgrade to PAYG (Billing → Upgrade) — it's the standard fix.

## Decision 3 — Node sizing (already encoded in Terraform)

Always-Free A1 envelope: **4 OCPU + 24 GB RAM total**, **200 GB block storage
total**, 10 GB Object Storage, 1× 10 Mbps Load Balancer.

Our `variables.tf` defaults, and why:

| Var | Default | Note |
|---|---|---|
| `node_count` | 2 | a real multi-node cluster |
| `node_ocpus` | 2 | 2×2 = 4 OCPU (the whole A1 CPU allowance) |
| `node_memory_gbs` | 12 | 2×12 = 24 GB (the whole A1 RAM allowance) |

- Block storage math: each node's boot volume defaults ~46–50 GB → 2 nodes ≈
  100 GB, leaving ~100 GB for PVCs — inside the 200 GB cap. Fine.
- ⚠️ **If 2 nodes won't schedule** (A1 capacity), fall back to **one bigger
  node**: `node_count=1, node_ocpus=4, node_memory_gbs=24`. Same total, often
  easier to place. Set it in `terraform.tfvars`.

---

## Step-by-step

### 1. Create the account
1. Go to **oracle.com/cloud/free** → *Start for free*.
2. Email + phone verification; **credit/debit card** for identity (Always-Free
   resources don't charge; expect a temporary ~1€ auth hold).
3. ⚠️ Choose the **home region** (Decision 1) — permanent.
4. Finish; you land in the OCI Console.

### 2. (Optional) Upgrade to PAYG
Only if you hit A1 capacity walls later — Billing & Cost Management → *Upgrade
and Manage Payment* (Decision 2).

### 3. Create a compartment (don't use root)
Identity & Security → **Compartments** → *Create Compartment*
(name e.g. `finance-alert`). Best practice + matches our `compartment_ocid`.
Copy its **OCID**.

### 4. Generate an SSH key (if you don't have one)
```bash
ssh-keygen -t ed25519 -C "oci-finance-alert" -f ~/.ssh/oci_finance_alert
# public key → ssh_public_key in terraform.tfvars:
cat ~/.ssh/oci_finance_alert.pub
```

### 5. Install the OCI CLI + create API auth
```bash
# Windows (PowerShell):
winget install Oracle.OCI-CLI      # or the official installer script
oci setup config
```
`oci setup config` walks you through:
- it asks for your **user OCID**, **tenancy OCID**, **region** (copy from the
  Console: user avatar → *Tenancy*/*My profile*),
- it **generates an API key pair** into `~/.oci/`.
Then upload the public key: Console → your profile → **API Keys** → *Add API
Key* → paste `~/.oci/oci_api_key_public.pem`.

Verify:
```bash
oci iam region list      # should return JSON, not an auth error
```

### 6. Collect the values for `terraform.tfvars`
```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```
Fill:
- `tenancy_ocid` — Console → Tenancy details.
- `compartment_ocid` — the compartment from step 3.
- `region` — your home region id (e.g. `eu-milan-1`).
- `allowlist_cidrs` — your public IP: `curl ifconfig.me` → append `/32`.
- `ssh_public_key` — the `.pub` from step 4.

### 7. Plan & apply (via the Terraform container — no host install)
```bash
cd infra/terraform
D="docker run --rm -v $PWD:/wd -w /wd -v $HOME/.oci:/root/.oci hashicorp/terraform:1.9"
$D init
$D plan       # review: VCN, NSG, OKE cluster, A1 node pool, bucket, OCIR
$D apply       # type yes
```
> The container needs your `~/.oci` mounted (done above) for auth. The API
> key path in `~/.oci/config` must be readable inside the container — if the
> config uses an absolute Windows path, edit it to `/root/.oci/oci_api_key.pem`
> for the container run, or run terraform from WSL.

### 8. Point kubectl at the new cluster
```bash
$D output -raw kubeconfig_command    # prints the `oci ce ...` command
# run it (needs OCI CLI); then:
kubectl get nodes                     # your OKE nodes, Ready
```

---

## ⚠️ When A1 apply fails ("Out of host capacity")

Not your fault — it's Oracle capacity. In order of effort:
1. **Retry** `apply` — capacity frees up; try off-peak hours.
2. **Fewer/bigger node**: `node_count=1` (one 4-OCPU node) is often placeable
   when two aren't.
3. **Run the capacity-retry bot** (below) — automates the retry until it lands.
4. **Upgrade to PAYG** (Decision 2) — the most reliable fix.
5. Different region only as a last resort (home region is fixed; you'd only be
   changing where *non-home* resources go, which A1 Always-Free doesn't allow —
   so realistically this means a new account, avoid).

### The capacity-retry bot — `infra/oci/a1-retry.sh`

There is **no OCI API for "is A1 capacity free right now"** — the only signal
is *attempting to launch*, and capacity appears in short, unpredictable
windows. The bot automates catching one:

1. Applies the cluster/network/storage once (no capacity constraint), then
2. loops: wait a grace period → check the node pool's **ACTIVE node count** via
   OCI CLI (Terraform can't see per-node lifecycle state) → if short, **destroy
   + recreate the node pool** so each cycle is a fresh launch attempt →
   back off with jitter and repeat.
3. On success it (optionally) pings your Telegram bot (reusing
   `backend/.env`) and exits.

**Fully containerised — you install nothing but Docker.** Terraform and the
OCI CLI both run in throwaway containers; auth comes from `terraform.tfvars` +
your API private key at `~/.oci/oci_api_key.pem` (no host CLI, no
`~/.oci/config`).

👉 **Full step-by-step: [`RUN-A1-BOT.md`](RUN-A1-BOT.md).** In short:

```bash
bash infra/oci/a1-retry.sh
# tune: INTERVAL=240 GRACE=210 MAX_HOURS=48 bash infra/oci/a1-retry.sh
# leave it running; watch infra/oci/a1-retry.log
```

> Honest caveat: authored against our Terraform but not yet exercised against a
> live account — the OKE async-node-launch + destroy/recreate flow may need a
> tweak on first run. We'll iterate once you point it at the account.

---

## Cost guardrail

Everything our Terraform creates is Always-Free-eligible. To be safe:
- Set a **Budget alert** (Billing → Budgets) at e.g. 1€ so any accidental paid
  resource pings you immediately.
- After the 30-day trial, confirm nothing paid is running (Billing → Cost
  Analysis).
