# Get the A1 capacity-retry bot running — step by step

Starting point: **you already have an OCI account** (home region set, e.g.
Milan). Goal: the bot in `infra/oci/a1-retry.sh` running and retrying until it
grabs Always-Free A1 capacity for your OKE nodes.

You install **nothing but Docker**. Terraform and the OCI CLI both run in
throwaway containers; the bot feeds them auth from `terraform.tfvars` + one key
file. Total hands-on time: ~15 minutes, then the bot runs unattended.

> Everything below is done once. The ⚠️ notes are the parts people get wrong.

---

## What the bot needs from you (the whole list)

| # | Thing | Where it comes from |
|---|---|---|
| 1 | Docker Desktop running | your machine |
| 2 | A **compartment** OCID | OCI Console |
| 3 | An **API key** → user OCID, tenancy OCID, fingerprint | OCI Console |
| 4 | The API **private key** at `~/.oci/oci_api_key.pem` | downloaded in step 3 |
| 5 | An **SSH public key** | `ssh-keygen` |
| 6 | Your **public IP** (`/32`) | `curl ifconfig.me` |
| 7 | `terraform.tfvars` filled with 2–6 | you, one file |

Then: `bash infra/oci/a1-retry.sh`.

---

## Step 1 — Docker Desktop running

```bash
docker info      # must print server info, not an error
```
If it errors, start Docker Desktop and wait for the whale icon to settle.

## Step 2 — Create a compartment (don't use the root tenancy)

OCI Console → **Identity & Security → Compartments → Create Compartment**.
Name it `finance-alert`, create, open it, **copy its OCID**
(`ocid1.compartment.oc1..…`). Keep it for the tfvars.

> Why not root: a sub-compartment is the standard blast-radius boundary — you
> can delete everything in it in one go, and scope policies to it.

## Step 3 — Create an API key (gives you 3 of the values + the private key)

OCI Console → top-right **profile avatar → My profile** → scroll to
**Resources → API keys → Add API key**:

