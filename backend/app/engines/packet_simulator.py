"""Discrete-event extension sharing the canonical graph and operational rules.

Fixed-size synthetic packet arrivals, store-and-forward, finite shared queues.
An undirected connection has ONE shared service capacity in both directions.
TCP/UDP are workload labels: no handshake, ACK, retransmission or congestion control.
"""
import heapq
import math
import random
from itertools import count
import networkx as nx
from fastapi import HTTPException
from app.engines.analytical_simulator import validate_inputs, _edge_cost
from app.engines.graph_adapter import network_graph

MAX_PACKETS = 20000
MAX_HOPS = 200000


def flow_route(network, flow, assumptions):
    graph = network_graph(network)
    # Preserve chosen physical link IDs when projecting parallel links for Dijkstra.
    weighted = nx.Graph()
    weighted.add_nodes_from(sorted(graph.nodes))
    for u, v, key, data in sorted(graph.edges(keys=True, data=True), key=lambda e: e[2]):
        cost = _edge_cost(data["definition"], flow.offered_mbps, flow.packet_size_bytes, assumptions)
        old = weighted.get_edge_data(u, v)
        if old is None or (cost, key) < (old["weight"], old["id"]):
            weighted.add_edge(u, v, weight=cost, id=key)
    try:
        nodes = nx.shortest_path(weighted, flow.source_node_id, flow.target_node_id, weight="weight", method="dijkstra")
        return nodes, [weighted[u][v]["id"] for u, v in zip(nodes, nodes[1:])]
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return [], []


