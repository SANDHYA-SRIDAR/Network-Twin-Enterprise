from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool
from typing import Annotated
from app.api.auth import require_access_token

from app.engines.analytical_simulator import ENGINE_VERSION, run_experiment, run_modernization
from app.models.failure_simulation import FailureSimulationRequest, SavedTopologyResponse, SimulationExperimentResponse, ExperimentModernizeRequest, CandidateDecisionRequest, TrafficDemand
from app.services.assistant import AssistantQuestion, explain_experiment
from app.models.network import NetworkDefinition
from app.services.network_validation import validate_network_definition
from app.services.supabase_repository import repository
from app.services.transformation import service_outcome, describe_selection, evaluate_candidate, proposal_revision

router = APIRouter(prefix="/failure-simulation", tags=["failure-simulation"])

SCENARIO_CATALOG = [
    {"id": "link_failure", "title": "Link failure", "description": "Fail a selected connection and calculate rerouting or loss.", "parameters": ["link_id"]},
    {"id": "traffic_increase", "title": "Traffic increase", "description": "Increase offered traffic and evaluate congestion and delivery.", "parameters": ["factor"]},
    {"id": "bandwidth_change", "title": "Bandwidth change", "description": "Set a selected connection capacity for the simulation.", "parameters": ["link_id", "bandwidth_mbps"]},
    {"id": "redundancy_add", "title": "Redundancy add", "description": "Add a candidate connection between saved devices in the simulation copy.", "parameters": ["source_node_id", "target_node_id", "bandwidth_mbps"]},
    {"id": "device_failure", "title": "Device failure", "description": "Fail a selected device and its forwarding paths.", "parameters": ["node_id"]},
    {"id": "segment_isolation", "title": "Segment isolation", "description": "Isolate a selected device and its attached traffic paths.", "parameters": ["node_id"]},
    {"id": "capacity_increase", "title": "Capacity increase", "description": "Increase the capacity of a selected connection.", "parameters": ["link_id", "increase_mbps"]},
    {"id": "cloud_migration", "title": "Cloud migration", "description": "Placement-only analysis; network effects are unavailable without site and cloud-latency data.", "parameters": ["node_id"]},
]


