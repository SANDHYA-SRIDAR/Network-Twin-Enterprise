# Enterprise Network Digital Twin — Implementation Plan

## Goal
Build a high-fidelity authenticated network topology simulator with a React Flow canvas, durable per-user topology state, real-time synchronization, reversible editing, recommendations, and a flexible diagnostic assistant.

## Prerequisite
- Connect the existing backend project with reference `dgyhkcxnolueumekejkh` through **Project Settings → Connectors → Supabase** before implementation.
- Do not place project secrets or private API keys in browser code. The generated browser and server clients will be used after the connection is available.
- Email/password and Google must be enabled in that project's authentication settings. Google sign-in will use the supported Lovable broker flow once the integration is generated.

## Application Structure
- Public `/auth` page for registration, email/password sign-in, Google sign-in, forgot-password, and confirmation feedback.
- Public `/reset-password` recovery page with a complete password-update form.
- Public `/` entry that redirects according to session state rather than retaining the template placeholder.
- Protected `/topology` workspace for the simulator.
- Protected `/recommendations` portal for alternative configurations and implementation actions.
- Persistent top navigation with product identity, topology/recommendations navigation, user menu, logout, and Sun/Moon theme control.
- Keep the AI assistant as **one database-backed conversation** associated with each signed-in user.

## Database and Security
Create migrations for:
- `user_profiles`: one row per auth user, display name and preferences, created automatically by an auth-user trigger.
- `network_nodes`: user-owned React Flow node type, label/configuration, coordinates, and timestamps.
- `network_connections`: user-owned source/target handles, connection styling/configuration, and timestamps.
- `chat_messages`: one ordered user-owned assistant conversation, storing valid message roles/parts and timestamps.
- Optional topology revision/recommendation metadata only where needed to make implemented changes auditable.

For every table:
- Add explicit grants, enable row-level security, and scope reads/writes to the authenticated owner.
- Add indexes and ownership constraints needed for topology loads and realtime filtering.
- Add tables to the Realtime publication in the migration.
- Keep roles separate from profiles if roles are later required; this build will not invent an admin role.

## Authentication and Session Experience
- Build a sleek auth screen with separate sign-in and registration modes, validation, accessible errors, and loading states.
- Collect display name during registration and pass it as signup metadata; the database trigger creates `user_profiles`.
- Treat email-confirmation signup as pending until a real session exists.
- Persist sessions across refreshes and show a checked “Remember me” control matching the requested until-logout behavior.
- Wire one root auth-state listener, protected-route gating, current-user presentation, and safe logout that clears protected query state before returning to `/auth`.

## Simulator Workspace
- Use React Flow for a full-height enterprise canvas with a semantic dot-matrix background and stable light/dark styling.
- Left component bank: Core Router, Distribution Switch, Cloud Server, and Smart Load Balancer, each with distinct Lucide iconography and connection handles.
- Support drag/drop creation, selection, movement, connection creation, and keyboard/control deletion.
- Persist node drops, settled coordinate changes, edge creation, node deletion, and edge deletion to the database with clear failure recovery.
- Load the signed-in user's saved topology before presenting the editable workspace.

## Undo, Redo, and Synchronization
- Maintain bounded topology snapshots for all user-visible mutations: add, move, delete, connect, disconnect, and recommendation implementation.
- Floating canvas-edge Undo/Redo controls show disabled states correctly and include keyboard shortcuts.
- Undo/redo applies the full node-and-edge snapshot and reconciles the corresponding inserts, updates, and deletes with the database.
- Subscribe to user-scoped Realtime events for nodes and connections; merge remote inserts/updates/deletes into React Flow immediately.
- Prevent duplicate application of the current client's optimistic writes and avoid creating history entries for remote events.
- Unsubscribe on user/session change and surface synchronization failures without discarding the local canvas.

## AI Assistant Module
- Compose the visible assistant using installed AI Elements primitives for conversation, messages, prompt input, loading, and tool-style diagnostic results.
- Seed polished mock diagnostic exchanges based on topology conditions; no live AI provider is implied by this request.
- Persist the single conversation in `chat_messages` and restore it after refresh/login.
- Right panel supports width dragging with sensible limits, minimize-to-icon-rail, restore, and “Pop Out” into a full-workspace grid mode.
- Assistant messages remain unboxed; user messages use a deliberate high-contrast token pair.

## Alerts and Recommendations Workflow
- Add a persistent health banner above the canvas for bottleneck warnings, healthy state, and optimal-path readiness.
- Add a prominent “Changes Recommended” action linking to `/recommendations` with a smooth route/view transition.
- Present recommendation cards with compact topology previews and custom data visualizations for alternatives such as load-balancer insertion and redundant paths.
- “Implement Change” computes a deterministic topology patch, records one undo snapshot, applies it to the main topology, synchronizes nodes/edges, and returns the user to the updated canvas.
- Include success, conflict, and failed-sync feedback states.

## Visual System
- Use the specified deep slate and indigo dark palette (`#0f172a` / `#1e293b`) through semantic design tokens, with clean enterprise grays in light mode.
- Use Shadcn controls, crisp Lucide network icons, compact information density, restrained motion, visible focus states, and accessible contrast.
- Preserve panel and canvas usability across desktop and smaller screens without overlapping controls; on narrow screens, component bank and assistant become controlled drawers/rails.

## Technical Details
- Install React Flow and the required AI Elements registry components before composing the workspace/chat UI.
- Use TanStack Start file routes and generated backend integration clients; do not introduce another router or edge functions.
- Use authenticated server functions for initial database reads/writes where appropriate and the browser client for Realtime subscriptions under RLS.
- Add unique route metadata for `/`, `/auth`, `/reset-password`, `/topology`, and `/recommendations`.
- Keep all colors in semantic Tailwind v4 tokens and use existing Shadcn components for controls.

## Validation
- Run lint, type checks, tests, and the full build.
- Verify registration/profile trigger behavior, email confirmation state, Google return flow, refresh persistence, password reset, and logout.
- Verify add/move/connect/delete plus undo/redo survive reload and remain isolated between users.
- Open two authenticated browser contexts and confirm Realtime node/edge updates appear without refresh.
- Verify at desktop and mobile widths: drag/drop, cables, banner, floating controls, assistant resize/minimize/pop-out, recommendations implementation, themes, focus behavior, and no overlap.
