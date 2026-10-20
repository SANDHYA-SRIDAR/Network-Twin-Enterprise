<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

# Project operating rules

- Preserve the existing app structure and avoid rewriting working code from scratch.
- Treat the repository as the source of truth; do not claim a feature is complete unless it is verified by a test, build, or runtime check.
- Distinguish clearly between DONE AND VERIFIED, IMPLEMENTED BUT NOT VERIFIED, MOCKED, IN PROGRESS, and NOT IMPLEMENTED.
- Keep the status evidence in project-status.md current.
- Do not present mock telemetry or synthetic data as real Mininet or VM evidence.
- Keep a single canonical network model and avoid duplicate topology stores.
- Reuse the existing FastAPI backend and React frontend unless a change is required for integration.
- Never expose secrets or credentials in frontend code, logs, or responses.
- Validate changes with the smallest relevant command before claiming success.
