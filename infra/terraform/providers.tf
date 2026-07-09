# OCI provider auth.
#
# Locally this reads ~/.oci/config (the API-key config `oci setup config`
# writes). In CI (M5) you'd instead export TF_VAR_* and the OCI_CLI_* env vars,
# or use OKE workload identity. Only `region` + `tenancy_ocid` are declared
# here; the user/fingerprint/key come from the config file so no secret ever
# lands in a .tf file.
provider "oci" {
  tenancy_ocid = var.tenancy_ocid
  region       = var.region
  # config_file_profile = "DEFAULT"   # uncomment to pin a non-default profile
}
