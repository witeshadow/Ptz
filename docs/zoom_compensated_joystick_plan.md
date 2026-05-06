# Zoom-Compensated Joystick Implementation Plan

This branch was created for adding zoom-aware joystick pan/tilt speed compensation.

## Goal

When a camera is zoomed in, joystick pan/tilt speed should be reduced so small framing changes remain controllable. The zoom axis itself should not be slowed by this compensation.

## Intended behavior

- Wide zoom: pan/tilt joystick speed remains close to normal.
- Medium zoom: pan/tilt speed is moderately reduced.
- Tight zoom: pan/tilt speed is substantially reduced.
- Zoom joystick axis remains unchanged.
- Preset recall behavior remains unchanged.
- If live zoom cannot be queried, joystick movement should continue at normal speed and show/debug that compensation is unavailable.

## Settings to add

Add this under `DEFAULT_SETTINGS["joystick"]` in `server.py`:

```python
"zoomCompensation": {
    "enabled": True,
    "minFactor": 0.20,
    "maxFactor": 1.00,
    "curve": 1.2,
    "zoomMin": 0,
    "zoomMax": 16384,
    "pollMs": 300,
},
```

Add matching defaults to the frontend joystick normalization function.

## Backend endpoint

Add a route:

```text
GET /api/position?cam=0
```

The route should:

1. Load settings.
2. Resolve `cam` from query string, defaulting to `activeCam` if missing.
3. Validate camera index.
4. Validate configured IP.
5. Call existing `inquire_visca_absolute_position(ip, port, viscaAddr)`.
6. Return:

```json
{
  "ok": true,
  "cam": 0,
  "position": {
    "pan": 0,
    "tilt": 0,
    "zoom": 0,
    "pan_hex": "0000",
    "tilt_hex": "0000",
    "zoom_hex": "0000"
  }
}
```

On failures, return `ok:false` with an explanatory message and appropriate HTTP status.

## Frontend state

Add:

```js
livePositions: {},
```

Shape:

```js
state.livePositions[camIdx] = {
  pan,
  tilt,
  zoom,
  pan_hex,
  tilt_hex,
  zoom_hex,
  updatedAt: Date.now(),
};
```

## Compensation helpers

Add near joystick helper functions:

```js
function clampNumber(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function normalizeZoomCompensation(value) {
  const src = value || {};
  return {
    enabled: src.enabled !== false,
    minFactor: Number.isFinite(Number(src.minFactor)) ? Number(src.minFactor) : 0.2,
    maxFactor: Number.isFinite(Number(src.maxFactor)) ? Number(src.maxFactor) : 1.0,
    curve: Number.isFinite(Number(src.curve)) ? Number(src.curve) : 1.2,
    zoomMin: Number.isFinite(Number(src.zoomMin)) ? Number(src.zoomMin) : 0,
    zoomMax: Number.isFinite(Number(src.zoomMax)) ? Number(src.zoomMax) : 16384,
    pollMs: Number.isFinite(Number(src.pollMs)) ? Number(src.pollMs) : 300,
  };
}

function zoomFractionForCompensation(zoom, cfg) {
  const min = Number(cfg.zoomMin ?? 0);
  const max = Number(cfg.zoomMax ?? 16384);
  if (max <= min) return 0;
  return clampNumber((Number(zoom || 0) - min) / (max - min), 0, 1);
}

function zoomSpeedFactor(zoom, cfg) {
  if (!cfg || cfg.enabled === false) return 1;
  const minFactor = clampNumber(Number(cfg.minFactor ?? 0.2), 0.05, 1);
  const maxFactor = clampNumber(Number(cfg.maxFactor ?? 1.0), minFactor, 1.5);
  const curve = Math.max(0.1, Number(cfg.curve ?? 1.2));
  const frac = zoomFractionForCompensation(zoom, cfg);
  return maxFactor - ((maxFactor - minFactor) * Math.pow(frac, curve));
}

function joystickZoomFactor(camIdx = state.activeCam) {
  const cfg = state.joystick?.zoomCompensation;
  const pos = state.livePositions?.[camIdx];
  if (!pos || pos.zoom === undefined || pos.zoom === null) return 1;
  return zoomSpeedFactor(pos.zoom, cfg);
}
```

## Polling live zoom

Add polling while joystick is active/connected:

```js
let lastJoystickZoomPollAt = 0;
let joystickZoomPollInFlight = false;

async function pollJoystickZoomIfNeeded(force = false) {
  const cfg = state.joystick?.zoomCompensation;
  if (!cfg?.enabled) return;
  if (!gamepadConnected && !force) return;

  const now = Date.now();
  const pollMs = Math.max(150, Number(cfg.pollMs || 300));
  if (!force && now - lastJoystickZoomPollAt < pollMs) return;
  if (joystickZoomPollInFlight) return;

  lastJoystickZoomPollAt = now;
  joystickZoomPollInFlight = true;
  try {
    const camIdx = state.activeCam;
    const res = await fetch(`/api/position?cam=${encodeURIComponent(camIdx)}`);
    const data = await res.json();
    if (data.ok && data.position) {
      state.livePositions[camIdx] = { ...data.position, updatedAt: Date.now() };
    }
  } catch (err) {
    if (state.showJoystickDebug) console.debug('[JOYSTICK] Zoom position poll failed', err);
  } finally {
    joystickZoomPollInFlight = false;
  }
}
```

Call this from the gamepad loop before applying movement:

```js
pollJoystickZoomIfNeeded();
```

## Apply compensation

In `applyGamepadInput()`, compute adjusted pan/tilt before `sendPtzDriveCommand`:

```js
function applyGamepadInput() {
  if (!gamepadConnected) return;
  pollJoystickZoomIfNeeded();

  const factor = joystickZoomFactor(state.activeCam);
  const pan = gamepadState.pan * factor;
  const tilt = -gamepadState.tilt * factor;
  const zoom = gamepadState.zoom;

  const cmd = { pan, tilt, zoom };
  // keep existing debug/dedup logging behavior here
  sendPtzDriveCommand(pan, tilt, zoom);
}
```

Important: leave the zoom axis uncompensated.

## UI additions

In joystick settings, add:

- Enable Zoom Speed Compensation checkbox.
- Minimum pan/tilt speed at full zoom number input.
- Curve/aggressiveness number input.
- Current zoom and current factor display in debug.

Suggested labels:

```text
Zoom speed compensation
Minimum speed at full zoom
Compensation curve
Current zoom
Speed factor
```

## Tests to add

### `tests/test_frontend_contracts.py`

Add checks that:

- `zoomCompensation` exists.
- `normalizeZoomCompensation` exists.
- `zoomSpeedFactor` exists.
- `pollJoystickZoomIfNeeded` exists.
- `applyGamepadInput` keeps zoom axis uncompensated.
- UI contains `Zoom speed compensation`.

### `tests/test_server.py`

Add endpoint tests:

- `GET /api/position?cam=0` returns position including zoom.
- Missing camera IP returns 400.
- Invalid camera index returns 400.
- VISCA inquiry failure returns error JSON.

## Manual test checklist

1. Enable joystick.
2. Enable zoom compensation.
3. Zoom all the way out and test pan/tilt.
4. Zoom halfway and verify slower pan/tilt.
5. Zoom tightly and verify much slower pan/tilt.
6. Verify zoom axis still feels normal.
7. Disable compensation and verify original behavior returns.
8. Restart app and verify settings persist.
