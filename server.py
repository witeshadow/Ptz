#!/usr/bin/env python3
"""PTZ Preset Control Server — VISCA over IP for AVIPAS cameras."""

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import glob
import json
import os
import platform
import queue
import re
import socket
import struct
import subprocess
import tempfile
import threading
import time

try:
    from playwright.sync_api import sync_playwright as _sync_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

try:
    import cv2 as _cv2
    _HAS_CV2 = True
except ImportError:
    _cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

_IS_MACOS = platform.system() == "Darwin"

# ── Paths ──────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(_HERE, "public")
DATA_DIR = os.path.join(_HERE, "data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
SETTINGS_F = os.path.join(DATA_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "activeCam": 0,
    "cameras": [
        {"name": "Camera 1", "ip": "", "port": 52381, "viscaAddr": 1, "atemInput": 1, "streamUrl": "", "usbDevice": ""},
        {"name": "Camera 2", "ip": "", "port": 52381, "viscaAddr": 1, "atemInput": 2, "streamUrl": "", "usbDevice": ""},
        {"name": "Camera 3", "ip": "", "port": 52381, "viscaAddr": 1, "atemInput": 3, "streamUrl": "", "usbDevice": ""},
    ],
    "labels": {"0:1": "Stage Left", "0:5": "Wide"},
    "dwellMs": 3000,
    "atem": {"ip": "", "enabled": False},
}


# ── Settings ───────────────────────────────────────────────────────────────────
def _ensure_dirs():
    os.makedirs(IMAGES_DIR, exist_ok=True)


def load_settings() -> dict:
    _ensure_dirs()
    if not os.path.exists(SETTINGS_F):
        write_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)
    with open(SETTINGS_F) as f:
        return json.load(f)


def write_settings(data: dict):
    _ensure_dirs()
    with open(SETTINGS_F, "w") as f:
        json.dump(data, f, indent=2)


# ── SSE ────────────────────────────────────────────────────────────────────────
_sse_clients: list[queue.SimpleQueue] = []
_sse_lock = threading.Lock()


def _broadcast(event: dict):
    msg = f"data: {json.dumps(event)}\n\n".encode()
    with _sse_lock:
        for q in list(_sse_clients):
            try:
                q.put_nowait(msg)
            except Exception:
                pass


# ── ATEM state ─────────────────────────────────────────────────────────────────
_atem_state = {"connected": False, "preview": 0}
_atem_state_lock = threading.Lock()


def _set_atem(connected: bool, preview: int | None = None):
    with _atem_state_lock:
        _atem_state["connected"] = connected
        if preview is not None:
            _atem_state["preview"] = preview


def _get_atem() -> dict:
    with _atem_state_lock:
        return dict(_atem_state)


# ── ATEM UDP client ────────────────────────────────────────────────────────────
ATEM_PORT = 9910
ATEM_HELLO = bytes(
    [
        0x10,
        0x14,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x26,
        0x00,
        0x00,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
    ]
)


def _make_ack(session_id: int, remote_id: int) -> bytes:
    return bytes([0x80, 0x0C]) + struct.pack(">HH", session_id, remote_id) + bytes(6)


def _parse_header(data: bytes):
    word0 = struct.unpack(">H", data[0:2])[0]
    flags = (word0 >> 11) & 0x1F
    remote_id = struct.unpack(">H", data[4:6])[0]
    return flags, remote_id


def _parse_commands(payload: bytes):
    pos = 0
    while pos + 8 <= len(payload):
        cmd_len = struct.unpack(">H", payload[pos : pos + 2])[0]
        if cmd_len < 8 or pos + cmd_len > len(payload):
            break
        cmd_name = payload[pos + 4 : pos + 8].decode("ascii", errors="replace")
        cmd_data = payload[pos + 8 : pos + cmd_len]
        yield cmd_name, cmd_data
        pos += cmd_len


