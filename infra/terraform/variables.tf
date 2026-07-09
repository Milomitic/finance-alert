# ── Identity / region (from your OCI account) ────────────────────────────────
variable "tenancy_ocid" {
  description = "OCID of your tenancy (root)."
  type        = string
}

variable "compartment_ocid" {
  description = "OCID of the compartment to create resources in (a sub-compartment is best practice, not the root tenancy)."
  type        = string
}

variable "region" {
  description = "OCI region identifier, e.g. eu-milan-1. Your home region — where Always-Free A1 lives."
  type        = string
  default     = "eu-milan-1"
}

# ── API-key auth (from the key pair you generate in the Console) ──────────────
# Passed explicitly so Terraform (running in a container) never needs to read a
# host ~/.oci/config with host-specific key paths — the classic container gotcha.
variable "user_ocid" {
  description = "OCID of the user the API key belongs to."
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of the uploaded API public key (shown in the Console when you add the key)."
  type        = string
}

variable "private_key_path" {
  description = "Path to the API private key AS SEEN INSIDE the Terraform container. Leave the default — the a1-retry bot mounts your host key there."
  type        = string
  default     = "/root/.oci/oci_api_key.pem"
}

# ── Access control ───────────────────────────────────────────────────────────
variable "allowlist_cidrs" {
  description = "Source CIDRs allowed to reach the K8s API (6443) and the app (443). Your home/office public IP as /32. THIS is the network-edge allowlist the security plan chose."
  type        = list(string)
  # No default on purpose — an empty/0.0.0.0/0 default would silently expose
  # the cluster. Must be set in terraform.tfvars.
}

variable "ssh_public_key" {
  description = "SSH public key installed on the worker nodes (for break-glass debugging)."
  type        = string
}

# ── k3s VM (compute.tf) ──────────────────────────────────────────────────────
variable "cluster_name" {
  description = "Name prefix for the cluster's resources (VM, VCN, NSG…)."
  type        = string
  default     = "finance-alert"
}

# A1.Flex shape for the single k3s node. Keep within your account's Always-Free
# A1 allowance (this tenancy: 2 OCPU / 12 GB — check `oci limits value list
# --service-name compute --query 'data[?contains(name,\`standard-a1\`)]'`).
variable "node_ocpus" {
  description = "OCPUs for the k3s VM (A1.Flex)."
  type        = number
  default     = 2
}

variable "node_memory_gbs" {
  description = "Memory (GB) for the k3s VM (A1.Flex)."
  type        = number
  default     = 12
}

variable "boot_volume_gbs" {
  description = "Boot volume size (GB). Always-Free block storage is 200 GB total."
  type        = number
  default     = 50
}

# ── Storage ──────────────────────────────────────────────────────────────────
variable "backup_bucket_name" {
  description = "Object Storage bucket for DB backups / Postgres WAL archiving (M7)."
  type        = string
  default     = "finance-alert-backups"
}

variable "ocir_repo_name" {
  description = "OCI Container Registry repository for the app image."
  type        = string
  default     = "finance-alert/app"
}

variable "create_ocir" {
  description = "Create the OCIR container repository. OFF by default: CreateContainerRepository returns 403 FREE_TIER_NOT_SUPPORTED on pure Always-Free accounts (repos auto-create on first docker push anyway). Enable after upgrading to PAYG."
  type        = bool
  default     = false
}