1. Choose **Generate API key pair**.
2. Click **Download private key** (save it — you'll move it in step 4).
   Optionally download the public key too.
3. Click **Add**.
4. A **Configuration file preview** pops up. It contains exactly what you need:
   ```
   user=ocid1.user.oc1..xxxx          ← user_ocid
   fingerprint=aa:bb:cc:…             ← fingerprint
   tenancy=ocid1.tenancy.oc1..xxxx    ← tenancy_ocid
   region=eu-milan-1                  ← region
   ```
   Copy those four. **Close the dialog only after copying** — the fingerprint is
   annoying to find again.

## Step 4 — Put the private key where the bot looks

The bot mounts `~/.oci/` into the containers and expects the key named
`oci_api_key.pem`:

```bash
mkdir -p ~/.oci
mv /c/Users/giuli/Downloads/<the-downloaded-key>.pem ~/.oci/oci_api_key.pem
chmod 600 ~/.oci/oci_api_key.pem          # silence the SDK's perms warning
ls -l ~/.oci/oci_api_key.pem              # confirm it's there
```
⚠️ `~/.oci` should contain **only this key** — no `config` file. The bot passes
auth via env, so a stray `config` with host paths would only cause confusion.

## Step 5 — SSH key for the worker nodes

```bash
ssh-keygen -t ed25519 -C "oci-finance-alert" -f ~/.ssh/oci_finance_alert
cat ~/.ssh/oci_finance_alert.pub          # copy this whole line for tfvars
```
(Break-glass access to nodes; Terraform installs it on them.)

## Step 6 — Your public IP (the network allowlist)

```bash
curl ifconfig.me                          # e.g. 93.44.x.y  → use 93.44.x.y/32
```
⚠️ If your ISP changes your IP, the K8s API/app lock you out until you update
`allowlist_cidrs` and re-apply. Never use `0.0.0.0/0`.

## Step 7 — Fill `terraform.tfvars`

```bash
git switch cloud                          # infra/ lives on the cloud branch
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```
Edit `terraform.tfvars` with the values you gathered:

```hcl
tenancy_ocid     = "ocid1.tenancy.oc1..xxxx"      # step 3
compartment_ocid = "ocid1.compartment.oc1..xxxx"  # step 2
region           = "eu-milan-1"                    # step 3 (your home region)
user_ocid        = "ocid1.user.oc1..xxxx"          # step 3
fingerprint      = "aa:bb:cc:dd:ee:ff:…"           # step 3
allowlist_cidrs  = ["93.44.x.y/32"]                # step 6
ssh_public_key   = "ssh-ed25519 AAAA… oci-finance-alert"   # step 5
# private_key_path: leave unset — defaults to the container path the bot mounts.
```
Don't set `private_key_path` — its default (`/root/.oci/oci_api_key.pem`) is the
in-container path the bot mounts your key to.

## Step 8 — Launch the bot

From anywhere in the repo:

```bash
bash infra/oci/a1-retry.sh
```

What happens:
1. **Preflight** — checks Docker, tfvars, the key, and does a real auth probe
   (`oci iam region list` in a container). The first run **pulls the terraform +
   oci-cli images** (a few hundred MB, once).
2. **Bootstrap apply** — creates VCN, NSG, OKE cluster, storage. The node pool
   is created too but its VMs may fail on capacity — expected.
3. **Retry loop** — every cycle: wait `GRACE`s → count ACTIVE nodes → if short,
   destroy + recreate the node pool (fresh launch attempt) → back off → repeat.
4. **Success** — logs `🎉 SUCCESS`, pings your Telegram (if `backend/.env` has a
   bot token), and exits.

Watch progress:
```bash
tail -f infra/oci/a1-retry.log
```

Tunables (env vars): `INTERVAL` (base backoff, def 180s), `GRACE` (node-launch
wait, def 210s), `MAX_HOURS` (give-up, def 72), `NOTIFY=0` (no Telegram):
```bash
INTERVAL=240 GRACE=210 MAX_HOURS=48 bash infra/oci/a1-retry.sh
```

⚠️ **Leave it running.** In pure Always-Free, catching Milan capacity can take
hours to days. Run it in a terminal you can leave open (or `tmux`/a spare
window). Re-running after a stop is safe — Terraform is idempotent, so it picks
up where it left off.

## Step 9 — When it lands: point kubectl at the cluster

```bash
cd infra/terraform
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/wd" -w /wd -v "$HOME/.oci:/root/.oci:ro" \
  hashicorp/terraform:1.9 output -raw kubeconfig_command
# run the printed `oci ce cluster create-kubeconfig …` (needs kubectl + a kube-
# config); then:
kubectl get nodes         # your A1 nodes, Ready
```
That's the M3 finish line — a real OKE cluster with Always-Free A1 nodes. M4
(ingress + TLS) builds on it.

---

## Troubleshooting

| Symptom in the log | Cause → fix |
|---|---|
| `docker daemon unreachable` | Docker Desktop not started. Start it. |
| `OCI auth FAILED` | Wrong OCID/fingerprint in tfvars, or key not at `~/.oci/oci_api_key.pem`. Re-check step 3/4. |
| `manifest unknown` / oci-cli image won't pull | Set an alternative image: `OCI_CLI_IMAGE=<image> bash …`. |
| Apply error mentioning **NSG / security rule** | OKE net rules are picky; paste the log line and we'll adjust `vcn.tf`. |
| Loops forever, only `0/2 ACTIVE` | Genuine capacity scarcity. Options: try `node_count=1, node_ocpus=4, node_memory_gbs=24` in tfvars (one bigger node schedules more easily), run overnight, or upgrade to PAYG (the reliable fix — see OCI-SETUP.md). |
| Key perms warning | `chmod 600 ~/.oci/oci_api_key.pem`. |

> Honest note: this bot is authored against our Terraform but hasn't been run
> against a live account yet. The OKE async-launch + destroy/recreate flow may
> need a small tweak on first real run — send me the `a1-retry.log` and we'll
> fix it together.
