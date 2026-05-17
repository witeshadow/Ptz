# Implementation Plan: Full-Screen Joystick & touchOSC Integration

## Overview
Two parallel features to enhance PTZ control on mobile/tablet:
1. **Full-screen dedicated joystick page** (iOS 12 iPad optimized)
2. **touchOSC controller integration** (OSC protocol, multi-device)

Both features completed on branch: `claude/add-virtual-joystick-gzs75`

---

## Feature 1: Full-Screen Virtual Joystick Page

### Requirements (from user feedback)
- Toggle button stays visible at bottom-left when joystick is open
- Rotation flips layout (landscape layout differs from portrait)
- Zoom slider similar to current compact slider
- Joystick-only mode (no preset controls)
- Live camera lock status displayed prominently (red warning)
- iOS 12 Safari compatibility

### Architecture

#### Frontend Changes (public/index.html)

1. **New HTML Elements**
   ```html
   <!-- Fullscreen joystick page container -->
   <div id="fullscreen-joystick-page" style="display:none; position:fixed; inset:0; ...">
     <!-- Header with camera name and live status -->
     <!-- Large pan/tilt pad (left side in landscape) -->
     <!-- Zoom slider (right side in landscape) -->
     <!-- Live lock status indicator -->
     <!-- Toast/error display -->
   </div>
   ```

2. **Visibility States**
   - Hidden by default
   - Toggle via button/gesture
   - Toggle button remains visible (z-index:99)
   - Page uses z-index:100+

3. **Layout Strategy**
   - **Portrait:** Pan/tilt centered, zoom below
   - **Landscape:** Pan/tilt left 60%, zoom right 40%
   - Use CSS media queries for orientation
   - Apply CSS transforms for orientation change animation

4. **Touch Input**
   - Reuse existing `sendPtzDriveCommand()` 
   - Pan/tilt: multitouch distance calculation from center
   - Zoom: vertical slider with spring-back (release = stop)
   - Deadzone: apply existing deadzone logic
   - Sensitivity: use existing joystick sensitivity settings

5. **Live Status Display**
   - Header shows: camera name + "LIVE ON PROGRAM" (red background)
   - Locked state: red border/background on joystick elements
   - Error messages: toast at top of page
   - Status updates via existing event system (SSE)

#### Implementation Steps
1. Add HTML structure for fullscreen page
2. Add CSS for portrait/landscape layouts
3. Implement touch handlers (pan/tilt pad)
4. Implement zoom slider with spring-back
5. Wire up sensitivity/deadzone from settings
6. Add live status indicator
7. Test orientation rotation
8. Verify iOS 12 Safari compatibility

### Testing Checklist
- [ ] Page loads and displays correctly
- [ ] Touch pan/tilt responds immediately
- [ ] Zoom slider has spring-back behavior
- [ ] Orientation change flips layout smoothly
- [ ] Live lock status shows correctly
- [ ] Button toggle works in both directions
- [ ] iOS 12 Safari compatible (no ES6+ features)
- [ ] Works on actual iPad (not emulator)

---

## Feature 2: touchOSC Controller Integration (OSC)

### Requirements (from user feedback)
- 30 Hz rate limit (max 30 messages/sec)
- Multi-camera support with configurable buttons
- Camera and cut buttons like presets page
- Live camera lock status displayed prominently
- Server-side logging for diagnostics

### Architecture

#### Backend Changes (server.py)

1. **OSC Listener Thread**
   ```python
   class OSCListener(threading.Thread):
       def __init__(self, port=9000):
           self.port = port
           self.running = False
           
       def run(self):
           # Create UDP socket
           # Listen for OSC messages
           # Parse and route to camera control
           
       def parse_osc_message(self, data):
           # Simple OSC parser: /ptz/{cam_id}/{control} format
           # Return (address, value) or None
   ```

2. **OSC Message Mapping**
   - `/ptz/{cam_id}/pan`: -1.0 to 1.0 → pan direction + speed
   - `/ptz/{cam_id}/tilt`: -1.0 to 1.0 → tilt direction + speed
   - `/ptz/{cam_id}/zoom`: -1.0 to 1.0 → zoom direction + speed
   - `/ptz/{cam_id}/stop`: → stop all motion
   - Message rate limited to 30 Hz per camera

3. **Rate Limiting**
   ```python
   osc_rate_limiter = {
       # cam_id: (last_message_time, messages_since_limit)
   }
   
   def should_process_osc_message(cam_id, current_time):
       # Allow max 30 messages/sec per camera
       # Return True if message should be processed
   ```

4. **Live Mode Safety**
   - Check `isProtectedLiveCamera(cam_id)` before moving
   - Log rejection with timestamp
   - Return error response (can be logged/displayed on controller)

