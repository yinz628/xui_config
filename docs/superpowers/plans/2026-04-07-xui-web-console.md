# X-UI Web Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Data-First web console with simple password auth, editable sources/groups, generate actions, and report/state views.

**Architecture:** Build an independent `web` service with FastAPI, Jinja2, and HTMX. Reuse the existing generator core and file outputs instead of introducing a second state system.

**Tech Stack:** Python 3.10, FastAPI, Jinja2, HTMX, pytest

---

## Task 1: Add Web App Skeleton and Auth
- [ ] Add failing tests for login redirect and successful session login.
- [ ] Implement `xui_port_pool_generator_web` package, session middleware, `/login`, `/logout`, and guarded routes.
- [ ] Verify the auth tests pass.

## Task 2: Add Config Editing Pages
- [ ] Add failing tests for saving `sources` and `groups`.
- [ ] Implement dashboard, sources page, groups table page, mapping read/write helpers, and validation-backed save flows.
- [ ] Verify the config editing tests pass.

## Task 3: Add Generate and Reports Pages
- [ ] Add failing tests for triggering `run_pipeline()` and reading `report/state`.
- [ ] Implement generate action, result summary rendering, and reports page.
- [ ] Verify the generation/report tests pass.

## Task 4: Add Deployment Wiring
- [ ] Add failing tests for `web` service presence in Compose and required env vars.
- [ ] Update `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.env.example`, and deploy docs for the `web` service.
- [ ] Verify deployment contract tests pass.

## Task 5: Run Full Verification
- [ ] Run the full pytest suite.
- [ ] Verify the FastAPI app imports and the smoke/help commands still work.
- [ ] Report any environment-level blockers separately from code-level pass/fail.
