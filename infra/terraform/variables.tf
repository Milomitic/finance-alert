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
  description = "OCI region identifier, e.g. eu-frankfurt-1. Pick one where Ampere A1 Always-Free capacity is actually available."
  type        = string
  default     = "eu-frankfurt-1"
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

# ── OKE cluster + nodes ──────────────────────────────────────────────────────
variable "cluster_name" {
  description = "Name of the OKE cluster."
  type        = string
  default     = "finance-alert"
}

variable "kubernetes_version" {
  description = "K8s version for the control plane + nodes. Must be one OKE offers in your region (see the cluster_option data source)."
  type        = string
  default     = "v1.32.1"
}

# Ampere A1 Always-Free envelope is 4 OCPU + 24 GB total. Defaults below use it
# fully across 2 nodes (a real multi-node cluster) — enough headroom for the
# app + Postgres + Prometheus/Grafana/Loki that land in later milestones.
variable "node_count" {
  description = "Number of worker nodes."
  type        = number
  default     = 2
}

variable "node_ocpus" {
  description = "OCPUs per node (A1.Flex). node_count * node_ocpus must be <= 4 for Always Free."
  type        = number
  default     = 2
}

variable "node_memory_gbs" {
  description = "Memory (GB) per node. node_count * node_memory_gbs must be <= 24 for Always Free."
  type        = number
  default     = 12
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
