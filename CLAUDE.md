# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

PTZ Preset Control is a local web app for recalling and cataloguing presets on AVIPAS cameras over VISCA IP. It also integrates with Blackmagic ATEM switchers so the active camera can follow the configured preview or program input.

## Running The Server

```bash
python server.py
```

The app serves from `http://localhost:5001`.

Optional dependencies:

| Feature | Dependency |
|---|---|
| URL capture (VDO.ninja, browser streams) | `pip install playwright && playwright install chromium` |
| USB capture fallback | `pip install opencv-python` |
| Primary USB capture | `ffmpeg` on the system path |

## Architecture

The project is intentionally small and centered in two files:

- `server.py`: threaded stdlib HTTP server, VISCA control, ATEM integration, SSE, device capture, and persistence.
- `public/index.html`: single-file SPA with inline CSS and JavaScript.

**This project does not use Flask.** The HTTP server is Python's stdlib `http.server.BaseHTTPRequestHandler` + `socketserver.ThreadingMixIn`. There is no `app` object, no `@route` decorator, no `request` object, and no `jsonify`. All routing is hand-written in `Handler.do_GET`, `do_POST`, and `do_DELETE`. All JSON responses use the `_json(status, data)` helper method.

## Adding Routes

1. Add a branch in `do_GET`, `do_POST`, or `do_DELETE` matching on `path` (already stripped of the query string: `path = self.path.split("?")[0]`).
2. Use `re.match(r"^/api/your/(\d+)$", path)` for parameterised routes.
3. Read the body with `self._read_body()` and parse with `json.loads`.
4. Return JSON with `self._json(status_code, {"key": value})`.
5. Return errors as `self._json(404, {"error": "message"})`.

There is no middleware layer. Auth, CORS, and validation are all manual.

## Error Response Conventions

All JSON error responses use `{"ok": false, "error": "..."}`. Success responses use
`{"ok": true, ...rest}`. Do not use `success`/`message` keys — those appear in older
VISCA-specific code and are not the general pattern.

Exception handling:
- Catch broad `Exception` in HTTP handlers and return HTTP 500 with `str(e)` in the `error` field.
- Catch `OSError` specifically in VISCA/ATEM socket code.
- Use `except Exception: pass` only in cleanup/teardown paths (SSE disconnect, Playwright close, ATEM socket close).

## Adding a Feature End-to-End

A typical feature touches three places in this order:

1. **`server.py` route** — add a branch in `do_GET`/`do_POST`/`do_DELETE`, implement a handler method.
2. **Settings schema** — if persisting new state, add the key to `DEFAULT_SETTINGS` and ensure `load_settings()` merges it for older saves that predate the key.
3. **`public/index.html`** — add to `state`, wire a `fetch()` to the new route, call `schedSave()` if the state should persist, call `render()` if the UI needs updating.

Always verify both sides after: `python -m py_compile server.py` and the JS syntax check from the Verification section.

## State And Persistence

Persistent runtime state lives under `data/`:

- `data/settings.json`: cameras, labels, dwell time, grid settings, ATEM config, live/edit mode, and follow mode.
- `data/images/{cam}_{preset}.jpg`: saved preset thumbnails.

Preset labels are keyed in settings as `"{cam}:{preset}"`.

The browser stores only the selected local webcam device in `localStorage`.

## Settings Schema

The server accepts and stores whatever the frontend POSTs to `/settings` without validation. The canonical shape is:

```json
{
  "activeCam": 0,
  "cameras": [
    {
      "name": "Camera 1",
      "ip": "",
      "port": 52381,
      "viscaAddr": 1,
      "atemInput": 1,
      "streamUrl": "",
      "usbDevice": "",
      "enabled": true
    }
  ],
  "labels": { "0:1": "Stage Left", "0:5": "Wide" },
  "dwellMs": 3000,
  "atem": { "ip": "", "enabled": false },
  "liveMode": true,
  "atemFollows": "preview",
  "presetStart": 0,
  "presetEnd": 11,
  "gridCols": 4,
  "gridRows": 3,
  "fillWindow": false,
  "showAtemDebug": false
}
```

Key details:
- `labels` keys are the string `"{cam}:{preset}"` (e.g. `"0:1"`), not a tuple.
- `presetStart`/`presetEnd`/`gridCols`/`gridRows`/`fillWindow`/`showAtemDebug` are frontend display settings. The server stores them opaquely without reading them.
- The frontend debounces writes at 400 ms via `schedSave()`. Add new settings fields to both `DEFAULT_SETTINGS` in `server.py` and the `state` object in `public/index.html`.

## Thread Safety

One thread is spawned per HTTP request (`ThreadingMixIn`) plus the persistent `_atem_loop` daemon thread. Four module-level locks guard shared mutable state:

| Lock | Protects |
|---|---|
| `_sse_lock` | `_sse_clients` list |
| `_atem_state_lock` | `_atem_state` dict — use `_get_atem()` / `_set_atem()` |
| `_seq_lock` | `_sequence_number` (VISCA UDP sequence counter) |
| `_pw_lock` | `_pw_ctx / _pw_browser / _pw_page` (Playwright instance) |

Rules:
- Never access `_atem_state` directly; always use `_get_atem()` / `_set_atem()`.
- Hold `_sse_lock` only during list mutation, not during the blocking `q.get()`.
- `load_settings()` and `write_settings()` are NOT lock-protected. Do not add a second concurrent writer.

## ATEM Integration

`server.py` runs a background `_atem_loop()` that maintains the UDP connection to the ATEM switcher and broadcasts Server-Sent Events on `/events`.

