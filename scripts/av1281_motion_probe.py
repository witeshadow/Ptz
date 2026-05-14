#!/usr/bin/env python3
"""Probe AV-1281 preset recall completion and motion settling over VISCA."""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys
import time
from dataclasses import dataclass


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SETTINGS_F = os.path.join(REPO_ROOT, "data", "settings.json")


@dataclass(frozen=True)
class ViscaReply:
    kind: str
    responder: int
    code: int
    payload: bytes
    socket_number: int | None = None


@dataclass(frozen=True)
class MotionSample:
    pan: int
    tilt: int
    zoom: int
    focus: int | None
    taken_at: float

    def comparable(self, include_focus: bool) -> tuple[int, ...]:
        if include_focus:
            return (
                self.pan,
                self.tilt,
                self.zoom,
                -1 if self.focus is None else self.focus,
            )
        return (self.pan, self.tilt, self.zoom)

    def format(self) -> str:
        text = (
            f"pan=0x{self.pan:04X} ({self.pan:5d})  "
            f"tilt=0x{self.tilt:04X} ({self.tilt:5d})  "
            f"zoom=0x{self.zoom:04X} ({self.zoom:5d})"
        )
        if self.focus is not None:
            text += f"  focus=0x{self.focus:04X} ({self.focus:5d})"
        return text


@dataclass(frozen=True)
class ProbeResult:
    preset: int
    replies: list[ViscaReply]
    saw_completion: bool
    settled: bool
    samples: list[MotionSample]
    error: str | None


def _nibbles_to_int(data: bytes) -> int:
    return int("".join(f"{byte & 0x0F:X}" for byte in data), 16)


def _to_signed_16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def classify_visca_payload(payload: bytes) -> ViscaReply | None:
    if len(payload) < 3 or payload[-1] != 0xFF:
        return None

    responder = payload[0]
    code = payload[1]
    high_nibble = code & 0xF0
    socket_number = code & 0x0F

    if high_nibble == 0x40:
        return ViscaReply("ack", responder, code, payload, socket_number)
    if high_nibble == 0x50 and len(payload) == 3:
        return ViscaReply("completion", responder, code, payload, socket_number)
    if high_nibble == 0x60:
        return ViscaReply("error", responder, code, payload, socket_number)
    if high_nibble == 0x50:
        return ViscaReply("inquiry", responder, code, payload)
    return ViscaReply("unknown", responder, code, payload)


def parse_pan_tilt_payload(payload: bytes) -> tuple[int, int] | None:
    if len(payload) != 11 or payload[1] != 0x50:
        return None
    if any(byte > 0x0F for byte in payload[2:10]):
        return None
    return _nibbles_to_int(payload[2:6]), _nibbles_to_int(payload[6:10])


def parse_zoom_or_focus_payload(payload: bytes) -> int | None:
    if len(payload) != 7 or payload[1] != 0x50:
        return None
    if any(byte > 0x0F for byte in payload[2:6]):
        return None
    return _nibbles_to_int(payload[2:6])


class SequenceCounter:
    def __init__(self) -> None:
        self._value = 1

    def next(self) -> int:
        value = self._value
        self._value = (self._value + 1) & 0xFFFFFFFF
        return value


def build_packet(payload: bytes, transport: str, seq: int) -> bytes:
    if transport == "sony-udp":
        return struct.pack(">HHI", 0x0100, len(payload), seq) + payload
    return payload


def unwrap_packet(data: bytes, transport: str) -> bytes:
    if transport == "sony-udp" and len(data) >= 8:
        return data[8:]
    return data


def load_camera_from_settings(camera_index: int) -> dict:
    with open(SETTINGS_F) as f:
        settings = json.load(f)
    cameras = settings.get("cameras", [])
    if camera_index < 0 or camera_index >= len(cameras):
        raise ValueError(
            f"Camera index {camera_index} is out of range for {SETTINGS_F}"
        )
    return cameras[camera_index]


