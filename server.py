#!/usr/bin/env python3
"""PTZ Preset Control Server — VISCA over IP for AVIPAS cameras (no external dependencies)."""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import socket
import struct

_sequence_number = 1


def send_visca_preset_recall(ip: str, port: int, preset_number: int, camera_address: int = 1):
    """Send a VISCA over IP preset recall command via UDP.

    VISCA over IP packet layout:
        Bytes 0-1: Payload type  (0x01 0x00 = command)
        Bytes 2-3: Payload length (big-endian)
        Bytes 4-7: Sequence number (big-endian uint32)
        Bytes 8+:  VISCA payload

    Preset Recall payload: 8x 01 04 3F 02 pp FF
        x  = camera address (1-7)
        pp = preset index (0x00-0x7F)
    """
    global _sequence_number

    camera_byte = 0x80 | (camera_address & 0x07)
    visca_payload = bytes([camera_byte, 0x01, 0x04, 0x3F, 0x02, preset_number & 0x7F, 0xFF])
    header = struct.pack(">HHI", 0x0100, len(visca_payload), _sequence_number)
    packet = header + visca_payload
    _sequence_number = (_sequence_number + 1) & 0xFFFFFFFF

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


PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._serve_file(os.path.join(PUBLIC_DIR, "index.html"), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/recall":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json(400, {"success": False, "message": "Invalid JSON"})
                return

            ip = str(data.get("ip", "")).strip()
            port = int(data.get("port", 52381))
            # UI sends 1-based preset numbers; VISCA uses 0-based
            preset = max(0, int(data.get("preset", 1)) - 1)
            camera = max(1, min(7, int(data.get("camera", 1))))

            if not ip:
                self._json(400, {"success": False, "message": "Camera IP is required"})
                return

            success, message = send_visca_preset_recall(ip, port, preset, camera)
            self._json(200, {"success": success, "message": message})
        else:
            self.send_error(404)

    # ------------------------------------------------------------------ helpers

    def _serve_file(self, path: str, content_type: str):
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} — {fmt % args}")


if __name__ == "__main__":
    host, port = "0.0.0.0", 5000
    httpd = HTTPServer((host, port), Handler)
    print(f"PTZ Preset Control listening on  http://{host}:{port}")
    print("Press Ctrl-C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
