"""Scenario + telemetry dataset generator for NetTransform (ML + NSGA-II pipeline).

    python generate_dataset.py --scenarios 400 --telemetry 60 --recovery 150 --seed 7 --out data
    python generate_dataset.py --topology my_topology.json --scenarios 200 --out data_mine   # your own saved topology

Outputs (CSV, every row carries provenance="simulated"):
  scenarios.csv        one row / scenario: topology+traffic+scenario features, before/after metrics, SLA labels,
                       and (for the first --recovery scenarios) the NSGA-II recovery outcome
  telemetry_links.csv  per-link time series (util, queue, loss, delay, counters) with measurement noise + fault label
  telemetry_nodes.csv  per-device time series (cpu, memory, temperature)
  pareto_fronts.csv    every Pareto-optimal recovery option NSGA-II found (for learning a recommender)
"""
from __future__ import annotations

import argparse, csv, json, math, os, random
import numpy as np, networkx as nx

from nettwin_engine import Flow, Link, Topo, evaluate, single_link_vulnerability
from nsga2 import run_nsga2, pareto_front

SLA = {"max_loss_pct": 1.0, "max_latency_ms": 50.0}
SCEN = ["baseline", "link_failure", "device_failure", "traffic_increase", "bandwidth_degradation", "capacity_increase"]


# ------------------------------------------------------------------ random enterprise topologies
def random_topology(rng: random.Random) -> Topo:
    t = Topo()
    n_core, n_dist, n_acc = rng.choice([1, 2]), rng.randint(2, 4), rng.randint(3, 6)
    cap = lambda: rng.choice([100, 1000, 1000, 10000])
    def add(n, typ): t.nodes[n] = {"type": typ, "up": True}
    def link(a, b, c, d):
        t.links[f"l{len(t.links)}"] = Link(f"l{len(t.links)}", a, b, c, d, rng.choice([0, 0, 0, 0.01, 0.05, 0.5]))
    core = [f"core{i}" for i in range(n_core)]; dist = [f"dist{i}" for i in range(n_dist)]; acc = [f"acc{i}" for i in range(n_acc)]
    for n in core: add(n, "router")
    for n in dist: add(n, "switch")
    for n in acc: add(n, "switch")
    if n_core == 2: link(core[0], core[1], 10000, round(rng.uniform(0.1, 0.5), 3))
    for d in dist:
        for c in core: link(d, c, cap() if rng.random() < .8 else 10000, round(rng.uniform(0.2, 2), 3))
    for a in acc:
        homes = rng.sample(dist, 2 if rng.random() < 0.5 and len(dist) > 1 else 1)   # dual-homing = redundancy
        for d in homes: link(a, d, cap(), round(rng.uniform(0.1, 1.5), 3))
        for h in range(rng.randint(1, 3)):
            n = f"{a}-h{h}"; add(n, rng.choice(["pc", "pc", "server"])); link(a, n, rng.choice([100, 1000]), round(rng.uniform(0.05, 0.5), 3))
    return t


def random_flows(topo: Topo, rng: random.Random, level: float) -> list:
    """Flow rates are a fraction of the bottleneck capacity of their own path (so the BASELINE is mostly healthy);
    `level` (0.5 / 1 / 1.5) moves the whole network from lightly to heavily loaded."""
    from nettwin_engine import logical_graph
    g = logical_graph(topo)
    hosts = sorted(n for n, v in topo.nodes.items() if v["type"] in ("pc", "server"))
    servers = [h for h in hosts if topo.nodes[h]["type"] == "server"] or hosts[-1:]
    flows = []
    for h in rng.sample(hosts, k=min(len(hosts), rng.randint(3, 10))):
        dst = rng.choice([s for s in servers if s != h] or [x for x in hosts if x != h])
        path = nx.shortest_path(g, h, dst, weight="weight")
        bottleneck = min(g[u][v]["cap"] for u, v in zip(path, path[1:]))
        flows.append(Flow(h, dst, round(bottleneck * rng.uniform(0.02, 0.25) * level, 3)))
    return flows


# ------------------------------------------------------------------ scenarios
def apply_scenario(topo: Topo, flows: list, kind: str, rng: random.Random):
    t, f, meta = topo.copy(), [Flow(x.src, x.dst, x.mbps) for x in flows], {"target": "", "magnitude": 0.0}
    links, nodes = sorted(t.links), sorted(n for n, v in t.nodes.items() if v["type"] in ("router", "switch"))
    if kind == "link_failure":
        lid = rng.choice(links); t.links[lid].up = False; meta.update(target=lid, magnitude=1.0)
    elif kind == "device_failure":
        n = rng.choice(nodes); t.nodes[n]["up"] = False; meta.update(target=n, magnitude=1.0)
    elif kind == "traffic_increase":
        m = round(rng.uniform(1.5, 8.0), 2); [setattr(x, "mbps", x.mbps * m) for x in f]; meta.update(target="all_flows", magnitude=m)
    elif kind == "bandwidth_degradation":
        lid = rng.choice(links); m = rng.choice([0.5, 0.25, 0.1]); t.links[lid].cap_mbps *= m; meta.update(target=lid, magnitude=m)
    elif kind == "capacity_increase":
        lid = rng.choice(links); t.links[lid].cap_mbps *= 4; meta.update(target=lid, magnitude=4.0)
    return t, f, meta


