# PTZ Preset Control — Proposed Improvements

## 1. Remove Duplicate Function Definitions (High Priority)

**Location:** Functions `_send_atem_aux_source()` and `_wait_for_atem_aux_source()` in `server.py`

These functions are defined twice: the first pair is immediately shadowed by identical definitions later in the file. This is a bug that should be fixed immediately by removing the duplicate definitions.

**Impact:** Reduces code size, eliminates confusion, and removes a maintenance hazard.

---

## 2. Refactor State Management Into a Dedicated Module

**Current state:** Global state for ATEM, SSE clients, and Playwright instances is scattered across module-level variables with separate locks:
- `_atem_state` + `_atem_state_lock`
- `_atem_last_action` + `_atem_last_action_lock`
- `_atem_conn` + `_atem_conn_lock`
- `_sse_clients` + `_sse_lock`
- `_pw_ctx`, `_pw_browser`, `_pw_page` + `_pw_lock`

**Proposal:** Extract a `StateManager` class that consolidates thread-safe state operations. This would:
- Reduce boilerplate lock management
- Make state access more discoverable
- Enable easier state debugging/inspection
- Provide a clear place to add state validation in future

**Example shape:**

```python
import copy

class StateManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._atem = {...}
        self._atem_last_action = {...}
        self._atem_conn = {...}
    
    def set_atem_preview(self, source: int) -> None:
        with self._lock:
            self._atem['preview'] = source
    
    def get_atem(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._atem)
    
    # ... other accessors
```

**Impact:** Reduces ~100 lines of lock management, improves readability and maintainability. Not urgent but reduces cognitive load for future changes.

---

## 3. Consolidate Endpoint Validation Logic

**Current state:** The HTTP handlers repeat similar validation patterns:

- `_handle_atem_cut()`: validates source int, checks ATEM enabled/connected
- `_handle_atem_preview_post()`: validates camIdx, checks ATEM enabled/connected, looks up camera
- `_handle_atem_aux_route()`: validates aux key, camIdx, checks ATEM enabled/connected, looks up camera

**Proposal:** Extract a validation helper:

```python
def _require_atem_enabled_and_connected() -> tuple[bool, dict | None]:
    """Return (ok, error_response). If not ok, response is ready to send."""
    cfg = load_settings().get("atem", {})
    if not cfg.get("enabled"):
        return False, {"ok": False, "error": "ATEM is disabled in settings"}
    if not _get_atem().get("connected"):
        return False, {"ok": False, "error": "ATEM is not connected"}
    return True, None

def _require_camera(cam_idx: int) -> tuple[bool, dict | None]:
    """Return (ok, error_response) for camera lookup."""
    cams = load_settings().get("cameras", [])
    if cam_idx < 0 or cam_idx >= len(cams):
        return False, {"ok": False, "error": "Camera not found"}
    return True, None
```

Then handlers call these and return early if validation fails. This reduces duplicate logic and makes validation behavior consistent across endpoints.

**Impact:** ~40 fewer lines of mostly redundant validation code, easier to update validation logic in one place.

---

## 4. Add Logging for Long-Running Operations

**Current:** ATEM loop logs some events (connection, config changes, commands) but misses others:
- Socket timeouts during normal operation
- Position inquiry failures (silently return None)
- Capture attempts that fail and fall back to the next method

**Proposal:** Add diagnostic logging to:
1. `inquire_visca_absolute_position()` — log when the inquiry fails
2. `_try_record_position()` — log when position recording is skipped (camera unconfigured, inquiry failed)
3. `capture_usb_device()` and fallback chain — log each attempt and reason for fallback

This helps operators debug why a capture didn't produce position data, or why a camera's image is blank.

**Impact:** Improves debuggability with minimal code additions (5–10 lines).

---

## 5. Add Health Check Endpoint

**Proposal:** Add a lightweight `/health` endpoint that returns minimal liveness data:

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

For detailed diagnostics, add a separate authenticated endpoint (e.g., `/health/details` or `/diagnostics`) that includes ATEM/camera state and requires authentication.

This enables:
- Monitoring scripts to detect if the server is alive
- Load balancers / reverse proxies to health-check the app
- Operators to access detailed system state via authenticated endpoint

The minimal public endpoint avoids exposing internal topology to unauthenticated clients.

**Impact:** ~20 lines of code for basic health check; additional auth-protected diagnostics endpoint for full system state visibility.

---

## 6. Validate Preset Number Range on Input

**Current:** The `_handle_recall()` function validates presets but allows any non-negative value without checking the VISCA preset range. VISCA presets are typically 0–127 (7-bit).

**Proposal:** Enforce range:

```python
preset = max(0, min(127, int(data.get("preset", 0))))
```

Or add an explicit bounds check with a clear error message.

**Impact:** Prevents silent bugs where an out-of-range preset is sent to a camera and fails in an unexpected way. ~1 line change with better error feedback.

---

## 7. Reduce ATEM Loop Reconnect Backoff

**Current:** When the `_atem_loop()` function encounters a connection failure, it sleeps for 3 seconds before retrying.

**Observation:** For a device that's physically powered off or network-disconnected, 3 seconds is reasonable. But for transient socket timeouts or momentary network glitches, 3 seconds is slow. The loop may also be missing packets if it backs off during a state transition.

**Proposal:** Consider a smaller initial backoff (e.g., 1 second) or a sequence: try immediately, then 1s, 2s, 3s with exponential backoff. This trades reconnect latency for slightly higher CPU in the steady state.

**Trade-off:** Very minor. Could be added later if operators report slow recovery from brief disconnects.

---

## 8. Add Operators' Manual / Runbook Comments

**Context:** The app is used in live production by experienced operators. The code has comments for VISCA protocol details and ATEM packet formats, but lacks operator-facing documentation on:
- What "settle" vs "confirm" vs "autocut" wait modes mean
- Why auto-cut delay is configurable and when to use it
- What happens if you move the live camera in live mode
- How the ATEM integration failure modes are handled

**Proposal:** Add a `docs/OPERATOR_GUIDE.md` with:
1. Feature overview (what each button/setting does)
2. Live mode guardrails and their rationale
3. Common failure scenarios (camera offline, ATEM unavailable) and recovery steps
4. Capture troubleshooting (why an image is blank, how to fall back to manual)

This isn't code, but improves the barrier to entry for new operators.

---

## Summary of Changes by Priority

| Priority | Improvement | Effort | Impact |
|----------|-------------|--------|--------|
| **High** | Remove duplicate functions | 1 min | Eliminates a bug, reduces confusion |
| **Medium** | Consolidate validation helpers | 30 min | ~40 lines removed, easier maintenance |
| **Medium** | Add logging for long-running ops | 15 min | Improves debuggability |
| **Low** | Refactor state into StateManager | 2 hours | Better code organization, not urgent |
| **Low** | Add health check endpoint | 20 min | Nice-to-have for monitoring |
| **Low** | Validate preset range | 2 min | Prevents edge-case bugs |
| **Low** | Reduce ATEM backoff | 5 min | Faster recovery, minimal benefit |
| **Low** | Write operator guide | 1 hour | Improves usability, not code |

---

## Recommended Starting Point

1. **First:** Remove the duplicate function definitions (1 min, high confidence)
2. **Second:** Add validation helpers (30 min, straightforward refactor)
3. **Third:** Add logging to long-running ops (15 min, low risk)
4. **Later:** State manager refactor and operator guide (when maintenance burden becomes clear)
