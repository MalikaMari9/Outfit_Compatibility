# Future Implementation Plan
Date: 2026-02-23

## Current Backend Policy (Active)
- MongoDB is required for backend startup.
- If MongoDB is unavailable, backend should not expose normal service behavior.
- Upload handling should use a single repo-local root (`runtime/uploads`).
- Ollama explanation remains enabled in pipeline configuration.

## Future Option: Hybrid Availability Mode
This is not active now. Keep for future implementation if uptime requirements increase.

### Goal
Allow ML endpoints to remain available even when MongoDB is degraded, while keeping auth/profile/admin flows DB-dependent.

### Behavior
- Backend process starts regardless of DB readiness.
- DB-dependent routes (`/signin`, `/signup`, `/account`, `/wardrobe`, admin) return `503` when DB is down.
- ML routes (`/compatibility`, `/recommend`) continue to operate if model/runtime stack is healthy.
- `/feedback` can either:
  - fail with `503` (strict DB write), or
  - queue locally and sync later (advanced path).

### Why Keep This as Future Work
- Current project policy favors consistency and simpler operational behavior.
- Hybrid mode introduces extra state handling and explicit per-route health gating.
- Hybrid mode is best added when deployment uptime and resilience become priorities.

## Future Readiness Checklist
- Add DB health state in backend runtime.
- Add route-level guards for DB-required endpoints.
- Add explicit API error schema for `503` degraded responses.
- Add optional local queue for feedback persistence during DB outages.
- Add monitoring for DB health and pipeline health separately.
