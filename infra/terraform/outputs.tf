# Values you need after `apply`. `terraform output` prints them; CI reads them.

output "cluster_id" {
  description = "OCID of the OKE cluster."
  value       = oci_containerengine_cluster.this.id
}

output "kubeconfig_command" {
  description = "Run this to point kubectl at the new cluster."
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.this.id} --file $HOME/.kube/config --region ${var.region} --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT"
}

output "ingress_public_ip" {
  description = "Reserved public IP for the ingress LB — point the domain A-record here (M4)."
  value       = oci_core_public_ip.ingress.ip_address
}

output "backup_bucket" {
  description = "Object Storage bucket for backups / WAL."
  value       = oci_objectstorage_bucket.backups.name
}

output "ocir_repo_path" {
  description = "OCIR image path prefix (push the app image here in M5)."
  value       = "${var.region}.ocir.io/${data.oci_objectstorage_namespace.this.namespace}/${var.ocir_repo_name}"
}
