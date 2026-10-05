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

# ⚠️ Il versioning SENZA questa regola riempie la tenancy (2026-10-06).
#
# Barman cancella i backup oltre la retention (30d), ma con il versioning
# attivo una cancellazione lascia solo un delete marker: la versione vera
# resta e si paga. Misurato: 8,8 GB visibili, 21,6 GB occupati, 7.042 delete
# marker, contro i 20 GB dell'Always Free. Da quel momento ogni PutObject
# risponde StorageLimitExceeded: backup base falliti dal 28 settembre, WAL
# non archiviati dal 27 (19 GB in coda sul disco del nodo) e il drill di
# ripristino rosso. Il versioning resta: protegge da una cancellazione
# sbagliata per una settimana, che e' cio' per cui era stato acceso.
resource "oci_objectstorage_object_lifecycle_policy" "backups" {
  namespace = data.oci_objectstorage_namespace.this.namespace
  bucket    = oci_objectstorage_bucket.backups.name

  rules {
    name        = "versioni-precedenti-dopo-7-giorni"
    action      = "DELETE"
    target      = "previous-object-versions"
    time_amount = 7
    time_unit   = "DAYS"
    is_enabled  = true
  }

  depends_on = [oci_identity_policy.objectstorage_lifecycle]
}

# Senza questa policy OCI non esegue le lifecycle rule del bucket
# (InsufficientServicePermissions): e' il servizio Object Storage della
# regione, non un utente, a cancellare le versioni.
resource "oci_identity_policy" "objectstorage_lifecycle" {
  compartment_id = var.compartment_ocid
  name           = "objectstorage-lifecycle-backups"
  description    = "Object Storage puo' applicare le lifecycle rule del bucket dei backup"
  statements = [
    "Allow service objectstorage-${var.region} to manage object-family in compartment id ${var.compartment_ocid}",
  ]
}

# OCI Container Registry repo for the app image (pushed by CI in M5).
# Disabled by default: CreateContainerRepository returns 403
# FREE_TIER_NOT_SUPPORTED on a pure Always-Free account. Flip create_ocir=true
# after upgrading to PAYG (still $0 if only Always-Free resources run). Until
# then, OCIR repos are auto-created on first `docker push` anyway.
resource "oci_artifacts_container_repository" "app" {
  count          = var.create_ocir ? 1 : 0
  compartment_id = var.compartment_ocid
  display_name   = var.ocir_repo_name
  is_public      = false
}
