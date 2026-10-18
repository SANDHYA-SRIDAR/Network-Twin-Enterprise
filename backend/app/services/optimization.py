"""Bounded NSGA-II over combinations of the existing, explicitly modeled actions."""
from copy import deepcopy
from time import monotonic
import json
from threading import Lock

from fastapi import HTTPException
from app.engines.analytical_simulator import DOWN, shortest_path
from app.models.network import NetworkDefinition
from app.services.transformation import evaluate_candidate

OBJECTIVES = ["undelivered_fraction", "unreachable_fraction", "latency_target_ratio",
              "loss_fraction", "single_link_vulnerability", "change_units", "change_count"]
_SEARCH_LOCK = Lock()  # pymoo 0.6.1.6 seeds global RNG state: serialize seeded searches.


def dominates(left, right):
    return all(a <= b for a, b in zip(left, right)) and any(a < b for a, b in zip(left, right))


def objective_values(candidate, demand, criteria):
    m = candidate["metrics"]
    latency = m["average_latency_ms"]
    # Finite penalty only for optimization; displayed unsupported latency stays null.
    return [1 - min(1, m["throughput_mbps"] / demand.offered_mbps),
            1 - m["reachable_nodes"] / max(1, m["total_nodes"]),
            latency / criteria.latency_target_ms if latency is not None else 1_000_000.0,
            m["packet_loss_pct"] / 100, 1 - candidate["components"]["resilience"],
            candidate["change_units"], len(candidate["changes"])]


def recovery_constraints(candidate, demand, criteria):
    m = candidate["metrics"]
    errors = list(candidate["constraints"])
    minimum = criteria.optimizer.minimum_delivery_ratio if criteria.optimizer else 0.95
    if not m["flow_connected"]:
        errors.append("Required service demand is unreachable")
    if m["throughput_mbps"] + 1e-6 < minimum * demand.offered_mbps:
        errors.append("Delivered throughput is below the required fraction of offered traffic")
    if m["average_latency_ms"] is None or m["average_latency_ms"] > criteria.latency_target_ms:
        errors.append("Finite mean latency does not satisfy the declared target")
    return errors


def decode(failed, actions, mask, tier, demand, assumptions, allow_repair=True):
    """Gene 0: action bitmask; gene 1: unchanged/125%/200% demand capacity headroom."""
    graph = deepcopy(failed)
    for field in ("nodes", "links"):
        original = {item.id: item for item in getattr(failed, field)}
        merged = {key: deepcopy(item) for key, item in original.items()}
        applied = {}
        for index, action in enumerate(actions):
            if not mask & (1 << index):
                continue
            for item in getattr(action, field):
                if item.id not in original or item.model_dump() != original[item.id].model_dump():
                    if item.id in applied and applied[item.id] != item.model_dump():
                        raise ValueError(f"Conflicting action changes to {item.id}")
                    if not allow_repair and item.id in original and original[item.id].status in DOWN and item.status not in DOWN:
                        raise ValueError("Repair is not permitted")
                    applied[item.id] = item.model_dump()
                    merged[item.id] = deepcopy(item)
        setattr(graph, field, list(merged.values()))
    # Existing parallel connections are legitimate. New duplicate operational pairs are not.
    old_ids = {e.id for e in failed.links}
    pairs = {frozenset((e.source_node_id, e.target_node_id)) for e in graph.links if e.id in old_ids and e.status not in DOWN}
    for edge in graph.links:
        if edge.id not in old_ids and edge.status not in DOWN:
            pair = frozenset((edge.source_node_id, edge.target_node_id))
            if pair in pairs:
                raise ValueError("New action duplicates an existing operational connection")
            pairs.add(pair)
    if tier:
        mapping = {n.metadata["replaces_node_id"]: n.id for n in graph.nodes if n.metadata.get("replaces_node_id")}
        route = shortest_path(graph, mapping.get(demand.source_node_id, demand.source_node_id),
                              mapping.get(demand.target_node_id, demand.target_node_id),
                              demand.offered_mbps, demand.packet_size_bytes, assumptions)
        for edge in graph.links:
            if edge.id in (route or []):
                edge.bandwidth_mbps = min(1_000_000, max(edge.bandwidth_mbps or 1000, demand.offered_mbps * (1.25 if tier == 1 else 2)))
    return NetworkDefinition.model_validate(graph.model_dump())


