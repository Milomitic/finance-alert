# ─────────────────────────────────────────────────────────────────────────────
# Object Storage (backups / Postgres WAL archiving) + OCIR (image registry).
# Both within Always-Free allowances.
# ─────────────────────────────────────────────────────────────────────────────

# Object Storage is addressed by a per-tenancy "namespace" (not the compartment).
data "oci_objectstorage_namespace" "this" {
  compartment_id = var.compartment_ocid
}

resource "oci_objectstorage_bucket" "backups" {
  compartment_id = var.compartment_ocid
  namespace      = data.oci_objectstorage_namespace.this.namespace
  name           = var.backup_bucket_name
  access_type    = "NoPublicAccess" # private — backups are never world-readable

  # Auto-tier + versioning give cheap point-in-time recovery of backup objects.
  versioning = "Enabled"
}

# OCI Container Registry repo for the app image (pushed by CI in M5).
resource "oci_artifacts_container_repository" "app" {
  compartment_id = var.compartment_ocid
  display_name   = var.ocir_repo_name
  is_public      = false
}