def send_command(
    sock: socket.socket,
    ip: str,
    port: int,
    payload: bytes,
    transport: str,
    seq_counter: SequenceCounter,
) -> None:
    packet = build_packet(payload, transport, seq_counter.next())
    sock.sendto(packet, (ip, port))


def recv_payload(sock: socket.socket, transport: str) -> bytes:
    data, _ = sock.recvfrom(2048)
    return unwrap_packet(data, transport)


def wait_for_completion(
    sock: socket.socket,
    transport: str,
    timeout_s: float,
) -> tuple[list[ViscaReply], bool]:
    replies: list[ViscaReply] = []
    deadline = time.monotonic() + timeout_s
    saw_completion = False

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sock.settimeout(remaining)
        try:
            payload = recv_payload(sock, transport)
        except socket.timeout:
            break
        reply = classify_visca_payload(payload)
        if reply is None:
            continue
        replies.append(reply)
        if reply.kind == "completion":
            saw_completion = True
            break
        if reply.kind == "error":
            break

    return replies, saw_completion


def send_inquiry(
    sock: socket.socket,
    ip: str,
    port: int,
    payload: bytes,
    transport: str,
    seq_counter: SequenceCounter,
    timeout_s: float,
    parser,
):
    send_command(sock, ip, port, payload, transport, seq_counter)
    deadline = time.monotonic() + timeout_s
    raw_replies: list[str] = []

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sock.settimeout(remaining)
        try:
            response_payload = recv_payload(sock, transport)
        except socket.timeout:
            break
        reply = classify_visca_payload(response_payload)
        if reply is None:
            continue
        raw_replies.append(response_payload.hex())
        if reply.kind == "error":
            raise RuntimeError(f"VISCA error reply: {response_payload.hex()}")
        parsed = parser(response_payload)
        if parsed is not None:
            return parsed

    seen_suffix = f"; saw {' | '.join(raw_replies)}" if raw_replies else ""
    raise TimeoutError(
        f"No parsable VISCA inquiry response to {payload.hex()}{seen_suffix}"
    )


def query_motion_sample(
    sock: socket.socket,
    ip: str,
    port: int,
    camera_address: int,
    transport: str,
    seq_counter: SequenceCounter,
    include_focus: bool,
    inquiry_timeout_s: float,
) -> MotionSample:
    camera_byte = 0x80 | (camera_address & 0x07)
    pan, tilt = send_inquiry(
        sock,
        ip,
        port,
        bytes([camera_byte, 0x09, 0x06, 0x12, 0xFF]),
        transport,
        seq_counter,
        inquiry_timeout_s,
        parse_pan_tilt_payload,
    )
    zoom = send_inquiry(
        sock,
        ip,
        port,
        bytes([camera_byte, 0x09, 0x04, 0x47, 0xFF]),
        transport,
        seq_counter,
        inquiry_timeout_s,
        parse_zoom_or_focus_payload,
    )
    focus = None
    if include_focus:
        focus = send_inquiry(
            sock,
            ip,
            port,
            bytes([camera_byte, 0x09, 0x04, 0x48, 0xFF]),
            transport,
            seq_counter,
            inquiry_timeout_s,
            parse_zoom_or_focus_payload,
        )
    return MotionSample(pan, tilt, zoom, focus, time.monotonic())


def motion_sample_to_dict(sample: MotionSample) -> dict:
    return {
        "pan": sample.pan,
        "tilt": sample.tilt,
        "zoom": sample.zoom,
        "focus": sample.focus,
        "pan_hex": f"{sample.pan:04X}",
        "tilt_hex": f"{sample.tilt:04X}",
        "zoom_hex": f"{sample.zoom:04X}",
        "focus_hex": f"{sample.focus:04X}" if sample.focus is not None else None,
        "pan_signed": _to_signed_16(sample.pan),
        "tilt_signed": _to_signed_16(sample.tilt),
    }


