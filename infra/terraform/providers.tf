# OCI provider auth — explicit API-key values.
#
# We pass every auth field as a variable instead of reading ~/.oci/config,
# because Terraform runs INSIDE a container (see infra/oci/a1-retry.sh): a
# host config file would carry host-specific key paths the container can't
# resolve. The private key itself is never in a .tf file — only its path
# (var.private_key_path, the container mount point) and its fingerprint are.
# tenancy/user OCIDs + fingerprint are identifiers, not secrets; they live in
# the gitignored terraform.tfvars.
provider "oci" {
  auth             = "ApiKey"
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}