def simulate_packets(network, flows, duration=1, queue_packets=32, seed=17, prioritize=False):
    validate_inputs(network)
    if network.routing.static_routes or network.security.firewall_rules or network.security.segmentation:
        raise HTTPException(422, "Packet mode does not implement static routes, firewall rules or segmentation policies.")
    node_ids = {n.id for n in network.nodes}
    if any(f.source_node_id not in node_ids or f.target_node_id not in node_ids for f in flows):
        raise HTTPException(422, "A traffic endpoint is absent from the topology.")
    assumptions = set()
    routes = [flow_route(network, f, assumptions) for f in flows]
    # Peak traffic occurs during the second half of the observation interval.
    schedules = []
    for f in flows:
        times = []
        for start, multiplier in ((0, 1), (duration / 2, f.peak_multiplier)):
            spacing = f.packet_size_bytes * 8 / (f.offered_mbps * multiplier * 1e6)
            packets = math.floor(duration / 2 / spacing + 1e-9)
            if packets + sum(len(x) for x in schedules) + len(times) > MAX_PACKETS:
                raise HTTPException(422, "Packet budget exceeded (20,000). Reduce traffic, peak multiplier or duration; packets are never silently sampled.")
            times.extend(start + (i + .5) * spacing for i in range(packets))
        schedules.append(times)
        if not times:
            raise HTTPException(422, f"Flow {f.id} generates no complete packets in this interval. Increase its rate or duration.")
    if sum(len(t) * max(1, len(r[1])) for t, r in zip(schedules, routes)) > MAX_HOPS:
        raise HTTPException(422, "Packet-hop budget exceeded (200,000). Reduce traffic or graph size.")
    links = {e.id: e for e in network.links}
    queues = {key: [] for key in links}
    busy = {key: False for key in links}
    stats = {key: {"id": key, "status": e.status, "busy_seconds": 0., "arrivals": 0, "drops": 0, "queue_drops": 0, "random_drops": 0, "max_queue": 0} for key, e in links.items()}
    results = [{"id": f.id, "application": f.application, "users": f.users, "protocol": f.protocol, "priority": f.priority,
                "sent": 0, "delivered": 0, "dropped": 0, "latencies": [], "route_node_ids": r[0], "route_link_ids": r[1]} for f, r in zip(flows, routes)]
    series = [{"time_seconds": round((i + 1) * duration / 20, 6), "delivered_bits": 0, "dropped": 0} for i in range(20)]
    events, sequence = [], count()
    rng = random.Random(seed)

    def event(time, kind, packet, link=None):
        heapq.heappush(events, (time, next(sequence), kind, packet, link))

    def bucket(time):
        return min(19, int(time / duration * 20))

    def drop(packet, time):
        results[packet[0]]["dropped"] += 1
        series[bucket(time)]["dropped"] += 1

    def start_service(link_id, packet, time):
        busy[link_id] = True
        link = links[link_id]
        capacity = link.bandwidth_mbps if link.bandwidth_mbps is not None else 1000
        service = flows[packet[0]].packet_size_bytes * 8 / (capacity * 1e6)
        stats[link_id]["busy_seconds"] += max(0, min(duration, time + service) - time)
        event(time + service, "complete", packet, link_id)

    for index, times in enumerate(schedules):
        for time in times:
            event(time, "generate", (index, time, 0))
    while events:
        time, _, kind, packet, link_id = heapq.heappop(events)
        if time > duration:
            break
        index, born, hop = packet
        flow = flows[index]
        route = routes[index][1]
        if kind == "generate":
            results[index]["sent"] += 1
            if not route:
                drop(packet, time)
                continue
            event(time, "arrive", packet)
        elif kind == "arrive":
            if hop == len(route):
                results[index]["delivered"] += 1
                results[index]["latencies"].append((time - born) * 1000)
                series[bucket(time)]["delivered_bits"] += flow.packet_size_bytes * 8
                continue
            link_id = route[hop]
            stat = stats[link_id]
            stat["arrivals"] += 1
            if not busy[link_id]:
                start_service(link_id, packet, time)
            elif len(queues[link_id]) >= queue_packets:
                stat["drops"] += 1
                stat["queue_drops"] += 1
                drop(packet, time)
            else:
                heapq.heappush(queues[link_id], (flow.priority if prioritize else 0, next(sequence), packet))
                stat["max_queue"] = max(stat["max_queue"], len(queues[link_id]))
        else:
            link = links[link_id]
            if rng.random() < (link.packet_loss_pct or 0) / 100:
                stats[link_id]["drops"] += 1
                stats[link_id]["random_drops"] += 1
                drop(packet, time)
            else:
                event(time + (link.delay_ms if link.delay_ms is not None else 1) / 1000, "arrive", (index, born, hop + 1))
            if queues[link_id]:
                start_service(link_id, heapq.heappop(queues[link_id])[2], time)
            else:
                busy[link_id] = False
    latencies = []
    for flow, result in zip(flows, results):
        latencies.extend(result["latencies"])
        values = result.pop("latencies")
        result.update(pending=result["sent"] - result["delivered"] - result["dropped"],
                      throughput_mbps=result["delivered"] * flow.packet_size_bytes * 8 / duration / 1e6,
                      packet_loss_pct=100 * result["dropped"] / result["sent"] if result["sent"] else None,
                      average_latency_ms=sum(values) / len(values) if values else None,
                      flow_connected=bool(result["route_link_ids"]))
    for key, stat in stats.items():
        stat["utilization_pct"] = min(100, 100 * stat.pop("busy_seconds") / duration)
        stat["congested"] = stat["queue_drops"] > 0 or stat["utilization_pct"] >= 95
        stat["on_route"] = any(key in route[1] for route in routes)
    for row in series:
        row["throughput_mbps"] = row.pop("delivered_bits") / (duration / 20) / 1e6
    sent, delivered, dropped = (sum(r[key] for r in results) for key in ("sent", "delivered", "dropped"))
    for link in network.links:
        if link.bandwidth_mbps is None or link.delay_ms is None or link.packet_loss_pct is None:
            assumptions.add(f"Unconfigured fields on {link.id}: defaults 1000 Mbps / 1 ms / 0% loss, never measurements.")
    return {"flows": results, "links": list(stats.values()), "series": series,
            "nodes": [{"id": n.id, "status": n.status, "flow_ids": [r["id"] for r in results if n.id in r["route_node_ids"]],
                       "unreachable_destination": any(f.target_node_id == n.id and not r["flow_connected"] for f, r in zip(flows, results))} for n in network.nodes],
            "sent": sent, "delivered": delivered, "dropped": dropped, "pending": sent - delivered - dropped,
            "throughput_mbps": sum(r["throughput_mbps"] for r in results), "packet_loss_pct": 100 * dropped / sent if sent else None,
            "average_latency_ms": sum(latencies) / len(latencies) if latencies else None,
            "connectivity_pct": 100 * sum(r["flow_connected"] for r in results) / len(flows),
            "mean_link_utilization_pct": sum(s["utilization_pct"] for s in stats.values()) / max(1, len(stats)),
            "assumptions": sorted(assumptions), "provenance": "synthetic_discrete_event", "engine_version": "network-traffic-events/1.0"}