def inquire_absolute_position(
    *,
    ip: str,
    port: int,
    camera_address: int,
    transport: str,
    local_port: int | None = None,
    inquiry_timeout: float = 1.0,
    include_focus: bool = False,
) -> dict:
    seq_counter = SequenceCounter()
    if local_port is None and transport == "sony-udp":
        local_port = port

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", 0 if local_port is None else local_port))
        sock.settimeout(inquiry_timeout)
        sample = query_motion_sample(
            sock,
            ip,
            port,
            camera_address,
            transport,
            seq_counter,
            include_focus,
            inquiry_timeout,
        )
        result = motion_sample_to_dict(sample)
        result["transport"] = transport
        return result
    finally:
        sock.close()


def print_replies(replies: list[ViscaReply]) -> None:
    if not replies:
        print("No VISCA replies received while waiting for completion.")
        return
    print("VISCA replies while waiting for preset recall:")
    for reply in replies:
        suffix = ""
        if reply.socket_number is not None:
            suffix = f" socket={reply.socket_number}"
        print(
            f"  {reply.kind:<10} code=0x{reply.code:02X}{suffix} raw={reply.payload.hex()}"
        )


def probe_preset(
    *,
    ip: str,
    port: int,
    camera_address: int,
    preset: int,
    transport: str,
    local_port: int | None,
    completion_timeout: float,
    settle_timeout: float,
    poll_interval: float,
    stable_count: int,
    inquiry_timeout: float,
    include_focus: bool,
    require_settle: bool = True,
    verbose: bool = True,
) -> ProbeResult:
    camera_byte = 0x80 | (camera_address & 0x07)
    preset_payload = bytes([camera_byte, 0x01, 0x04, 0x3F, 0x02, preset & 0x7F, 0xFF])
    seq_counter = SequenceCounter()
    if local_port is None and transport == "sony-udp":
        local_port = port
    samples: list[MotionSample] = []
    replies: list[ViscaReply] = []
    saw_completion = False

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", 0 if local_port is None else local_port))
        sock.settimeout(inquiry_timeout)
        if verbose:
            print(
                f"Sending preset {preset} to {ip}:{port} "
                f"using {transport} (local port {sock.getsockname()[1]})."
            )
        send_command(sock, ip, port, preset_payload, transport, seq_counter)
        replies, saw_completion = wait_for_completion(
            sock,
            transport,
            completion_timeout,
        )
        if verbose:
            print_replies(replies)
            if saw_completion:
                print("VISCA completion arrived before settle polling.")
            else:
                print(
                    "No VISCA completion arrived in time; falling back to motion polling."
                )

        if not require_settle:
            if verbose:
                print("Manual dwell mode: skipping settle polling.")
            return ProbeResult(
                preset=preset,
                replies=replies,
                saw_completion=saw_completion,
                settled=False,
                samples=samples,
                error=None,
            )

        settle_deadline = time.monotonic() + settle_timeout
        last_key: tuple[int, ...] | None = None
        stable_runs = 0
        observed_change = False
        guard_deadline = time.monotonic() + max(poll_interval * stable_count, 0.6)

        while time.monotonic() < settle_deadline:
            sample = query_motion_sample(
                sock,
                ip,
                port,
                camera_address,
                transport,
                seq_counter,
                include_focus,
                inquiry_timeout,
            )
            samples.append(sample)
            key = sample.comparable(include_focus)
            if key == last_key:
                stable_runs += 1
            else:
                if last_key is not None:
                    observed_change = True
                stable_runs = 1
            last_key = key
            if verbose:
                print(f"[sample {stable_runs}/{stable_count}] {sample.format()}")
            if stable_runs >= stable_count:
                if (
                    observed_change
                    or time.monotonic() >= guard_deadline
                    or saw_completion
                ):
                    if verbose:
                        print("Motion appears settled.")
                    return ProbeResult(
                        preset=preset,
                        replies=replies,
                        saw_completion=saw_completion,
                        settled=True,
                        samples=samples,
                        error=None,
                    )
            time.sleep(poll_interval)

        if verbose:
            print("Timed out before motion settled.")
        return ProbeResult(
            preset=preset,
            replies=replies,
            saw_completion=saw_completion,
            settled=False,
            samples=samples,
            error=None,
        )
    except Exception as exc:
        if verbose:
            print(f"Probe failed: {exc}")
        # Preserve a confirmed VISCA completion if settle polling fails later.
        # This keeps autocut mode able to fall back to completion without
        # masking true send/completion-path failures where no completion arrived.
        if saw_completion:
            return ProbeResult(
                preset=preset,
                replies=replies,
                saw_completion=saw_completion,
                settled=False,
                samples=samples,
                error=None,
            )
        return ProbeResult(
            preset=preset,
            replies=replies,
            saw_completion=saw_completion,
            settled=False,
            samples=samples,
            error=str(exc),
        )
    finally:
        sock.close()


