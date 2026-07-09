# ─────────────────────────────────────────────────────────────────────────────
# OKE (Oracle Kubernetes Engine). Control plane = BASIC_CLUSTER → FREE. Worker
# nodes run on Ampere A1.Flex within the Always-Free envelope, so total cost $0.
# ─────────────────────────────────────────────────────────────────────────────

data "oci_identity_availability_domains" "this" {
  compartment_id = var.tenancy_ocid
}

# The OKE-optimised node images vary by region + k8s version + arch. Rather
# than hardcode a region-specific OCID, look them up and pick an ARM
# (aarch64) image matching the requested k8s version.
data "oci_containerengine_node_pool_option" "this" {
  node_pool_option_id = "all"
  compartment_id      = var.compartment_ocid
}

locals {
  k8s_ver_bare = replace(var.kubernetes_version, "v", "")
  arm_images = [
    for s in data.oci_containerengine_node_pool_option.this.sources :
    s.image_id
    if can(regex("aarch64", s.source_name)) && can(regex(local.k8s_ver_bare, s.source_name))
  ]
  # First matching ARM image; empty (→ apply fails clearly) if none matched,
  # which flags a bad kubernetes_version for the region.
  node_image_id = length(local.arm_images) > 0 ? local.arm_images[0] : ""
}

resource "oci_containerengine_cluster" "this" {
  compartment_id     = var.compartment_ocid
  name               = var.cluster_name
  vcn_id             = oci_core_vcn.this.id
  kubernetes_version = var.kubernetes_version
  type               = "BASIC_CLUSTER" # the FREE control-plane tier

  endpoint_config {
    subnet_id            = oci_core_subnet.public.id
    is_public_ip_enabled = true
    nsg_ids              = [oci_core_network_security_group.nodes.id]
  }

  options {
    # Subnet where Service type=LoadBalancer provisions LBs (M4 ingress).
    service_lb_subnet_ids = [oci_core_subnet.public.id]
  }
}

resource "oci_containerengine_node_pool" "this" {
  cluster_id         = oci_containerengine_cluster.this.id
  compartment_id     = var.compartment_ocid
  name               = "${var.cluster_name}-pool"
  kubernetes_version = var.kubernetes_version
  node_shape         = "VM.Standard.A1.Flex" # Ampere ARM — the Always-Free shape

  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gbs
  }

  node_source_details {
    source_type = "IMAGE"
    image_id    = local.node_image_id
  }

  node_config_details {
    size    = var.node_count
    nsg_ids = [oci_core_network_security_group.nodes.id]

    # Spread nodes across every AD so A1 capacity in one AD isn't a hard block.
    dynamic "placement_configs" {
      for_each = data.oci_identity_availability_domains.this.availability_domains
      content {
        availability_domain = placement_configs.value.name
        subnet_id           = oci_core_subnet.public.id
      }
    }
  }

  ssh_public_key = var.ssh_public_key
}
