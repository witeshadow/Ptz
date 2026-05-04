#!/usr/bin/env python3
"""PTZ Preset Control Server — VISCA over IP for AVIPAS cameras (with ATEM integration)."""

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import glob
import json
import logging
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

from scripts.av1281_motion_probe import (
    ProbeResult,
    inquire_absolute_position as _probe_inquire_absolute_position,
    motion_sample_to_dict as _probe_motion_sample_to_dict,
    probe_preset as _probe_preset,
)

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

_logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(_HERE, "public")
DATA_DIR = os.path.join(_HERE, "data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
SETTINGS_F = os.path.join(DATA_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "activeCam": 0,
    "cameras": [
        {
            "name": "Camera 1",
            "ip": "",
            "port": 1259,
            "viscaAddr": 1,
            "atemInput": 1,
            "streamUrl": "",
            "usbDevice": "",
            "enabled": True,
        },
        {
            "name": "Camera 2",
            "ip": "",
            "port": 1259,
            "viscaAddr": 2,
            "atemInput": 2,
            "streamUrl": "",
            "usbDevice": "",
            "enabled": True,
        },
        {
            "name": "Camera 3",
            "ip": "",
            "port": 1259,
            "viscaAddr": 3,
            "atemInput": 3,
            "streamUrl": "",
            "usbDevice": "",
            "enabled": True,
        },
        {
            "name": "Camera 4",
            "ip": "",
            "port": 52381,
            "viscaAddr": 1,
            "atemInput": 4,
            "streamUrl": "",
            "usbDevice": "",
            "enabled": False,
        },
    ],
    "labels": {"0:1": "Stage Left", "0:5": "Wide"},
    "dwellMs": 3000,
    "scanWaitMode": "settle",
    "atem": {"ip": "", "enabled": False},
    "liveMode": True,
    "lockLiveMode": False,
    "unlockOnExitLiveMode": True,
    "atemFollows": "preview",
    "autoCutDelayMs": 0,
    "atemOutputMap": {
        "webcam": {"webcam": "", "streamUrl": ""},
        "sdi1": {"webcam": "", "streamUrl": ""},
        "sdi2": {"webcam": "", "streamUrl": ""},
        "sdi3": {"webcam": "", "streamUrl": ""},
        "sdi4": {"webcam": "", "streamUrl": ""},
    },
    "atemSourceLabels": {},
    "captureOutput": "webcam",
    "activeCamAux": "sdi1",
    "positions": {},
}

VISCA_RAW_UDP_PORT = 1259
VISCA_COMPLETION_TIMEOUT_S = 2.0
VISCA_SETTLE_TIMEOUT_S = 8.0
VISCA_POLL_INTERVAL_S = 0.2
VISCA_STABLE_COUNT = 3
VISCA_INQUIRY_TIMEOUT_S = 1.0
ATEM_STATE_CONFIRM_TIMEOUT_S = 2.0


def _visca_transport_for_port(port: int) -> str:
    return "raw-udp" if port == VISCA_RAW_UDP_PORT else "sony-udp"


def _normalize_recall_wait_mode(wait_mode: str | None) -> str:
    if wait_mode == "dwell":
        return "dwell"
    if wait_mode == "confirm":
        return "confirm"
    if wait_mode == "autocut":
        return "autocut"
    return "settle"


def _normalize_scan_wait_mode(wait_mode: str | None) -> str:
    normalized = _normalize_recall_wait_mode(wait_mode)
    return normalized if normalized in {"dwell", "settle"} else "settle"


def _probe_recall_command_succeeded(result: ProbeResult) -> bool:
    if result.error is not None:
        return False
    return not any(r.kind == "error" for r in result.replies)


def _probe_autocut_ready(result: ProbeResult) -> bool:
    return (
        result.error is None
        and not any(r.kind == "error" for r in result.replies)
        and (result.settled or result.saw_completion)
    )


def _format_probe_message(result: ProbeResult, wait_mode: str) -> str:
    parts = []
    ack = next((reply for reply in result.replies if reply.kind == "ack"), None)
    completion = next(
        (reply for reply in result.replies if reply.kind == "completion"),
        None,
    )
    if ack:
        parts.append(f"ACK {ack.payload.hex()}")
    if completion:
        parts.append(f"Completion {completion.payload.hex()}")
    if wait_mode == "settle" and result.settled and result.samples:
        pos = _probe_motion_sample_to_dict(result.samples[-1])
        parts.append(
            "Settled "
            f"pan {pos['pan_hex']} tilt {pos['tilt_hex']} zoom {pos['zoom_hex']}"
        )
    elif wait_mode == "settle" and not result.settled:
        parts.append("Motion did not settle in time")
    elif wait_mode == "confirm":
        if completion is None and ack is None:
            parts.append("Command sent")
    elif wait_mode == "autocut":
        if result.settled and result.samples:
            pos = _probe_motion_sample_to_dict(result.samples[-1])
            parts.append(
                "Settled "
                f"pan {pos['pan_hex']} tilt {pos['tilt_hex']} zoom {pos['zoom_hex']}"
            )
        elif result.saw_completion:
            parts.append("VISCA completion confirmed")
        else:
            parts.append("Motion stop was not confirmed")
    elif wait_mode == "dwell":
        parts.append("Manual dwell mode")
    if result.error:
        parts.append(result.error)
    if wait_mode == "dwell" and not parts:
        parts.append("Command sent")
    return " • ".join(parts) if parts else "VISCA preset recall completed"


def recall_visca_preset(
    ip: str,
    port: int,
    preset_number: int,
    camera_address: int = 1,
    wait_mode: str = "settle",
):
    wait_mode = _normalize_recall_wait_mode(wait_mode)
    result = _probe_preset(
        ip=ip,
        port=port,
        camera_address=camera_address,
        preset=preset_number,
        transport=_visca_transport_for_port(port),
        local_port=None,
        completion_timeout=VISCA_COMPLETION_TIMEOUT_S,
        settle_timeout=VISCA_SETTLE_TIMEOUT_S,
        poll_interval=VISCA_POLL_INTERVAL_S,
        stable_count=VISCA_STABLE_COUNT,
        inquiry_timeout=VISCA_INQUIRY_TIMEOUT_S,
        include_focus=False,
        require_settle=wait_mode == "settle",
        verbose=False,
    )
    success = (
        _probe_recall_command_succeeded(result) and result.settled
        if wait_mode == "settle"
        else _probe_autocut_ready(result)
        if wait_mode == "autocut"
        else _probe_recall_command_succeeded(result)
    )
    payload = {
        "success": success,
        "message": _format_probe_message(result, wait_mode),
        "settled": result.settled,
        "sawCompletion": result.saw_completion,
        "waitMode": wait_mode,
        "position": (
            _probe_motion_sample_to_dict(result.samples[-1]) if result.samples else None
        ),
    }
    return payload


def inquire_visca_absolute_position(
    ip: str, port: int, camera_address: int = 1
) -> tuple[bool, dict | str]:
    """
    Query a camera for its absolute pan/tilt/zoom position via VISCA and return the parsed result.

    Parameters:
        ip (str): Target camera IP address.
        port (int): Target camera port.
        camera_address (int): VISCA camera logical address (usually 1–7).

    Returns:
        tuple:
            - True and a dict with the inquiry result when the probe succeeds.
            - False and an error message string when the inquiry fails (an error line is printed on failure).
    """
    try:
        result = _probe_inquire_absolute_position(
            ip=ip,
            port=port,
            camera_address=camera_address,
            transport=_visca_transport_for_port(port),
            local_port=None,
            inquiry_timeout=VISCA_INQUIRY_TIMEOUT_S,
            include_focus=False,
        )
        return True, result
    except Exception as exc:
        print(
            f"[VISCA] Position inquiry failed for {ip}:{port} addr={camera_address}: {exc!r}"
        )
        return False, str(exc)


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
_atem_state = {
    "connected": False,
    "preview": 0,
    "program": 0,
    "aux1": 0,
    "aux2": 0,
    "aux3": 0,
    "aux4": 0,
}
_atem_state_lock = threading.Lock()
_atem_last_action = {
    "name": "",
    "stage": "",
    "source": 0,
    "reason": "",
    "ok": None,
    "message": "",
    "timestamp": 0.0,
}
_atem_last_action_lock = threading.Lock()
_atem_conn = {
    "sock": None,
    "addr": None,
    "session_id": 0,
    "packet_id": 0,
}
_atem_conn_lock = threading.Lock()


def _set_atem(
    connected: bool,
    preview: int | None = None,
    program: int | None = None,
    aux: tuple[int, int] | None = None,
):
    with _atem_state_lock:
        _atem_state["connected"] = connected
        if preview is not None:
            _atem_state["preview"] = preview
        if program is not None:
            _atem_state["program"] = program
        if aux is not None:
            key = f"aux{aux[0] + 1}"
            if key in _atem_state:
                _atem_state[key] = aux[1]


def _get_atem() -> dict:
    with _atem_state_lock:
        return dict(_atem_state)


def _set_atem_last_action(
    name: str,
    stage: str,
    source: int,
    reason: str,
    ok: bool | None,
    message: str,
):
    with _atem_last_action_lock:
        _atem_last_action.update(
            {
                "name": name,
                "stage": stage,
                "source": source,
                "reason": reason,
                "ok": ok,
                "message": message,
                "timestamp": time.time(),
            }
        )


def _get_atem_last_action() -> dict:
    with _atem_last_action_lock:
        return dict(_atem_last_action)


def _get_atem_connection_debug() -> dict:
    with _atem_conn_lock:
        addr = _atem_conn["addr"]
        return {
            "session_id": int(_atem_conn["session_id"] or 0),
            "packet_id": int(_atem_conn["packet_id"] or 0),
            "address": f"{addr[0]}:{addr[1]}" if addr else "",
        }


def _clear_atem_conn():
    with _atem_conn_lock:
        _atem_conn["sock"] = None
        _atem_conn["addr"] = None
        _atem_conn["session_id"] = 0
        _atem_conn["packet_id"] = 0


def _update_atem_conn(sock, addr, session_id: int):
    with _atem_conn_lock:
        _atem_conn["sock"] = sock
        _atem_conn["addr"] = addr
        _atem_conn["session_id"] = session_id
        if not _atem_conn["packet_id"]:
            _atem_conn["packet_id"] = 0


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
    # bytes 10-11 = ATEM's sequence number for this packet (what we ACK back)
    seq_num = struct.unpack(">H", data[10:12])[0] if len(data) >= 12 else 0
    return flags, seq_num


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


def _build_atem_command(name: str, payload: bytes) -> bytes:
    cmd_name = name.encode("ascii")
    if len(cmd_name) != 4:
        raise ValueError("ATEM command names must be 4 ASCII bytes")
    total_len = 8 + len(payload)
    return struct.pack(">H2x4s", total_len, cmd_name) + payload


def _send_atem_command(name: str, payload: bytes) -> tuple[bool, str]:
    packet_payload = _build_atem_command(name, payload)
    with _atem_conn_lock:
        sock = _atem_conn["sock"]
        addr = _atem_conn["addr"]
        session_id = int(_atem_conn["session_id"] or 0)
        if not sock or not addr or session_id <= 0:
            return False, "ATEM is not connected"
        packet_id = (int(_atem_conn["packet_id"] or 0) + 1) & 0x7FFF
        if packet_id == 0:
            packet_id = 1
        _atem_conn["packet_id"] = packet_id
        packet_len = 12 + len(packet_payload)
        word0 = (0x01 << 11) | packet_len
        packet = (
            struct.pack(">HHHHHH", word0, session_id, 0, 0, 0, packet_id)
            + packet_payload
        )
        try:
            sock.sendto(packet, addr)
        except OSError as exc:
            return False, str(exc)
    return True, f"ATEM packet {packet_id} sent"


def _send_atem_preview(source_id: int) -> tuple[bool, str]:
    """Set ATEM ME1 preview bus to source_id via CPvI command."""
    # CPvI payload: ME index (1 byte), padding (1 byte), source (2 bytes big-endian)
    return _send_atem_command("CPvI", b"\x00\x00" + struct.pack(">H", source_id))


def _wait_for_atem_program_source(source: int, timeout_s: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _get_atem().get("program") == source:
            return True
        time.sleep(0.05)
    return _get_atem().get("program") == source


def _wait_for_atem_preview_source(source: int, timeout_s: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _get_atem().get("preview") == source:
            return True
        time.sleep(0.05)
    return _get_atem().get("preview") == source


def _send_atem_aux_source(aux_idx: int, source_id: int) -> tuple[bool, str]:
    """Route an ATEM AUX output to a given source via CAuS command."""
    # CAuS payload: mask=0x01, aux channel (0-based), source (big-endian uint16)
    return _send_atem_command(
        "CAuS", bytes([0x01, aux_idx]) + struct.pack(">H", source_id)
    )


def _wait_for_atem_aux_source(
    aux_idx: int, source: int, timeout_s: float = 1.0
) -> bool:
    """
    Waits until the specified AUX output reports the given source or the timeout elapses.

    Parameters:
        aux_idx (int): Zero-based AUX index (0 -> "aux1", 1 -> "aux2", etc.).
        source (int): ATEM source id to wait for on the AUX output.
        timeout_s (float): Maximum time in seconds to wait.

    Returns:
        True if the AUX routed to `source` before the timeout, False otherwise.
    """
    key = f"aux{aux_idx + 1}"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _get_atem().get(key) == source:
            return True
        time.sleep(0.05)
    return _get_atem().get(key) == source


def cut_atem_to_source(source: int, reason: str = "manual") -> tuple[bool, str]:
    """
    Attempt to switch the ATEM to the given program source using a preview-then-cut strategy with fallbacks and record progress to the ATEM last-action state.

    Performs staged actions: set preview if required, execute a cut, and if confirmations fail attempt a direct program switch; updates `_atem_last_action` with stage, status, and human-readable messages.

    Parameters:
        source (int): Target ATEM source index (must be greater than 0).
        reason (str): Context for the request, typically "manual" or "auto".

    Returns:
        tuple: `(ok, message)` where `ok` is `True` if the ATEM ended on the requested source, `False` otherwise, and `message` is a descriptive success or error string.
    """
    if source <= 0:
        _set_atem_last_action(
            "cut", "invalid", source, reason, False, "Invalid ATEM source"
        )
        return False, "Invalid ATEM source"
    preview_payload = bytes([0, 0]) + struct.pack(">H", source)
    current = _get_atem()
    _set_atem_last_action(
        "cut",
        "start",
        source,
        reason,
        None,
        f"Starting cut request for source {source} (preview={current.get('preview')} program={current.get('program')})",
    )
    if current.get("preview") != source:
        ok, message = _send_atem_command("CPvI", preview_payload)
        if not ok:
            _set_atem_last_action(
                "cut",
                "preview-send",
                source,
                reason,
                False,
                f"Preview command failed: {message}",
            )
            return False, message
        if not _wait_for_atem_preview_source(
            source, timeout_s=ATEM_STATE_CONFIRM_TIMEOUT_S
        ):
            _set_atem_last_action(
                "cut",
                "preview-confirm",
                source,
                reason,
                False,
                f"Preview did not confirm on source {source}",
            )
            ok, program_message = _send_atem_command("CPgI", preview_payload)
            if not ok:
                _set_atem_last_action(
                    "cut",
                    "program-fallback-send",
                    source,
                    reason,
                    False,
                    f"Direct program switch failed: {program_message}",
                )
                return (
                    False,
                    f"Preview did not change to {source} and direct program switch failed: {program_message}",
                )
            if _wait_for_atem_program_source(
                source, timeout_s=ATEM_STATE_CONFIRM_TIMEOUT_S
            ):
                msg = f"Preview did not change • direct program switch moved program to {source}"
                _set_atem_last_action(
                    "cut", "program-fallback-confirm", source, reason, True, msg
                )
                return (
                    True,
                    msg,
                )
            _set_atem_last_action(
                "cut",
                "program-fallback-confirm",
                source,
                reason,
                False,
                f"ATEM did not confirm preview or program switched to {source}",
            )
            return (
                False,
                f"ATEM did not confirm preview or program switched to {source}",
            )

    ok, cut_message = _send_atem_command("DCut", bytes([0, 0, 0, 0]))
    if not ok:
        _set_atem_last_action(
            "cut",
            "cut-send",
            source,
            reason,
            False,
            f"Cut command failed: {cut_message}",
        )
        return False, cut_message
    if _wait_for_atem_program_source(source, timeout_s=ATEM_STATE_CONFIRM_TIMEOUT_S):
        msg = f"Preview set to {source} • Cut executed"
        _set_atem_last_action("cut", "cut-confirm", source, reason, True, msg)
        return True, msg

    ok, program_message = _send_atem_command("CPgI", preview_payload)
    if not ok:
        _set_atem_last_action(
            "cut",
            "program-fallback-send",
            source,
            reason,
            False,
            f"Cut did not take and direct program switch failed: {program_message}",
        )
        return (
            False,
            f"Cut did not take and direct program switch failed: {program_message}",
        )
    if _wait_for_atem_program_source(source, timeout_s=ATEM_STATE_CONFIRM_TIMEOUT_S):
        msg = f"Cut did not take • direct program switch moved program to {source}"
        _set_atem_last_action(
            "cut", "program-fallback-confirm", source, reason, True, msg
        )
        return (
            True,
            msg,
        )
    _set_atem_last_action(
        "cut",
        "program-fallback-confirm",
        source,
        reason,
        False,
        f"ATEM did not confirm program switched to {source} after cut or direct switch",
    )
    return (
        False,
        f"ATEM did not confirm program switched to {source} after cut or direct switch",
    )


def _atem_loop():
    while True:
        cfg = load_settings().get("atem", {})
        if not cfg.get("enabled") or not cfg.get("ip", "").strip():
            time.sleep(2)
            continue

        ip = cfg["ip"].strip()
        _logger.info(f"ATEM: Connecting to {ip}:{ATEM_PORT}")
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5.0)
            atem_addr = (ip, ATEM_PORT)
            sock.sendto(ATEM_HELLO, atem_addr)
            data, _ = sock.recvfrom(2048)
            _logger.debug(f"ATEM: HELLO response raw={data[:12].hex()}")
            # ACK the HELLO response with session_id=0 (not yet assigned)
            _, hello_seq = _parse_header(data)
            sock.sendto(_make_ack(0, hello_seq), atem_addr)

            # drain init dump; pick up actual session_id from first data packet
            session_id = 0
            init_done = False
            init_preview: int | None = None
            init_program: int | None = None
            pkt_count = 0
            while not init_done:
                try:
                    data, _ = sock.recvfrom(2048)
                    pkt_count += 1
                    # ATEM assigns session_id in data packets (HELLO response has 0)
                    pkt_sid = struct.unpack(">H", data[2:4])[0]
                    if pkt_sid != 0:
                        session_id = pkt_sid
                        _update_atem_conn(sock, atem_addr, session_id)
                    flags, seq_num = _parse_header(data)
                    if flags & 0x01:  # ATEM wants ACK (RELIABLE flag)
                        sock.sendto(_make_ack(session_id, seq_num), atem_addr)
                    for cmd, cmd_data in _parse_commands(
                        data[12:] if len(data) > 12 else b""
                    ):
                        if cmd == "InCm":
                            init_done = True
                            break
                        elif cmd in ("PrvI", "PrgI") and len(cmd_data) >= 4:
                            me = cmd_data[0]
                            source = struct.unpack(">H", cmd_data[2:4])[0]
                            _logger.debug(f"ATEM: init {cmd} me={me} source={source}")
                            if me == 0:
                                if cmd == "PrvI":
                                    init_preview = source
                                else:
                                    init_program = source
                        elif cmd == "AuxS" and len(cmd_data) >= 4:
                            aux_idx = cmd_data[0]
                            aux_src = struct.unpack(">H", cmd_data[2:4])[0]
                            _set_atem(False, aux=(aux_idx, aux_src))
                except socket.timeout:
                    _logger.debug(f"ATEM: init drain timeout after {pkt_count} packets")
                    break  # proceed even if InCm wasn't seen

            _set_atem(True, preview=init_preview, program=init_program)
            _update_atem_conn(sock, atem_addr, session_id)
            _broadcast({"type": "atem", **_get_atem()})
            _logger.info(
                f"ATEM: Connected with preview={init_preview} program={init_program}"
            )

            sock.settimeout(1.0)
            last_recv = time.monotonic()
            last_keepalive = time.monotonic()
            last_cfg_check = time.monotonic()
            last_seq = 0  # last ATEM sequence number received — used for keepalives

            while True:
                # re-check config every 5 s instead of every loop iteration
                now = time.monotonic()
                if now - last_cfg_check >= 5.0:
                    cur_cfg = load_settings().get("atem", {})
                    last_cfg_check = now
                    if (
                        not cur_cfg.get("enabled")
                        or cur_cfg.get("ip", "").strip() != ip
                    ):
                        _logger.info("ATEM: Config changed — reconnecting")
                        break

                try:
                    data, _ = sock.recvfrom(2048)
                    now = time.monotonic()
                    last_recv = now
                    flags, seq_num = _parse_header(data)
                    last_seq = seq_num
                    if flags & 0x01:  # ATEM wants ACK (RELIABLE flag)
                        sock.sendto(_make_ack(session_id, seq_num), atem_addr)
                    for cmd, cmd_data in _parse_commands(
                        data[12:] if len(data) > 12 else b""
                    ):
                        cur = _get_atem()
                        # filter PrvI/PrgI to ME1 (cmd_data[0] == 0) for multi-ME switchers
                        if (
                            cmd in ("PrvI", "PrgI")
                            and len(cmd_data) >= 4
                            and cmd_data[0] == 0
                        ):
                            source = struct.unpack(">H", cmd_data[2:4])[0]
                            if cmd == "PrvI" and source != cur["preview"]:
                                _logger.debug(f"ATEM: PrvI source={source}")
                                _set_atem(True, preview=source)
                                _broadcast({"type": "preview", "source": source})
                            elif cmd == "PrgI" and source != cur["program"]:
                                _logger.debug(f"ATEM: PrgI source={source}")
                                _set_atem(True, program=source)
                                _broadcast({"type": "program", "source": source})
                        elif cmd == "AuxS" and len(cmd_data) >= 4:
                            aux_idx = cmd_data[0]
                            aux_src = struct.unpack(">H", cmd_data[2:4])[0]
                            akey = f"aux{aux_idx + 1}"
                            if akey in cur and aux_src != cur[akey]:
                                _logger.debug(
                                    f"ATEM: AuxS idx={aux_idx} source={aux_src}"
                                )
                                _set_atem(True, aux=(aux_idx, aux_src))
                                _broadcast(
                                    {"type": "aux", "index": aux_idx, "source": aux_src}
                                )
                except socket.timeout:
                    pass

                now = time.monotonic()
                if now - last_recv > 5.0:
                    _logger.info("ATEM: No data for 5 seconds — reconnecting")
                    break
                if now - last_keepalive >= 0.5:
                    sock.sendto(_make_ack(session_id, last_seq), atem_addr)
                    last_keepalive = time.monotonic()

        except Exception as exc:
            _logger.exception(f"ATEM: Error: {exc!r}")
        finally:
            _clear_atem_conn()
            _set_atem(False)
            _logger.info("ATEM: Disconnected — will retry in 3 seconds")
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
    expected_reply_byte = ((camera_address + 8) << 4) & 0xF0
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
        deadline = time.monotonic() + 2.0
        ack_payload = None
        completion_payload = None
        raw_payloads = []
        responder_note = None

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                response, _ = sock.recvfrom(1024)
            except socket.timeout:
                break

            payload = response[8:] if len(response) >= 8 else response
            if len(payload) < 3 or payload[-1] != 0xFF:
                continue
            raw_payloads.append(payload.hex())
            if payload[0] != expected_reply_byte and responder_note is None:
                responder_note = (
                    f"unexpected responder 0x{payload[0]:02x} "
                    f"(expected 0x{expected_reply_byte:02x})"
                )

            code = payload[1]
            if code == 0x41:
                ack_payload = payload
            elif code == 0x51:
                completion_payload = payload
                break
            elif code & 0xF0 == 0x60:
                return False, f"VISCA error {payload.hex()}"

        suffix = f" [{responder_note}]" if responder_note else ""
        if completion_payload and ack_payload:
            return (
                True,
                f"ACK {ack_payload.hex()} • Completion {completion_payload.hex()}{suffix}",
            )
        if completion_payload:
            return True, f"Completion {completion_payload.hex()}{suffix}"
        if ack_payload:
            return True, f"ACK {ack_payload.hex()} (no completion received){suffix}"
        if raw_payloads:
            return (
                True,
                f"Command sent (unparsed VISCA response: {' | '.join(raw_payloads)})",
            )
        return True, "Command sent (no VISCA response received)"
    except OSError as exc:
        return False, str(exc)
    finally:
        sock.close()


def inquire_visca_pan_tilt_position(
    ip: str, port: int, camera_address: int = 1
) -> tuple[bool, dict | str]:
    camera_byte = 0x80 | (camera_address & 0x07)
    expected_reply_byte = ((camera_address + 8) << 4) & 0xF0
    visca_payload = bytes([camera_byte, 0x09, 0x06, 0x12, 0xFF])
    header = struct.pack(">HHI", 0x0100, len(visca_payload), 0)
    packet = header + visca_payload
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)
    try:
        sock.sendto(packet, (ip, port))
        deadline = time.monotonic() + 2.0
        raw_payloads = []
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                response, _ = sock.recvfrom(1024)
            except socket.timeout:
                break

            payload = response[8:] if len(response) >= 8 else response
            if len(payload) < 11 or payload[-1] != 0xFF:
                continue
            raw_payloads.append(payload.hex())

            code = payload[1]
            if code == 0x50:
                pan_hex = "".join(f"{b & 0x0F:x}" for b in payload[2:6]).upper()
                tilt_hex = "".join(f"{b & 0x0F:x}" for b in payload[6:10]).upper()
                return True, {
                    "pan_hex": pan_hex,
                    "tilt_hex": tilt_hex,
                    "pan": int(pan_hex, 16),
                    "tilt": int(tilt_hex, 16),
                    "raw": payload.hex(),
                    "responder": f"0x{payload[0]:02x}",
                    "expected_responder": f"0x{expected_reply_byte:02x}",
                }
            if code & 0xF0 == 0x60:
                return False, f"VISCA error {payload.hex()}"

        if raw_payloads:
            return (
                False,
                f"Unparsed VISCA position response: {' | '.join(raw_payloads)}",
            )
        return False, "No VISCA position response received"
    except OSError as exc:
        return False, str(exc)
    finally:
        sock.close()


# ── Playwright capture ─────────────────────────────────────────────────────────
_pw_lock = threading.Lock()
_pw_ctx = None  # playwright instance
_pw_browser = None
_pw_page = None
_pw_page_url = None


def _capture_url(url: str) -> bytes:
    """Capture screenshot from URL using headless Playwright browser.

    Supports standard HTTP streams (RTMP, HLS, etc). Note: vdo.ninja URLs are
    rejected at the HTTP handler level before reaching this function.
    """
    global _pw_ctx, _pw_browser, _pw_page, _pw_page_url
    with _pw_lock:
        # Redact URL for logging (remove query params that may contain tokens)
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            redacted_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except Exception:
            redacted_url = "<redacted>"

        if _pw_ctx is None:
            _pw_ctx = _sync_playwright().start()
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
            try:
                _pw_page = _pw_browser.new_page()
                _pw_page.goto(url, wait_until="domcontentloaded")
                _logger.debug(f"Capture: Loaded URL {redacted_url}")
                # wait up to 30s for a video element with decoded data
                _pw_page.wait_for_function(
                    "() => { const v = document.querySelector('video'); "
                    "return v && v.readyState >= 2 && v.videoWidth > 0; }",
                    timeout=30_000,
                )
                _logger.debug(f"Capture: Video element ready for {redacted_url}")
            except Exception as e:
                _logger.error(
                    f"Capture: Failed to load video from {redacted_url}: {e!r}"
                )
                # Try fullpage screenshot as fallback
                if _pw_page:
                    _logger.debug("Capture: Falling back to page screenshot")
                _pw_page_url = None  # force reload next time
                raise
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
                capture_output=True,
                timeout=5,
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
                        devices.append(
                            {"index": m.group(1), "name": m.group(2).strip()}
                        )
        except Exception:
            pass
    else:
        for dev in sorted(glob.glob("/dev/video*")):
            idx = dev.replace("/dev/video", "")
            name = dev
            try:
                r = subprocess.run(
                    ["v4l2-ctl", "--device", dev, "--info"],
                    capture_output=True,
                    timeout=3,
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
    """
    Capture a single JPEG frame from a USB/video device and return its bytes.

    Parameters:
        index (str): Device identifier. On macOS this may be an avfoundation device spec (e.g. "0" or "0:none").
                     On Linux this is the numeric video device index (e.g. "0" → /dev/video0).

    Returns:
        bytes: JPEG image bytes of the captured frame.

    Raises:
        RuntimeError: If ffmpeg capture fails and no cv2 fallback is available, or on macOS when avfoundation
                      cannot access the camera (suggests checking Camera privacy settings).
    """
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp = f.name
    try:
        if _IS_MACOS:
            print(f"[Capture] macOS device={index}, trying avfoundation…")
            # Try each device variant without a forced framerate first (lets avfoundation
            # negotiate the native rate), then retry with supported framerates.
            for device_arg in (index, f"{index}:none"):
                for framerate_args in (
                    ["-framerate", "60"],
                    ["-framerate", "59.940180"],
                    ["-framerate", "30"],
                    [],
                ):
                    framerate_str = (
                        framerate_args[1] if len(framerate_args) > 1 else "auto"
                    )
                    args = [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "avfoundation",
                        *framerate_args,
                        "-i",
                        device_arg,
                        "-frames:v",
                        "1",
                        "-q:v",
                        "3",
                        tmp,
                    ]
                    if _ffmpeg_grab(args, tmp):
                        print(
                            f"[Capture] Success with device_arg={device_arg} framerate={framerate_str}"
                        )
                        break
                else:
                    continue
                break
            else:
                if _HAS_CV2:
                    print(
                        "[Capture] avfoundation exhausted all options, fallback to cv2…"
                    )
                    return _capture_cv2(int(index))
                raise RuntimeError(
                    f"ffmpeg avfoundation failed for device {index!r}. "
                    "Check: System Settings > Privacy > Camera — grant access to Terminal/Python."
                )
        else:
            print(f"[Capture] Linux device=/dev/video{index}, trying v4l2…")
            args = [
                "ffmpeg",
                "-y",
                "-f",
                "v4l2",
                "-i",
                f"/dev/video{index}",
                "-ss",
                "0.1",
                "-frames:v",
                "1",
                "-q:v",
                "3",
                tmp,
            ]
            if not _ffmpeg_grab(args, tmp):
                if _HAS_CV2:
                    print("[Capture] v4l2 failed, fallback to cv2…")
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
    for _ in range(3):  # first frames often corrupt on cold open
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


def _try_record_position(settings: dict, cam: int, preset: int) -> dict | None:
    """
    Query a camera's absolute pan/tilt/zoom and store the result in settings["positions"] under the key "{cam}:{preset}".

    Parameters:
        settings (dict): Loaded settings dictionary to update; must be written to disk by the caller if persistence is desired.
        cam (int): Camera index within settings["cameras"].
        preset (int): Preset number to use as the storage key suffix.

    Returns:
        dict: Position dictionary with keys "pan", "tilt", "zoom", "pan_hex", "tilt_hex", "zoom_hex" on success.
        None: If the camera index is out of bounds, the camera has no IP configured, or the VISCA inquiry fails.
    """
    cams = settings.get("cameras", [])
    if cam < 0 or cam >= len(cams):
        print(
            f"[Position] Skip record: camera index {cam} out of bounds (total={len(cams)})"
        )
        return None
    cfg = cams[cam]
    ip = str(cfg.get("ip", "")).strip()
    if not ip:
        print(f"[Position] Skip record: camera {cam} has no IP configured")
        return None
    port = int(cfg.get("port", 52381) or 52381)
    visca_addr = int(cfg.get("viscaAddr", 1) or 1)
    ok, result = inquire_visca_absolute_position(ip, port, visca_addr)
    if not ok or not isinstance(result, dict):
        print(
            f"[Position] Skip record: inquiry failed for camera {cam} (ok={ok}, result_type={type(result).__name__})"
        )
        return None
    pos = {
        "pan": result.get("pan"),
        "tilt": result.get("tilt"),
        "zoom": result.get("zoom"),
        "pan_hex": result.get("pan_hex"),
        "tilt_hex": result.get("tilt_hex"),
        "zoom_hex": result.get("zoom_hex"),
    }
    if "positions" not in settings:
        settings["positions"] = {}
    settings["positions"][f"{cam}:{preset}"] = pos
    return pos


# ── Validation helpers ─────────────────────────────────────────────────────────
def _require_atem_enabled_and_connected() -> tuple[bool, dict | None]:
    """
    Validate that ATEM is enabled in settings and has an active connection.

    Returns:
        (bool, dict|None): Tuple where the first element is `True` when ATEM is enabled and connected, `False` otherwise. The second element is `None` on success or an error response dict (e.g. `{"ok": False, "error": "<message>"}`) describing the failure.
    """
    cfg = load_settings().get("atem", {})
    if not cfg.get("enabled"):
        return False, {"ok": False, "error": "ATEM is disabled in settings"}
    if not _get_atem().get("connected"):
        return False, {"ok": False, "error": "ATEM is not connected"}
    return True, None


def _require_camera(
    settings: dict, cam_idx: int
) -> tuple[bool, dict | None, dict | None]:
    """
    Validate that a zero-based camera index refers to a configured camera.

    Parameters:
        settings (dict): Server settings dictionary expected to contain a "cameras" list.
        cam_idx (int): Zero-based index of the camera to validate.

    Returns:
        tuple:
            - (bool) True if the camera index is valid, False otherwise.
            - (dict | None) An error response dict `{"ok": False, "error": <message>}` when invalid, otherwise None.
            - (dict | None) The camera configuration dict when valid, otherwise None.
    """
    cams = settings.get("cameras", [])
    if cam_idx < 0 or cam_idx >= len(cams):
        return False, {"ok": False, "error": "Camera not found"}, None
    return True, None, cams[cam_idx]


# ── HTTP handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        """
        Log an HTTP request message to standard output prefixed with the client's address.

        Parameters:
            format (str): A printf-style format string describing the message.
            *args: Values to be interpolated into `format`.

        Description:
            Prints a single line to stdout in the form:
                "<client-address> — <formatted message>"
        """
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
        elif path == "/atem/debug":
            cfg = load_settings().get("atem", {})
            with _sse_lock:
                n_clients = len(_sse_clients)
            self._json(
                200,
                {
                    "state": _get_atem(),
                    "connection": _get_atem_connection_debug(),
                    "last_action": _get_atem_last_action(),
                    "sse_clients": n_clients,
                    "settings": {
                        "ip": cfg.get("ip", ""),
                        "enabled": bool(cfg.get("enabled", False)),
                    },
                },
            )
        elif path == "/events":
            self._sse()
        elif path == "/api/devices":
            self._json(200, list_usb_devices())
        elif path == "/api/system":
            self._json(
                200,
                {
                    "playwrightAvailable": _HAS_PLAYWRIGHT,
                    "playwrightError": None
                    if _HAS_PLAYWRIGHT
                    else "Playwright not installed. Run: pip install playwright && playwright install chromium",
                },
            )
        elif m := re.match(r"^/api/position/(\d+)$", path):
            self._get_position(int(m.group(1)))
        elif m := re.match(r"^/api/image/(\d+)/(\d+)/position$", path):
            self._get_image_position(int(m.group(1)), int(m.group(2)))
        elif m := re.match(r"^/api/image/(\d+)/(\d+)$", path):
            self._get_image(int(m.group(1)), int(m.group(2)))
        else:
            clean = path.lstrip("/")
            if clean:
                self._serve_static(clean)
            else:
                self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/recall":
            self._handle_recall()
        elif path == "/atem/cut":
            self._handle_atem_cut()
        elif path == "/api/atem/preview":
            self._handle_atem_preview_post()
        elif path == "/api/atem/aux-route":
            self._handle_atem_aux_route()
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
        try:
            port = int(data.get("port", 52381))
            preset = max(0, int(data.get("preset", 0)))
            camera = max(1, min(7, int(data.get("camera", 1))))
        except (TypeError, ValueError):
            self._json(400, {"success": False, "message": "Invalid numeric parameter"})
            return
        wait_mode = _normalize_recall_wait_mode(str(data.get("waitMode", "settle")))
        if not ip:
            self._json(400, {"success": False, "message": "Camera IP is required"})
            return
        result = recall_visca_preset(ip, port, preset, camera, wait_mode)
        self._json(200, result)

    def _handle_settings_post(self):
        body = self._read_body()
        try:
            data = json.loads(body)
            write_settings(data)
            self._json(200, {"ok": True})
        except Exception as e:
            self._json(400, {"ok": False, "error": str(e)})

    def _handle_atem_cut(self):
        """
        Handle POST /atem/cut: validate input, request an ATEM cut, and respond with JSON.

        Parses the request JSON body for "source" (int) and optional "reason" ("manual" or "auto", defaults to "manual").
        - Returns HTTP 400 with {"ok": False, "error": ...} when the body is invalid JSON or "source" cannot be parsed as an integer.
        - Calls internal validation to ensure ATEM is enabled and connected; if that check fails responds with the provided error payload and HTTP 409.
        - Invokes cut_atem_to_source(source, reason=reason) and returns:
          - HTTP 200 with {"ok": True, "message": <msg>, "source": <source>, "reason": <reason>, "lastAction": <snapshot>} on success.
          - HTTP 502 with {"ok": False, "message": <msg>, "source": <source>, "reason": <reason>, "lastAction": <snapshot>} on failure.

        The JSON response always includes "ok", "message", "source", "reason", and a snapshot of the ATEM last action from _get_atem_last_action().
        """
        body = self._read_body()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "Invalid JSON"})
            return

        try:
            source = int(data.get("source", 0))
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "Invalid ATEM source"})
            return
        reason = str(data.get("reason", "manual")).strip().lower()
        if reason not in {"manual", "auto"}:
            reason = "manual"

        ok, error_resp = _require_atem_enabled_and_connected()
        if not ok:
            self._json(409, error_resp)
            return

        ok, message = cut_atem_to_source(source, reason=reason)
        status = 200 if ok else 502
        self._json(
            status,
            {
                "ok": ok,
                "message": message,
                "source": source,
                "reason": reason,
                "lastAction": _get_atem_last_action(),
            },
        )

    def _handle_atem_preview_post(self):
        """
        Handle POST /api/atem/preview: set the ATEM preview source from a camera configuration.

        Expects a JSON body with an integer `camIdx` identifying the camera configuration. Validates request JSON and camera index, ensures ATEM is enabled and connected, and that the target camera has an `atemInput` configured. Sends the corresponding preview routing command to the ATEM and returns a JSON response.

        Responses:
        - 200: {"ok": true, "message": "<send message>", "source": <atem_input>} on success.
        - 400: {"ok": false, "error": "..."} for invalid JSON, invalid `camIdx`, or when the camera has no ATEM input configured.
        - 404: {"ok": false, "error": "..."} when the requested camera is not found or misconfigured.
        - 409: error payload from precondition check when ATEM is disabled or not connected.
        - 502: {"ok": false, "message": "<error message>", "source": <atem_input>} if sending the ATEM command fails.
        """
        body = self._read_body()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "Invalid JSON"})
            return

        try:
            cam_idx = int(data.get("camIdx", -1))
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "Invalid camIdx"})
            return

        ok, error_resp = _require_atem_enabled_and_connected()
        if not ok:
            self._json(409, error_resp)
            return

        settings = load_settings()
        ok, error_resp, cam_cfg = _require_camera(settings, cam_idx)
        if not ok:
            self._json(404, error_resp)
            return

        try:
            atem_input = int(cam_cfg.get("atemInput") or 0)
        except (TypeError, ValueError):
            atem_input = 0
        if not atem_input:
            self._json(
                400, {"ok": False, "error": "Camera has no ATEM input configured"}
            )
            return

        ok, message = _send_atem_preview(atem_input)
        status = 200 if ok else 502
        self._json(status, {"ok": ok, "message": message, "source": atem_input})

    def _handle_atem_aux_route(self):
        """
        Route an ATEM AUX channel to a camera's ATEM input based on a JSON POST body.

        Expects a JSON body with:
        - "aux": one of "sdi1", "sdi2", "sdi3", "sdi4".
        - "camIdx": integer camera index.

        Behavior:
        - Validates JSON and parameters, returns 400 for malformed input or unsupported aux keys.
        - Requires the ATEM feature to be enabled and connected; returns 409 if not available.
        - Requires the referenced camera to exist and have an ATEM input configured; returns 404 for missing camera or 400 if the camera lacks an ATEM input.
        - Sends the AUX routing command to the ATEM and returns 502 if the send fails.
        - Waits for ATEM confirmation (1.0s); returns 504 if the routing is not confirmed.
        - On success returns 200 with confirmation details including "aux" and "source".

        Responses (examples):
        - 200: {"ok": True, "confirmed": True, "message": <status>, "aux": <aux_key>, "source": <atem_input>}
        - 400: {"ok": False, "error": <message>}
        - 404: {"ok": False, "error": <message>}
        - 409: <error payload from precondition check>
        - 502: {"ok": False, "error": <send error message>}
        - 504: {"ok": False, "confirmed": False, "error": <message>, "aux": <aux_key>, "source": <atem_input>}
        """
        body = self._read_body()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "Invalid JSON"})
            return

        aux_key = str(data.get("aux", "")).strip()
        aux_map = {"sdi1": 0, "sdi2": 1, "sdi3": 2, "sdi4": 3}
        if aux_key not in aux_map:
            self._json(400, {"ok": False, "error": "aux must be sdi1–sdi4"})
            return
        aux_idx = aux_map[aux_key]

        try:
            cam_idx = int(data.get("camIdx", -1))
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "Invalid camIdx"})
            return

        ok, error_resp = _require_atem_enabled_and_connected()
        if not ok:
            self._json(409, error_resp)
            return

        settings = load_settings()
        ok, error_resp, cam_cfg = _require_camera(settings, cam_idx)
        if not ok:
            self._json(404, error_resp)
            return

        try:
            atem_input = int(cam_cfg.get("atemInput") or 0)
        except (TypeError, ValueError):
            atem_input = 0
        if not atem_input:
            self._json(
                400, {"ok": False, "error": "Camera has no ATEM input configured"}
            )
            return

        ok, message = _send_atem_aux_source(aux_idx, atem_input)
        if not ok:
            self._json(502, {"ok": False, "error": message})
            return
        confirmed = _wait_for_atem_aux_source(aux_idx, atem_input, timeout_s=1.0)
        if not confirmed:
            self._json(
                504,
                {
                    "ok": False,
                    "confirmed": False,
                    "error": f"ATEM did not confirm route on {aux_key}",
                    "aux": aux_key,
                    "source": atem_input,
                },
            )
            return
        self._json(
            200,
            {
                "ok": True,
                "confirmed": True,
                "message": message,
                "aux": aux_key,
                "source": atem_input,
            },
        )

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
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(data)

    def _get_position(self, cam: int):
        cams = load_settings().get("cameras", [])
        if cam < 0 or cam >= len(cams):
            self._json(404, {"ok": False, "error": "Camera not found"})
            return

        cfg = cams[cam]
        ip = str(cfg.get("ip", "")).strip()
        port = int(cfg.get("port", 52381) or 52381)
        visca_addr = int(cfg.get("viscaAddr", 1) or 1)
        if not ip:
            self._json(400, {"ok": False, "error": "Camera IP is not configured"})
            return

        ok, result = inquire_visca_absolute_position(ip, port, visca_addr)
        if ok:
            self._json(200, {"ok": True, **result})
        else:
            self._json(502, {"ok": False, "error": result})

    def _get_image_position(self, cam: int, preset: int):
        positions = load_settings().get("positions", {})
        pos = positions.get(f"{cam}:{preset}")
        if pos is None:
            self._json(404, {"ok": False, "error": "No position data for this preset"})
            return
        self._json(200, {"ok": True, **pos})

    def _post_image(self, cam: int, preset: int):
        _ensure_dirs()
        data = self._read_body()
        fpath = os.path.join(IMAGES_DIR, f"{cam}_{preset}.jpg")
        with open(fpath, "wb") as f:
            f.write(data)
        settings = load_settings()
        position = _try_record_position(settings, cam, preset)
        if position is not None:
            write_settings(settings)
        self._json(200, {"ok": True, "position": position})

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
                # Check for unsupported vdo.ninja URLs early (WebRTC streaming)
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(url)
                    hostname = parsed.hostname or ""
                    if hostname == "vdo.ninja" or hostname.endswith(".vdo.ninja"):
                        self._json(
                            400,
                            {
                                "ok": False,
                                "error": (
                                    "vdo.ninja uses WebRTC streaming which cannot be "
                                    "captured by headless browser. Use a standard RTMP/HLS "
                                    "stream instead, or convert vdo.ninja to a standard "
                                    "format with ffmpeg."
                                ),
                            },
                        )
                        return
                except Exception:
                    pass
                if not _HAS_PLAYWRIGHT:
                    self._json(
                        503,
                        {
                            "ok": False,
                            "error": "playwright not installed — run: pip install playwright && playwright install chromium",
                        },
                    )
                    return
                jpeg = _capture_url(url)
            else:
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": "no capture source configured for this camera",
                    },
                )
                return
            _ensure_dirs()
            fpath = os.path.join(IMAGES_DIR, f"{cam}_{preset}.jpg")
            with open(fpath, "wb") as f:
                f.write(jpeg)
            settings = load_settings()
            position = _try_record_position(settings, cam, preset)
            if position is not None:
                write_settings(settings)
            self._json(200, {"ok": True, "position": position})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})

    def _delete_image(self, cam: int, preset: int):
        fpath = os.path.join(IMAGES_DIR, f"{cam}_{preset}.jpg")
        if os.path.exists(fpath):
            os.remove(fpath)
        settings = load_settings()
        key = f"{cam}:{preset}"
        if key in settings.get("positions", {}):
            del settings["positions"][key]
            write_settings(settings)
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
        fpath = os.path.join(PUBLIC_DIR, clean)
        public_root = os.path.abspath(PUBLIC_DIR)
        if os.path.abspath(fpath) != public_root and not os.path.abspath(
            fpath
        ).startswith(public_root + os.sep):
            self.send_response(403)
            self.end_headers()
            return
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    load_settings()  # ensure data/ and default settings.json exist
    atem_thread = threading.Thread(target=_atem_loop, daemon=True, name="atem")
    atem_thread.start()
    host, port = "0.0.0.0", 5001
    httpd = ThreadedHTTPServer((host, port), Handler)
    logger.info(f"PTZ Preset Control listening on http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down.")