def _atem_loop():
    while True:
        cfg = load_settings().get("atem", {})
        if not cfg.get("enabled") or not cfg.get("ip", "").strip():
            time.sleep(2)
            continue

        ip = cfg["ip"].strip()
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5.0)
            sock.sendto(ATEM_HELLO, (ip, ATEM_PORT))
            data, _ = sock.recvfrom(2048)
            session_id = struct.unpack(">H", data[2:4])[0]

            # drain init dump until InCm (or timeout)
            init_done = False
            while not init_done:
                try:
                    data, _ = sock.recvfrom(2048)
                    flags, remote_id = _parse_header(data)
                    if flags & 0x10:  # ATEM wants ACK
                        sock.sendto(_make_ack(session_id, remote_id), (ip, ATEM_PORT))
                    for cmd, _ in _parse_commands(data[12:] if len(data) > 12 else b""):
                        if cmd == "InCm":
                            init_done = True
                            break
                except socket.timeout:
                    break  # proceed even if InCm wasn't seen

            _set_atem(True)
            _broadcast({"type": "atem", "connected": True})

            sock.settimeout(1.0)
            last_recv = time.monotonic()
            last_keepalive = time.monotonic()

            while True:
                # re-check config each iteration
                cur_cfg = load_settings().get("atem", {})
                if not cur_cfg.get("enabled") or cur_cfg.get("ip", "").strip() != ip:
                    break

                try:
                    data, _ = sock.recvfrom(2048)
                    now = time.monotonic()
                    last_recv = now
                    flags, remote_id = _parse_header(data)
                    if flags & 0x10:
                        sock.sendto(_make_ack(session_id, remote_id), (ip, ATEM_PORT))
                    for cmd, cmd_data in _parse_commands(
                        data[12:] if len(data) > 12 else b""
                    ):
                        if cmd == "PrvI" and len(cmd_data) >= 4:
                            source = struct.unpack(">H", cmd_data[2:4])[0]
                            _set_atem(True, source)
                            _broadcast({"type": "preview", "source": source})
                except socket.timeout:
                    pass

                now = time.monotonic()
                if now - last_recv > 5.0:
                    break  # reconnect
                if now - last_keepalive >= 0.5:
                    sock.sendto(_make_ack(session_id, 0), (ip, ATEM_PORT))
                    last_keepalive = time.monotonic()

        except Exception:
            pass
        finally:
            _set_atem(False)
            try:
                _broadcast({"type": "atem", "connected": False})
            except Exception:
                pass
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

        time.sleep(3)


# ── VISCA ──────────────────────────────────────────────────────────────────────
_sequence_number = 1
_seq_lock = threading.Lock()


def send_visca_preset_recall(
    ip: str, port: int, preset_number: int, camera_address: int = 1
):
    global _sequence_number
    camera_byte = 0x80 | (camera_address & 0x07)
    visca_payload = bytes(
        [camera_byte, 0x01, 0x04, 0x3F, 0x02, preset_number & 0x7F, 0xFF]
    )
    with _seq_lock:
        seq = _sequence_number
        _sequence_number = (_sequence_number + 1) & 0xFFFFFFFF
    header = struct.pack(">HHI", 0x0100, len(visca_payload), seq)
    packet = header + visca_payload
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)
    try:
        sock.sendto(packet, (ip, port))
        try:
            response, _ = sock.recvfrom(1024)
            return True, f"ACK {response.hex()}"
        except socket.timeout:
            return True, "Command sent (no ACK)"
    except OSError as exc:
        return False, str(exc)
    finally:
        sock.close()


# ── Playwright capture ─────────────────────────────────────────────────────────
_pw_lock     = threading.Lock()
_pw_ctx      = None   # playwright instance
_pw_browser  = None
_pw_page     = None
_pw_page_url = None


def _capture_url(url: str) -> bytes:
    global _pw_ctx, _pw_browser, _pw_page, _pw_page_url
    with _pw_lock:
        if _pw_ctx is None:
            _pw_ctx     = _sync_playwright().start()
            _pw_browser = _pw_ctx.chromium.launch(
                headless=True,
                args=[
                    "--autoplay-policy=no-user-gesture-required",
                    "--use-fake-ui-for-media-stream",
                ],
            )
        if _pw_page is None or _pw_page_url != url:
            if _pw_page:
                try:
                    _pw_page.close()
                except Exception:
                    pass
            _pw_page = _pw_browser.new_page()
            _pw_page.goto(url, wait_until="domcontentloaded")
            # wait up to 15 s for a video element with decoded data
            _pw_page.wait_for_function(
                "() => { const v = document.querySelector('video'); "
                "return v && v.readyState >= 2 && v.videoWidth > 0; }",
                timeout=15_000,
            )
            _pw_page_url = url
        video = _pw_page.query_selector("video")
        if video:
            return video.screenshot(type="jpeg", quality=70)
        return _pw_page.screenshot(type="jpeg", full_page=False)