def topo_features(t: Topo, flows: list) -> dict:
    g = nx.Graph(); g.add_nodes_from(t.nodes)
    for l in t.links.values(): g.add_edge(l.a, l.b)
    caps = [l.cap_mbps for l in t.links.values()]
    return {"n_nodes": len(t.nodes), "n_links": len(t.links), "avg_degree": round(2 * g.number_of_edges() / max(1, g.number_of_nodes()), 3),
            "density": round(nx.density(g), 4), "n_bridges": len(list(nx.bridges(g))) if nx.is_connected(g) else -1,
            "diameter": nx.diameter(g) if nx.is_connected(g) else -1, "avg_link_cap_mbps": round(float(np.mean(caps)), 1),
            "min_link_cap_mbps": min(caps), "n_flows": len(flows), "total_offered_mbps": round(sum(x.mbps for x in flows), 2),
            "max_flow_mbps": max(x.mbps for x in flows)}


def metrics(prefix: str, r: dict) -> dict:
    s = r["summary"]; keep = ["delivery_ratio", "loss_pct", "mean_latency_ms", "max_latency_ms", "unreachable_flows", "max_link_utilization_pct",
                              "mean_utilization_of_used_links_pct", "high_utilization_links", "congested_links", "reachable_pairs_pct"]
    return {f"{prefix}_{k}": (round(s[k], 5) if isinstance(s[k], float) else s[k]) for k in keep}


def sla_label(s: dict) -> str:
    if s["unreachable_flows"] > 0 or s["delivery_ratio"] < 0.9: return "outage"
    if s["loss_pct"] > SLA["max_loss_pct"] or (s["mean_latency_ms"] or 0) > SLA["max_latency_ms"] or s["congested_links"] > 0: return "degraded"
    return "ok"


# ------------------------------------------------------------------ NSGA-II recovery (real search space)
N_NEW, N_UP = 6, 3     # --new-links / --upgrades: raise these (>= 14 / 6) and exhaustive search stops being possible


def recovery_actions(failed: Topo, base: Topo, flows: list, res: dict, rng: random.Random, n_new=None, n_up=None):
    n_new, n_up = n_new or N_NEW, n_up or N_UP
    acts = []
    broken_nodes = [n for n in failed.nodes if not failed.nodes[n]["up"]]
    broken_links = [l for l in failed.links if not failed.links[l].up]
    if broken_nodes or broken_links: acts.append(("repair_failed", 1 * (len(broken_nodes) + len(broken_links)), None))
    g = nx.Graph(); g.add_nodes_from(failed.nodes)
    for l in failed.links.values(): g.add_edge(l.a, l.b)
    net = [n for n, v in failed.nodes.items() if v["up"] and v["type"] in ("router", "switch")]
    cands = []
    for i, a in enumerate(net):
        for b in net[i + 1:]:
            if not g.has_edge(a, b):
                try: d = nx.shortest_path_length(res["graph"], a, b)
                except Exception: d = 99                       # different components -> most valuable
                cands.append((-d, a, b))
    cands.sort(); 
    for _, a, b in cands[:n_new]: acts.append((f"add_link:{a}-{b}", 3, ("add", a, b)))
    loaded = sorted(res["links"].items(), key=lambda kv: -kv[1]["offered_load_ratio"])[:n_up]
    for (u, v), s in loaded:
        if s["offered_load_ratio"] > 0.3: acts.append((f"upgrade:{u}-{v}", 2, ("up", s["ids"][0])))
    return acts


def apply_bits(failed: Topo, base: Topo, acts, bits) -> tuple:
    t, cost = failed.copy(), 0
    for bit, (name, c, spec) in zip(bits, acts):
        if not bit: continue
        cost += c
        if name == "repair_failed":
            for n in t.nodes: t.nodes[n]["up"] = base.nodes[n]["up"]
            for l in t.links: t.links[l].up = base.links[l].up
        elif spec[0] == "add":
            lid = f"new:{spec[1]}-{spec[2]}"; t.links[lid] = Link(lid, spec[1], spec[2], 1000, 1.0, 0.0)
        elif spec[0] == "up":
            t.links[spec[1]].cap_mbps *= 4
    return t, cost


