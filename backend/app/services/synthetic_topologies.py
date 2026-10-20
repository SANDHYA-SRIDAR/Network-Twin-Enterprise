"""Seeded synthetic enterprise topology generator.

Provides deterministic baseline training graphs and disjoint evaluation graphs.
These are modeled synthetic topologies, not physical network measurements.
"""
from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from app.models.network import (
    InterfaceDefinition,
    IPConfiguration,
    LinkDefinition,
    NetworkDefinition,
    NodeDefinition,
)

TRAIN_SEED_START = 1000
TRAIN_SEED_COUNT = 25
VAL_SEED_START = 2000
VAL_SEED_COUNT = 10
TEST_SEED_START = 3000
TEST_SEED_COUNT = 50
STAGE2B_TEST_SEED_START = 4000
STAGE2B_TEST_SEED_COUNT = 50



def generate_synthetic_enterprise_topology(seed: int, *, name: str | None = None) -> NetworkDefinition:
    """Generate a realistic enterprise network with core, distribution, access, and server tiers."""
    rng = random.Random(seed)
    topo_name = name or f"Enterprise-Synthetic-{seed}"

    nodes: list[NodeDefinition] = []
    links: list[LinkDefinition] = []

    # 1. Core layer: 2 redundant core routers
    for i in (1, 2):
        cid = f"core-{i}"
        nodes.append(NodeDefinition(
            id=cid,
            name=f"Core-Router-{i}",
            device_type="router",
            role="core",
            status="active",
            interfaces=[
                InterfaceDefinition(
                    id=f"{cid}-eth0",
                    name="GigabitEthernet0/0",
                    ip_configuration=IPConfiguration(ip_address=f"10.0.0.{i}", subnet_mask="255.255.255.0"),
                )
            ],
            resources={"processing_capacity_mbps": 10000.0},
        ))

    # Link between cores
    links.append(LinkDefinition(
        id="link:core1-core2",
        source_node_id="core-1",
        target_node_id="core-2",
        bandwidth_mbps=10000.0,
        delay_ms=0.5 + rng.random() * 0.5,
        packet_loss_pct=0.0,
    ))

    # 2. Distribution layer: 2 or 3 distribution switches
    dist_count = 2 if rng.random() < 0.5 else 3
    for d in range(1, dist_count + 1):
        did = f"dist-{d}"
        nodes.append(NodeDefinition(
            id=did,
            name=f"Dist-Switch-{d}",
            device_type="switch",
            role="distribution",
            status="active",
            interfaces=[
                InterfaceDefinition(
                    id=f"{did}-eth0",
                    name="FastEthernet0/1",
                    ip_configuration=IPConfiguration(
                        ip_address=f"10.0.1.{d}", subnet_mask="255.255.255.0"
                    ),
                )
            ],
            resources={"processing_capacity_mbps": 5000.0},
        ))
        # Dual-homed to both core routers
        links.append(LinkDefinition(
            id=f"link:{did}-core1",
            source_node_id=did,
            target_node_id="core-1",
            bandwidth_mbps=rng.choice([1000.0, 2500.0, 10000.0]),
            delay_ms=0.8 + rng.random() * 0.8,
            packet_loss_pct=round(rng.random() * 0.02, 4),
        ))
        links.append(LinkDefinition(
            id=f"link:{did}-core2",
            source_node_id=did,
            target_node_id="core-2",
            bandwidth_mbps=rng.choice([1000.0, 2500.0, 10000.0]),
            delay_ms=0.8 + rng.random() * 0.8,
            packet_loss_pct=round(rng.random() * 0.02, 4),
        ))

    # Cross-link between dist-1 and dist-2
    links.append(LinkDefinition(
        id="link:dist1-dist2",
        source_node_id="dist-1",
        target_node_id="dist-2",
        bandwidth_mbps=2500.0,
        delay_ms=0.8 + rng.random() * 0.5,
        packet_loss_pct=0.0,
    ))

    # 3. Server farm: 2 servers attached to distribution layer
    for s_idx, s_role in enumerate(["dns", "web"], 1):
        sid = f"server-{s_role}"
        nodes.append(NodeDefinition(
            id=sid,
            name=f"Server-{s_role.upper()}",
            device_type="server",
            role="server",
            status="active",
            interfaces=[
                InterfaceDefinition(
                    id=f"{sid}-eth0",
                    name="eth0",
                    ip_configuration=IPConfiguration(
                        ip_address=f"10.0.2.{s_idx}", subnet_mask="255.255.255.0"
                    ),
                )
            ],
            resources={"processing_capacity_mbps": 2000.0},
        ))
        target_dist = "dist-1" if s_idx == 1 else "dist-2"
        links.append(LinkDefinition(
            id=f"link:{sid}-{target_dist}",
            source_node_id=sid,
            target_node_id=target_dist,
            bandwidth_mbps=rng.choice([1000.0, 2500.0]),
            delay_ms=0.5 + rng.random() * 0.5,
            packet_loss_pct=0.0,
        ))

    # 4. Access layer: 2 or 3 access switches
    acc_count = 2 if rng.random() < 0.5 else 3
    for a in range(1, acc_count + 1):
        aid = f"acc-{a}"
        nodes.append(NodeDefinition(
            id=aid,
            name=f"Access-Switch-{a}",
            device_type="switch",
            role="access",
            status="active",
            interfaces=[
                InterfaceDefinition(
                    id=f"{aid}-eth0",
                    name="FastEthernet0/1",
                    ip_configuration=IPConfiguration(
                        ip_address=f"10.0.3.{a}", subnet_mask="255.255.255.0"
                    ),
                )
            ],
            resources={"processing_capacity_mbps": 1000.0},
        ))
        # Uplink to dist switches
        primary_dist = f"dist-{((a - 1) % dist_count) + 1}"
        links.append(LinkDefinition(
            id=f"link:{aid}-{primary_dist}",
            source_node_id=aid,
            target_node_id=primary_dist,
            bandwidth_mbps=1000.0,
            delay_ms=1.0 + rng.random() * 1.0,
            packet_loss_pct=round(rng.random() * 0.03, 4),
        ))
        # Some access switches have secondary redundant uplink
        if rng.random() < 0.6:
            secondary_dist = "dist-2" if primary_dist == "dist-1" else "dist-1"
            links.append(LinkDefinition(
                id=f"link:{aid}-{secondary_dist}",
                source_node_id=aid,
                target_node_id=secondary_dist,
                bandwidth_mbps=1000.0,
                delay_ms=1.0 + rng.random() * 1.0,
                packet_loss_pct=round(rng.random() * 0.03, 4),
            ))

        # 5. Workstation PC on this access switch
        pid = f"pc-{a}"
        nodes.append(NodeDefinition(
            id=pid,
            name=f"PC-{a}",
            device_type="pc",
            role="endpoint",
            status="active",
            interfaces=[
                InterfaceDefinition(
                    id=f"{pid}-eth0",
                    name="eth0",
                    ip_configuration=IPConfiguration(
                        ip_address=f"10.0.4.{a}", subnet_mask="255.255.255.0"
                    ),
                )
            ],
            resources={},
        ))
        links.append(LinkDefinition(
            id=f"link:{pid}-{aid}",
            source_node_id=pid,
            target_node_id=aid,
            bandwidth_mbps=1000.0,
            delay_ms=1.0 + rng.random() * 0.5,
            packet_loss_pct=0.0,
        ))

    return NetworkDefinition(name=topo_name, nodes=nodes, links=links)


