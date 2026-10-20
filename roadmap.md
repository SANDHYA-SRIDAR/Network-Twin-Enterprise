# Roadmap

The complete, code-grounded roadmap for the **Network Failure Simulation & Modernization** page is in [docs/failure-simulation-modernization-roadmap.md](docs/failure-simulation-modernization-roadmap.md), reviewed on 2026-10-17. It covers the full workflow, analytical formulas, scenario/transformation rules, scoring, AI/persistence boundaries, the inspected experiment, and remaining acceptance gates. Its status labels distinguish implemented behavior from live verification and future work.

- [x] Connect the backend and establish schema/security
- [x] Add authentication, profiles, session persistence, and protected navigation
- [x] Build the React Flow topology simulator with persistence and realtime
- [x] Add undo/redo and recommendation implementation workflow
- [x] Add the resizable/minimizable/fullscreen diagnostic assistant with stored chat
- [x] Apply the enterprise light/dark visual system and route metadata
- [ ] Verify all authenticated interaction paths and mobile layout with a live session (previous checkbox lacked reproducible evidence)
- [x] Add Cisco-style device library and persistent device configuration inspector
- [x] Add manual topology save with user feedback
- [x] Upgrade assistant diagnostics and topology health alerts
- [x] Replace recommendation additions with optimized, auto-addressed topologies
- [ ] Add persistent cable selection, cable restyling, and cable-aware undo/redo
- [ ] Add interface-port metadata and theme-aware canvas rendering
- [ ] Replace template recommendations with existing-topology analysis and targeted implementation
- [ ] Verify cable, properties, recommendations, theme, and responsive workflows

## Analytical research workflow (2026-10-16)

- [x] Audit checked-out integration branch and retain canonical topology storage.
- [x] Consolidate deterministic routing/metrics, explicit defaults and unsupported states.
- [x] Evaluate/rank multiple recovery strategies with criteria and outage stress cases.
- [x] Add history, candidate inspection, export and optional AI explanation transport.
- [x] Verify backend contracts, schema exports, frontend build/types and native HTTP workflow.
- [ ] Apply and verify migrations with real Supabase sessions; exercise authenticated browser paths.
- [ ] Validate a live AI provider and container startup separately.
- [ ] Add external validation only as a separate measured-evidence adapter.