def optimize_candidates(failed, seeds, demand, failed_metrics, assumptions, criteria):
    settings = criteria.optimizer
    base = {"algorithm": "pymoo_nsga2", "parameters": settings.model_dump(), "objectives": OBJECTIVES,
            "provenance": "simulated", "pareto_candidate_ids": [], "candidates": [],
            "limitations": ["Approximate non-dominated alternatives among evaluated action combinations, not global optimality.",
                            "Single steady-state demand; resilience checks connectivity under selected-route link outages only.",
                            "Cost/change complexity are relative proxies; hardware feasibility remains conditional.",
                            "Timeout is checked between bounded graph evaluations; an in-flight evaluation completes."]}
    started = monotonic()
    try:
        import numpy as np
        from pymoo.algorithms.moo.nsga2 import NSGA2
        from pymoo.core.problem import ElementwiseProblem
        from pymoo.operators.crossover.sbx import SBX
        from pymoo.operators.mutation.pm import PM
        from pymoo.operators.repair.rounding import RoundingRepair
        from pymoo.optimize import minimize
    except ImportError:
        return {**base, "status": "fallback", "reason": "Optimizer dependency unavailable; deterministic strategies retained"}
    # No novel bypass actions for intentionally isolated/unsupported placement scenarios.
    actions = [NetworkDefinition.model_validate(c["topology"]) for c in sorted(seeds, key=lambda c: c["id"]) if c["id"] != "retain"]
    base["action_ids"] = [c["id"] for c in sorted(seeds, key=lambda c: c["id"]) if c["id"] != "retain"]
    upper = 2 ** len(actions) - 1
    cache, graphs, rejected = {}, {}, []
    def assess(mask, tier):
        if monotonic() - started > settings.timeout_seconds:
            raise TimeoutError()
        key = (int(mask), int(tier) if actions else 0)
        if key in cache:
            return cache[key]
        try:
            graph = decode(failed, actions, *key, demand, assumptions, criteria.allow_repair)
            graph_key = json.dumps(graph.model_dump(mode="json"), sort_keys=True)
            if graph_key in graphs:
                cache[key] = graphs[graph_key]
                return cache[key]
            names = [name for index, name in enumerate(base["action_ids"]) if key[0] & (1 << index)]
            label = " + ".join(names) or "retain"
            item = evaluate_candidate(f"nsga:{key[0]}:{key[1]}", f"NSGA-II: {label}; capacity tier {key[1]}",
                                      graph, failed, demand, failed_metrics, assumptions, criteria)
            item["encoding"] = list(key)
            item["objectives"] = objective_values(item, demand, criteria)
            item["constraints"] = recovery_constraints(item, demand, criteria)
            item["feasible"] = not item["constraints"]
            item["origin"] = "nsga2"
            graphs[graph_key] = item
            cache[key] = item
        except (ValueError, HTTPException) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "Decoded graph failed analytical validation"
            rejected.append({"encoding": list(key), "constraints": [reason], "feasible": False})
            cache[key] = {"objectives": [1_000_000.0] * len(OBJECTIVES), "feasible": False}
        return cache[key]

    class NetworkProblem(ElementwiseProblem):
        def __init__(self):
            super().__init__(n_var=2, n_obj=len(OBJECTIVES), n_ieq_constr=1,
                             xl=np.array([0, 0]), xu=np.array([max(1, upper), 2]), vtype=int)

        def _evaluate(self, x, out, *args, **kwargs):
            mask = min(upper, int(x[0]))
            item = assess(mask, int(x[1]))
            out["F"] = item["objectives"]
            out["G"] = [0 if item["feasible"] else 1]

    if not _SEARCH_LOCK.acquire(timeout=settings.timeout_seconds):
        return {**base, "status": "fallback", "reason": "Optimizer is busy; deterministic strategies retained"}
    try:
        rng = np.random.default_rng(settings.seed)
        sampling = np.column_stack([rng.integers(0, max(1, upper) + 1, settings.population_size),
                                    rng.integers(0, 3, settings.population_size)])
        # Every deterministic action is an initial control, not an untested substitute for search.
        for index, mask in enumerate([0] + [1 << i for i in range(len(actions))]):
            sampling[index] = [mask, 0]
        # No action library means no unrequested capacity modifications (e.g. isolation).
        if not actions:
            sampling[:] = 0
        algorithm = NSGA2(pop_size=settings.population_size, sampling=sampling,
                          crossover=SBX(prob=settings.crossover_probability, eta=15, vtype=float, repair=RoundingRepair()),
                          mutation=PM(prob=settings.mutation_probability, eta=20, vtype=float, repair=RoundingRepair()),
                          eliminate_duplicates=False)
        result = minimize(NetworkProblem(), algorithm, ("n_gen", settings.generations), seed=settings.seed, verbose=False)
        if monotonic() - started > settings.timeout_seconds:
            raise TimeoutError()
    except TimeoutError:
        return {**base, "status": "fallback", "reason": "Search time budget exceeded; deterministic strategies retained",
                "evaluated_configurations": len(graphs)}
    except (RuntimeError, ArithmeticError):
        return {**base, "status": "fallback", "reason": "Optimizer execution failed; deterministic strategies retained"}
    finally:
        _SEARCH_LOCK.release()
    candidates = sorted(graphs.values(), key=lambda c: c["id"])
    feasible = [c for c in candidates if c["feasible"]]
    front = [c["id"] for c in feasible if not any(dominates(other["objectives"], c["objectives"]) for other in feasible)]
    for c in candidates:
        c["pareto"] = c["id"] in front
    return {**base, "status": "completed" if front else "no_feasible_candidates", "candidates": candidates,
            "pareto_candidate_ids": front, "rejected_encodings": rejected,
            "evaluated_configurations": len(graphs), "generations_completed": int(result.algorithm.n_gen - 1),
            "baseline_comparison": [{"id": c["id"], "objectives": objective_values(c, demand, criteria),
                                     "recovery_constraints": recovery_constraints(c, demand, criteria)} for c in seeds]}
