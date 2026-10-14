from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.engines.analytical_simulator import ENGINE_VERSION, run_experiment, run_modernization
from app.models.failure_simulation import FailureSimulationRequest, SavedTopologyResponse, SimulationExperimentResponse
from app.models.network import NetworkDefinition
from app.services.network_validation import validate_network_definition
from app.services.supabase_repository import repository

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


def access_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to load and simulate your saved topology.")
    return authorization[7:].strip()


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
async def get_saved_topology(authorization: str | None = Header(default=None)) -> SavedTopologyResponse:
    token = access_token(authorization)
    _, network = await current_topology(token)
    return SavedTopologyResponse(topology_fingerprint=fingerprint(network), topology=network.model_dump(mode="json"))


@router.post("/run", response_model=SimulationExperimentResponse)
async def run_failure_simulation(request: FailureSimulationRequest, authorization: str | None = Header(default=None)) -> SimulationExperimentResponse:
    token = access_token(authorization)
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
    metrics = {
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
    response = {
        "experiment_id": row["id"], "status": "completed", "scenario_type": row["scenario_id"],
        "engine_version": row["engine_version"], "provenance": "simulated",
        "topology_fingerprint": row["topology_fingerprint"],
        "baseline_topology": row["baseline_snapshot"], "failed_topology": row["failure_snapshot"],
        "baseline_metrics": metrics.get("baseline", {}), "failed_metrics": metrics.get("failure", {}),
        "failure_steps": metrics.get("failure_steps", []), "assumptions": metrics.get("assumptions", []),
        "modernization": row.get("proposal"), "modernized_topology": row.get("modernized_snapshot"),
        "modernized_metrics": metrics.get("modernized"), "modernization_steps": metrics.get("modernization_steps", []),
    }
    return response


@router.post("/{experiment_id}/modernize", response_model=SimulationExperimentResponse)
async def modernize_failure_simulation(experiment_id: str, authorization: str | None = Header(default=None)) -> SimulationExperimentResponse:
    token = access_token(authorization)
    user_id = await repository.user_id(token)
    row = await repository.get_experiment(token, experiment_id, user_id)
    if row.get("status") == "modernized" and row.get("modernized_snapshot"):
        return SimulationExperimentResponse(**_experiment_result(row))
    try:
        baseline = NetworkDefinition.model_validate(row["baseline_snapshot"])
        failed = NetworkDefinition.model_validate(row["failure_snapshot"])
        from app.models.failure_simulation import TrafficDemand
        traffic = TrafficDemand.model_validate(row["traffic_configuration"])
        stored_metrics = row.get("metrics") or {}
        proposal_result = run_modernization(baseline, failed, row["scenario_id"], row.get("scenario_parameters") or {}, traffic, stored_metrics.get("failure", {}), stored_metrics.get("assumptions", []))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Saved experiment data is incomplete and cannot be modernized.") from exc
    metrics = {**stored_metrics, "modernized": proposal_result["modernized_metrics"], "modernization_steps": proposal_result["modernization_steps"], "assumptions": proposal_result["assumptions"]}
    await repository.update_experiment(token, experiment_id, user_id, {
        "modernized_snapshot": proposal_result["modernized_topology"], "proposal": proposal_result["modernization"],
        "metrics": metrics, "status": "modernized",
    })
    row.update({"modernized_snapshot": proposal_result["modernized_topology"], "proposal": proposal_result["modernization"], "metrics": metrics, "status": "modernized"})
    return SimulationExperimentResponse(**_experiment_result(row))


@router.get("/experiments/{experiment_id}", response_model=SimulationExperimentResponse)
async def get_simulation_experiment(experiment_id: str, authorization: str | None = Header(default=None)) -> SimulationExperimentResponse:
    token = access_token(authorization)
    user_id = await repository.user_id(token)
    row = await repository.get_experiment(token, experiment_id, user_id)
    return SimulationExperimentResponse(**_experiment_result(row))
