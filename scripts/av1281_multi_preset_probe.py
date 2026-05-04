#!/usr/bin/env python3
"""Run the AV-1281 motion probe across multiple presets."""

from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import av1281_motion_probe as probe  # noqa: E402


def parse_preset_spec(text: str) -> list[int]:
    presets: list[int] = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            step = 1 if end >= start else -1
            presets.extend(range(start, end + step, step))
        else:
            presets.append(int(chunk))
    if not presets:
        raise ValueError("At least one preset is required.")
    return presets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe multiple AV-1281 presets and report VISCA completion/settle results."
    )
    parser.add_argument(
        "--presets",
        required=True,
        help="Comma-separated preset list and/or ranges, for example: 1,3,5-9",
    )
    parser.add_argument("--ip", help="Camera IP address. Falls back to data/settings.json if omitted.")
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
        "--pause-between",
        type=float,
        default=0.5,
        help="Seconds to wait between preset tests.",
    )
    parser.add_argument(
        "--include-focus",
        action="store_true",
        help="Also poll focus and require it to settle along with pan/tilt/zoom.",
    )
    parser.add_argument(
        "--quiet-per-preset",
        action="store_true",
        help="Suppress detailed sample output and print only the summary lines.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args = probe.resolve_args(args)
        presets = parse_preset_spec(args.presets)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Testing presets {presets} on {args.ip}:{args.port} "
        f"using {args.transport} (camera address {args.camera_address})."
    )

    passed = 0
    results: list[probe.ProbeResult] = []

    for index, preset in enumerate(presets, start=1):
        print()
        print(f"=== Preset {preset} ({index}/{len(presets)}) ===")
        result = probe.probe_preset(
            ip=args.ip,
            port=args.port,
            camera_address=args.camera_address,
            preset=preset,
            transport=args.transport,
            local_port=args.local_port,
            completion_timeout=args.completion_timeout,
            settle_timeout=args.settle_timeout,
            poll_interval=args.poll_interval,
            stable_count=args.stable_count,
            inquiry_timeout=args.inquiry_timeout,
            include_focus=args.include_focus,
            verbose=not args.quiet_per_preset,
        )
        results.append(result)

        ack_seen = any(reply.kind == "ack" for reply in result.replies)
        completion_seen = any(reply.kind == "completion" for reply in result.replies)
        last_sample = result.samples[-1].format() if result.samples else "no samples"

        if result.error:
            status = "ERROR"
        elif result.settled:
            status = "PASS"
            passed += 1
        else:
            status = "TIMEOUT"

        print(
            f"Summary: {status}  ack={ack_seen}  completion={completion_seen}  "
            f"samples={len(result.samples)}  last={last_sample}"
        )

        if index < len(presets) and args.pause_between > 0:
            time.sleep(args.pause_between)

    print()
    print(f"Passed {passed}/{len(results)} presets.")
    if passed != len(results):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
