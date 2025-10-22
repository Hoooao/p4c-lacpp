#include <core.p4>
#include <tofino1_specs.p4>
#include <tofino1_base.p4>
#include <tofino1_arch.p4>

header ethernet_t {
    bit<48> dst_addr;
    bit<48> src_addr;
    bit<16> eth_type;
}

header A{
    bit<16> first;
}
header B{
    bit<16> first;
}

header C{
    bit<16> first;
}
header D{
    bit<16> first;
}
struct Headers {
    ethernet_t eth_hdr;
    A     a;
    B     b;
    C     c;
    D     d;
}

struct ingress_metadata_t {
}

struct egress_metadata_t {
}

parser SwitchIngressParser(packet_in pkt, out Headers hdr, out ingress_metadata_t ig_md, out ingress_intrinsic_metadata_t ig_intr_md) {
    state start {
        pkt.extract<ingress_intrinsic_metadata_t>(ig_intr_md);
        pkt.extract<ethernet_t>(hdr.eth_hdr);
        pkt.extract<A>(hdr.a);
        pkt.extract<B>(hdr.b);
        pkt.extract<C>(hdr.c);
        transition accept;
    }
}

control ingress(inout Headers h, inout ingress_metadata_t ig_md, in ingress_intrinsic_metadata_t ig_intr_md, in ingress_intrinsic_metadata_from_parser_t ig_prsr_md, inout ingress_intrinsic_metadata_for_deparser_t ig_dprsr_md, inout ingress_intrinsic_metadata_for_tm_t ig_tm_md) {

// Note: WAR does not necessarily force different stages.

    action set_a(bit<16> val) {
        h.a.first = val;
    }
    action set_b(bit<16> val) {
        h.b.first = val;
    }
    action set_c(bit<16> val) {
        h.c.first = val;
    }
    action set_d(bit<16> val) {
        h.d.first = val;
    }   
    
    table tbl_init {
        key = {
            h.c.first       : exact;
        }
        actions = {
            set_a();
        }
        size = 512;
    }

    // Force tbl_init and tbl_match_a to be in different stage by RAW on a.first
    table tbl_match_a{
        key = {
            h.a.first       : exact;
        }
        actions = {
            set_b();
        }
        size = 512;
    }

    // Create a WAR by having tbl_write_a write a.first read by tbl_match_a
    table tbl_write_a{
        key = {
            h.d.first       : exact;
        }
        actions = {
            set_a();
        }
        size = 512;
    }


    apply {
        tbl_init.apply();
        tbl_match_a.apply();
        tbl_write_a.apply();
    }
}

control SwitchIngressDeparser(packet_out pkt, inout Headers h, in ingress_metadata_t ig_md, in ingress_intrinsic_metadata_for_deparser_t ig_dprsr_md) {
    apply {
        pkt.emit<Headers>(h);
    }
}

parser SwitchEgressParser(packet_in pkt, out Headers h, out egress_metadata_t eg_md, out egress_intrinsic_metadata_t eg_intr_md) {
    state start {
        pkt.extract<egress_intrinsic_metadata_t>(eg_intr_md);
        transition accept;
    }
}

control SwitchEgress(inout Headers h, inout egress_metadata_t eg_md, in egress_intrinsic_metadata_t eg_intr_md, in egress_intrinsic_metadata_from_parser_t eg_intr_md_from_prsr, inout egress_intrinsic_metadata_for_deparser_t eg_intr_dprs_md, inout egress_intrinsic_metadata_for_output_port_t eg_intr_oport_md) {
    apply {
    }
}

control SwitchEgressDeparser(packet_out pkt, inout Headers h, in egress_metadata_t eg_md, in egress_intrinsic_metadata_for_deparser_t eg_intr_dprs_md) {
    apply {
        pkt.emit<Headers>(h);
    }
}

Pipeline<Headers, ingress_metadata_t, Headers, egress_metadata_t>(SwitchIngressParser(), ingress(), SwitchIngressDeparser(), SwitchEgressParser(), SwitchEgress(), SwitchEgressDeparser()) pipe;
Switch<Headers, ingress_metadata_t, Headers, egress_metadata_t, _, _, _, _, _, _, _, _, _, _, _, _>(pipe) main;