def optimise_recovery(base: Topo, failed: Topo, flows: list, res_failed: dict, seed: int, pop=24, gens=15):
    rng = random.Random(seed)
    acts = recovery_actions(failed, base, flows, res_failed, rng)
    if not acts: return None
    cache = {}
    def ev(bits):
        t, cost = apply_bits(failed, base, acts, bits)
        r = evaluate(t, flows); s = r["summary"]
        vul = single_link_vulnerability(t, flows, r) if s["connected_flows"] == len(flows) else 1.0
        lat = (s["mean_latency_ms"] or SLA["max_latency_ms"] * 10) / SLA["max_latency_ms"]
        obj = [1 - s["delivery_ratio"], lat, vul, cost]
        cv = max(0.0, 0.95 - s["delivery_ratio"])                 # constraint: >= 95 % delivered
        cache[bits] = (obj, cv, s); return obj, cv
    res = run_nsga2(ev, len(acts), pop_size=pop, generations=gens, seed=seed, initial=[tuple([0] * len(acts))] + [tuple(int(i == j) for j in range(len(acts))) for i in range(len(acts))])
    front = pareto_front(res.archive)
    return acts, res, front, cache


def pick_knee(objs: list, weights=(0.4, 0.2, 0.2, 0.2)):
    a = np.array(objs); lo, hi = a.min(0), a.max(0); span = np.where(hi - lo > 0, hi - lo, 1)
    return int(np.argmin((((a - lo) / span) * np.array(weights)).sum(1)))


