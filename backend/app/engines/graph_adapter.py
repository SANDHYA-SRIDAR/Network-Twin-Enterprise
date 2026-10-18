"""Ephemeral NetworkX views; Pydantic/Supabase remain the only topology model/store."""
import networkx as nx

from app.models.network import NetworkDefinition

DOWN = {"down", "offline", "failed", "unavailable"}


def operational(link, nodes) -> bool:
    if link.status in DOWN or nodes[link.source_node_id].status in DOWN or nodes[link.target_node_id].status in DOWN:
        return False
    for node_id, interface_id in ((link.source_node_id, link.source_interface_id), (link.target_node_id, link.target_interface_id)):
        if interface_id and next(i for i in nodes[node_id].interfaces if i.id == interface_id).status in DOWN:
            return False
    return link.cable_type != "console"


def network_graph(network: NetworkDefinition, operational_only: bool = True) -> nx.MultiGraph:
    graph = nx.MultiGraph()
    nodes = {n.id: n for n in network.nodes}
    for node in sorted(network.nodes, key=lambda n: n.id):
        if not operational_only or node.status not in DOWN:
            graph.add_node(node.id, definition=node)
    for link in sorted(network.links, key=lambda e: e.id):
        if not operational_only or operational(link, nodes):
            graph.add_edge(link.source_node_id, link.target_node_id, key=link.id,
                           id=link.id, definition=link, operational=operational(link, nodes))
    return graph


def structural_analysis(network: NetworkDefinition, seed: int = 17) -> dict:
    graph = network_graph(network)
    # Louvain uses an explicitly undirected structural projection, not traffic/cost weights.
    # Each operational parallel connection contributes one unit of adjacency strength.
    projection = nx.Graph()
    projection.add_nodes_from(graph.nodes)
    for u, v in graph.edges():
        projection.add_edge(u, v, weight=projection.get_edge_data(u, v, {}).get("weight", 0) + 1)
    if projection.number_of_edges():
        communities = nx.community.louvain_communities(projection, weight="weight", seed=seed)
        modularity = nx.community.modularity(projection, communities, weight="weight")
    else:
        communities = [{node} for node in sorted(graph.nodes)]
        modularity = None  # No edges: modularity's denominator is undefined.
    ordered = sorted((sorted(group) for group in communities), key=lambda group: tuple(group))
    membership = {node: index for index, group in enumerate(ordered) for node in group}
    bridges = sorted(key for u, v in nx.bridges(projection) if graph.number_of_edges(u, v) == 1 for key in graph[u][v])
    return {
        "graph_type": "undirected_multigraph", "operational_nodes": graph.number_of_nodes(),
        "operational_links": graph.number_of_edges(),
        "connected_components": [sorted(c) for c in sorted(nx.connected_components(graph), key=lambda c: tuple(sorted(c)))],
        "bridge_link_ids": bridges, "degree": dict(sorted(graph.degree())),
        "communities": ordered, "membership": membership, "modularity": modularity,
        "community_algorithm": "networkx_louvain", "seed": seed,
        "community_weight_basis": "count of operational parallel connections, not bandwidth or measured traffic",
        "unavailable_node_ids": sorted(n.id for n in network.nodes if n.id not in graph),
        "provenance": "analytical_structure", "limitations": ["Community membership is not evidence of an anomaly.", "No directed conversion: directed inputs are rejected by the canonical schema."],
    }


def graph_changes(before: NetworkDefinition, after: NetworkDefinition) -> dict:
    result = {}
    for field in ("nodes", "links"):
        old = {x.id: x.model_dump(mode="json") for x in getattr(before, field)}
        new = {x.id: x.model_dump(mode="json") for x in getattr(after, field)}
        result[field] = {"added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
                         "changed": sorted(key for key in old.keys() & new.keys() if old[key] != new[key])}
    return result