The frontend listens for:

- `atem`: connection state plus initial preview/program values
- `preview`: preview source changes
- `program`: program source changes

In Live mode, the UI can follow either preview or program based on `atemFollows`.

Protocol details:
- Port **9910** (UDP). Send `ATEM_HELLO`, receive response, ACK with `session_id=0`. The actual `session_id` comes from the first data packet (not the HELLO response).
- Drain packets until `InCm` (or 5 s timeout) to complete the init dump.
- In steady state, only ME1 commands are processed (`cmd_data[0] == 0`).
- Send `_make_ack(session_id, last_seq)` every 500 ms as a keepalive.
- Reconnect triggers: no data for 5 s, or config change detected (IP/enabled checked every 5 s by re-reading settings).

## VISCA Protocol Notes

VISCA over IP wraps the serial payload in an 8-byte UDP header:

```
bytes 0–1:  0x01 0x00        (payload type: VISCA command)
bytes 2–3:  payload length   (big-endian uint16)
bytes 4–7:  sequence number  (big-endian uint32)
```

- Default port: **52381** (UDP).
- `viscaAddr` (1–7) maps to the command byte as `0x80 | (viscaAddr & 0x07)`.
- Preset numbers are **0-indexed** on the wire and masked to 7 bits (`& 0x7F`, max 127).
- Response sequence: ACK (`0x41`) then Completion (`0x51`). Error codes are `0x6x`. The server waits up to 2 s for completion; times out with a success + warning message.
- Position inquiry command: `[camera_byte, 0x09, 0x06, 0x12, 0xFF]`. Response encodes pan and tilt as 4 nibbles each (low 4 bits per byte), big-endian.

## Capture Priority

When scanning or capturing preset thumbnails, the app uses this priority:

1. Configured USB device through `ffmpeg`
2. Configured stream URL through Playwright
3. Browser webcam capture fallback

## Platform Differences

`_IS_MACOS = platform.system() == "Darwin"` gates capture behaviour:

- **Linux**: `ffmpeg -f v4l2 -i /dev/video{index}`; devices listed via `/dev/video*` + optional `v4l2-ctl --info`.
- **macOS**: `ffmpeg -f avfoundation`; tries multiple framerate options (60, 59.94, 30, none) and device variants (`index` and `"{index}:none"`). Requires Camera permission granted to Terminal/Python in System Settings.

Always branch on `_IS_MACOS` when adding new capture logic.

## Frontend Architecture

`public/index.html` is a single ~2 000-line file with one `<style>` block and one `<script>` block. There are no build tools, bundlers, or external assets.

Hard constraints:
- All JavaScript must be in the **one** `<script>` block. The CI check extracts it with `re.search(r'<script>([\s\S]*?)</script>', html)` — a second `<script>` tag means its contents are silently skipped and go unchecked.
- Do not add external `.js` or `.css` files; nothing links to them.

State model:
- `state` is the single JS object (not a reactive framework). Call `schedSave()` after any mutation that should persist; it debounces `pushSettings()` at 400 ms.
- `localStorage` stores only `ptz-webcam-device`. Nothing else is persisted client-side.

Image cache-busting:
- Images are served `Cache-Control: immutable`. The frontend uses `imageVersions[key]` as a `?v=N` query param. Call `bumpImageVersion(cam, preset)` then `refreshPresetBtn(preset, cam)` after any capture or upload.

## JavaScript Conventions

- `const` for all module-level values and function declarations; `let` for mutable loop/local variables; no `var`.
- `async`/`await` for all `fetch()` calls; no `.then()` chains.
- `'use strict'` is active globally — do not re-declare it in nested scopes.
- Failed fetches silently fall back via `.catch(() => ({}))` — the UI recovers rather than throws. Follow this pattern; do not `alert()` on routine network errors.

## Verification

Run these locally before pushing:

```bash
# Python format, lint, syntax, and smoke tests
ruff format --check server.py
ruff check server.py
python -m py_compile server.py
python -c "import server"

# JS syntax (requires Node 20+)
python3 - <<'EOF'
import re, sys, subprocess, tempfile, os
html = open('public/index.html').read()
m = re.search(r'<script>([\s\S]*?)</script>', html)
if not m: sys.exit('ERROR: no <script> block found')
with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
    f.write(m.group(1)); fname = f.name
try:
    r = subprocess.run(['node', '--check', fname], capture_output=True, text=True)
    if r.returncode != 0: print(r.stderr); sys.exit(1)
    print('JS syntax OK')
finally:
    os.unlink(fname)
EOF

# HTML structure
python3 -c "
from html.parser import HTMLParser; import sys
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class C(HTMLParser):
    def __init__(self): super().__init__(); self.stack=[]; self.errors=[]
    def handle_starttag(self,t,a): (None if t in VOID else self.stack.append(t))
    def handle_endtag(self,t):
        if t in VOID: return
        if self.stack and self.stack[-1]==t: self.stack.pop()
        else: self.errors.append(f'Bad </{t}>')
c=C(); c.feed(open('public/index.html').read())
if c.errors or c.stack: print(c.errors, c.stack); sys.exit(1)
print('HTML OK')
"
```

CI runs Python 3.12 / Node 20 on ubuntu-latest. No `pyproject.toml` or `ruff.toml`; ruff uses defaults. Active suppressions: `# noqa: A002` on `Handler.log_message` (built-in name shadow), `# type: ignore[assignment]` on the `cv2 = None` fallback.