def fingerprint(network: NetworkDefinition) -> str:
    canonical = json.dumps(network.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


AccessToken = Annotated[str, Depends(require_access_token)]


async def persist_update(token, row, user_id, body):
    # Existing updated_at trigger provides optimistic protection for long AI/search requests.
    guard = {"expected_updated_at": row["updated_at"]} if row.get("updated_at") else {}
    await repository.update_experiment(token, row["id"], user_id, body, **guard)


@router.get("/scenarios")
async def list_scenarios() -> dict[str, Any]:
    return {"scenarios": SCENARIO_CATALOG, "provenance": "application scenario catalog"}


async def current_topology(token: str) -> tuple[str, NetworkDefinition]:
    user_id = await repository.user_id(token)
    network = await repository.load_topology(token, user_id)
    if len(network.nodes) > 500 or len(network.links) > 2000:
        raise HTTPException(status_code=413, detail="Topology exceeds the simulation limit of 500 devices and 2000 connections.")
    issues = validate_network_definition(network)
    if issues:
        raise HTTPException(status_code=422, detail={"message": "Saved topology is invalid for simulation.", "errors": [issue.model_dump() for issue in issues]})
    return user_id, network


@router.get("/topology", response_model=SavedTopologyResponse)
async def get_saved_topology(token: AccessToken) -> SavedTopologyResponse:
    _, network = await current_topology(token)
    return SavedTopologyResponse(topology_fingerprint=fingerprint(network), topology=network.model_dump(mode="json"))


@router.post("/run", response_model=SimulationExperimentResponse)
async def run_failure_simulation(request: FailureSimulationRequest, token: AccessToken) -> SimulationExperimentResponse:
    user_id, network = await current_topology(token)
    current_fingerprint = fingerprint(network)
    if request.topology_fingerprint and request.topology_fingerprint != current_fingerprint:
        raise HTTPException(status_code=409, detail="The saved topology changed after you loaded it. Reload the simulation before running.")
    if not network.nodes:
        raise HTTPException(status_code=422, detail="Save at least two devices before running a network simulation.")
    if request.traffic.source_node_id not in {node.id for node in network.nodes} or request.traffic.target_node_id not in {node.id for node in network.nodes}:
        raise HTTPException(status_code=422, detail="Traffic endpoints must belong to your saved topology.")
    result = run_experiment(network, request.scenario_type, request.parameters, request.traffic)
    result["topology_fingerprint"] = current_fingerprint
    result["scenario_type"] = request.scenario_type
    result["scenario_parameters"] = request.parameters
    metrics = {
        "analysis": result["analysis"],
        "baseline": result["baseline_metrics"], "failure": result["failed_metrics"],
        "failure_steps": result["failure_steps"], "assumptions": result["assumptions"],
    }
    await repository.save_experiment(token, {
        "id": result["experiment_id"], "user_id": user_id, "topology_fingerprint": current_fingerprint,
        "scenario_id": request.scenario_type, "scenario_parameters": request.parameters,
        "traffic_configuration": result["traffic"], "engine_version": ENGINE_VERSION,
        "baseline_snapshot": result["baseline_topology"], "failure_snapshot": result["failed_topology"],
        "modernized_snapshot": None, "proposal": None, "metrics": metrics, "status": "failure_simulated",
    })
    return SimulationExperimentResponse(**result)


def _experiment_result(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    proposal = row.get("proposal")
    if isinstance(proposal, dict):
        proposal = {**proposal, "revision": proposal_revision(proposal)}
    if isinstance(proposal, dict) and metrics.get("modernized") and "service_outcome" not in proposal:
        # Describe existing saved results honestly without rewriting their snapshots or scores.
        outcome = service_outcome(metrics.get("failure", {}), metrics["modernized"])
        disabled = [link["id"] for link in metrics["modernized"].get("links", []) if link.get("status") in {"failed", "down", "offline", "unavailable"}]
        isolation = f" Disabled connections remain isolated and red: {', '.join(disabled)}; they have not been repaired or removed." if disabled else ""
        proposal = {**proposal, **outcome, "summary": f"{proposal.get('summary', '')} {outcome['service_outcome']}.{isolation}"}
    response = {
        "decisions": metrics.get("decisions", []),
        "analysis": metrics.get("analysis"),
        "traffic": row.get("traffic_configuration", {}), "scenario_parameters": row.get("scenario_parameters", {}),
        "experiment_id": row["id"], "status": "completed", "scenario_type": row["scenario_id"],
        "engine_version": row["engine_version"], "provenance": "simulated",
        "topology_fingerprint": row["topology_fingerprint"],
        "baseline_topology": row["baseline_snapshot"], "failed_topology": row["failure_snapshot"],
        "baseline_metrics": metrics.get("baseline", {}), "failed_metrics": metrics.get("failure", {}),
        "failure_steps": metrics.get("failure_steps", []), "assumptions": metrics.get("assumptions", []),
        "modernization": proposal, "modernized_topology": row.get("modernized_snapshot"),
        "modernized_metrics": metrics.get("modernized"), "modernization_steps": metrics.get("modernization_steps", []),
        "assistant": metrics.get("assistant"),
    }
    return response


@router.post("/{experiment_id}/modernize", response_model=SimulationExperimentResponse)
async def modernize_failure_simulation(experiment_id: str, token: AccessToken, request: ExperimentModernizeRequest = ExperimentModernizeRequest()) -> SimulationExperimentResponse:
    user_id = await repository.user_id(token)
    row = await repository.get_experiment(token, experiment_id, user_id)
    if row["engine_version"] != ENGINE_VERSION:
        raise HTTPException(status_code=409, detail="This experiment uses an older engine. Run a new experiment before comparing strategies.")
    try:
        baseline = NetworkDefinition.model_validate(row["baseline_snapshot"])
        failed = NetworkDefinition.model_validate(row["failure_snapshot"])
        from app.models.failure_simulation import TrafficDemand
        traffic = TrafficDemand.model_validate(row["traffic_configuration"])
        stored_metrics = row.get("metrics") or {}
        proposal_result = await run_in_threadpool(run_modernization, baseline, failed, row["scenario_id"], row.get("scenario_parameters") or {}, traffic, stored_metrics.get("failure", {}), stored_metrics.get("assumptions", []), request)
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Saved experiment data is incomplete and cannot be modernized.") from exc
    metrics = {**stored_metrics, "assistant": None, "modernized": proposal_result["modernized_metrics"], "modernization_steps": proposal_result["modernization_steps"], "assumptions": proposal_result["assumptions"]}
    await persist_update(token, row, user_id, {
        "modernized_snapshot": proposal_result["modernized_topology"], "proposal": proposal_result["modernization"],
        "metrics": metrics, "status": "modernized",
    })
    row.update({"modernized_snapshot": proposal_result["modernized_topology"], "proposal": proposal_result["modernization"], "metrics": metrics, "status": "modernized"})
    return SimulationExperimentResponse(**_experiment_result(row))


@router.post("/{experiment_id}/decision", response_model=SimulationExperimentResponse)
async def decide_candidate(experiment_id: str, request: CandidateDecisionRequest, token: AccessToken):
    user_id = await repository.user_id(token)
    row = await repository.get_experiment(token, experiment_id, user_id)
    if row["engine_version"] != ENGINE_VERSION:
        raise HTTPException(409, "Rerun this experiment with the current engine before deciding.")
    proposal = deepcopy(row.get("proposal"))
    if not proposal:
        raise HTTPException(409, "Evaluate recovery options before selecting a candidate.")
    if request.proposal_revision != proposal_revision(proposal) or request.topology_fingerprint != row["topology_fingerprint"]:
        raise HTTPException(409, "The proposal or topology changed. Reload the experiment before deciding.")
    candidate = next((c for c in proposal["candidates"] if c["id"] == request.candidate_id), None)
    if candidate is None:
        raise HTTPException(404, "Candidate does not belong to this experiment.")
    if request.action == "accept":
        current = await repository.load_topology(token, user_id)
        if fingerprint(current) != row["topology_fingerprint"]:
            raise HTTPException(409, "The saved topology changed. Run a new experiment before accepting this plan.")
    metrics = deepcopy(row["metrics"])
    if request.action != "reject":
        if not candidate["feasible"]:
            raise HTTPException(422, "Candidate violates declared constraints and cannot be selected or accepted.")
        criteria = ExperimentModernizeRequest.model_validate(proposal["criteria"])
        demand = TrafficDemand.model_validate(row["traffic_configuration"])
        assumptions = set(metrics["assumptions"])
        candidate_graph = NetworkDefinition.model_validate(candidate["topology"])
        failed = NetworkDefinition.model_validate(row["failure_snapshot"])
        checked = await run_in_threadpool(evaluate_candidate, candidate["id"], candidate["title"], candidate_graph,
                                          failed, demand, metrics["failure"], assumptions, criteria)
        if not checked["feasible"]:
            raise HTTPException(422, "Candidate no longer satisfies configuration constraints.")
        if candidate.get("origin") == "nsga2":
            from app.services.optimization import recovery_constraints
            if recovery_constraints(checked, demand, criteria):
                raise HTTPException(422, "Candidate does not satisfy recovery constraints.")
        if request.action == "accept":
            from app.services.optimization import recovery_constraints
            if recovery_constraints(checked, demand, criteria):
                raise HTTPException(422, "Candidate does not meet the declared service targets and cannot be accepted as a recovery plan.")
        checked.update({k: candidate[k] for k in ("origin", "encoding", "objectives", "pareto") if k in candidate})
        candidates = [checked if c["id"] == checked["id"] else c for c in proposal["candidates"]]
        selected = describe_selection(checked, candidates, metrics["failure"], demand, criteria, assumptions, row["scenario_id"], operator=True)
        selected.pop("selected_topology")
        proposal = {**proposal, **selected, "selection_source": "operator"}
        metrics.update(modernized=checked["metrics"], modernization_steps=checked["steps"], assumptions=sorted(assumptions), assistant=None)
        row["modernized_snapshot"] = candidate_graph.model_dump(mode="json")
    decision = {"action": request.action, "candidate_id": candidate["id"], "note": request.note,
                "created_at": datetime.now(timezone.utc).isoformat(), "user_id": user_id,
                "proposal_revision": request.proposal_revision, "topology_fingerprint": request.topology_fingerprint,
                "scope": "experiment_plan_only", "canonical_topology_changed": False,
                "previous_selected_candidate_id": (row.get("proposal") or {}).get("selected_strategy_id"),
                "candidate_snapshot": candidate["topology"]}
    metrics["decisions"] = [*metrics.get("decisions", []), decision]
    body = {"proposal": proposal, "metrics": metrics, "modernized_snapshot": row.get("modernized_snapshot")}
    await persist_update(token, row, user_id, body)
    row.update(body)
    return SimulationExperimentResponse(**_experiment_result(row))


@router.get("/experiments")
async def list_experiments(token: AccessToken):
    user_id = await repository.user_id(token)
    return {"experiments": await repository.list_experiments(token, user_id)}


@router.post("/{experiment_id}/assistant")
async def explain_saved_experiment(experiment_id: str, request: AssistantQuestion, token: AccessToken):
    user_id = await repository.user_id(token)
    row = await repository.get_experiment(token, experiment_id, user_id)
    explanation = await explain_experiment(_experiment_result(row), request.question)
    await persist_update(token, row, user_id, {"metrics": {**row["metrics"], "assistant": explanation}})
    return explanation


@router.get("/experiments/{experiment_id}", response_model=SimulationExperimentResponse)
async def get_simulation_experiment(experiment_id: str, token: AccessToken) -> SimulationExperimentResponse:
    user_id = await repository.user_id(token)
    row = await repository.get_experiment(token, experiment_id, user_id)
    return SimulationExperimentResponse(**_experiment_result(row))
