# Cable-Aware Topology and Contextual Recommendations

## Overview
Extend the existing NexusTwin workspace without replacing its authentication, realtime synchronization, assistant, or device inspector. Add cable selection and persistence, interface-port editing, a truly theme-aware canvas, and recommendations that modify only the topology already on the canvas.

## What will change

### Cable selection and canvas history
- Add a compact cable toolbar to the canvas with Copper Straight-Through, Copper Crossover, Fiber, Serial DCE/DTE, and Console options.
- Apply the selected cable type to newly drawn links with the requested solid, dashed, orange, red zig-zag, and light-blue visual treatments.
- Let users select an existing cable and change its type from the toolbar.
- Include cable additions, deletions, and style changes in the existing undo/redo snapshots.
- Store cable identity and path details in each `network_connections.configuration` record and restore them when loading or receiving realtime updates.

### Theme-aware workspace and saving
- Make the React Flow canvas, grid dots, controls, minimap, nodes, and cable contrast update immediately with the existing light/dark toggle.
- Keep the top-navigation Save Topology action and ensure bulk save includes all node metadata, coordinates, interface ports, edge handles, and cable types.
- Preserve the exact success message: **“Topology Saved Successfully”**.

### Node properties
- Extend the Node Properties drawer with editable interface ports alongside Device Name, IP Address, Subnet Mask, and Default Gateway.
- Persist interface ports with the existing node configuration metadata and include edits in undo/redo history.
- Keep IPv4 validation and immediate canvas updates.

### Existing-topology recommendations
- Replace fixed template recommendations with recommendations generated only from the signed-in user’s current nodes and connections.
- Detect actionable issues such as unsuitable cable choices, missing high-speed server links, subnet-mask mismatches, duplicate addresses, missing gateways, isolated devices, and unconfigured interfaces.
- Render cards that name the exact affected devices or connection and explain the proposed change.
- Implement each recommendation by updating only the affected existing nodes or edges; do not replace the topology or add unrelated template devices.
- Persist the change, preserve a pre-change undo snapshot, return to the canvas, select and visually highlight the modified node or cable, and keep any automatic IP correction visible in Node Properties.
- Show a healthy-state card when no actionable recommendation exists.

## Technical details
- Extend node configuration JSON with `interfacePorts` and edge configuration JSON with `cableType` plus the existing path information; no new table is required.
- Pass the current topology to the recommendations view through persisted backend records, then write a small pending-highlight payload for the returning canvas to consume once.
- Use semantic theme tokens for cable colors and canvas surfaces; no database schema migration is needed.
- Keep recommendation writes owner-scoped through the current authenticated browser client and existing row-level policies.

## Verification
- Verify each cable style can be selected, created, changed, saved, reloaded, undone, and redone.
- Verify interface ports persist after reload and the canvas visibly changes between light and dark modes.
- Verify recommendation cards reference only current canvas items, implementation changes only targeted records, and the returning canvas highlights the result.
- Check desktop and narrow-screen layouts for toolbar, inspector, alert bar, and assistant overlap.
