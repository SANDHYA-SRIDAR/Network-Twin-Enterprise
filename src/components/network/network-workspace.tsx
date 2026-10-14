"use client";

import {
  addEdge, Background, BackgroundVariant, BaseEdge, Controls, Handle, MiniMap, Position,
  ReactFlow, ReactFlowProvider, useEdgesState, useNodesState, useReactFlow,
  type Connection, type Edge, type EdgeChange, type EdgeProps, type Node, type NodeChange,
} from "@xyflow/react";
import {
  AlertTriangle, Antenna, Bot, ChevronRight, CloudCog, Cpu, Gauge, HardDrive,
  Cable, Maximize2, Minimize2, Monitor, Network, Redo2, Router, Save, Server,
  Trash2, Undo2, Waypoints, X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { Conversation, ConversationContent, ConversationScrollButton } from "@/components/ai-elements/conversation";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import { PromptInput, PromptInputFooter, PromptInputSubmit, PromptInputTextarea } from "@/components/ai-elements/prompt-input";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, generateUUID } from "@/lib/utils";
import { supabase } from "@/integrations/supabase/custom-client";
import { calculateLinkMetrics, findPathMetrics } from "@/lib/network-simulation";

type BaseDeviceType = "core-router" | "distribution-switch" | "cloud-server" | "load-balancer";
type DeviceModel = "pc-pt" | "1941-router" | "server-pt" | "hub-pt" | "accesspoint-pt" | "2960-24tt-switch" | "smart-load-balancer";
type DeviceConfig = { ipAddress: string; subnetMask: string; defaultGateway: string; interfacePorts: string; httpPort: string };
type DeviceData = { label: string; deviceType: BaseDeviceType; model: DeviceModel; status: "healthy" | "warning" | "offline"; config: DeviceConfig };
type DeviceNode = Node<DeviceData, "device">;
type CableType = "straight-through" | "crossover" | "fiber" | "serial" | "console";
type CableData = { cableType: CableType; highlighted?: boolean; status?: string; baseLatencyMs?: number; maxCapacityMbps?: number; currentLoadMbps?: number; priorityLoadMbps?: number; qos?: boolean };
type CableEdge = Edge<CableData, "cable">;
type Snapshot = { nodes: DeviceNode[]; edges: CableEdge[] };
type ChatEntry = { id: string; role: "user" | "assistant"; text: string };
type PanelMode = "closed" | "open" | "full";

const emptyConfig = (): DeviceConfig => ({ ipAddress: "", subnetMask: "255.255.255.0", defaultGateway: "", interfacePorts: "GigabitEthernet0/0, GigabitEthernet0/1", httpPort: "80" });
const catalog: Array<{ model: DeviceModel; type: BaseDeviceType; label: string; subtitle: string; icon: typeof Router }> = [
  { model: "pc-pt", type: "cloud-server", label: "PC-PT", subtitle: "End-user workstation", icon: Monitor },
  { model: "1941-router", type: "core-router", label: "1941 Router", subtitle: "ISR branch gateway", icon: Router },
  { model: "server-pt", type: "cloud-server", label: "Server-PT", subtitle: "Application host", icon: Server },
  { model: "hub-pt", type: "distribution-switch", label: "Hub-PT", subtitle: "Shared Ethernet hub", icon: Cpu },
  { model: "accesspoint-pt", type: "distribution-switch", label: "AccessPoint-PT", subtitle: "Wireless access", icon: Antenna },
  { model: "2960-24tt-switch", type: "distribution-switch", label: "2960-24TT Switch", subtitle: "Catalyst access switch", icon: Waypoints },
  { model: "smart-load-balancer", type: "load-balancer", label: "Smart Load Balancer", subtitle: "Traffic optimization", icon: CloudCog },
];
const modelIcons = { "pc-pt": Monitor, "1941-router": Router, "server-pt": Server, "hub-pt": Cpu, "accesspoint-pt": Antenna, "2960-24tt-switch": Waypoints, "smart-load-balancer": CloudCog };
const legacyModels: Record<BaseDeviceType, DeviceModel> = { "core-router": "1941-router", "distribution-switch": "2960-24tt-switch", "cloud-server": "server-pt", "load-balancer": "smart-load-balancer" };
const ipv4Pattern = /^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$/;
const validAddressList = (value: string, router: boolean) => {
  const addresses = value.split(",").map(item => item.trim()).filter(Boolean);
  return addresses.length > 0 && (router || addresses.length === 1) && addresses.every(item => {
    const [ip, prefix] = item.split("/");
    return typeof ip === "string" && ipv4Pattern.test(ip) && (prefix === undefined || (/^\d+$/.test(prefix) && Number(prefix) >= 1 && Number(prefix) <= 30));
  });
};
const cableOptions: Array<{ value: CableType; label: string; short: string }> = [
  { value: "straight-through", label: "Copper Straight-Through", short: "Straight" },
  { value: "crossover", label: "Copper Crossover", short: "Crossover" },
  { value: "fiber", label: "Fiber", short: "Fiber" },
  { value: "serial", label: "Serial DCE/DTE", short: "Serial" },
  { value: "console", label: "Console", short: "Console" },
];

function cableStyle(type: CableType, highlighted = false): React.CSSProperties {
  const color = type === "fiber" ? "var(--cable-fiber)" : type === "serial" ? "var(--cable-serial)" : type === "console" ? "var(--cable-console)" : "var(--cable-copper)";
  return { stroke: color, strokeWidth: highlighted ? 5 : 2.5, strokeDasharray: type === "crossover" ? "9 6" : undefined, filter: highlighted ? "drop-shadow(0 0 5px var(--primary))" : undefined };
}

function CableEdgeView({ id, sourceX, sourceY, targetX, targetY, data, markerEnd, selected }: EdgeProps<CableEdge>) {
  const cableType = data?.cableType ?? "straight-through";
  const usage = calculateLinkMetrics({ id, source: "", target: "", status: data?.status ?? "active", baseLatencyMs: data?.baseLatencyMs ?? 1, maxCapacityMbps: data?.maxCapacityMbps ?? 1000, currentLoadMbps: data?.currentLoadMbps ?? 100 });
  const utilizationColor = usage.utilizationPct > 80 ? "#ef4444" : usage.utilizationPct >= 50 ? "#f59e0b" : "#22c55e";
  const path = cableType === "serial"
    ? (() => { const segments = 12; let value = `M ${sourceX} ${sourceY}`; for (let i = 1; i < segments; i += 1) { const t = i / segments; const x = sourceX + (targetX - sourceX) * t; const y = sourceY + (targetY - sourceY) * t + (i % 2 ? -6 : 6); value += ` L ${x} ${y}`; } return `${value} L ${targetX} ${targetY}`; })()
    : `M ${sourceX} ${sourceY} C ${(sourceX + targetX) / 2} ${sourceY}, ${(sourceX + targetX) / 2} ${targetY}, ${targetX} ${targetY}`;
  return <BaseEdge id={id} path={path} {...(markerEnd ? { markerEnd } : {})} style={{ ...cableStyle(cableType, Boolean(data?.highlighted || selected)), stroke: data?.status === "offline" ? "#6b7280" : utilizationColor, strokeWidth: selected ? 5 : 3, animation: usage.utilizationPct > 80 ? "pulse 1s infinite" : undefined }} />;
}