# ── USB device capture ─────────────────────────────────────────────────────────
def list_usb_devices() -> list:
    devices = []
    if _IS_MACOS:
        try:
            r = subprocess.run(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                capture_output=True, timeout=5,
            )
            in_video = False
            for line in r.stderr.decode("utf-8", errors="replace").splitlines():
                if "AVFoundation video devices" in line:
                    in_video = True
                    continue
                if "AVFoundation audio devices" in line:
                    break
                if in_video:
                    m = re.search(r"\[(\d+)\]\s+(.+)", line)
                    if m:
                        devices.append({"index": m.group(1), "name": m.group(2).strip()})
        except Exception:
            pass
    else:
        for dev in sorted(glob.glob("/dev/video*")):
            idx = dev.replace("/dev/video", "")
            name = dev
            try:
                r = subprocess.run(
                    ["v4l2-ctl", "--device", dev, "--info"],
                    capture_output=True, timeout=3,
                )
                for line in r.stdout.decode().splitlines():
                    if "Card type" in line:
                        name = line.split(":", 1)[1].strip()
                        break
            except Exception:
                pass
            devices.append({"index": idx, "name": name})
    return devices


def _ffmpeg_grab(args: list, tmp: str) -> bool:
    r = subprocess.run(args, capture_output=True, timeout=15)
    stderr = r.stderr.decode("utf-8", errors="replace")
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        print(f"[ffmpeg] exit={r.returncode}\n{stderr[-600:]}")
        return False
    return True


def capture_usb_device(index: str) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp = f.name
    try:
        if _IS_MACOS:
            # Try each device variant without a forced framerate first (lets avfoundation
            # negotiate the native rate), then retry with 30fps for cameras that require it.
            for device_arg in (index, f"{index}:none"):
                for framerate_args in (["-framerate", "60"], ["-framerate", "30"], ["-framerate", "59.940180"], []):
                    args = [
                        "ffmpeg", "-y",
                        "-f", "avfoundation", *framerate_args,
                        "-i", device_arg,
                        "-frames:v", "1", "-q:v", "3",
                        tmp,
                    ]
                    if _ffmpeg_grab(args, tmp):
                        break
                else:
                    continue
                break
            else:
                if _HAS_CV2:
                    return _capture_cv2(int(index))
                raise RuntimeError(
                    f"ffmpeg avfoundation failed for device {index!r}. "
                    "Check: System Settings > Privacy > Camera — grant access to Terminal/Python."
                )
        else:
            args = [
                "ffmpeg", "-y",
                "-f", "v4l2", "-i", f"/dev/video{index}",
                "-ss", "0.1",
                "-frames:v", "1", "-q:v", "3", tmp,
            ]
            if not _ffmpeg_grab(args, tmp):
                if _HAS_CV2:
                    return _capture_cv2(int(index))
                raise RuntimeError(f"ffmpeg v4l2 failed for /dev/video{index}")

        with open(tmp, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _capture_cv2(index: int) -> bytes:
    cap = _cv2.VideoCapture(index)
    for _ in range(3):   # first frames often corrupt on cold open
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"cv2: no frame from device {index}")
    _, buf = _cv2.imencode(".jpg", frame, [_cv2.IMWRITE_JPEG_QUALITY, 70])
    return bytes(buf)


# ── MIME types ─────────────────────────────────────────────────────────────────
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".css": "text/css",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


