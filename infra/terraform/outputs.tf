# Values you need after `apply`. `terraform output` prints them.

output "instance_id" {
  description = "OCID of the k3s VM."
  value       = oci_core_instance.k3s.id
}

output "ingress_public_ip" {
  description = "Ephemeral public IP of the k3s VM — SSH here, and (M4) the domain A-record points here."
  value       = oci_core_instance.k3s.public_ip
}

output "ssh_command" {
  description = "SSH into the VM (Oracle Linux default user is 'opc')."
  value       = "ssh -i ~/.ssh/oci_finance_alert opc@${oci_core_instance.k3s.public_ip}"
}

output "fetch_kubeconfig" {
  description = "Copy a working local kubeconfig off the box (server rewritten to the public IP)."
  value       = "ssh -i ~/.ssh/oci_finance_alert opc@${oci_core_instance.k3s.public_ip} 'sudo cat /etc/rancher/k3s/k3s.yaml' | sed 's#127.0.0.1#${oci_core_instance.k3s.public_ip}#' > kubeconfig-oci && export KUBECONFIG=$PWD/kubeconfig-oci"
}

output "backup_bucket" {
  description = "Object Storage bucket for DB backups / WAL."
  value       = oci_objectstorage_bucket.backups.name
}

output "compartment_ocid" {
  description = "Echo of the compartment OCID (the bot needs it for OCI CLI calls)."
  value       = var.compartment_ocid
}

output "ocir_repo_path" {
  description = "OCIR image path prefix (usable once create_ocir=true on PAYG, or via docker push)."
  value       = "${var.region}.ocir.io/${data.oci_objectstorage_namespace.this.namespace}/${var.ocir_repo_name}"
}