def get_training_topologies() -> list[NetworkDefinition]:
    """25 deterministic topologies for baseline fitting."""
    return [
        generate_synthetic_enterprise_topology(s, name=f"Enterprise-Train-{s}")
        for s in range(TRAIN_SEED_START, TRAIN_SEED_START + TRAIN_SEED_COUNT)
    ]


def get_validation_topologies() -> list[NetworkDefinition]:
    """10 validation topologies using disjoint seeds."""
    return [
        generate_synthetic_enterprise_topology(s, name=f"Enterprise-Val-{s}")
        for s in range(VAL_SEED_START, VAL_SEED_START + VAL_SEED_COUNT)
    ]


def get_test_topologies() -> list[NetworkDefinition]:
    """50 evaluation test topologies using disjoint seeds."""
    return [
        generate_synthetic_enterprise_topology(s, name=f"Enterprise-Test-{s}")
        for s in range(TEST_SEED_START, TEST_SEED_START + TEST_SEED_COUNT)
    ]


def get_stage2b_test_topologies() -> list[NetworkDefinition]:
    """50 fresh evaluation test topologies for Stage 2b using disjoint seeds 4000..4049."""
    return [
        generate_synthetic_enterprise_topology(s, name=f"Enterprise-Stage2b-Test-{s}")
        for s in range(STAGE2B_TEST_SEED_START, STAGE2B_TEST_SEED_START + STAGE2B_TEST_SEED_COUNT)
    ]


