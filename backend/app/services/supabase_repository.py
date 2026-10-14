from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.config import settings
from app.models.network import InterfaceDefinition, IPConfiguration, LinkDefinition, NetworkDefinition, NodeDefinition


class SupabaseRepository:
    """Use the caller's JWT for every Supabase request so existing RLS stays authoritative."""

    def _configuration(self) -> tuple[str, str]:
        if not settings.supabase_url or not settings.supabase_publishable_key:
            raise HTTPException(status_code=503, detail="The backend is missing Supabase URL or publishable-key configuration.")
        return settings.supabase_url.rstrip("/"), settings.supabase_publishable_key

    async def _request(self, token: str, method: str, path: str, **kwargs: Any) -> httpx.Response:
        base_url, key = self._configuration()
        headers = {"apikey": key, "Authorization": f"Bearer {token}"}
        headers.update(kwargs.pop("headers", {}))
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(method, f"{base_url}{path}", headers=headers, **kwargs)
        if response.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="Your Supabase session is invalid or has expired. Sign in again.")
        if response.is_error:
            raise HTTPException(status_code=502, detail=f"Supabase request failed with status {response.status_code}.")
        return response

    async def user_id(self, token: str) -> str:
        if not token:
            raise HTTPException(status_code=401, detail="A Supabase access token is required.")
        response = await self._request(token, "GET", "/auth/v1/user")
        try:
            return str(UUID(response.json()["id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=401, detail="Supabase returned an invalid user identity.") from exc

    async def load_topology(self, token: str, user_id: str) -> NetworkDefinition:
        nodes_response, links_response = await self._request(token, "GET", "/rest/v1/network_nodes", params={"select": "*", "user_id": f"eq.{user_id}", "order": "id.asc"}), await self._request(token, "GET", "/rest/v1/network_connections", params={"select": "*", "user_id": f"eq.{user_id}", "order": "id.asc"})
        node_rows = nodes_response.json()
        link_rows = links_response.json()
        nodes: list[NodeDefinition] = []
        for row in node_rows:
            config = row.get("configuration") if isinstance(row.get("configuration"), dict) else {}
            model = str(config.get("model", ""))
            kind = {"core-router": "router", "distribution-switch": "switch", "cloud-server": "server", "load-balancer": "load_balancer"}.get(row["node_type"], "server")
            if model == "pc-pt":
                kind = "pc"
            ip_text = config.get("ipAddress", "")
            ips = [part.strip() for part in ip_text.split(",") if part.strip()] if isinstance(ip_text, str) else []
            mask = str(config.get("subnetMask", "255.255.255.0"))
            ports = [part.strip() for part in str(config.get("interfacePorts", "")).split(",") if part.strip()]
            interfaces = []
            for index, ip in enumerate(ips):
                address, _, prefix = ip.partition("/")
                interfaces.append(InterfaceDefinition(
                    id=f"{row['id']}-if{index}", name=ports[index] if index < len(ports) else f"eth{index}",
                    ip_configuration=IPConfiguration(ip_address=address, subnet_mask=mask, prefix_length=int(prefix) if prefix.isdigit() else 24,
                                                     gateway=config.get("defaultGateway") or None),
                ))
            resources = {}
            for source_key, dest_key in (("processingCapacityMbps", "processing_capacity_mbps"), ("bandwidthMbps", "bandwidth_mbps")):
                value = config.get(source_key)
                if isinstance(value, (int, float)) and value > 0:
                    resources[dest_key] = float(value)
            nodes.append(NodeDefinition(
                id=str(row["id"]), name=str(row["label"]), device_type=kind,
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
        return NetworkDefinition(name="Saved topology", description="Authenticated user's current Supabase topology", nodes=nodes, links=links, metadata={"source": "supabase"})

    async def save_experiment(self, token: str, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._request(token, "POST", "/rest/v1/simulation_experiments", json=body, headers={"Prefer": "return=representation"})
        values = response.json()
        return values[0] if isinstance(values, list) and values else body

    async def get_experiment(self, token: str, experiment_id: str, user_id: str) -> dict[str, Any]:
        response = await self._request(token, "GET", "/rest/v1/simulation_experiments", params={"select": "*", "id": f"eq.{experiment_id}", "user_id": f"eq.{user_id}"})
        rows = response.json()
        if not rows:
            raise HTTPException(status_code=404, detail="Simulation experiment was not found.")
        return rows[0]

    async def update_experiment(self, token: str, experiment_id: str, user_id: str, body: dict[str, Any]) -> None:
        await self._request(token, "PATCH", "/rest/v1/simulation_experiments", params={"id": f"eq.{experiment_id}", "user_id": f"eq.{user_id}"}, json=body, headers={"Prefer": "return=minimal"})


repository = SupabaseRepository()