5. **Settings**
   ```python
   DEFAULT_SETTINGS["osc"] = {
       "enabled": False,
       "port": 9000,
       "sensitivity": {"pan": 1.0, "tilt": 1.0, "zoom": 1.0},
       "deadzone": 0.1,
       "rateLimit": 30,  # Hz
   }
   ```

6. **Endpoints**
   - `GET /api/osc/status`: Return listener status, port, message log
   - `POST /api/osc/config`: Update OSC settings
   - `GET /api/osc/log`: Return last N messages for diagnostics

7. **VISCA Command Mapping**
   ```python
   def osc_value_to_ptz(address, value, sensitivity):
       # Map normalized OSC value (-1 to 1) to VISCA speed (0-24)
       # Apply sensitivity multiplier
       # Clamp to valid VISCA range
   ```

#### Frontend Changes (public/index.html)

1. **Settings UI** (add to joystick settings section)
   ```html
   <!-- OSC Settings -->
   <div id="osc-settings-section">
     <input id="f-osc-enabled" type="checkbox" />
     <label>Enable OSC Listener</label>
     
     <label>OSC Port</label>
     <input id="f-osc-port" type="number" min="1024" max="65535" value="9000" />
     
     <!-- Sensitivity sliders (pan, tilt, zoom) -->
     <!-- Deadzone slider -->
   </div>
   ```

2. **Diagnostic Panel**
   ```html
   <div id="osc-diagnostic-panel">
     <div>OSC Status: <span id="osc-status">Inactive</span></div>
     <div>Port: <span id="osc-port-display">9000</span></div>
     <div>Messages (last 10):</div>
     <div id="osc-message-log" style="font-family:monospace; font-size:0.8rem;">
       <!-- Messages logged here -->
     </div>
   </div>
   ```

3. **Event Handling**
   - Listen for `osc-message` events via SSE
   - Update diagnostic panel with last messages
   - Display status changes in real-time

#### Implementation Steps
1. Add OSC listener thread to `server.py`
2. Implement rate limiting logic
3. Add VISCA command mapping for OSC values
4. Add OSC settings to `DEFAULT_SETTINGS`
5. Implement settings endpoints (`/api/osc/status`, `/api/osc/config`)
6. Add frontend settings UI
7. Add diagnostic panel
8. Write touchOSC template file

#### Testing Checklist (Backend)
- [ ] OSC listener starts/stops correctly
- [ ] Messages parsed correctly
- [ ] Pan/tilt/zoom values map to VISCA speeds
- [ ] Rate limiting enforces 30 Hz max
- [ ] Live lock prevents movement correctly
- [ ] Settings persist across restarts
- [ ] Error handling for invalid messages
- [ ] No crashes on malformed input

---

## touchOSC Template File

### File: `touchosc-ptz-template.tosc` (v2 format)

### Template Layout
```
┌─────────────────────────────┐
│ Camera: [1] [2] [3]         │
│ Live Status: [ON AIR]       │
├─────────────────────────────┤
│ Pan Fader (X)               │
│ ─────────────────── ────    │
│ Tilt Fader (Y)              │
│ ─────────────────── ────    │
│ Zoom Fader                  │
│ ──────────────────          │
├─────────────────────────────┤
│ Cut  [PREV] [PROG]          │
│ Stop [●STOP]                │
└─────────────────────────────┘
```

### Controls
1. **Pan Fader** (vertical slider)
   - Range: -1 to 1
   - OSC: `/ptz/{cam_id}/pan` 
   - Labels: ← LEFT | RIGHT →

2. **Tilt Fader** (vertical slider)
   - Range: -1 to 1
   - OSC: `/ptz/{cam_id}/tilt`
   - Labels: ↑ UP | DOWN ↓

3. **Zoom Fader** (vertical slider)
   - Range: -1 to 1
   - OSC: `/ptz/{cam_id}/zoom`
   - Labels: 🔍 OUT | IN 🔍

4. **Camera Selector** (configurable buttons for cam 1, 2, 3)
   - User adds/removes buttons in template editor
   - Each sends OSC message to set active camera

5. **Cut Preview/Program Buttons**
   - Preview: `/ptz/{cam_id}/cut/preview`
   - Program: `/ptz/{cam_id}/cut/program`
   - Requires separate backend endpoint

6. **Stop Button** (momentary)
   - Sends: `/ptz/{cam_id}/stop`
   - Releases: nothing (spring action)

7. **Live Status Display** (label, read-only)
   - Shows "ON AIR" in red if camera is on program and locked
   - Updates via reverse OSC from app

