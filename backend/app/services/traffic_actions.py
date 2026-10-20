"""Explicit service-chain experiments, not device/protocol emulation."""
from copy import deepcopy
from fastapi import HTTPException
from app.models.network import NodeDefinition, LinkDefinition
from app.engines.analytical_simulator import apply_scenario, validate_inputs


def apply_service_action(network, flows, kind, parameters):
    graph, traffic = deepcopy(network), deepcopy(flows)
    prefix = "candidate:service:"
    ids = {n.id for n in graph.nodes} | {e.id for e in graph.links}
    while any(i.startswith(prefix) for i in ids):
        prefix += "new:"
    if kind == "sd_wan":
        from app.services.wan_demo import wan_context, transformed_graph
        context = wan_context(network)
        if context is None:
            raise HTTPException(422, "SD-WAN needs declared branch_wan/wan_service roles and a WAN failure domain. Choose the labeled WAN sample or use the WAN demonstration.")
        failed, _, _ = apply_scenario(network, "link_failure", {"link_id": context[2].id})
        graph = transformed_graph(network, failed)
    elif kind == "cloud_security":
        edge = next((e for e in graph.links if e.id == parameters.get("link_id")), None)
        if edge is None:
            raise HTTPException(422, "Choose a valid link for a modeled cloud-security service chain.")
        old_target = edge.target_node_id
        node_id = prefix + "security"
        graph.nodes.append(NodeDefinition(id=node_id, name="Cloud security gateway (delay-only model)", device_type="router", role="cloud_security", metadata={"position": {"x": 350, "y": 180}}))
        edge.target_node_id, edge.target_interface_id = node_id, None
        graph.links.append(LinkDefinition(id=prefix+"security-egress", source_node_id=node_id, target_node_id=old_target,
                          bandwidth_mbps=edge.bandwidth_mbps, delay_ms=5, packet_loss_pct=0, status=edge.status,
                          metadata={"design_assumption": "Additional 5 ms service-chain delay; no threat detection or firewall policy efficacy modeled"}))
    elif kind == "load_balancer":
        target_id = parameters.get("node_id") or flows[0].target_node_id
        target = next((n for n in graph.nodes if n.id == target_id), None)
        if target is None or target.device_type != "server":
            raise HTTPException(422, "Choose an existing server as the load-balancer service endpoint.")
        target.name, target.device_type, target.role = "Load balancer (per-flow round robin)", "load_balancer", "load_balancer"
        targets = []
        for index in range(2):
            id = prefix + f"backend-{index}"
            targets.append(id)
            graph.nodes.append(NodeDefinition(id=id, name=f"Application replica {index+1}", device_type="server", role="application_replica", status=target.status, metadata={"position": {"x": 700, "y": index*200}}))
            graph.links.append(LinkDefinition(id=prefix+f"replica-link-{index}", source_node_id=target_id, target_node_id=id,
                              bandwidth_mbps=100, delay_ms=1, packet_loss_pct=0, status=target.status,
                              metadata={"design_assumption": "100 Mbps backend access, 1 ms delay; no CPU/service-time model"}))
        index = 0
        for flow in traffic:
            if flow.target_node_id == target_id:
                flow.target_node_id = targets[index % 2]
                index += 1
        if index == 0:
            raise HTTPException(422, "No application targets the selected service endpoint.")
    validate_inputs(graph)
    return graph, traffic