function parseConfiguration(value: unknown, type: BaseDeviceType): Pick<DeviceData, "model" | "config"> {
  const raw = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const model = catalog.some(item => item.model === raw["model"]) ? raw["model"] as DeviceModel : legacyModels[type];
  return { model, config: { ipAddress: typeof raw["ipAddress"] === "string" ? raw["ipAddress"] : "", subnetMask: typeof raw["subnetMask"] === "string" ? raw["subnetMask"] : "255.255.255.0", defaultGateway: typeof raw["defaultGateway"] === "string" ? raw["defaultGateway"] : "", interfacePorts: typeof raw["interfacePorts"] === "string" ? raw["interfacePorts"] : "GigabitEthernet0/0, GigabitEthernet0/1", httpPort: typeof raw["httpPort"] === "string" ? raw["httpPort"] : "80" } };
}

function DeviceNodeCard({ data, selected }: { data: DeviceData; selected?: boolean }) {
  const Icon = modelIcons[data.model] ?? HardDrive;
  return <div className={cn("min-w-44 border bg-card shadow-lg transition", selected ? "border-primary ring-2 ring-primary/20" : "border-border")}>
    <Handle type="target" position={Position.Left} className="!size-2.5 !border-2 !border-card !bg-primary" />
    <div className="flex items-center gap-3 p-3"><div className="grid size-9 place-items-center rounded-md bg-primary/10 text-primary"><Icon className="size-4" /></div><div className="min-w-0"><div className="max-w-32 truncate text-xs font-semibold">{data.label}</div><div className="mt-1 flex items-center gap-1.5 text-[9px] uppercase text-muted-foreground"><span className={cn("size-1.5 rounded-full", data.status === "warning" ? "bg-amber-500" : data.status === "offline" ? "bg-destructive" : "bg-success")} />{data.status}</div></div></div>
    <div className="flex items-center justify-between gap-3 border-t px-3 py-1.5 font-mono text-[9px] text-muted-foreground"><span>{data.model.toUpperCase()}</span><span>{data.config.ipAddress || "DHCP / UNSET"}</span></div>
    <Handle type="source" position={Position.Right} className="!size-2.5 !border-2 !border-card !bg-primary" />
  </div>;
}

const initialChat: ChatEntry[] = [
  { id: "welcome", role: "assistant", text: "**Topology analysis online.** I’m monitoring addressing, path diversity, device health, and configuration conflicts." },
];

export function NetworkWorkspace() { return <ReactFlowProvider><WorkspaceInner /></ReactFlowProvider>; }