def inject_anomaly(
    base: NetworkDefinition, anomaly_type: str, seed: int
) -> tuple[NetworkDefinition, dict[str, Any]]:
    """Inject a known anomaly into a topology for evaluation."""
    from app.models.failure_simulation import TrafficDemand

    rng = random.Random(seed)
    topo = deepcopy(base)
    ground_truth: dict[str, Any] = {"anomaly_type": anomaly_type, "target_id": None}

    if anomaly_type == "overloaded_link":
        # Applies real offered load above link capacity (e.g. 1.5x capacity)
        # Select an operational access/distribution uplink
        candidate_links = [l for l in topo.links if ("acc" in l.id and "dist" in l.id) or ("pc" in l.id and "acc" in l.id)]
        link = rng.choice(candidate_links) if candidate_links else topo.links[0]
        cap = link.bandwidth_mbps if link.bandwidth_mbps is not None else 1000.0
        # Create traffic demand passing across this path with offered load > capacity
        traffic = TrafficDemand(source_node_id="pc-1", target_node_id="server-web", offered_mbps=cap * 1.5)
        ground_truth["target_id"] = link.id
        ground_truth["feature"] = "offered_load_ratio"
        ground_truth["injected_value"] = 1.5
        ground_truth["traffic"] = traffic

    elif anomaly_type == "contextual_subtle_anomaly":
        # Subtle multidimensional anomaly on core trunk that fixed threshold rules cannot express
        # Individual metrics are within normal ranges (delay < 25ms, loss < 5%, bw > 50Mbps)
        # But for a core router-to-router trunk, the combination is abnormal.
        core_links = [l for l in topo.links if "core" in l.source_node_id and "core" in l.target_node_id]
        link = core_links[0] if core_links else topo.links[0]
        link.delay_ms = 18.0
        link.packet_loss_pct = 2.5
        link.bandwidth_mbps = 1000.0
        ground_truth["target_id"] = link.id
        ground_truth["feature"] = "contextual_impairment"
        ground_truth["injected_value"] = {"delay_ms": 18.0, "packet_loss_pct": 2.5, "bandwidth_mbps": 1000.0}

    elif anomaly_type == "lossy_link":
        link = rng.choice(topo.links)
        link.packet_loss_pct = float(rng.randint(8, 25))
        ground_truth["target_id"] = link.id
        ground_truth["feature"] = "packet_loss_pct"
        ground_truth["injected_value"] = link.packet_loss_pct

    elif anomaly_type == "high_delay_link":
        link = rng.choice(topo.links)
        link.delay_ms = float(rng.randint(60, 200))
        ground_truth["target_id"] = link.id
        ground_truth["feature"] = "delay_ms"
        ground_truth["injected_value"] = link.delay_ms

    elif anomaly_type == "bridge_link":
        # Create an artificial bridge link to a new subnet leaf
        leaf_id = f"leaf-node-{seed}"
        topo.nodes.append(NodeDefinition(
            id=leaf_id, name=f"Leaf-{seed}", device_type="server", status="active"
        ))
        bridge_id = f"link:bridge-{seed}"
        core = topo.nodes[0].id
        topo.links.append(LinkDefinition(
            id=bridge_id, source_node_id=core, target_node_id=leaf_id,
            bandwidth_mbps=1000.0, delay_ms=1.0, packet_loss_pct=0.0
        ))
        ground_truth["target_id"] = bridge_id
        ground_truth["feature"] = "is_bridge"
        ground_truth["injected_value"] = True

    elif anomaly_type == "isolated_node":
        # A completely isolated node
        iso_id = f"isolated-{seed}"
        topo.nodes.append(NodeDefinition(
            id=iso_id, name=f"Isolated-{seed}", device_type="server", status="active"
        ))
        ground_truth["target_id"] = iso_id
        ground_truth["feature"] = "is_isolated"
        ground_truth["injected_value"] = True

    elif anomaly_type == "duplicate_ip":
        # Config issue: duplicate IP on interface
        if len(topo.nodes) >= 2 and topo.nodes[0].interfaces and topo.nodes[1].interfaces:
            target_ip = topo.nodes[0].interfaces[0].ip_configuration.ip_address
            topo.nodes[1].interfaces[0].ip_configuration.ip_address = target_ip
            ground_truth["target_id"] = topo.nodes[1].id
            ground_truth["feature"] = "duplicate_ip"
            ground_truth["injected_value"] = target_ip

    return topo, ground_truth