# ------------------------------------------------------------------ telemetry time series
def telemetry(topo: Topo, flows: list, kind: str, meta: dict, rng: random.Random, nprng, T: int, sid: str, w_links, w_nodes):
    t0 = rng.randint(T // 3, 2 * T // 3)
    phase = rng.uniform(0, 2 * math.pi)
    faulted, f_after, _ = apply_scenario(topo, flows, kind, random.Random(rng.random())) if kind != "baseline" else (topo, flows, meta)
    for tick in range(T):
        active = kind != "baseline" and tick >= t0
        mult = max(0.2, 1 + 0.25 * math.sin(2 * math.pi * tick / T + phase) + nprng.normal(0, 0.04) + (0.5 if nprng.random() < 0.03 else 0))
        cur_t, cur_f = (faulted, f_after) if active else (topo, flows)
        r = evaluate(cur_t, [Flow(x.src, x.dst, x.mbps * mult) for x in cur_f])
        tgt = meta_target(kind, faulted, topo)
        for (u, v), s in r["links"].items():
            noise = lambda sd: float(nprng.normal(0, sd))
            util = max(0.0, s["utilization_pct"] * (1 + noise(0.03)) + noise(0.3))
            w_links.writerow([sid, tick * 10, "|".join(s["ids"]), u, v, round(util, 3), round(max(0, s["offered_load_ratio"] * 100 * (1 + noise(0.03))), 3),
                              round(max(0, s["blocking_pct"] + s["loss_pct_cfg"] + noise(0.02)), 4), round(max(0, s["queue_pkts"] + noise(0.2)), 3),
                              round(s["delay_ms"] + s["sojourn_ms"] + float(nprng.exponential(0.05)), 4),
                              round(util / 100 * s["cap_mbps"], 3), int(nprng.poisson(0.02 + s["blocking_pct"])), int(active),
                              kind if active else "none", int(active and tgt is not None and (tgt in s["ids"] or tgt in (u, v))), 1, "simulated"])
        for lid, l in cur_t.links.items():              # a down interface reports oper_up=0, zero counters (not a missing row)
            if not cur_t.link_ok(l):
                w_links.writerow([sid, tick * 10, lid, l.a, l.b, 0, 0, 100.0, 0, "", 0, 0, int(active), kind if active else "none", int(active and tgt is not None and (tgt == lid or tgt in (l.a, l.b))), 0, "simulated"])
        pps = {n: 0.0 for n in topo.nodes}
        for (u, v), s in r["links"].items():
            for n in (u, v): pps[n] += s["offered_mbps"]
        for n, v in cur_t.nodes.items():
            if not v["up"]:
                w_nodes.writerow([sid, tick * 10, n, v["type"], 0, 0, 25.0, int(active), kind, "simulated"]); continue
            cap = {"router": 5000, "switch": 20000}.get(v["type"], 1000)
            cpu = min(100, 4 + 70 * pps[n] / cap + nprng.normal(0, 1.5))
            w_nodes.writerow([sid, tick * 10, n, v["type"], round(cpu, 2), round(35 + 0.1 * cpu + nprng.normal(0, 0.8), 2), round(30 + 0.25 * cpu + nprng.normal(0, 0.5), 2), int(active), kind if active else "none", "simulated"])


def meta_target(kind, faulted, topo):
    if kind in ("link_failure", "bandwidth_degradation", "capacity_increase"):
        for lid, l in faulted.links.items():
            a = topo.links[lid]
            if (l.up != a.up) or (l.cap_mbps != a.cap_mbps): return lid
    if kind == "device_failure":
        for n, v in faulted.nodes.items():
            if v["up"] != topo.nodes[n]["up"]: return n
    return None


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=400); ap.add_argument("--telemetry", type=int, default=60, help="scenarios that also get time series")
    ap.add_argument("--recovery", type=int, default=150, help="scenarios that also get an NSGA-II recovery search")
    ap.add_argument("--ticks", type=int, default=90); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--topology", help="NetTransform topology JSON (NetworkDefinition) to use instead of random topologies")
    ap.add_argument("--new-links", type=int, default=6); ap.add_argument("--upgrades", type=int, default=3)
    ap.add_argument("--out", default="data"); a = ap.parse_args()
    global N_NEW, N_UP; N_NEW, N_UP = a.new_links, a.upgrades
    os.makedirs(a.out, exist_ok=True); rng = random.Random(a.seed); nprng = np.random.default_rng(a.seed)
    fixed = Topo.from_project_json(json.load(open(a.topology))) if a.topology else None
    rows, fronts = [], []
    fl = open(f"{a.out}/telemetry_links.csv", "w", newline=""); fn = open(f"{a.out}/telemetry_nodes.csv", "w", newline="")
    wl, wn = csv.writer(fl), csv.writer(fn)
    wl.writerow("scenario_id,t_seconds,link_ids,node_u,node_v,util_pct,offered_load_pct,loss_pct,queue_pkts,latency_ms,throughput_mbps,error_counter,fault_active,fault_type,link_affected,oper_up,provenance".split(","))
    wn.writerow("scenario_id,t_seconds,node,device_type,cpu_pct,mem_pct,temp_c,fault_active,fault_type,provenance".split(","))
    for i in range(a.scenarios):
        topo = fixed.copy() if fixed else random_topology(rng)
        flows = random_flows(topo, rng, rng.choice([0.5, 1, 1, 1.5]))
        kind = SCEN[i % len(SCEN)]
        failed, f2, meta = apply_scenario(topo, flows, kind, rng)
        before, after = evaluate(topo, flows), evaluate(failed, f2)
        sid = f"s{i:05d}"
        row = {"scenario_id": sid, "scenario": kind, "target": meta["target"], "magnitude": meta["magnitude"], **topo_features(topo, flows),
               **metrics("before", before), **metrics("after", after), "label_before": sla_label(before["summary"]), "label_after": sla_label(after["summary"]),
               "delta_delivery": round(after["summary"]["delivery_ratio"] - before["summary"]["delivery_ratio"], 5), "provenance": "simulated"}
        if i < a.recovery and kind in ("link_failure", "device_failure", "traffic_increase", "bandwidth_degradation") and row["label_after"] != "ok":
            out = optimise_recovery(topo, failed, f2, after, a.seed + i)
            if out:
                acts, res, front, cache = out
                objs = [cache[k][0] for k in front] if front else []
                row.update(recovery_pareto_size=len(front), recovery_search_space=res.search_space_size, recovery_evaluations=len(res.archive))
                if front:
                    k = front[pick_knee(objs)]
                    row.update(recovery_choice="+".join(n for b, (n, _, _) in zip(k, acts) if b) or "retain",
                               recovery_choice_cost=cache[k][0][3], recovery_choice_delivery=round(1 - cache[k][0][0], 4),
                               recovery_choice_latency_ms=cache[k][2]["mean_latency_ms"])
                    for kk in front:
                        fronts.append({"scenario_id": sid, "actions": "+".join(n for b, (n, _, _) in zip(kk, acts) if b) or "retain",
                                       "undelivered_fraction": round(cache[kk][0][0], 5), "latency_ratio": round(cache[kk][0][1], 5),
                                       "single_link_vulnerability": round(cache[kk][0][2], 4), "cost": cache[kk][0][3], "is_knee": kk == k})
        rows.append(row)
        if i < a.telemetry: telemetry(topo, flows, kind, meta, rng, nprng, a.ticks, sid, wl, wn)
        if (i + 1) % 50 == 0: print(f"{i+1}/{a.scenarios} scenarios", flush=True)
    fl.close(); fn.close()
    cols = sorted({k for r in rows for k in r}, key=lambda c: (c not in ("scenario_id", "scenario"), c))
    with open(f"{a.out}/scenarios.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    if fronts:
        with open(f"{a.out}/pareto_fronts.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(fronts[0])); w.writeheader(); w.writerows(fronts)
    print("done:", a.out, len(rows), "scenarios,", len(fronts), "pareto options")


if __name__ == "__main__":
    main()