function WorkspaceInner() {
  const { screenToFlowPosition } = useReactFlow();
  const [nodes, setNodes, onNodesChangeBase] = useNodesState<DeviceNode>([]);
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState<CableEdge>([]);
  const [history, setHistory] = useState<Snapshot[]>([]); const [future, setFuture] = useState<Snapshot[]>([]);
  const [userId, setUserId] = useState(""); const [loading, setLoading] = useState(true); const [sync, setSync] = useState<"saved" | "saving" | "error">("saved");
  const [assistantPanel, setAssistantPanel] = useState<PanelMode>("open"); const [telemetryPanel, setTelemetryPanel] = useState<PanelMode>("open");
  const [assistantWidth, setAssistantWidth] = useState(360); const [telemetryWidth, setTelemetryWidth] = useState(280);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null); const [selectedCable, setSelectedCable] = useState<CableType>("straight-through");
  const [simulationSourceId, setSimulationSourceId] = useState(""); const [simulationTargetId, setSimulationTargetId] = useState("");
  const [latencyHistory, setLatencyHistory] = useState<number[]>([]);
  const [messages, setMessages] = useState<ChatEntry[]>(initialChat); const [thinking, setThinking] = useState(false);
  const nodesRef = useRef(nodes); const edgesRef = useRef(edges); const editingRef = useRef(false);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]); useEffect(() => { edgesRef.current = edges; }, [edges]);
  const mountedRef = useRef(true); useEffect(() => () => { mountedRef.current = false; }, []);
  const realtimeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncQueue = useRef<Promise<void>>(Promise.resolve());
  useEffect(() => { try { const stored = JSON.parse(localStorage.getItem("nettransform-panel-preferences") ?? "null") as { assistantPanel?: PanelMode; telemetryPanel?: PanelMode; assistantWidth?: number; telemetryWidth?: number } | null; if (stored?.assistantPanel === "closed" || stored?.assistantPanel === "open") setAssistantPanel(stored.assistantPanel); if (stored?.telemetryPanel === "closed" || stored?.telemetryPanel === "open") setTelemetryPanel(stored.telemetryPanel); if (typeof stored?.assistantWidth === "number") setAssistantWidth(Math.min(580, Math.max(320, stored.assistantWidth))); if (typeof stored?.telemetryWidth === "number") setTelemetryWidth(Math.min(420, Math.max(240, stored.telemetryWidth))); } catch { /* Ignore invalid local panel preferences. */ } }, []);
  useEffect(() => { localStorage.setItem("nettransform-panel-preferences", JSON.stringify({ assistantPanel, telemetryPanel, assistantWidth, telemetryWidth })); }, [assistantPanel, telemetryPanel, assistantWidth, telemetryWidth]);

  const simulationLinks = useMemo(() => edges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target, status: edge.data?.status ?? "active", baseLatencyMs: edge.data?.baseLatencyMs ?? 1, maxCapacityMbps: edge.data?.maxCapacityMbps ?? 1000, currentLoadMbps: edge.data?.currentLoadMbps ?? 100, priorityLoadMbps: edge.data?.priorityLoadMbps ?? 20, qos: edge.data?.qos ?? false })), [edges]);
  const networkMetrics = useMemo(() => {
    const links = simulationLinks.map(link => calculateLinkMetrics(link));
    const endpoints = nodes.filter(node => !["core-router", "distribution-switch"].includes(node.data.deviceType));
    const sourceId = endpoints.find(node => node.id === simulationSourceId)?.id ?? endpoints[0]?.id;
    const targetId = endpoints.find(node => node.id === simulationTargetId)?.id ?? endpoints.at(-1)?.id;
    const path = sourceId && targetId ? findPathMetrics(nodes.map(node => ({ id: node.id, status: node.data.status })), simulationLinks, sourceId, targetId) : null;
    return { links, path, utilization: links.length ? links.reduce((sum, value) => sum + value.utilizationPct, 0) / links.length : 0 };
  }, [nodes, simulationLinks, simulationSourceId, simulationTargetId]);
  useEffect(() => {
    const latency = networkMetrics.path?.latencyMs;
    if (latency !== null && latency !== undefined) setLatencyHistory(history => [...history, latency].slice(-24));
  }, [networkMetrics.path?.latencyMs]);

  const snapshot = useCallback(() => ({ nodes: structuredClone(nodesRef.current), edges: structuredClone(edgesRef.current) }), []);
  const record = useCallback(() => { setHistory(h => [...h.slice(-39), snapshot()]); setFuture([]); }, [snapshot]);
  const rowsFor = useCallback((next: Snapshot) => ({
    nodeRows: next.nodes.map(n => ({ id: n.id, user_id: userId, node_type: n.data.deviceType, label: n.data.label, position_x: n.position.x, position_y: n.position.y, status: n.data.status, configuration: { model: n.data.model, ...n.data.config } })),
    edgeRows: next.edges.map(e => ({ id: e.id, user_id: userId, source_node_id: e.source, target_node_id: e.target, source_handle: e.sourceHandle ?? null, target_handle: e.targetHandle ?? null, status: e.data?.status === "offline" ? "offline" : "active", configuration: { pathType: "cable", cableType: e.data?.cableType ?? "straight-through", base_latency_ms: e.data?.baseLatencyMs ?? 1, max_capacity_mbps: e.data?.maxCapacityMbps ?? 1000, current_load_mbps: e.data?.currentLoadMbps ?? 100, priority_load_mbps: e.data?.priorityLoadMbps ?? 20, qos: e.data?.qos ?? false } })),
  }), [userId]);

  const syncSnapshot = useCallback((next: Snapshot, removedNodeIds: string[] = [], removedEdgeIds: string[] = []) => {
    if (!userId) return Promise.resolve(); setSync("saving");
    const run = syncQueue.current.catch(() => undefined).then(async () => {
      const { nodeRows, edgeRows } = rowsFor(next); const errors: unknown[] = [];
      if (nodeRows.length) { const { error } = await supabase.from("network_nodes").upsert(nodeRows); if (error) errors.push(error); }
      if (edgeRows.length) { const { error } = await supabase.from("network_connections").upsert(edgeRows); if (error) errors.push(error); }
      if (removedEdgeIds.length) { const { error } = await supabase.from("network_connections").delete().eq("user_id", userId).in("id", removedEdgeIds); if (error) errors.push(error); }
      if (removedNodeIds.length) { const { error } = await supabase.from("network_nodes").delete().eq("user_id", userId).in("id", removedNodeIds); if (error) errors.push(error); }
      if (mountedRef.current) setSync(errors.length ? "error" : "saved");
      if (errors.length) throw errors[0];
    });
    syncQueue.current = run.catch(() => undefined);
    return run;
  }, [rowsFor, userId]);

  const saveTopology = useCallback(async (current: Snapshot = snapshot(), showFeedback = true): Promise<boolean> => {
    if (!userId) {
      if (showFeedback) toast.error("Sign in before saving this topology");
      return false;
    }
    setSync("saving");
    try {
      const { nodeRows, edgeRows } = rowsFor(current);
      const [{ data: savedNodes, error: nodesReadError }, { data: savedEdges, error: edgesReadError }] = await Promise.all([
        supabase.from("network_nodes").select("id").eq("user_id", userId), supabase.from("network_connections").select("id").eq("user_id", userId),
      ]);
      if (nodesReadError || edgesReadError) throw nodesReadError ?? edgesReadError;
      const removedEdges = (savedEdges ?? []).map(row => row.id).filter(id => !current.edges.some(edge => edge.id === id));
      const removedNodes = (savedNodes ?? []).map(row => row.id).filter(id => !current.nodes.some(node => node.id === id));
      if (nodeRows.length) { const { error } = await supabase.from("network_nodes").upsert(nodeRows); if (error) throw error; }
      if (edgeRows.length) { const { error } = await supabase.from("network_connections").upsert(edgeRows); if (error) throw error; }
      if (removedEdges.length) { const { error } = await supabase.from("network_connections").delete().eq("user_id", userId).in("id", removedEdges); if (error) throw error; }
      if (removedNodes.length) { const { error } = await supabase.from("network_nodes").delete().eq("user_id", userId).in("id", removedNodes); if (error) throw error; }
      setSync("saved");
      if (showFeedback) toast.success("Topology Saved Successfully");
      return true;
    } catch {
      setSync("error");
      if (showFeedback) toast.error("Topology could not be saved");
      return false;
    }
  }, [rowsFor, snapshot, userId]);
  useEffect(() => { const save = () => void saveTopology(); window.addEventListener("nexustwin:save", save); return () => window.removeEventListener("nexustwin:save", save); }, [saveTopology]);

  const mapNode = useCallback((r: { id: string; node_type: string; label: string; position_x: number; position_y: number; status: string; configuration: unknown }): DeviceNode => {
    const deviceType = r.node_type as BaseDeviceType; const parsed = parseConfiguration(r.configuration, deviceType);
    return { id: r.id, type: "device", position: { x: r.position_x, y: r.position_y }, data: { label: r.label, deviceType, status: r.status as DeviceData["status"], ...parsed } };
  }, []);
  const mapEdge = useCallback((r: { id: string; source_node_id: string; target_node_id: string; source_handle: string | null; target_handle: string | null; status: string; configuration?: unknown }): CableEdge => {
    const raw = r.configuration && typeof r.configuration === "object" && !Array.isArray(r.configuration) ? r.configuration as Record<string, unknown> : {};
    const metric = (key: string, fallback: number) => { const value = raw[key]; return typeof value === "number" && Number.isFinite(value) ? value : fallback; };
    const value = raw["cableType"];
    const cableType = cableOptions.some(option => option.value === value) ? value as CableType : "straight-through";
    return { id: r.id, source: r.source_node_id, target: r.target_node_id, sourceHandle: r.source_handle, targetHandle: r.target_handle, type: "cable", animated: false, data: { cableType, status: r.status, baseLatencyMs: metric("base_latency_ms", 1), maxCapacityMbps: metric("max_capacity_mbps", 1000), currentLoadMbps: metric("current_load_mbps", 100), priorityLoadMbps: metric("priority_load_mbps", 20), qos: raw["qos"] === true } };
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      const { data: auth } = await supabase.auth.getUser(); if (!auth.user || !active) return; setUserId(auth.user.id);
      const [{ data: rows }, { data: links }, { data: chats }] = await Promise.all([supabase.from("network_nodes").select("*").order("created_at"), supabase.from("network_connections").select("*").order("created_at"), supabase.from("chat_messages").select("*").eq("user_id", auth.user.id).order("sequence")]);
      if (!active) return; setNodes((rows ?? []).map(mapNode)); setEdges((links ?? []).map(mapEdge));
      if (chats?.length) setMessages(chats.map(r => ({ id: r.id, role: r.role as ChatEntry["role"], text: Array.isArray(r.parts) ? String((r.parts[0] as { text?: string })?.text ?? "") : "" })));
      const pendingUndo = localStorage.getItem(`nexustwin-recommendation-undo-${auth.user.id}`);
      if (pendingUndo) { try { setHistory([JSON.parse(pendingUndo) as Snapshot]); } catch { /* Invalid local snapshot is safely ignored. */ } localStorage.removeItem(`nexustwin-recommendation-undo-${auth.user.id}`); }
      const pendingHighlight = localStorage.getItem(`nexustwin-recommendation-highlight-${auth.user.id}`);
      if (pendingHighlight) { try { const target = JSON.parse(pendingHighlight) as { nodeId?: string; edgeId?: string }; if (target.nodeId) setSelectedNodeId(target.nodeId); if (target.edgeId) { setSelectedEdgeId(target.edgeId); setEdges(current => current.map(edge => edge.id === target.edgeId ? { ...edge, data: { cableType: edge.data?.cableType ?? "straight-through", highlighted: true } } : edge)); } } catch { /* Ignore invalid transient highlight state. */ } localStorage.removeItem(`nexustwin-recommendation-highlight-${auth.user.id}`); }
      setLoading(false);
    })(); return () => { active = false; };
  }, [mapEdge, mapNode, setEdges, setNodes]);

  useEffect(() => {
    if (!userId) return;
    const reload = () => { if (realtimeTimer.current) clearTimeout(realtimeTimer.current); realtimeTimer.current = setTimeout(() => { void (async () => { const [{ data: rows }, { data: links }] = await Promise.all([supabase.from("network_nodes").select("*").eq("user_id", userId), supabase.from("network_connections").select("*").eq("user_id", userId)]); if (!mountedRef.current) return; setNodes((rows ?? []).map(mapNode)); setEdges((links ?? []).map(mapEdge)); })(); }, 250); };
    const channel = supabase.channel(`topology-${userId}`).on("postgres_changes", { event: "*", schema: "public", table: "network_nodes", filter: `user_id=eq.${userId}` }, reload).on("postgres_changes", { event: "*", schema: "public", table: "network_connections", filter: `user_id=eq.${userId}` }, reload).subscribe();
    return () => { if (realtimeTimer.current) clearTimeout(realtimeTimer.current); void supabase.removeChannel(channel); };
  }, [mapEdge, mapNode, setEdges, setNodes, userId]);

  const onDragStart = (e: DragEvent, model: DeviceModel) => { e.dataTransfer.setData("application/nexustwin", model); e.dataTransfer.effectAllowed = "move"; };
  const onDrop = async (e: DragEvent) => { e.preventDefault(); const model = e.dataTransfer.getData("application/nexustwin") as DeviceModel; const item = catalog.find(x => x.model === model); if (!item || !userId) return; record(); const position = screenToFlowPosition({ x: e.clientX, y: e.clientY }); const id = generateUUID(); const next: DeviceNode = { id, type: "device", position, data: { label: item.label, deviceType: item.type, model, status: "healthy", config: emptyConfig() } }; setNodes(n => [...n, next]); setSync("saving"); const { error } = await supabase.from("network_nodes").insert({ id, user_id: userId, node_type: item.type, label: item.label, position_x: position.x, position_y: position.y, configuration: { model, ...next.data.config } }); setSync(error ? "error" : "saved"); };
  const onConnect = async (connection: Connection) => { if (!userId) return; record(); const id = generateUUID(); const data = { cableType: selectedCable, status: "active", baseLatencyMs: 1, maxCapacityMbps: 1000, currentLoadMbps: 100, priorityLoadMbps: 20, qos: false }; const edge: CableEdge = { ...connection, id, type: "cable", animated: false, data }; setEdges(es => addEdge(edge, es)); setSync("saving"); const { error } = await supabase.from("network_connections").insert({ id, user_id: userId, source_node_id: connection.source, target_node_id: connection.target, source_handle: connection.sourceHandle ?? null, target_handle: connection.targetHandle ?? null, status: "active", configuration: { pathType: "cable", cableType: selectedCable, base_latency_ms: 1, max_capacity_mbps: 1000, current_load_mbps: 100, priority_load_mbps: 20, qos: false } }); setSync(error ? "error" : "saved"); };
  const onNodesChange = (changes: NodeChange<DeviceNode>[]) => { const removed = changes.filter(c => c.type === "remove").map(c => c.id); if (removed.length) { record(); if (removed.includes(selectedNodeId ?? "")) setSelectedNodeId(null); } onNodesChangeBase(changes); const ended = changes.find(c => c.type === "position" && c.dragging === false); if (ended) queueMicrotask(() => void syncSnapshot({ nodes: nodesRef.current, edges: edgesRef.current }).catch(() => undefined)); if (removed.length) queueMicrotask(() => void syncSnapshot({ nodes: nodesRef.current, edges: edgesRef.current }, removed).catch(() => undefined)); };
  const onEdgesChange = (changes: EdgeChange<CableEdge>[]) => { const removed = changes.filter(c => c.type === "remove").map(c => c.id); if (removed.length) { record(); if (removed.includes(selectedEdgeId ?? "")) setSelectedEdgeId(null); } onEdgesChangeBase(changes); if (removed.length) queueMicrotask(() => void syncSnapshot({ nodes: nodesRef.current, edges: edgesRef.current }, [], removed).catch(() => undefined)); };
  const chooseCable = (cableType: CableType) => { setSelectedCable(cableType); if (!selectedEdgeId) return; record(); const next = edgesRef.current.map(edge => edge.id === selectedEdgeId ? { ...edge, data: { cableType, highlighted: true } } : edge); setEdges(next); void syncSnapshot({ nodes: nodesRef.current, edges: next }).catch(() => toast.error("Cable type could not be saved")); };
  const simulateNodeFailure = () => {
    if (!selectedNodeId) { toast.error("Select a device first"); return; }
    record();
    const nextNodes = nodesRef.current.map(node => node.id === selectedNodeId ? { ...node, data: { ...node.data, status: node.data.status === "offline" ? "healthy" as const : "offline" as const } } : node);
    setNodes(nextNodes);
    void syncSnapshot({ nodes: nextNodes, edges: edgesRef.current }).then(() => toast.success("Simulated device status saved"), () => toast.error("Simulation status could not be saved"));
  };
  const failSelectedLink = () => {
    if (!selectedEdgeId) { toast.error("Select a link first"); return; }
    record();
    const nextEdges = edgesRef.current.map(edge => edge.id === selectedEdgeId ? { ...edge, data: { ...(edge.data ?? { cableType: "straight-through" as CableType }), status: edge.data?.status === "offline" ? "active" : "offline" } } : edge);
    setEdges(nextEdges);
    void syncSnapshot({ nodes: nodesRef.current, edges: nextEdges }).then(() => toast.success("Simulated link status saved"), () => toast.error("Simulation status could not be saved"));
  };
  const spikeSelectedLink = () => {
    if (!selectedEdgeId) { toast.error("Select a link first"); return; }
    record();
    const nextEdges = edgesRef.current.map(edge => edge.id === selectedEdgeId ? { ...edge, data: { ...(edge.data ?? { cableType: "straight-through" as CableType }), currentLoadMbps: (edge.data?.maxCapacityMbps ?? 1000) * 1.5 } } : edge);
    setEdges(nextEdges);
    void syncSnapshot({ nodes: nodesRef.current, edges: nextEdges }).then(() => toast.success("Traffic spike simulated and saved"), () => toast.error("Traffic load could not be saved"));
  };
  const deployModernization = () => {
    if (!edgesRef.current.length) { toast.error("Add links before deploying the blueprint"); return; }
    record();
    const groups = new Map<string, CableEdge[]>();
    for (const edge of edgesRef.current) { const key = [edge.source, edge.target].sort().join(":"); groups.set(key, [...(groups.get(key) ?? []), edge]); }
    const nextEdges = edgesRef.current.map(edge => { const key = [edge.source, edge.target].sort().join(":"); const parallel = groups.get(key) ?? [edge]; const totalLoad = parallel.reduce((sum, link) => sum + (link.data?.currentLoadMbps ?? 100), 0); return { ...edge, data: { ...(edge.data ?? { cableType: "straight-through" as CableType }), qos: true, currentLoadMbps: totalLoad / parallel.length, priorityLoadMbps: Math.min(totalLoad / parallel.length * 0.2, (edge.data?.maxCapacityMbps ?? 1000) * 0.2) } }; });
    setEdges(nextEdges);
    void syncSnapshot({ nodes: nodesRef.current, edges: nextEdges }).then(() => toast.success("Load balancing and QoS simulation saved"), () => toast.error("Modernization settings could not be saved"));
  };
  const undo = () => { const previous = history.at(-1); if (!previous) return; const current = snapshot(); setFuture(f => [current, ...f]); setHistory(h => h.slice(0, -1)); setNodes(previous.nodes); setEdges(previous.edges); void syncSnapshot(previous, current.nodes.filter(n => !previous.nodes.some(p => p.id === n.id)).map(n => n.id), current.edges.filter(e => !previous.edges.some(p => p.id === e.id)).map(e => e.id)).catch(() => undefined); };
  const redo = () => { const next = future[0]; if (!next) return; const current = snapshot(); setHistory(h => [...h, current]); setFuture(f => f.slice(1)); setNodes(next.nodes); setEdges(next.edges); void syncSnapshot(next, current.nodes.filter(n => !next.nodes.some(p => p.id === n.id)).map(n => n.id), current.edges.filter(e => !next.edges.some(p => p.id === e.id)).map(e => e.id)).catch(() => undefined); };
  useEffect(() => { const key = (e: KeyboardEvent) => { if (!(e.metaKey || e.ctrlKey)) return; if (e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); } }; window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); });

  const selectedNode = nodes.find(node => node.id === selectedNodeId);
  const selectedEdge = edges.find(edge => edge.id === selectedEdgeId);
  const beginEdit = () => { if (!editingRef.current) { record(); editingRef.current = true; } };
  const updateSelected = (field: "label" | keyof DeviceConfig, value: string) => { if (!selectedNodeId) return; beginEdit(); setNodes(current => current.map(node => node.id === selectedNodeId ? { ...node, data: { ...node.data, ...(field === "label" ? { label: value } : { config: { ...node.data.config, [field]: value } }) } } : node)); };
  const commitSelected = () => { if (!editingRef.current) return; editingRef.current = false; queueMicrotask(() => void syncSnapshot({ nodes: nodesRef.current, edges: edgesRef.current }).catch(() => toast.error("Device settings could not be saved"))); };
  const updateSelectedLink = (field: "baseLatencyMs" | "maxCapacityMbps" | "currentLoadMbps" | "priorityLoadMbps", value: number) => {
    if (!selectedEdgeId || !Number.isFinite(value) || value < 0) return;
    if (!editingRef.current) { record(); editingRef.current = true; }
    const next = edgesRef.current.map(edge => edge.id === selectedEdgeId ? { ...edge, data: { ...(edge.data ?? { cableType: "straight-through" as CableType }), [field]: value } } : edge);
    setEdges(next);
  };
  const commitSelectedLink = () => {
    if (!editingRef.current) return;
    editingRef.current = false;
    queueMicrotask(() => void syncSnapshot({ nodes: nodesRef.current, edges: edgesRef.current }).catch(() => toast.error("Link simulation settings could not be saved")));
  };

  const duplicateIps = useMemo(() => { const counts = new Map<string, number>(); nodes.forEach(node => { const ip = node.data.config.ipAddress; if (ip) counts.set(ip, (counts.get(ip) ?? 0) + 1); }); return new Set([...counts].filter(([, count]) => count > 1).map(([ip]) => ip)); }, [nodes]);
  const selectedFields: Array<["label" | keyof DeviceConfig, string]> = selectedNode ? [
    ["label", "Device Name"],
    ["ipAddress", selectedNode.data.deviceType === "core-router" ? "Interface IPv4 addresses" : "IP Address"],
    ["subnetMask", "Subnet Mask"],
    ["defaultGateway", "Default Gateway"],
    ["interfacePorts", "Interface Ports"],
    ...(selectedNode.data.deviceType === "cloud-server" && selectedNode.data.model === "server-pt" ? [["httpPort", "HTTP Service Port"] as ["httpPort", string]] : []),
  ] : [];
  const routerLinkOrder = selectedNode?.data.deviceType === "core-router" ? edges
    .filter(edge => edge.source === selectedNode.id || edge.target === selectedNode.id)
    .map((edge, index) => `${index + 1}: ${nodes.find(node => node.id === (edge.source === selectedNode.id ? edge.target : edge.source))?.data.label ?? "device"}`)
    .join(" · ") : "";
  const isolatedCount = useMemo(() => nodes.filter(node => !edges.some(edge => edge.source === node.id || edge.target === node.id)).length, [edges, nodes]);
  const unconfiguredCount = nodes.filter(node => !node.data.config.ipAddress).length;
  const alert = duplicateIps.size ? `${duplicateIps.size} duplicate IP address conflict${duplicateIps.size > 1 ? "s" : ""} detected` : isolatedCount && nodes.length > 1 ? `${isolatedCount} isolated device${isolatedCount > 1 ? "s" : ""} require cabling` : unconfiguredCount && nodes.length ? `${unconfiguredCount} device${unconfiguredCount > 1 ? "s" : ""} awaiting IP configuration` : nodes.length ? "Topology synchronized — addressing and active paths nominal" : "Canvas ready — drag Cisco devices to begin";
  const warning = Boolean(duplicateIps.size || (isolatedCount && nodes.length > 1) || (unconfiguredCount && nodes.length));

  const send = async ({ text }: { text: string }) => { const value = text.trim(); if (!value || !userId) return; const userMessage = { id: generateUUID(), role: "user" as const, text: value }; setMessages(m => [...m, userMessage]); setThinking(true); await supabase.from("chat_messages").insert({ id: userMessage.id, user_id: userId, role: "user", parts: [{ type: "text", text: value }] }); let response = `I’m analyzing **${nodes.length} devices** across **${edges.length} links**.`; if (duplicateIps.size) response += ` I found duplicate addressing on **${[...duplicateIps].join(", ")}**. Assign a unique host address to each device before testing reachability.`; else if (isolatedCount) response += ` **${isolatedCount} device${isolatedCount > 1 ? "s are" : " is"} isolated**. Connect each one to an access or distribution device.`; else if (unconfiguredCount) response += ` **${unconfiguredCount} device${unconfiguredCount > 1 ? "s have" : " has"} no IP address**. Use the device inspector or implement an auto-addressed recommendation.`; else response += " Addressing is unique and every device has a link. The current layout is ready for gateway and failover validation."; const assistant = { id: generateUUID(), role: "assistant" as const, text: response }; setTimeout(() => { if (!mountedRef.current) return; setMessages(m => [...m, assistant]); setThinking(false); void supabase.from("chat_messages").insert({ id: assistant.id, user_id: userId, role: "assistant", parts: [{ type: "text", text: response }] }); }, 500); };
  const deleteChatHistory = async () => { if (!userId || !window.confirm("Delete your AI assistant chat history? This will not delete topology or simulation data.")) return; const { error } = await supabase.from("chat_messages").delete().eq("user_id", userId); if (error) { toast.error("Chat history could not be deleted"); return; } setMessages(initialChat); toast.success("Chat history deleted"); };
  useEffect(() => {
    const toggleAssistant = () => setAssistantPanel(current => current === "closed" ? "open" : "closed");
    const toggleTelemetry = () => setTelemetryPanel(current => current === "closed" ? "open" : "closed");
    window.addEventListener("nettransform:toggle-assistant", toggleAssistant);
    window.addEventListener("nettransform:toggle-telemetry", toggleTelemetry);
    return () => { window.removeEventListener("nettransform:toggle-assistant", toggleAssistant); window.removeEventListener("nettransform:toggle-telemetry", toggleTelemetry); };
  }, [assistantPanel, telemetryPanel]);
  useEffect(() => { window.dispatchEvent(new CustomEvent("nettransform:panel-state", { detail: { assistantOpen: assistantPanel !== "closed", telemetryOpen: telemetryPanel !== "closed" } })); }, [assistantPanel, telemetryPanel]);

  return (
    <main className="relative flex min-h-0 flex-1 overflow-hidden">
      <aside className="z-20 w-14 shrink-0 border-r bg-card p-2 md:w-60 md:p-4">
        <div className="mb-5 hidden md:block">
          <p className="font-mono text-[10px] uppercase text-muted-foreground">Cisco device drawer</p>
          <h2 className="mt-1 text-sm font-semibold">Network devices</h2>
        </div>
        <div className="space-y-2">
          {catalog.map(item => (
            <TooltipProvider key={item.model}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div draggable onDragStart={e => onDragStart(e, item.model)} className="group flex cursor-grab items-center gap-3 border bg-background p-2 transition hover:border-primary active:cursor-grabbing md:p-3">
                    <div className="grid size-8 shrink-0 place-items-center rounded-md bg-accent text-primary md:size-9">
                      <item.icon className="size-4" />
                    </div>
                    <div className="hidden min-w-0 md:block">
                      <div className="truncate text-xs font-semibold">{item.label}</div>
                      <div className="text-[10px] text-muted-foreground">{item.subtitle}</div>
                    </div>
                  </div>
                </TooltipTrigger>
                <TooltipContent side="right" className="md:hidden">{item.label}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ))}
        </div>
        <div className="mt-6 hidden border-t pt-4 md:block">
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>DEVICES</span>
            <span className="font-mono text-foreground">{nodes.length}</span>
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-muted-foreground">
            <span>LINKS</span>
            <span className="font-mono text-foreground">{edges.length}</span>
          </div>
        </div>
      </aside>

      <section className="relative min-w-0 flex-1 grid-surface">
        <div className={cn("absolute left-3 right-3 top-3 z-20 flex items-center justify-between gap-3 border px-3 py-2 shadow-sm", warning ? "border-amber-500/40 bg-amber-500/10" : "border-success/40 bg-success/10")}><div className="flex min-w-0 items-center gap-2">{warning ? <AlertTriangle className="size-4 shrink-0 text-amber-500" /> : <Network className="size-4 shrink-0 text-success" />}<span className="truncate text-xs font-medium">{alert}</span><Badge variant="outline" className="hidden font-mono text-[9px] sm:inline-flex">{sync.toUpperCase()}</Badge></div><Button asChild size="sm"><Link to="/recommendations">Changes Recommended <ChevronRight /></Link></Button></div>
        <div className="absolute left-1/2 top-[4.5rem] z-20 flex -translate-x-1/2 flex-wrap items-center justify-center border bg-card shadow-md"><TooltipProvider><Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon" onClick={undo} disabled={!history.length} aria-label="Undo"><Undo2 /></Button></TooltipTrigger><TooltipContent>Undo</TooltipContent></Tooltip><Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon" onClick={redo} disabled={!future.length} aria-label="Redo"><Redo2 /></Button></TooltipTrigger><TooltipContent>Redo</TooltipContent></Tooltip></TooltipProvider><Button variant="ghost" size="sm" onClick={simulateNodeFailure}>Fail / Restore Device</Button><Button variant="ghost" size="sm" onClick={failSelectedLink}>Fail / Restore Link</Button><Button variant="ghost" size="sm" onClick={spikeSelectedLink}>Traffic Spike</Button><Button variant="ghost" size="sm" onClick={deployModernization}>Load Balance + QoS</Button></div>
        <div className="absolute bottom-4 left-1/2 z-30 flex max-w-[calc(100%-2rem)] -translate-x-1/2 items-center gap-1 overflow-x-auto border bg-card p-1 shadow-lg" aria-label="Cable selector"><div className="hidden items-center gap-1 border-r px-2 text-[10px] font-semibold uppercase text-muted-foreground sm:flex"><Cable className="size-3" /> Cable</div>{cableOptions.map(option => <TooltipProvider key={option.value}><Tooltip><TooltipTrigger asChild><Button size="sm" variant={selectedCable === option.value ? "secondary" : "ghost"} onClick={() => chooseCable(option.value)} className="shrink-0 px-2" aria-label={option.label}><span className={cn("h-0.5 w-7", option.value === "crossover" && "border-t-2 border-dashed border-cable-copper", option.value === "straight-through" && "bg-cable-copper", option.value === "fiber" && "bg-cable-fiber", option.value === "serial" && "bg-cable-serial", option.value === "console" && "bg-cable-console")} /><span className="hidden lg:inline">{option.short}</span></Button></TooltipTrigger><TooltipContent>{option.label}{selectedEdgeId ? " — apply to selected cable" : ""}</TooltipContent></Tooltip></TooltipProvider>)}</div>
        {loading ? <div className="grid h-full place-items-center text-sm text-muted-foreground">Loading synchronized topology…</div> : <ReactFlow nodes={nodes} edges={edges} nodeTypes={{ device: DeviceNodeCard }} edgeTypes={{ cable: CableEdgeView }} onNodesChange={onNodesChange} onNodeDragStart={record} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => { setSelectedNodeId(node.id); setSelectedEdgeId(null); }} onEdgeClick={(_, edge) => { setSelectedEdgeId(edge.id); setSelectedNodeId(null); setSelectedCable(edge.data?.cableType ?? "straight-through"); }} onPaneClick={() => { setSelectedNodeId(null); setSelectedEdgeId(null); }} onDrop={onDrop} onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }} fitView deleteKeyCode={["Backspace", "Delete"]} colorMode="system" defaultEdgeOptions={{ type: "cable" }}><Background variant={BackgroundVariant.Dots} gap={22} size={1} color="var(--canvas-dot)" /><Controls position="bottom-left" /><MiniMap position="bottom-right" nodeColor="var(--primary)" maskColor="color-mix(in oklch, var(--canvas) 75%, transparent)" /></ReactFlow>}
        {selectedNode && <aside className="absolute inset-y-3 right-3 z-40 flex w-[min(22rem,calc(100%-1.5rem))] flex-col border bg-card shadow-2xl"><div className="flex h-14 items-center justify-between border-b px-4"><div><p className="font-mono text-[9px] uppercase text-primary">Node Properties</p><h2 className="text-sm font-semibold">{selectedNode.data.model.toUpperCase()}</h2></div><Button variant="ghost" size="icon" onClick={() => setSelectedNodeId(null)} aria-label="Close device properties"><X /></Button></div><div className="border-b bg-muted/40 px-4 py-3"><div className="flex items-center gap-2 text-xs"><span className="size-2 rounded-full bg-success" /> Interface ready</div><p className="mt-1 text-[10px] text-muted-foreground">Static IPv4 and port configuration</p></div><div className="flex-1 space-y-5 overflow-y-auto p-4">{selectedFields.map(([field, label]) => { const value = field === "label" ? selectedNode.data.label : selectedNode.data.config[field]; const isRouterIp = field === "ipAddress" && selectedNode.data.deviceType === "core-router"; const invalid = field === "ipAddress" ? Boolean(value) && !validAddressList(value, isRouterIp) : field === "subnetMask" || field === "defaultGateway" ? Boolean(value) && !ipv4Pattern.test(value) : field === "httpPort" ? !/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65535 : false; const placeholder = field === "label" ? "Device hostname" : field === "subnetMask" ? "255.255.255.0" : field === "interfacePorts" ? "Gi0/0, Gi0/1, Fa0/1" : field === "httpPort" ? "80" : isRouterIp ? "10.0.1.1/24, 10.0.2.1/24" : "192.168.1.10"; return <div className="space-y-2" key={field}><Label htmlFor={`device-${field}`}>{label}</Label><Input id={`device-${field}`} value={value} onChange={e => updateSelected(field, e.target.value)} onBlur={commitSelected} className={cn("font-mono", invalid && "border-destructive focus-visible:ring-destructive")} placeholder={placeholder} />{invalid && <p className="text-xs text-destructive">{field === "httpPort" ? "Enter a port from 1 to 65535." : "Enter valid IPv4 address values."}</p>}{isRouterIp && <p className="text-[10px] text-muted-foreground">{routerLinkOrder ? `Match addresses to links in this order: ${routerLinkOrder}.` : "Connect the router first; enter one address per link."} Add CIDR suffixes such as /24 to set each subnet.</p>}{field === "httpPort" && <p className="text-[10px] text-muted-foreground">The HTTP service port is stored as part of this device configuration.</p>}</div>; })}<div className="border p-3 text-xs text-muted-foreground"><div className="flex justify-between"><span>Model</span><span className="font-mono text-foreground">{selectedNode.data.model}</span></div><div className="mt-2 flex justify-between"><span>Links</span><span className="font-mono text-foreground">{edges.filter(edge => edge.source === selectedNode.id || edge.target === selectedNode.id).length}</span></div></div></div><div className="border-t p-3"><Button className="w-full" onClick={() => { commitSelected(); toast.success("Device configuration saved"); }}><Save /> Save Configuration</Button></div></aside>}
        {selectedEdge && <aside className="absolute inset-y-3 right-3 z-40 flex w-[min(20rem,calc(100%-1.5rem))] flex-col border bg-card shadow-2xl"><div className="flex h-14 items-center justify-between border-b px-4"><div><p className="font-mono text-[9px] uppercase text-primary">Link Simulation</p><h2 className="text-sm font-semibold">{nodes.find(node => node.id === selectedEdge.source)?.data.label} → {nodes.find(node => node.id === selectedEdge.target)?.data.label}</h2></div><Button variant="ghost" size="icon" onClick={() => setSelectedEdgeId(null)} aria-label="Close link properties"><X /></Button></div><div className="flex-1 space-y-4 p-4">{([ ["baseLatencyMs", "Base latency (ms)"], ["maxCapacityMbps", "Max capacity (Mbps)"], ["currentLoadMbps", "Current load (Mbps)"], ["priorityLoadMbps", "Critical traffic (Mbps)"] ] as const).map(([field, label]) => <div className="space-y-2" key={field}><Label htmlFor={`link-${field}`}>{label}</Label><Input id={`link-${field}`} type="number" min="0" step="any" value={selectedEdge.data?.[field] ?? (field === "baseLatencyMs" ? 1 : field === "maxCapacityMbps" ? 1000 : field === "priorityLoadMbps" ? 20 : 100)} onFocus={() => { if (!editingRef.current) { record(); editingRef.current = true; } }} onChange={event => updateSelectedLink(field, Number(event.target.value))} onBlur={commitSelectedLink} /></div>)}<div className="text-xs text-muted-foreground">Utilization: {calculateLinkMetrics(simulationLinks.find(link => link.id === selectedEdge.id) ?? { id: selectedEdge.id, source: selectedEdge.source, target: selectedEdge.target, status: "active", baseLatencyMs: 1, maxCapacityMbps: 1000, currentLoadMbps: 100 }).utilizationPct.toFixed(1)}% · QoS {selectedEdge.data?.qos ? "enabled" : "disabled"}</div></div></aside>}
      </section>
      {assistantPanel !== "closed" && <aside style={{ width: assistantPanel === "full" ? undefined : assistantWidth }} className={cn("glass-panel z-40 flex flex-col border-l transition-[width] duration-200", assistantPanel === "full" ? "fixed inset-3" : "relative w-[min(92vw,36rem)] sm:w-auto")}>
        {assistantPanel === "open" && <div onMouseDown={e => { const startX = e.clientX, startW = assistantWidth; const move = (m: MouseEvent) => setAssistantWidth(Math.min(580, Math.max(320, startW + startX - m.clientX))); const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); }; window.addEventListener("mousemove", move); window.addEventListener("mouseup", up); }} className="absolute -left-1 top-0 z-50 hidden h-full w-2 cursor-col-resize sm:block" />}
        <div className="flex h-14 items-center justify-between border-b px-3"><div className="flex items-center gap-2"><div className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground"><Bot className="size-4" /></div><div><div className="text-xs font-semibold">AI Assistant</div><div className="text-[9px] text-success">TOPOLOGY CONTEXT ONLINE</div></div></div><div className="flex"><Button variant="ghost" size="icon" onClick={deleteChatHistory} aria-label="Delete chat history"><Trash2 /></Button><Button variant="ghost" size="icon" onClick={() => setAssistantPanel(current => current === "full" ? "open" : "full")} aria-label="Toggle assistant fullscreen">{assistantPanel === "full" ? <Minimize2 /> : <Maximize2 />}</Button><Button variant="ghost" size="icon" onClick={() => setAssistantPanel("closed")} aria-label="Collapse assistant"><X /></Button></div></div>
        <Conversation className="min-h-0"><ConversationContent className="gap-5 p-4">{messages.map(m => <Message key={m.id} from={m.role}><MessageContent className={m.role === "user" ? "bg-primary text-primary-foreground" : ""}><MessageResponse>{m.text}</MessageResponse></MessageContent></Message>)}{thinking && <Shimmer className="text-xs">Inspecting addresses and paths…</Shimmer>}</ConversationContent><ConversationScrollButton /></Conversation><div className="border-t p-3"><PromptInput onSubmit={(m: { text: string }) => send(m)}><PromptInputTextarea autoFocus placeholder="Ask me about your current IP configurations or how to troubleshoot this layout." /><PromptInputFooter className="justify-end"><PromptInputSubmit disabled={thinking} status={thinking ? "submitted" : "ready"} /></PromptInputFooter></PromptInput></div>
      </aside>}

      {/* Telemetry side panel */}
      {telemetryPanel !== "closed" && (
        <aside style={{ width: telemetryPanel === "full" ? undefined : telemetryWidth }} className={cn("glass-panel z-30 flex flex-col border-l bg-card p-4", telemetryPanel === "full" ? "fixed inset-3" : "relative w-[min(92vw,20rem)] sm:w-auto")}>
          {telemetryPanel === "open" && <div onMouseDown={e => { const startX = e.clientX, startW = telemetryWidth; const move = (m: MouseEvent) => setTelemetryWidth(Math.min(420, Math.max(240, startW + startX - m.clientX))); const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); }; window.addEventListener("mousemove", move); window.addEventListener("mouseup", up); }} className="absolute -left-1 top-0 z-50 hidden h-full w-2 cursor-col-resize sm:block" />}
          <div className="flex items-center justify-between border-b pb-2"><div><h2 className="text-sm font-semibold">Live Network Monitor</h2><p className="text-[10px] text-muted-foreground">Mathematical simulation from the saved topology</p></div><div className="flex"><Button variant="ghost" size="icon" onClick={() => setTelemetryPanel(current => current === "full" ? "open" : "full")} aria-label="Toggle monitor fullscreen">{telemetryPanel === "full" ? <Minimize2 /> : <Maximize2 />}</Button><Button variant="ghost" size="icon" onClick={() => setTelemetryPanel("closed")} aria-label="Collapse monitor"><X /></Button></div></div>
          <div className="mt-3 space-y-2 text-sm"><label className="block text-xs text-muted-foreground">Source<select className="mt-1 w-full rounded border bg-background p-2 text-foreground" value={simulationSourceId} onChange={event => setSimulationSourceId(event.target.value)}><option value="">First endpoint</option>{nodes.filter(node => !["core-router", "distribution-switch"].includes(node.data.deviceType)).map(node => <option key={node.id} value={node.id}>{node.data.label}</option>)}</select></label><label className="block text-xs text-muted-foreground">Destination<select className="mt-1 w-full rounded border bg-background p-2 text-foreground" value={simulationTargetId} onChange={event => setSimulationTargetId(event.target.value)}><option value="">Last endpoint</option>{nodes.filter(node => !["core-router", "distribution-switch"].includes(node.data.deviceType)).map(node => <option key={node.id} value={node.id}>{node.data.label}</option>)}</select></label><div className="rounded border p-2"><p className="text-xs text-muted-foreground">Path status</p><p className="font-semibold">{networkMetrics.path ? networkMetrics.path.connected ? "Connected" : "Disconnected / Destination unreachable" : "Add two endpoint devices"}</p></div><div className="rounded border p-2"><p className="text-xs text-muted-foreground">End-to-end latency</p><p className="font-semibold">{networkMetrics.path?.latencyMs === null || !networkMetrics.path ? "—" : `${networkMetrics.path.latencyMs.toFixed(1)} ms`}</p><p className="text-xs text-muted-foreground">Critical traffic: {networkMetrics.path?.priorityLatencyMs === null || !networkMetrics.path ? "—" : `${networkMetrics.path.priorityLatencyMs.toFixed(1)} ms`}</p><svg viewBox="0 0 100 28" className="mt-2 h-10 w-full" role="img" aria-label="Simulated latency history"><polyline fill="none" stroke="currentColor" strokeWidth="2" className="text-primary" points={latencyHistory.map((value, index) => `${latencyHistory.length < 2 ? 50 : index * 100 / (latencyHistory.length - 1)},${28 - value * 24 / Math.max(1, ...latencyHistory)}`).join(" ")} /></svg></div><div className="rounded border p-2"><p className="text-xs text-muted-foreground">Effective throughput</p><p className="font-semibold">{networkMetrics.path ? `${networkMetrics.path.throughputMbps.toFixed(1)} Mbps` : "—"}</p></div><div className="rounded border p-2"><p className="text-xs text-muted-foreground">Packet loss · Mean link utilization</p><p className="font-semibold">{networkMetrics.path ? `${networkMetrics.path.packetLossPct.toFixed(2)}% · ${networkMetrics.utilization.toFixed(1)}%` : "—"}</p></div><p className="text-[10px] text-muted-foreground">Simulated values only. Computed from per-link latency, capacity and load saved in Supabase.</p></div>
        </aside>
      )}
      <div className="absolute bottom-4 right-4 z-30 flex gap-2 sm:hidden"><Button size="icon" onClick={() => setAssistantPanel("full")} aria-label="Open network assistant"><Bot /></Button><Button size="icon" onClick={() => setTelemetryPanel("full")} aria-label="Open telemetry"><Gauge /></Button></div>
    </main>
  );
}
