from __future__ import annotations

from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from typing import Iterable, List

from app.models.network import (
    InterfaceDefinition,
    LinkDefinition,
    NetworkDefinition,
    NodeDefinition,
    ValidationIssue,
)

SUPPORTED_DEVICE_TYPES = {"router", "switch", "hub", "access_point", "pc", "server", "load_balancer"}
SUPPORTED_CABLE_TYPES = {"straight-through", "crossover", "fiber", "serial", "console"}


def _make_issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path=path, code=code, message=message)


def _network_for_ip(ip_value: str, mask_value: str) -> IPv4Network:
    return IPv4Network(f"{ip_value}/{mask_value}", strict=False)


def validate_network_definition(network: NetworkDefinition) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    seen_node_ids: set[str] = set()
    seen_link_ids: set[str] = set()
    interface_lookup: dict[str, InterfaceDefinition] = {}
    allocated_ips: dict[str, str] = {}

    for node in network.nodes:
        if node.id in seen_node_ids:
            issues.append(_make_issue(f"nodes[{node.id}]", "duplicate_node_id", f"Duplicate node id '{node.id}' detected."))
        else:
            seen_node_ids.add(node.id)

        if node.device_type not in SUPPORTED_DEVICE_TYPES:
            issues.append(_make_issue(f"nodes.{node.id}.device_type", "unsupported_device_type", f"Unsupported device type '{node.device_type}'."))

        for iface in node.interfaces:
            interface_lookup[f"{node.id}:{iface.id}"] = iface
            if iface.id in [existing.id for existing in node.interfaces if existing is not iface]:
                issues.append(_make_issue(f"nodes.{node.id}.interfaces", "duplicate_interface_id", f"Duplicate interface id '{iface.id}' detected."))
            if iface.ip_configuration:
                ip_value = iface.ip_configuration.ip_address
                mask_value = iface.ip_configuration.subnet_mask
                if ip_value in allocated_ips:
                    issues.append(_make_issue(f"nodes.{node.id}.interfaces.{iface.id}.ip_configuration.ip_address", "duplicate_ip", f"IP address '{ip_value}' is already assigned to '{allocated_ips[ip_value]}'."))
                else:
                    allocated_ips[ip_value] = f"{node.id}:{iface.id}"
                try:
                    network_obj = _network_for_ip(ip_value, mask_value)
                    if iface.ip_configuration.gateway:
                        gateway = iface.ip_configuration.gateway
                        try:
                            if IPv4Address(gateway) not in network_obj:
                                issues.append(
                                    _make_issue(
                                        f"nodes.{node.id}.interfaces.{iface.id}.ip_configuration.gateway",
                                        "gateway_outside_subnet",
                                        f"Gateway '{gateway}' is outside the subnet '{network_obj}' for interface '{iface.id}'.",
                                    )
                                )
                        except ValueError:
                            issues.append(_make_issue(f"nodes.{node.id}.interfaces.{iface.id}.ip_configuration.gateway", "invalid_gateway", f"Gateway '{gateway}' is not a valid IPv4 address."))
                except ValueError:
                    issues.append(_make_issue(f"nodes.{node.id}.interfaces.{iface.id}.ip_configuration", "invalid_subnet", f"Invalid subnet for interface '{iface.id}'."))

    for link in network.links:
        if link.id in seen_link_ids:
            issues.append(_make_issue(f"links[{link.id}]", "duplicate_link_id", f"Duplicate link id '{link.id}' detected."))
        else:
            seen_link_ids.add(link.id)

        if link.cable_type not in SUPPORTED_CABLE_TYPES:
            issues.append(_make_issue(f"links.{link.id}.cable_type", "unsupported_cable_type", f"Unsupported cable type '{link.cable_type}'."))

        if link.source_node_id not in seen_node_ids:
            issues.append(_make_issue(f"links.{link.id}.source_node_id", "missing_source_node", f"Source node '{link.source_node_id}' does not exist."))
        if link.target_node_id not in seen_node_ids:
            issues.append(_make_issue(f"links.{link.id}.target_node_id", "missing_target_node", f"Target node '{link.target_node_id}' does not exist."))

        if link.source_interface_id:
            source_key = f"{link.source_node_id}:{link.source_interface_id}"
            if source_key not in interface_lookup:
                issues.append(_make_issue(f"links.{link.id}.source_interface_id", "missing_source_interface", f"Source interface '{link.source_interface_id}' on node '{link.source_node_id}' does not exist."))

        if link.target_interface_id:
            target_key = f"{link.target_node_id}:{link.target_interface_id}"
            if target_key not in interface_lookup:
                issues.append(_make_issue(f"links.{link.id}.target_interface_id", "missing_target_interface", f"Target interface '{link.target_interface_id}' on node '{link.target_node_id}' does not exist."))

        if link.source_node_id == link.target_node_id:
            issues.append(_make_issue(f"links.{link.id}", "self_link", "A link cannot connect a node to itself."))

        if link.bandwidth_mbps is not None and link.bandwidth_mbps <= 0:
            issues.append(_make_issue(f"links.{link.id}.bandwidth_mbps", "invalid_bandwidth", "Bandwidth must be greater than zero."))
        if link.delay_ms is not None and link.delay_ms < 0:
            issues.append(_make_issue(f"links.{link.id}.delay_ms", "invalid_delay", "Delay cannot be negative."))
        if link.packet_loss_pct is not None and not 0 <= link.packet_loss_pct <= 100:
            issues.append(_make_issue(f"links.{link.id}.packet_loss_pct", "invalid_packet_loss", "Packet loss must be between 0 and 100."))

    if network.routing.default_gateway:
        try:
            IPv4Address(network.routing.default_gateway)
        except ValueError:
            issues.append(_make_issue("routing.default_gateway", "invalid_default_gateway", "Default gateway is not a valid IPv4 address."))

    return issues


def validate_network_payload(payload: NetworkDefinition) -> dict:
    errors = validate_network_definition(payload)
    return {"valid": not errors, "errors": [error.model_dump() for error in errors]}
