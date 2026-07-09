# ─────────────────────────────────────────────────────────────────────────────
# Network. One VCN with a public subnet that hosts the OKE API endpoint, the
# worker nodes, and (M4) the ingress load balancer. Access is fenced by a
# Network Security Group (NSG) whose ingress rules honour the IP allowlist.
#
# Hardening note for later: production-grade OKE puts WORKER NODES in a PRIVATE
# subnet behind a NAT gateway, exposing only the LB publicly. That's an extra
# subnet + NAT gateway; on Always Free with a tight NSG, public nodes are an
# acceptable, documented simplification for M3. Flagged as an M9 follow-up.
# ─────────────────────────────────────────────────────────────────────────────

resource "oci_core_vcn" "this" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "${var.cluster_name}-vcn"
  dns_label      = "favcn"
}

resource "oci_core_internet_gateway" "this" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.cluster_name}-igw"
  enabled        = true
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.cluster_name}-rt-public"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.this.id
  }
}

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = "10.0.10.0/24"
  display_name               = "${var.cluster_name}-subnet-public"
  route_table_id             = oci_core_route_table.public.id
  dns_label                  = "fapub"
  prohibit_public_ip_on_vnic = false
}

# ── NSG: the network-edge firewall (the IP allowlist lives here) ─────────────
resource "oci_core_network_security_group" "nodes" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${var.cluster_name}-nsg"
}

# K8s API server (6443) — only from the allowlist.
resource "oci_core_network_security_group_security_rule" "api_ingress" {
  for_each                  = toset(var.allowlist_cidrs)
  network_security_group_id = oci_core_network_security_group.nodes.id
  direction                 = "INGRESS"
  protocol                  = "6" # TCP
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  description               = "K8s API from allowlisted client"
  tcp_options {
    destination_port_range {
      min = 6443
      max = 6443
    }
  }
}

# App / ingress (443) — only from the allowlist.
resource "oci_core_network_security_group_security_rule" "https_ingress" {
  for_each                  = toset(var.allowlist_cidrs)
  network_security_group_id = oci_core_network_security_group.nodes.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  description               = "HTTPS/ingress from allowlisted client"
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# Intra-VCN: control-plane <-> nodes and node <-> node must talk freely.
resource "oci_core_network_security_group_security_rule" "intra_vcn_ingress" {
  network_security_group_id = oci_core_network_security_group.nodes.id
  direction                 = "INGRESS"
  protocol                  = "all"
  source                    = "10.0.0.0/16"
  source_type               = "CIDR_BLOCK"
  description               = "Intra-VCN (control plane + node-to-node)"
}

# Egress: nodes pull images, reach yfinance/SEC/etc., and the OKE control plane.
resource "oci_core_network_security_group_security_rule" "all_egress" {
  network_security_group_id = oci_core_network_security_group.nodes.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  description               = "Egress anywhere (image pulls + upstream data)"
}

# ── Reserved public IP ───────────────────────────────────────────────────────
# Created unattached now; the ingress LB (M4) binds it, and the domain A-record
# points here. Reserved (not ephemeral) so it survives stop/start — the roadmap
# gotcha: reserve BEFORE pointing DNS.
resource "oci_core_public_ip" "ingress" {
  compartment_id = var.compartment_ocid
  lifetime       = "RESERVED"
  display_name   = "${var.cluster_name}-ingress-ip"
}
