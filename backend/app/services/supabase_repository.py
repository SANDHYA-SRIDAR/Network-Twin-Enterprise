from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL
import hashlib
import json

import httpx
from fastapi import HTTPException

from app.config import settings
from app.models.network import InterfaceDefinition, IPConfiguration, LinkDefinition, NetworkDefinition, NodeDefinition


class SupabaseRepository:
    """Use the caller's JWT for every Supabase request so existing RLS stays authoritative."""

    def _configuration(self) -> tuple[str, str]:
        error = settings.supabase_configuration_error()
        if error:
            raise HTTPException(status_code=503, detail=error)
        return settings.supabase_url.rstrip("/"), settings.supabase_publishable_key

    async def _request(self, token: str, method: str, path: str, **kwargs: Any) -> httpx.Response:
        base_url, key = self._configuration()
        headers = {**kwargs.pop("headers", {}), "apikey": key, "Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.request(method, f"{base_url}{path}", headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Supabase is unavailable; retry when the service is reachable.") from exc
        if response.is_error:
            try:
                error_body = response.json()
                message = str(error_body.get("message", "")).lower() if isinstance(error_body, dict) else ""
            except ValueError:
                message = ""
            if "invalid api key" in message:
                raise HTTPException(status_code=503, detail="Supabase rejected the backend project API key. Check the public project key configuration and restart the backend; signing in again will not fix this server configuration error.")
        if response.status_code == 401 or (path == "/auth/v1/user" and response.status_code in (400, 403)):
            raise HTTPException(status_code=401, detail="Your Supabase session is invalid or has expired. Sign in again.", headers={"WWW-Authenticate": "Bearer"})
        if response.status_code == 403:
            raise HTTPException(status_code=403, detail="Supabase denied access to this resource under the current user's permissions.")
        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="Supabase request limit reached. Retry later.")
        if response.is_error:
            raise HTTPException(status_code=502, detail=f"Supabase request failed with status {response.status_code}.")
        return response

    @staticmethod
    def _rows(response: httpx.Response) -> list[dict[str, Any]]:
        try:
            values = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Supabase returned an invalid data response.") from exc
        if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
            raise HTTPException(status_code=502, detail="Supabase returned an invalid data response.")
        return values

    async def user_id(self, token: str) -> str:
        if not token:
            raise HTTPException(status_code=401, detail="A Supabase access token is required.")
        response = await self._request(token, "GET", "/auth/v1/user")
        try:
            return str(UUID(response.json()["id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="Supabase returned an invalid user identity.") from exc

    async def load_topology(self, token: str, user_id: str) -> NetworkDefinition:
        nodes_response, links_response = await self._request(token, "GET", "/rest/v1/network_nodes", params={"select": "*", "user_id": f"eq.{user_id}", "order": "id.asc"}), await self._request(token, "GET", "/rest/v1/network_connections", params={"select": "*", "user_id": f"eq.{user_id}", "order": "id.asc"})
        node_rows = self._rows(nodes_response)
        link_rows = self._rows(links_response)
        if any(not all(key in row for key in ("id", "node_type", "label")) for row in node_rows) or any(not all(key in row for key in ("id", "source_node_id", "target_node_id")) for row in link_rows):
            raise HTTPException(status_code=502, detail="Supabase topology rows are incomplete.")
        nodes: list[NodeDefinition] = []
        for row in node_rows:
            config = row.get("configuration") if isinstance(row.get("configuration"), dict) else {}
            model = str(config.get("model", ""))
            kind = {"core-router": "router", "distribution-switch": "switch", "cloud-server": "server", "load-balancer": "load_balancer"}.get(row["node_type"], "server")
            if model == "pc-pt":
                kind = "pc"
            kind = {"hub-pt": "hub", "accesspoint-pt": "access_point"}.get(model, kind)
            ip_text = config.get("ipAddress", "")
            ips = [part.strip() for part in ip_text.split(",") if part.strip()] if isinstance(ip_text, str) else []
            mask = str(config.get("subnetMask", "255.255.255.0"))
            ports = [part.strip() for part in str(config.get("interfacePorts", "")).split(",") if part.strip()]
            interfaces = []
            for index, ip in enumerate(ips):
                address, _, prefix = ip.partition("/")
                if "/" in ip and not prefix.isdigit():
                    raise HTTPException(status_code=422, detail="A saved interface has an invalid IPv4 prefix.")
                interfaces.append(InterfaceDefinition(
                    id=f"{row['id']}-if{index}", name=ports[index] if index < len(ports) else f"eth{index}",
                    ip_configuration=IPConfiguration(ip_address=address, subnet_mask=mask,
                                                     **({"prefix_length": int(prefix)} if prefix.isdigit() else {}),
                                                     gateway=config.get("defaultGateway") or None),
                ))
            resources = {}
            for source_key, dest_key in (("processingCapacityMbps", "processing_capacity_mbps"), ("bandwidthMbps", "bandwidth_mbps")):
                value = config.get(source_key)
                if isinstance(value, (int, float)) and value > 0:
                    resources[dest_key] = float(value)
            nodes.append(NodeDefinition(
                id=str(row["id"]), name=str(row["label"]), hostname=str(config.get("hostname") or row["label"]), model=model or kind, device_type=kind,
                role=kind, status={"healthy": "active", "warning": "degraded", "offline": "down"}.get(row.get("status"), str(row.get("status", "active"))),
                interfaces=interfaces, resources=resources,
                metadata={"position": {"x": row.get("position_x", 0), "y": row.get("position_y", 0)}, "model": model or kind, "configuration": config},
            ))
        links: list[LinkDefinition] = []
        for row in link_rows:
            config = row.get("configuration") if isinstance(row.get("configuration"), dict) else {}
            def numeric(*keys: str) -> float | None:
                for key in keys:
                    value = config.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        return float(value)
                return None
            links.append(LinkDefinition(
                id=str(row["id"]), source_node_id=str(row["source_node_id"]), target_node_id=str(row["target_node_id"]),
                cable_type=config.get("cableType", "straight-through"),
                bandwidth_mbps=numeric("max_capacity_mbps", "bandwidth_mbps"),
                delay_ms=numeric("base_latency_ms", "latency_ms", "delay_ms"),
                packet_loss_pct=numeric("packet_loss_pct", "packet_loss_pct"),
                status={"active": "active", "degraded": "degraded", "offline": "down"}.get(row.get("status"), str(row.get("status", "active"))),
                metadata={**config, "source_handle": row.get("source_handle"), "target_handle": row.get("target_handle"), "current_load_mbps": numeric("current_load_mbps", "currentLoadMbps")},
            ))
        timestamps = [r.get("created_at") for r in node_rows + link_rows if r.get("created_at")]
        modified = [r.get("updated_at") for r in node_rows + link_rows if r.get("updated_at")]
        revision = hashlib.sha256(json.dumps([node_rows, link_rows], sort_keys=True).encode()).hexdigest()
        return NetworkDefinition(id=str(uuid5(NAMESPACE_URL, f"nexustwin:{user_id}")), owner_id=user_id,
            version=revision, created_at=min(timestamps) if timestamps else None,
            updated_at=max(modified) if modified else None,
            name="Saved topology", description="Authenticated user's current Supabase topology", nodes=nodes, links=links,
            metadata={"source": "supabase", "schema_version": "1.0", "revision_policy": "SHA256 of canonical saved rows; one topology per owner"})

    async def list_experiments(self, token: str, user_id: str) -> list[dict[str, Any]]:
        response = await self._request(token, "GET", "/rest/v1/simulation_experiments", params={
            "select": "id,scenario_id,engine_version,status,created_at,topology_fingerprint",
            "user_id": f"eq.{user_id}", "order": "created_at.desc,id.asc", "limit": "50"})
        return self._rows(response)

    async def save_experiment(self, token: str, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._request(token, "POST", "/rest/v1/simulation_experiments", json=body, headers={"Prefer": "return=representation"})
        values = self._rows(response)
        if len(values) != 1 or values[0].get("id") != body["id"]:
            raise HTTPException(status_code=502, detail="Supabase did not confirm that the experiment was saved.")
        return values[0]

    async def get_experiment(self, token: str, experiment_id: str, user_id: str) -> dict[str, Any]:
        response = await self._request(token, "GET", "/rest/v1/simulation_experiments", params={"select": "*", "id": f"eq.{experiment_id}", "user_id": f"eq.{user_id}"})
        rows = self._rows(response)
        if not rows:
            raise HTTPException(status_code=404, detail="Simulation experiment was not found.")
        return rows[0]

    async def update_experiment(self, token: str, experiment_id: str, user_id: str, body: dict[str, Any], *, expected_updated_at: str | None = None) -> None:
        params = {"id": f"eq.{experiment_id}", "user_id": f"eq.{user_id}"}
        if expected_updated_at is not None:
            params["updated_at"] = f"eq.{expected_updated_at}"
        response = await self._request(token, "PATCH", "/rest/v1/simulation_experiments", params=params, json=body, headers={"Prefer": "return=representation"})
        rows = self._rows(response)
        if not rows:
            if expected_updated_at is not None:
                raise HTTPException(status_code=409, detail="Experiment changed during this operation. Reload it before trying again.")
            raise HTTPException(status_code=404, detail="Experiment was not found or was not updated under the current user's permissions.")
        if len(rows) != 1 or rows[0].get("id") != experiment_id:
            raise HTTPException(status_code=502, detail="Supabase did not confirm the experiment update.")


repository = SupabaseRepository()
