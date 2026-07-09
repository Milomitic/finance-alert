# ─────────────────────────────────────────────────────────────────────────────
# Compute: a single Ampere A1.Flex VM running k3s (lightweight, CNCF-certified
# Kubernetes). We pivoted here from managed OKE because a pure Always-Free
# tenancy pins the OKE cluster/node limits to 0; standalone A1 compute IS
# allowed (this account: 2 OCPU / 12 GB). k3s gives real Kubernetes on the free
# VM — with local-path storage (for the app's PVC), Traefik ingress and
# ServiceLB out of the box — and the app's Helm chart deploys straight onto it.
# The VCN / subnet / NSG from vcn.tf are reused as-is.
# ─────────────────────────────────────────────────────────────────────────────

data "oci_identity_availability_domains" "this" {
  compartment_id = var.tenancy_ocid
}

# Newest Oracle Linux aarch64 image that supports the A1.Flex shape (avoids
# hardcoding a region-specific image OCID that goes stale).
data "oci_core_images" "ol_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Oracle Linux"
  operating_system_version = "9"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_instance" "k3s" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.this.availability_domains[0].name
  display_name        = "${var.cluster_name}-k3s"
  shape               = "VM.Standard.A1.Flex"

  # Whole Always-Free A1 envelope on this account (2 OCPU / 12 GB).
  shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gbs
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ol_arm.images[0].id
    boot_volume_size_in_gbs = var.boot_volume_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    nsg_ids          = [oci_core_network_security_group.nodes.id]
    assign_public_ip = true # ephemeral public IP; a reserved IP + LB come in M4
    hostname_label   = "k3s"
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(file("${path.module}/cloud-init/k3s.yaml"))
  }

  # A newer OL image published later must NOT trigger a destroy/recreate (that
  # would wipe k3s + the app's data). Mutate the box via SSH/GitOps, not
  # re-provisioning. Same for the one-shot cloud-init.
  lifecycle {
    ignore_changes = [source_details[0].source_id, metadata["user_data"]]
  }
}