def probe_motion(args: argparse.Namespace) -> int:
    result = probe_preset(
        ip=args.ip,
        port=args.port,
        camera_address=args.camera_address,
        preset=args.preset,
        transport=args.transport,
        local_port=args.local_port,
        completion_timeout=args.completion_timeout,
        settle_timeout=args.settle_timeout,
        poll_interval=args.poll_interval,
        stable_count=args.stable_count,
        inquiry_timeout=args.inquiry_timeout,
        include_focus=args.include_focus,
        require_settle=True,
        verbose=True,
    )
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        return 1
    if result.settled:
        return 0
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe AV-1281 preset recall completion and motion settle behavior."
    )
    parser.add_argument(
        "--ip", help="Camera IP address. Falls back to data/settings.json if omitted."
    )
    parser.add_argument(
        "--port",
        type=int,
        help="VISCA port. Defaults to the configured camera port, or 1259 for raw-udp / 52381 for sony-udp.",
    )
    parser.add_argument(
        "--camera-address",
        type=int,
        help="VISCA camera address. Defaults to the configured camera address or 1.",
    )
    parser.add_argument(
        "--preset", type=int, required=True, help="Preset number to recall."
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Index in data/settings.json to use when --ip/--port/--camera-address are omitted.",
    )
    parser.add_argument(
        "--transport",
        choices=("raw-udp", "sony-udp"),
        default="raw-udp",
        help="Packet format to use. AV-1281 setups commonly use raw-udp on port 1259.",
    )
    parser.add_argument(
        "--local-port",
        type=int,
        help="Local UDP port to bind before sending. sony-udp defaults this to the remote port.",
    )
    parser.add_argument(
        "--completion-timeout",
        type=float,
        default=2.0,
        help="Seconds to wait for VISCA ACK/completion before polling position.",
    )
    parser.add_argument(
        "--settle-timeout",
        type=float,
        default=12.0,
        help="Maximum seconds to wait for position to settle.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.25,
        help="Seconds between settle polls.",
    )
    parser.add_argument(
        "--stable-count",
        type=int,
        default=3,
        help="How many identical samples in a row count as settled.",
    )
    parser.add_argument(
        "--inquiry-timeout",
        type=float,
        default=1.0,
        help="Seconds to wait for each inquiry reply.",
    )
    parser.add_argument(
        "--include-focus",
        action="store_true",
        help="Also poll focus and require it to settle along with pan/tilt/zoom.",
    )
    return parser


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    if args.ip and args.port and args.camera_address:
        return args

    config = load_camera_from_settings(args.camera_index)
    if not args.ip:
        args.ip = str(config.get("ip", "")).strip()
    if args.port is None:
        configured_port = config.get("port")
        if configured_port:
            args.port = int(configured_port)
    if args.camera_address is None:
        args.camera_address = int(config.get("viscaAddr", 1) or 1)

    if not args.ip:
        raise ValueError(
            "Camera IP is required. Provide --ip or configure it in data/settings.json."
        )
    if args.port is None:
        args.port = 1259 if args.transport == "raw-udp" else 52381
    if args.camera_address is None:
        args.camera_address = 1
    return args


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args = resolve_args(args)
        return probe_motion(args)
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