### OSC Message Format (Standard)
```
/ptz/{cam_id}/{control} {value}

Examples:
/ptz/1/pan 0.75      # Pan right at 75% speed
/ptz/1/tilt -0.5     # Tilt down at 50% speed
/ptz/1/zoom 1.0      # Zoom in at full speed
/ptz/1/stop 0        # Stop motion
/ptz/1/cut/preview 1 # Set to preview
/ptz/1/cut/program 1 # Set to program
```

### Template Customization Guide
1. User opens touchOSC Editor
2. Import provided template
3. Add/remove camera buttons as needed
4. Set app IP address (network settings)
5. Set server IP and port in OSC config
6. Enable each fader and button

### Export Steps
1. Create `.tosc` file (touchOSC v2 binary format)
2. Document file location and import instructions
3. Include `.toml` alternative for v1 compatibility (if needed)

---

## Implementation Order

### Phase 1: Backend OSC Foundation ✅ COMPLETE
1. ✅ Add OSC listener thread to `server.py`
2. ✅ Implement rate limiting (30 Hz)
3. ✅ Add VISCA command mapping
4. ✅ Add OSC settings endpoints (`/api/osc/status`, `/api/osc/config`)
5. ✅ Add server-side logging (keeps last 50 messages)

### Phase 2: Frontend OSC Settings & Diagnostics ✅ COMPLETE
1. ✅ Add OSC settings UI to joystick panel
2. ✅ Add diagnostic panel with message log
3. ✅ Wire up settings to POST requests
4. ✅ Display status and errors
5. ✅ Real-time status polling when debug panel open

### Phase 3: Full-Screen Joystick ✅ COMPLETE
1. ✅ Add HTML structure and CSS
2. ✅ Implement touch handlers (pan/tilt)
3. ✅ Implement zoom slider with spring-back (release stops zoom)
4. ✅ Add live status display with lock indicator
5. ✅ Wire up camera selector buttons
6. ✅ Fullscreen page accessible via double-click on compact joystick
7. ✅ Live status updates reflect ATEM program state

### Phase 4: touchOSC Template & Documentation 🔄 IN PROGRESS
1. ⏳ Create touchOSC template file (`.tosc` binary format)
2. ⏳ Document template setup instructions
3. ⏳ Write troubleshooting guide
4. ⏳ Test with real iOS device (requires iOS 12+ iPad)

### Phase 5: Testing & Validation ⏳ PENDING
1. ⏳ Local server testing (done ✓)
2. ⏳ iOS 12 iPad fullscreen joystick testing
3. ⏳ touchOSC integration testing
4. ⏳ Live mode safety verification
5. ⏳ Multi-camera control testing

---

## Files to Modify/Create

### Modified
- `server.py`: Add OSC listener, settings, endpoints
- `public/index.html`: Add fullscreen joystick, OSC UI, diagnostics

### Created
- `touchosc-ptz-template.tosc`: OSC controller template
- `docs/TOUCHOSC_SETUP.md`: Setup and customization guide

---

## Questions Answered by User

✅ Feature priority: Both in parallel
✅ Fullscreen button: Bottom-left, stays visible
✅ Rotation: Layout flips (landscape differs from portrait)
✅ Zoom: Similar to current slider with spring-back
✅ Presets in fullscreen: Joystick-only mode
✅ Camera support: Multi-camera with configurable buttons
✅ Rate limit: 30 Hz (max 30 messages/sec)
✅ Live lock display: Both features show prominently
✅ Feedback: Server-side logging only

---

## OSC Protocol Decision

**Chosen: OSC (OpenSound Control)**

Rationale:
- Network-native (already network-dependent app)
- Flexible message format (easy to extend)
- iOS-friendly (works with touchOSC app)
- Human-readable for debugging
- Standard in A/V production workflows

Alternative (MIDI) deferred due to:
- Requires USB or network bridge (NetMIDI)
- Less flexible message format
- Harder to debug
- More complexity for minimal gain in this context

---

## Testing Strategy

### Local Testing
1. Backend unit tests for OSC parsing and rate limiting
2. Frontend unit tests for touch handling
3. Manual testing of both features on desktop/tablet

### Device Testing (Required)
1. **iOS 12 iPad:** Full-screen joystick
2. **iOS Device:** touchOSC app integration
3. **Both:** Live mode lock, multi-camera, cut buttons

### Compatibility Verification
- iOS 12 Safari (no ES6+, touch events)
- Network between devices
- Firewall/NAT traversal

---

## Rollout Plan

1. **Internal Testing:** Verify both features work on real devices
2. **Documentation:** Complete setup guides and troubleshooting
3. **Branch Review:** Submit PR for code review
4. **Merge:** Merge to main when CI passes and testing complete
5. **Release Notes:** Document new features and limitations

---
