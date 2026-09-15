# Cisco Enterprise Topology Upgrade

## Overview
Upgrade the existing NexusTwin simulator rather than rebuild it. Keep the current authentication, persisted single conversation, realtime topology sync, theme system, undo/redo, and recommendations route, while expanding the workspace into the requested Cisco-style operating experience.

## What will change

### Navigation and saving
- Add a prominent **Save Topology** control to the shared top navigation with a cloud-upload icon.
- Wire it to a full bulk synchronization of every current node and cable, including coordinates, handles, statuses, labels, and configuration fields.
- Show a clear success toast reading **“Topology Saved Successfully”** and an error toast when saving fails.

### Cisco device library and canvas
- Replace the four-item component bank with seven Cisco-style templates: **PC-PT**, **1941 Router**, **Server-PT**, **Hub-PT**, **AccessPoint-PT**, **2960-24TT Switch**, and **Smart Load Balancer**.
- Give each device a distinct, recognizable Lucide-based network silhouette and compact Packet Tracer-inspired node treatment.
- Preserve drag/drop creation, smooth cable creation, deletion, movement, realtime synchronization, and the existing bounded undo/redo history.
- Persist device-specific visual identity and network settings through the existing node `configuration` JSON field.

### Device properties inspector
- Open a right-side properties blade when a device is selected, visually modeled after a Cisco desktop/configuration panel.
- Support editable **Device Name**, **IP Address**, **Subnet Mask**, and **Default Gateway** fields.
- Apply edits immediately to the canvas, add them to undo history, and save them to persistent storage.
- Validate IPv4-style values without blocking empty fields for unconfigured devices.

### Context-aware assistant
- Preserve the installed AI Elements conversation, message, loading, and composer primitives.
- Keep resize, minimize, and full-screen modes, while coordinating the assistant with the properties blade so controls do not overlap.
- Update the prompt to: **“Ask me about your current IP configurations or how to troubleshoot this layout.”**
- Make diagnostics inspect device types, configured IPs, duplicate addresses, missing gateways, isolated devices, and link counts before producing the stored response.

### Alerts and recommendations
- Expand the alert ticker to surface useful topology conditions such as isolated devices, duplicate IPs, unconfigured hosts, and healthy synchronization.
- Upgrade each recommendation into a real optimized topology template rather than adding one isolated device.
- On **Implement Change**, replace the current topology, assign sequential `192.168.1.X` addresses with `255.255.255.0`, populate gateways where appropriate, bulk synchronize nodes and cables, and return to the topology workspace.
- Preserve the pre-change snapshot so the replacement can be undone after returning.

### Quality and compatibility
- Keep the existing light/dark enterprise palette, authenticated routes, profile/session behavior, and custom browser-safe backend client.
- Add the global toast host and ensure all content routes retain unique metadata.
- Verify desktop and mobile layouts, save feedback, device configuration persistence, undo/redo, assistant modes, and recommendation-to-workspace IP assignment.

## Technical details
- Reuse `network_nodes.configuration` for `{ ipAddress, subnetMask, defaultGateway, model }`; no new table is required.
- Extend the app-side device type union while keeping stored values valid for text-based `node_type` columns. If the connected custom database still enforces the earlier four-value check constraint, that constraint must be expanded before the new device types can be saved.
- Refactor the large workspace into focused topology/device-inspector helpers where needed, while retaining React Flow and Shadcn controls.
- Treat a manual save or recommendation replacement as a reconciled snapshot: upsert all current rows and delete only rows that are absent from that snapshot.
