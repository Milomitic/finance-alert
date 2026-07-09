# Terraform + provider version pins. Pinning is not bureaucracy: a provider
# minor bump can change resource schemas, so a reproducible `apply` needs a
# known provider version — the IaC equivalent of a lockfile.
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
  }

  # State backend. Local by default (state in this dir). For a team / CI you
  # move state to OCI Object Storage (S3-compatible) — commented because it's
  # chicken-and-egg: the bucket is created by THIS config, so you apply once
  # locally, then migrate state into the bucket. Uncomment + `terraform init
  # -migrate-state` afterwards.
  #
  # backend "s3" {
  #   bucket                      = "finance-alert-tfstate"
  #   key                         = "oke/terraform.tfstate"
  #   region                      = "eu-frankfurt-1"
  #   endpoints                   = { s3 = "https://<namespace>.compat.objectstorage.eu-frankfurt-1.oraclecloud.com" }
  #   skip_region_validation      = true
  #   skip_credentials_validation = true
  #   skip_metadata_api_check     = true
  #   skip_requesting_account_id  = true
  #   use_path_style              = true
  # }
}
