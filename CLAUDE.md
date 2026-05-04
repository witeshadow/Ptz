# CLAUDE.md

Guidance for Claude Code or similar coding agents working in this repository.

## Project

PTZ Preset Control is a local web app for recalling and cataloguing AVIPAS camera presets over VISCA IP. It also integrates with a Blackmagic ATEM so the active camera can follow preview or program.

## Operating Context

This app is used for live production of a multi-camera church service.

- Operators are experienced and should be treated that way.
- The app still needs strong guardrails against live-production mistakes.
- Guardrails matter most for:
  - moving a camera that is live on program
  - overwriting preset thumbnails with the wrong image
  - bulk actions that silently produce misleading results
- Before or after the service, some workflows can favor convenience because nobody is watching live.

When in doubt: protect live output first, then optimize convenience.

## Run

```bash
python server.py
```

App URL: `http://localhost:5001`

Optional dependencies:

| Feature | Dependency |
|---|---|
| URL capture | `pip install playwright && playwright install chromium` |
| USB capture fallback | `pip install opencv-python` |
| Primary USB capture | `ffmpeg` on the system path |

## Architecture

The app is intentionally small:

- `server.py`: stdlib HTTP server, VISCA control, ATEM integration, SSE, capture, persistence
- `public/index.html`: single-file SPA with inline CSS and JavaScript

Important constraint:

- This is **not Flask**
- Routes are hand-written in `do_GET`, `do_POST`, and `do_DELETE`
- Frontend JS lives in the single `<script>` block in `public/index.html`

## State

Persistent state lives in `data/`:

- `data/settings.json`
- `data/images/{cam}_{preset}.jpg`

Preset label keys use the form `"{cam}:{preset}"`.

The browser stores only the selected preview webcam device in `localStorage`.

## Behavior That Matters

### Live safety

- Live-mode behavior must avoid accidental movement of the live camera.
- Scan or capture flows should not silently generate bad preset images.
- Prefer explicit errors over “doing something convenient but wrong.”

### ATEM

`server.py` runs a background `_atem_loop()` and pushes SSE events on `/events`.

Frontend event types:

- `atem`
- `preview`
- `program`

In Live mode, the UI can follow either preview or program via `atemFollows`.

ATEM status must reflect the switcher state observed from ATEM polling and inbound updates, not optimistic assumptions based on app actions. Outside actors can change preview/program selection or cut between cameras at any time, so the UI should treat app-issued commands as requests and ATEM-reported state as the source of truth.

### Action ordering

Explore serializing ATEM actions and camera recalls through a queue or equivalent coordinator when workflows become more concurrent.

- Queueing may help prevent overlapping recall, preview-select, and cut requests from producing misleading UI state.
- Any queue design should preserve live-safety guardrails, surface pending/running/failed state clearly, and still reconcile final state against what ATEM and the cameras actually report.

### Capture priority

Preset image capture uses this order:

1. Configured USB device through `ffmpeg`
2. Configured stream URL through Playwright
3. Browser webcam fallback

## Common Change Pattern

Most features touch these places in order:

1. `server.py` route or backend behavior
2. `DEFAULT_SETTINGS` if new state is persisted
3. `public/index.html` state, fetch logic, and rendering

If a new UI setting persists, add it to both server defaults and frontend state.

## Verification

Use these checks before pushing. **Always run `ruff format` first**:

```bash
ruff format server.py
ruff check server.py
python -m py_compile server.py
uv run pytest tests/test_frontend_contracts.py
python -m unittest discover -s tests/ -v
```

The CI runs all of these checks, so passing locally ensures your PR will pass.

## Working Rules

- Keep solutions simple and local.
- Preserve the single-file frontend structure unless there is a strong reason not to.
- Favor clear operator feedback for risky actions.
- Design for mobile and iOS Safari, not just desktop.