# ── HTTP handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):  # noqa: A002
        print(f"  {self.address_string()} — {format % args}")

    # ── routing ────────────────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._serve_static("index.html")
        elif path == "/settings":
            self._json(200, load_settings())
        elif path == "/atem/status":
            self._json(200, _get_atem())
        elif path == "/events":
            self._sse()
        elif path == "/api/devices":
            self._json(200, list_usb_devices())
        elif m := re.match(r"^/api/image/(\d+)/(\d+)$", path):
            self._get_image(int(m.group(1)), int(m.group(2)))
        else:
            clean = path.lstrip("/")
            if clean and not clean.startswith(".."):
                self._serve_static(clean)
            else:
                self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/recall":
            self._handle_recall()
        elif path == "/settings":
            self._handle_settings_post()
        elif m := re.match(r"^/api/image/(\d+)/(\d+)$", path):
            self._post_image(int(m.group(1)), int(m.group(2)))
        elif m := re.match(r"^/api/capture/(\d+)/(\d+)$", path):
            self._capture_image(int(m.group(1)), int(m.group(2)))
        else:
            self.send_error(404)

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if m := re.match(r"^/api/image/(\d+)/(\d+)$", path):
            self._delete_image(int(m.group(1)), int(m.group(2)))
        else:
            self.send_error(404)

    # ── handlers ───────────────────────────────────────────────────────────────
    def _handle_recall(self):
        body = self._read_body()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json(400, {"success": False, "message": "Invalid JSON"})
            return
        ip = str(data.get("ip", "")).strip()
        port = int(data.get("port", 52381))
        preset = max(0, int(data.get("preset", 0)))
        camera = max(1, min(7, int(data.get("camera", 1))))
        if not ip:
            self._json(400, {"success": False, "message": "Camera IP is required"})
            return
        ok, msg = send_visca_preset_recall(ip, port, preset, camera)
        self._json(200, {"success": ok, "message": msg})

    def _handle_settings_post(self):
        body = self._read_body()
        try:
            data = json.loads(body)
            write_settings(data)
            self._json(200, {"ok": True})
        except Exception as e:
            self._json(400, {"ok": False, "error": str(e)})

    def _get_image(self, cam: int, preset: int):
        fpath = os.path.join(IMAGES_DIR, f"{cam}_{preset}.jpg")
        if not os.path.exists(fpath):
            self.send_response(404)
            self.end_headers()
            return
        with open(fpath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _post_image(self, cam: int, preset: int):
        _ensure_dirs()
        data = self._read_body()
        fpath = os.path.join(IMAGES_DIR, f"{cam}_{preset}.jpg")
        with open(fpath, "wb") as f:
            f.write(data)
        self._json(200, {"ok": True})

    def _capture_image(self, cam: int, preset: int):
        try:
            req = json.loads(self._read_body())
        except Exception:
            req = {}

        usb = req.get("usbDevice", "").strip()
        url = req.get("url", "").strip()

        # fall back to per-camera settings when client sends nothing
        if not usb and not url:
            cams = load_settings().get("cameras", [])
            if cam < len(cams):
                usb = cams[cam].get("usbDevice", "").strip()
                url = cams[cam].get("streamUrl", "").strip()

        try:
            if usb:
                jpeg = capture_usb_device(usb)
            elif url:
                if not _HAS_PLAYWRIGHT:
                    self._json(503, {
                        "ok": False,
                        "error": "playwright not installed — run: pip install playwright && playwright install chromium",
                    })
                    return
                jpeg = _capture_url(url)
            else:
                self._json(400, {"ok": False, "error": "no capture source configured for this camera"})
                return
            _ensure_dirs()
            fpath = os.path.join(IMAGES_DIR, f"{cam}_{preset}.jpg")
            with open(fpath, "wb") as f:
                f.write(jpeg)
            self._json(200, {"ok": True})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})

    def _delete_image(self, cam: int, preset: int):
        fpath = os.path.join(IMAGES_DIR, f"{cam}_{preset}.jpg")
        if os.path.exists(fpath):
            os.remove(fpath)
        self._json(200, {"ok": True})

    def _sse(self):
        q = queue.SimpleQueue()
        with _sse_lock:
            _sse_clients.append(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        # send current ATEM state immediately
        init_event = {"type": "atem", **_get_atem()}
        try:
            self.wfile.write(f"data: {json.dumps(init_event)}\n\n".encode())
            self.wfile.flush()
        except Exception:
            with _sse_lock:
                _sse_clients.remove(q)
            return
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(msg)
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except Exception:
            pass
        finally:
            with _sse_lock:
                try:
                    _sse_clients.remove(q)
                except ValueError:
                    pass

    def _serve_static(self, name: str):
        clean = os.path.normpath(name)
        if clean.startswith(".."):
            self.send_response(403)
            self.end_headers()
            return
        fpath = os.path.join(PUBLIC_DIR, clean)
        if not os.path.isfile(fpath):
            self.send_response(404)
            self.end_headers()
            return
        ext = os.path.splitext(fpath)[1].lower()
        mime = _MIME.get(ext, "application/octet-stream")
        with open(fpath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── helpers ────────────────────────────────────────────────────────────────
    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _json(self, status: int, data: dict | list):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Server ─────────────────────────────────────────────────────────────────────
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    load_settings()  # ensure data/ and default settings.json exist
    atem_thread = threading.Thread(target=_atem_loop, daemon=True, name="atem")
    atem_thread.start()
    host, port = "0.0.0.0", 5001
    httpd = ThreadedHTTPServer((host, port), Handler)
    print(f"PTZ Preset Control listening on  http://localhost:{port}")
    print("Press Ctrl-C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
