"""Tests for server.py — VISCA/ATEM/HTTP."""

import http.client
import json
import os
import queue
import shutil
import socket
import struct
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import server


# ── ATEM packet helpers ────────────────────────────────────────────────────────


class TestAtemPackets(unittest.TestCase):
    def test_make_ack_length_and_fields(self):
        pkt = server._make_ack(0x1234, 0x0056)
        self.assertEqual(len(pkt), 12)
        self.assertEqual(pkt[0:2], bytes([0x80, 0x0C]))
        self.assertEqual(struct.unpack(">H", pkt[2:4])[0], 0x1234)
        self.assertEqual(struct.unpack(">H", pkt[4:6])[0], 0x0056)

    def test_make_ack_zero_ids(self):
        pkt = server._make_ack(0, 0)
        self.assertEqual(pkt[2:], bytes(10))

    def test_parse_header_flags_and_seq(self):
        # flags sit in bits 15-11 of word0; flags=1 => word0=0x0800
        word0 = 0x0800
        seq = 42
        data = struct.pack(">H", word0) + bytes(8) + struct.pack(">H", seq)
        flags, seq_num = server._parse_header(data)
        self.assertEqual(flags, 1)
        self.assertEqual(seq_num, 42)

    def test_parse_header_short_returns_zero_seq(self):
        _, seq_num = server._parse_header(bytes(8))
        self.assertEqual(seq_num, 0)

    def test_parse_commands_single(self):
        body = b"\x01\x02\x03\x04"
        cmd_len = 8 + len(body)
        payload = struct.pack(">H", cmd_len) + b"\x00\x00" + b"PrvI" + body
        cmds = list(server._parse_commands(payload))
        self.assertEqual(cmds, [("PrvI", body)])

    def test_parse_commands_two(self):
        def _cmd(name, data):
            cmd_len = 8 + len(data)
            return struct.pack(">H", cmd_len) + b"\x00\x00" + name.encode() + data

        payload = _cmd("PrvI", b"\x00\x01\x00\x02") + _cmd("PrgI", b"\x00\x01\x00\x03")
        cmds = list(server._parse_commands(payload))
        self.assertEqual(len(cmds), 2)
        self.assertEqual(cmds[0][0], "PrvI")
        self.assertEqual(cmds[1][0], "PrgI")

    def test_parse_commands_incm(self):
        cmd_len = 8
        payload = struct.pack(">H", cmd_len) + b"\x00\x00" + b"InCm"
        cmds = list(server._parse_commands(payload))
        self.assertEqual(cmds, [("InCm", b"")])

    def test_parse_commands_truncated_stops(self):
        # cmd_len says 20 but only 10 bytes in payload
        payload = struct.pack(">H", 20) + bytes(8)
        self.assertEqual(list(server._parse_commands(payload)), [])

    def test_parse_commands_empty(self):
        self.assertEqual(list(server._parse_commands(b"")), [])

    def test_cut_atem_to_source_sets_preview_then_cuts(self):
        with (
            patch(
                "server._get_atem",
                return_value={"preview": 3, "program": 2},
            ),
            patch(
                "server._send_atem_command",
                side_effect=[
                    (True, "preview ok"),
                    (True, "cut ok"),
                ],
            ) as mock_send,
            patch(
                "server._wait_for_atem_preview_source",
                return_value=True,
            ) as mock_wait_preview,
            patch(
                "server._wait_for_atem_program_source",
                return_value=True,
            ) as mock_wait,
        ):
            ok, message = server.cut_atem_to_source(7)

        self.assertTrue(ok)
        self.assertIn("Cut executed", message)
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(mock_send.call_args_list[0].args[0], "CPvI")
        self.assertEqual(mock_send.call_args_list[1].args[0], "DCut")
        mock_wait_preview.assert_called_once_with(
            7, timeout_s=server.ATEM_STATE_CONFIRM_TIMEOUT_S
        )
        mock_wait.assert_called_once_with(
            7, timeout_s=server.ATEM_STATE_CONFIRM_TIMEOUT_S
        )

    def test_cut_atem_to_source_falls_back_to_direct_program_switch(self):
        with (
            patch(
                "server._get_atem",
                return_value={"preview": 3, "program": 2},
            ),
            patch(
                "server._send_atem_command",
                side_effect=[
                    (True, "preview ok"),
                    (True, "program ok"),
                ],
            ) as mock_send,
            patch(
                "server._wait_for_atem_preview_source",
                return_value=False,
            ) as mock_wait_preview,
            patch(
                "server._wait_for_atem_program_source",
                return_value=True,
            ) as mock_wait,
        ):
            ok, message = server.cut_atem_to_source(9)

        self.assertTrue(ok)
        self.assertIn("direct program switch", message)
        self.assertEqual(
            [call.args[0] for call in mock_send.call_args_list], ["CPvI", "CPgI"]
        )
        mock_wait_preview.assert_called_once_with(
            9, timeout_s=server.ATEM_STATE_CONFIRM_TIMEOUT_S
        )
        mock_wait.assert_called_once_with(
            9, timeout_s=server.ATEM_STATE_CONFIRM_TIMEOUT_S
        )

    def test_cut_atem_to_source_returns_false_when_program_never_confirms(self):
        with (
            patch(
                "server._get_atem",
                return_value={"preview": 3, "program": 2},
            ),
            patch(
                "server._send_atem_command",
                side_effect=[
                    (True, "preview ok"),
                    (True, "program ok"),
                ],
            ),
            patch(
                "server._wait_for_atem_preview_source",
                return_value=False,
            ),
            patch(
                "server._wait_for_atem_program_source",
                return_value=False,
            ),
        ):
            ok, message = server.cut_atem_to_source(11)

        self.assertFalse(ok)
        self.assertIn("preview or program switched", message)

    def test_cut_atem_to_source_cuts_immediately_when_preview_already_matches(self):
        with (
            patch(
                "server._get_atem",
                return_value={"preview": 12, "program": 2},
            ),
            patch(
                "server._send_atem_command",
                return_value=(True, "cut ok"),
            ) as mock_send,
            patch(
                "server._wait_for_atem_program_source",
                return_value=True,
            ),
        ):
            ok, message = server.cut_atem_to_source(12)

        self.assertTrue(ok)
        self.assertIn("Cut executed", message)
        self.assertEqual([call.args[0] for call in mock_send.call_args_list], ["DCut"])
        self.assertEqual(server._get_atem_last_action()["stage"], "cut-confirm")


# ── ATEM state ─────────────────────────────────────────────────────────────────


class TestAtemState(unittest.TestCase):
    def setUp(self):
        server._set_atem(False, preview=0, program=0)

    def tearDown(self):
        server._set_atem(False, preview=0, program=0)

    def test_set_and_get(self):
        server._set_atem(True, preview=3, program=5)
        state = server._get_atem()
        self.assertTrue(state["connected"])
        self.assertEqual(state["preview"], 3)
        self.assertEqual(state["program"], 5)

    def test_partial_update_preserves_other_fields(self):
        server._set_atem(True, preview=3, program=5)
        server._set_atem(True, preview=7)
        state = server._get_atem()
        self.assertEqual(state["preview"], 7)
        self.assertEqual(state["program"], 5)

    def test_get_returns_copy(self):
        server._set_atem(False, preview=0, program=0)
        s1 = server._get_atem()
        s1["connected"] = True
        s2 = server._get_atem()
        self.assertFalse(s2["connected"])

    def test_threaded_set_get(self):
        errors = []

        def writer():
            for i in range(50):
                server._set_atem(True, preview=i)

        def reader():
            for _ in range(50):
                s = server._get_atem()
                if not isinstance(s["preview"], int):
                    errors.append("bad type")

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertEqual(errors, [])


# ── SSE broadcast ──────────────────────────────────────────────────────────────


class TestBroadcast(unittest.TestCase):
    def setUp(self):
        with server._sse_lock:
            server._sse_clients.clear()

    def tearDown(self):
        with server._sse_lock:
            server._sse_clients.clear()

    def test_delivers_to_single_client(self):
        q = queue.SimpleQueue()
        with server._sse_lock:
            server._sse_clients.append(q)
        server._broadcast({"type": "preview", "source": 3})
        msg = q.get(timeout=1)
        event = json.loads(msg.decode().split("data: ", 1)[1].strip())
        self.assertEqual(event["source"], 3)

    def test_delivers_to_multiple_clients(self):
        queues = [queue.SimpleQueue() for _ in range(3)]
        with server._sse_lock:
            server._sse_clients.extend(queues)
        server._broadcast({"type": "ping"})
        for q in queues:
            msg = q.get(timeout=1)
            self.assertIn(b"ping", msg)

    def test_no_clients_no_error(self):
        server._broadcast({"type": "test"})  # must not raise


# ── Settings I/O ───────────────────────────────────────────────────────────────


class TestSettings(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        images = os.path.join(self.tmpdir, "images")
        settings_f = os.path.join(self.tmpdir, "settings.json")
        self.patches = [
            patch("server.DATA_DIR", self.tmpdir),
            patch("server.IMAGES_DIR", images),
            patch("server.SETTINGS_F", settings_f),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_creates_defaults_when_missing(self):
        result = server.load_settings()
        self.assertIn("cameras", result)
        self.assertEqual(result["activeCam"], 0)
        self.assertTrue(os.path.exists(server.SETTINGS_F))

    def test_write_and_load_roundtrip(self):
        data = {"activeCam": 2, "cameras": [], "labels": {}}
        server.write_settings(data)
        loaded = server.load_settings()
        self.assertEqual(loaded["activeCam"], 2)

    def test_ensure_dirs_creates_images_dir(self):
        server._ensure_dirs()
        self.assertTrue(os.path.isdir(server.IMAGES_DIR))

    def test_write_overwrites_existing(self):
        server.write_settings({"activeCam": 1})
        server.write_settings({"activeCam": 9})
        with open(server.SETTINGS_F) as f:
            stored = json.load(f)
        self.assertEqual(stored["activeCam"], 9)


# ── DEFAULT_SETTINGS schema ────────────────────────────────────────────────────


class TestDefaultSettings(unittest.TestCase):
    REQUIRED = {
        "activeCam",
        "cameras",
        "labels",
        "dwellMs",
        "atem",
        "liveMode",
        "atemFollows",
        "atemSourceLabels",
    }

    def test_required_keys_present(self):
        for key in self.REQUIRED:
            self.assertIn(
                key, server.DEFAULT_SETTINGS, f"DEFAULT_SETTINGS missing {key!r}"
            )

    def test_camera_shape(self):
        cam = server.DEFAULT_SETTINGS["cameras"][0]
        for key in (
            "name",
            "ip",
            "port",
            "viscaAddr",
            "atemInput",
            "streamUrl",
            "usbDevice",
            "enabled",
        ):
            self.assertIn(key, cam)

    def test_default_has_four_cameras(self):
        self.assertEqual(len(server.DEFAULT_SETTINGS["cameras"]), 4)

    def test_atem_shape(self):
        atem = server.DEFAULT_SETTINGS["atem"]
        self.assertIn("ip", atem)
        self.assertIn("enabled", atem)

    def test_atem_source_labels_shape(self):
        self.assertIsInstance(server.DEFAULT_SETTINGS["atemSourceLabels"], dict)

    def test_labels_key_format(self):
        labels = server.DEFAULT_SETTINGS["labels"]
        for key in labels:
            self.assertRegex(
                key, r"^\d+:\d+$", f"label key {key!r} does not match 'cam:preset'"
            )


# ── VISCA packet construction ──────────────────────────────────────────────────


class _NoResponseSocket:
    """Fake socket that accepts sends and times out on recv."""

    def __init__(self):
        self.sent = []

    def settimeout(self, t):
        pass

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def recvfrom(self, n):
        raise socket.timeout()

    def close(self):
        pass


class TestViscaPackets(unittest.TestCase):
    def _recall(self, preset, cam_addr=1, ip="10.0.0.1", port=52381):
        sock = _NoResponseSocket()
        with patch("socket.socket", return_value=sock):
            ok, msg = server.send_visca_preset_recall(ip, port, preset, cam_addr)
        return ok, msg, sock.sent

    def test_no_response_still_returns_ok(self):
        ok, msg, _ = self._recall(5, 1)
        self.assertTrue(ok)
        self.assertIn("no VISCA response", msg)

    def test_header_type_bytes(self):
        _, _, sent = self._recall(0, 1)
        self.assertEqual(sent[0][0][0:2], bytes([0x01, 0x00]))

    def test_payload_length_field(self):
        _, _, sent = self._recall(0, 1)
        pkt = sent[0][0]
        payload_len = struct.unpack(">H", pkt[2:4])[0]
        self.assertEqual(payload_len, 7)

    def test_visca_terminator(self):
        _, _, sent = self._recall(0, 1)
        self.assertEqual(sent[0][0][-1], 0xFF)

    def test_camera_byte_for_various_addresses(self):
        for addr in (1, 2, 7):
            _, _, sent = self._recall(0, addr)
            payload = sent[0][0][8:]
            self.assertEqual(payload[0], 0x80 | addr)

    def test_preset_number_encoded(self):
        for preset in (0, 5, 11, 127):
            _, _, sent = self._recall(preset, 1)
            payload = sent[0][0][8:]
            self.assertEqual(payload[5], preset)

    def test_preset_masked_to_7_bits(self):
        _, _, sent = self._recall(0xFF, 1)
        payload = sent[0][0][8:]
        self.assertEqual(payload[5], 0x7F)

    def test_destination_address(self):
        _, _, sent = self._recall(0, 1, ip="192.168.1.5", port=12345)
        self.assertEqual(sent[0][1], ("192.168.1.5", 12345))

    def test_sequence_number_increments(self):
        _, _, sent1 = self._recall(0, 1)
        _, _, sent2 = self._recall(0, 1)
        seq1 = struct.unpack(">I", sent1[0][0][4:8])[0]
        seq2 = struct.unpack(">I", sent2[0][0][4:8])[0]
        self.assertEqual(seq2, seq1 + 1)

    def test_visca_error_returns_false(self):
        # payload[1] high nibble 0x6 = error
        error_payload = bytes([0x90, 0x60, 0x02, 0xFF])

        class ErrSock(_NoResponseSocket):
            def recvfrom(self, n):
                return bytes(8) + error_payload, ("10.0.0.1", 52381)

        with patch("socket.socket", return_value=ErrSock()):
            ok, msg = server.send_visca_preset_recall("10.0.0.1", 52381, 5, 1)

        self.assertFalse(ok)
        self.assertIn("VISCA error", msg)

    def test_ack_and_completion_reported(self):
        ack = bytes([0x90, 0x41, 0xFF])
        completion = bytes([0x90, 0x51, 0xFF])
        responses = iter([bytes(8) + ack, bytes(8) + completion])

        class AckCompSock(_NoResponseSocket):
            def recvfrom(self, n):
                try:
                    return next(responses), ("10.0.0.1", 52381)
                except StopIteration:
                    raise socket.timeout()

        with patch("socket.socket", return_value=AckCompSock()):
            ok, msg = server.send_visca_preset_recall("10.0.0.1", 52381, 5, 1)

        self.assertTrue(ok)
        self.assertIn("ACK", msg)
        self.assertIn("Completion", msg)


class TestRecallProbeModes(unittest.TestCase):
    def test_confirm_mode_treats_command_send_as_success(self):
        probe_result = SimpleNamespace(
            replies=[],
            saw_completion=False,
            settled=False,
            samples=[],
            error=None,
        )
        with patch("server._probe_preset", return_value=probe_result) as mock_probe:
            payload = server.recall_visca_preset(
                "10.0.0.1", 52381, 4, 1, wait_mode="confirm"
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["message"], "Command sent")
        self.assertEqual(payload["waitMode"], "confirm")
        self.assertFalse(payload["settled"])
        self.assertFalse(payload["sawCompletion"])
        self.assertFalse(mock_probe.call_args.kwargs["require_settle"])

    def test_settle_mode_still_requires_confirmed_stop(self):
        probe_result = SimpleNamespace(
            replies=[],
            saw_completion=True,
            settled=False,
            samples=[],
            error=None,
        )
        with patch("server._probe_preset", return_value=probe_result):
            payload = server.recall_visca_preset(
                "10.0.0.1", 52381, 4, 1, wait_mode="settle"
            )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["message"], "Motion did not settle in time")
        self.assertEqual(payload["waitMode"], "settle")

    def test_autocut_mode_accepts_visca_completion_without_settle(self):
        probe_result = SimpleNamespace(
            replies=[],
            saw_completion=True,
            settled=False,
            samples=[],
            error=None,
        )
        with patch("server._probe_preset", return_value=probe_result):
            payload = server.recall_visca_preset(
                "10.0.0.1", 52381, 4, 1, wait_mode="autocut"
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["message"], "VISCA completion confirmed")
        self.assertEqual(payload["waitMode"], "autocut")


# ── VISCA position inquiry ─────────────────────────────────────────────────────


class TestViscaPosition(unittest.TestCase):
    def _make_response(self, pan: int, tilt: int, cam_addr: int = 1):
        reply_byte = ((cam_addr + 8) << 4) & 0xF0
        # Encode as 4 nibbles (low 4 bits of each byte), big-endian
        pan_bytes = [(pan >> (12 - 4 * i)) & 0x0F for i in range(4)]
        tilt_bytes = [(tilt >> (12 - 4 * i)) & 0x0F for i in range(4)]
        payload = bytes([reply_byte, 0x50] + pan_bytes + tilt_bytes + [0x00, 0xFF])
        return bytes(8) + payload

    def _inquire(self, response_bytes):
        responses = iter([response_bytes])

        class MockSock(_NoResponseSocket):
            def recvfrom(self, n):
                try:
                    return next(responses), ("10.0.0.1", 52381)
                except StopIteration:
                    raise socket.timeout()

        with patch("socket.socket", return_value=MockSock()):
            return server.inquire_visca_pan_tilt_position("10.0.0.1", 52381, 1)

    def test_parse_pan_tilt(self):
        ok, result = self._inquire(self._make_response(0x1234, 0x5678))
        self.assertTrue(ok)
        self.assertEqual(result["pan_hex"], "1234")
        self.assertEqual(result["tilt_hex"], "5678")
        self.assertEqual(result["pan"], 0x1234)
        self.assertEqual(result["tilt"], 0x5678)

    def test_zero_position(self):
        ok, result = self._inquire(self._make_response(0x0000, 0x0000))
        self.assertTrue(ok)
        self.assertEqual(result["pan"], 0)
        self.assertEqual(result["tilt"], 0)

    def test_error_response_returns_false(self):
        # inquire_visca_pan_tilt_position skips payloads shorter than 11 bytes;
        # pad the error response so it passes the length guard.
        reply_byte = 0x90  # cam_addr=1
        error_payload = bytes([reply_byte, 0x60, 0x02]) + bytes(7) + bytes([0xFF])
        ok, msg = self._inquire(bytes(8) + error_payload)
        self.assertFalse(ok)
        self.assertIn("VISCA error", msg)

    def test_no_response_returns_false(self):
        with patch("socket.socket", return_value=_NoResponseSocket()):
            ok, msg = server.inquire_visca_pan_tilt_position("10.0.0.1", 52381, 1)
        self.assertFalse(ok)


# ── _try_record_position unit tests ───────────────────────────────────────────


class TestTryRecordPosition(unittest.TestCase):
    _MOCK_POSITION = {
        "pan": 0xABCD,
        "tilt": 0x1234,
        "zoom": 0x0050,
        "pan_hex": "ABCD",
        "tilt_hex": "1234",
        "zoom_hex": "0050",
        "pan_signed": -0x5433,
        "tilt_signed": 0x1234,
        "transport": "sony-udp",
    }

    def _settings_with_ip(self, ip="10.0.0.1"):
        s = dict(server.DEFAULT_SETTINGS)
        s["cameras"] = [dict(server.DEFAULT_SETTINGS["cameras"][0], ip=ip)]
        s["positions"] = {}
        return s

    def test_returns_none_when_no_ip(self):
        settings = dict(server.DEFAULT_SETTINGS)
        result = server._try_record_position(settings, 0, 1)
        self.assertIsNone(result)

    def test_returns_none_when_cam_out_of_range(self):
        settings = self._settings_with_ip()
        result = server._try_record_position(settings, 99, 1)
        self.assertIsNone(result)

    def test_returns_none_when_inquiry_fails(self):
        settings = self._settings_with_ip()
        with patch(
            "server.inquire_visca_absolute_position", return_value=(False, "timeout")
        ):
            result = server._try_record_position(settings, 0, 1)
        self.assertIsNone(result)

    def test_returns_position_and_updates_settings(self):
        settings = self._settings_with_ip()
        with patch(
            "server.inquire_visca_absolute_position",
            return_value=(True, self._MOCK_POSITION),
        ):
            result = server._try_record_position(settings, 0, 5)

        self.assertIsNotNone(result)
        self.assertEqual(result["pan_hex"], "ABCD")
        self.assertEqual(result["tilt_hex"], "1234")
        self.assertEqual(result["zoom_hex"], "0050")
        self.assertEqual(settings["positions"]["0:5"]["pan_hex"], "ABCD")

    def test_overwrites_existing_position(self):
        settings = self._settings_with_ip()
        settings["positions"] = {
            "0:5": {"pan_hex": "0000", "tilt_hex": "0000", "zoom_hex": "0000"}
        }
        with patch(
            "server.inquire_visca_absolute_position",
            return_value=(True, self._MOCK_POSITION),
        ):
            result = server._try_record_position(settings, 0, 5)
        self.assertEqual(result["pan_hex"], "ABCD")
        self.assertEqual(settings["positions"]["0:5"]["pan_hex"], "ABCD")


# ── HTTP integration ───────────────────────────────────────────────────────────


class _LiveServer:
    """Start a real ThreadedHTTPServer on a free port with an isolated data dir."""

    def __init__(self):
        self.tmpdir = tempfile.mkdtemp()
        images = os.path.join(self.tmpdir, "images")
        settings_f = os.path.join(self.tmpdir, "settings.json")
        self._patches = [
            patch("server.DATA_DIR", self.tmpdir),
            patch("server.IMAGES_DIR", images),
            patch("server.SETTINGS_F", settings_f),
        ]

    def __enter__(self):
        for p in self._patches:
            p.start()
        self.httpd = server.ThreadedHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_address[1]
        t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        t.start()
        return self

    def __exit__(self, *_):
        self.httpd.shutdown()
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ── request helpers ────────────────────────────────────────────────────────

    def _conn(self):
        return http.client.HTTPConnection("127.0.0.1", self.port)

    def get(self, path):
        c = self._conn()
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body

    def get_with_headers(self, path):
        c = self._conn()
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        headers = dict(r.getheaders())
        c.close()
        return r.status, headers, body

    def post(self, path, body=b"", content_type="application/json"):
        c = self._conn()
        c.request(
            "POST",
            path,
            body,
            {"Content-Type": content_type, "Content-Length": str(len(body))},
        )
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body

    def delete(self, path):
        c = self._conn()
        c.request("DELETE", path)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body


class TestHTTPRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = _LiveServer()
        cls.srv.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.srv.__exit__(None, None, None)

    def setUp(self):
        # Reset settings to defaults before each test for isolation.
        # Use a fresh positions dict so TestTryRecordPosition mutation doesn't bleed in.
        """
        Reset persistent test state before each test.
        
        Writes DEFAULT_SETTINGS to the settings file with an empty `positions` dictionary to ensure tests start with a clean configuration, and removes any existing JPEG files from the images directory. File-removal errors are ignored.
        """
        settings = dict(server.DEFAULT_SETTINGS)
        settings["positions"] = {}
        server.write_settings(settings)
        # Clean up any leftover image files from previous tests
        import glob
        for img_file in glob.glob(os.path.join(server.IMAGES_DIR, "*.jpg")):
            try:
                os.remove(img_file)
            except Exception:
                pass

    # ── static & settings ──────────────────────────────────────────────────────

    def test_get_index(self):
        status, body = self.srv.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"html", body)

    def test_get_index_html_variant(self):
        status, _ = self.srv.get("/index.html")
        self.assertEqual(status, 200)

    def test_get_settings_returns_json(self):
        status, body = self.srv.get("/settings")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("cameras", data)

    def test_post_settings_persists(self):
        payload = json.dumps({"activeCam": 2, "cameras": [], "labels": {}}).encode()
        status, body = self.srv.post("/settings", payload)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

        # Reading back must reflect the change
        _, body2 = self.srv.get("/settings")
        self.assertEqual(json.loads(body2)["activeCam"], 2)

    def test_post_settings_bad_json_returns_400(self):
        status, body = self.srv.post("/settings", b"not json")
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(body)["ok"])

    # ── ATEM ───────────────────────────────────────────────────────────────────

    def test_atem_status(self):
        status, body = self.srv.get("/atem/status")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("connected", data)
        self.assertIn("preview", data)
        self.assertIn("program", data)
        self.assertIn("aux4", data)

    def test_atem_debug(self):
        status, body = self.srv.get("/atem/debug")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("state", data)
        self.assertIn("connection", data)
        self.assertIn("last_action", data)
        self.assertIn("sse_clients", data)
        self.assertIn("settings", data)

    # ── recall ─────────────────────────────────────────────────────────────────

    def test_recall_missing_ip_returns_400(self):
        payload = json.dumps({"preset": 1}).encode()
        status, body = self.srv.post("/recall", payload)
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(body)["success"])

    def test_recall_bad_json_returns_400(self):
        status, _ = self.srv.post("/recall", b"not json")
        self.assertEqual(status, 400)

    def test_recall_bad_numeric_returns_400(self):
        payload = json.dumps({"ip": "10.0.0.1", "port": "bad", "preset": 1}).encode()
        status, body = self.srv.post("/recall", payload)
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(body)["success"])

    def test_recall_success_propagates_transport_message(self):
        payload = json.dumps(
            {"ip": "10.0.0.1", "port": 52381, "camera": 1, "preset": 4}
        ).encode()
        with patch(
            "server.recall_visca_preset",
            return_value={
                "success": True,
                "message": "ACK 9041ff • Completion 9051ff • Settled pan 1234 tilt 5678 zoom 00AA",
                "settled": True,
                "sawCompletion": True,
                "position": {
                    "pan_hex": "1234",
                    "tilt_hex": "5678",
                    "zoom_hex": "00AA",
                },
            },
        ) as mock_recall:
            status, body = self.srv.post("/recall", payload)

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["success"])
        self.assertIn("Completion", data["message"])
        self.assertTrue(data["settled"])
        self.assertEqual(data["position"]["zoom_hex"], "00AA")
        mock_recall.assert_called_once_with("10.0.0.1", 52381, 4, 1, "settle")

    def test_recall_failure_propagates_transport_message(self):
        payload = json.dumps(
            {"ip": "10.0.0.1", "port": 52381, "camera": 2, "preset": 6}
        ).encode()
        with (
            patch(
                "server.recall_visca_preset",
                return_value={
                    "success": False,
                    "message": "Motion did not settle in time",
                    "settled": False,
                    "sawCompletion": False,
                    "position": None,
                },
            ) as mock_recall,
            patch.object(server._logger, "warning") as mock_warning,
        ):
            status, body = self.srv.post("/recall", payload)

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertFalse(data["success"])
        self.assertIn("settle", data["message"])
        mock_recall.assert_called_once_with("10.0.0.1", 52381, 6, 2, "settle")
        mock_warning.assert_called_once_with(
            "Recall failed ip=%s port=%s cam=%s preset=%s wait=%s: %s",
            "10.0.0.1",
            52381,
            2,
            6,
            "settle",
            "Motion did not settle in time",
        )

    def test_recall_dwell_mode_passed_through(self):
        payload = json.dumps(
            {
                "ip": "10.0.0.1",
                "port": 1259,
                "camera": 1,
                "preset": 5,
                "waitMode": "dwell",
            }
        ).encode()
        with patch(
            "server.recall_visca_preset",
            return_value={
                "success": True,
                "message": "ACK 9041ff • Manual dwell mode",
                "settled": False,
                "sawCompletion": True,
                "waitMode": "dwell",
                "position": None,
            },
        ) as mock_recall:
            status, body = self.srv.post("/recall", payload)

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["success"])
        self.assertEqual(data["waitMode"], "dwell")
        mock_recall.assert_called_once_with("10.0.0.1", 1259, 5, 1, "dwell")

    def test_recall_confirm_mode_passed_through(self):
        payload = json.dumps(
            {
                "ip": "10.0.0.1",
                "port": 52381,
                "camera": 1,
                "preset": 5,
                "waitMode": "confirm",
            }
        ).encode()
        with patch(
            "server.recall_visca_preset",
            return_value={
                "success": True,
                "message": "Command sent",
                "settled": False,
                "sawCompletion": False,
                "waitMode": "confirm",
                "position": None,
            },
        ) as mock_recall:
            status, body = self.srv.post("/recall", payload)

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["success"])
        self.assertEqual(data["waitMode"], "confirm")
        mock_recall.assert_called_once_with("10.0.0.1", 52381, 5, 1, "confirm")

    def test_recall_autocut_mode_passed_through(self):
        payload = json.dumps(
            {
                "ip": "10.0.0.1",
                "port": 52381,
                "camera": 1,
                "preset": 5,
                "waitMode": "autocut",
            }
        ).encode()
        with patch(
            "server.recall_visca_preset",
            return_value={
                "success": True,
                "message": "VISCA completion confirmed",
                "settled": False,
                "sawCompletion": True,
                "waitMode": "autocut",
                "position": None,
            },
        ) as mock_recall:
            status, body = self.srv.post("/recall", payload)

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["success"])
        self.assertEqual(data["waitMode"], "autocut")
        mock_recall.assert_called_once_with("10.0.0.1", 52381, 5, 1, "autocut")

    # ── image API ──────────────────────────────────────────────────────────────

    def test_image_missing_returns_404(self):
        status, _ = self.srv.get("/api/image/0/99")
        self.assertEqual(status, 404)

    def test_image_upload_retrieve_delete(self):
        server.write_settings(self._settings_with_camera_ip())
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20

        with patch(
            "server.inquire_visca_absolute_position",
            return_value=(True, self._MOCK_POSITION),
        ):
            status, body = self.srv.post("/api/image/0/7", fake_jpeg, "image/jpeg")

        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

        status, data = self.srv.get("/api/image/0/7")
        self.assertEqual(status, 200)
        self.assertEqual(data, fake_jpeg)

        status, body = self.srv.delete("/api/image/0/7")
        self.assertEqual(status, 200)

        status, _ = self.srv.get("/api/image/0/7")
        self.assertEqual(status, 404)

    def test_image_response_is_cacheable(self):
        """
        Verifies that an uploaded image is retrievable and served with correct cache and content-type headers.
        
        Uploads a JPEG for camera 0 preset 3 (with a configured camera IP and a successful VISCA position inquiry), then requests the image and asserts:
        - response status is 200
        - response body equals the uploaded JPEG
        - `Cache-Control` header is "public, max-age=31536000, immutable"
        - `Content-Type` header is "image/jpeg"
        """
        server.write_settings(self._settings_with_camera_ip())
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20

        with patch(
            "server.inquire_visca_absolute_position",
            return_value=(True, self._MOCK_POSITION),
        ):
            status, _ = self.srv.post("/api/image/0/3", fake_jpeg, "image/jpeg")

        self.assertEqual(status, 200)

        status, headers, data = self.srv.get_with_headers("/api/image/0/3")
        self.assertEqual(status, 200)
        self.assertEqual(data, fake_jpeg)
        self.assertEqual(
            headers.get("Cache-Control"),
            "public, max-age=31536000, immutable",
        )
        self.assertEqual(headers.get("Content-Type"), "image/jpeg")

    def test_delete_nonexistent_image_still_200(self):
        status, body = self.srv.delete("/api/image/0/88")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    # ── position ───────────────────────────────────────────────────────────────

    def test_position_unconfigured_ip_returns_400(self):
        # Camera 0 from DEFAULT_SETTINGS has ip=""
        status, body = self.srv.get("/api/position/0")
        self.assertEqual(status, 400)
        data = json.loads(body)
        self.assertFalse(data["ok"])
        self.assertIn("IP", data["error"])

    def test_position_out_of_range_returns_404(self):
        status, body = self.srv.get("/api/position/99")
        self.assertEqual(status, 404)
        self.assertFalse(json.loads(body)["ok"])

    def test_position_success_returns_inquiry_payload(self):
        settings = dict(server.DEFAULT_SETTINGS)
        settings["cameras"] = [
            dict(server.DEFAULT_SETTINGS["cameras"][0], ip="10.0.0.9")
        ]
        server.write_settings(settings)

        with patch(
            "server.inquire_visca_absolute_position",
            return_value=(
                True,
                {
                    "pan": 0x1234,
                    "tilt": 0x5678,
                    "zoom": 0x00AA,
                    "pan_hex": "1234",
                    "tilt_hex": "5678",
                    "zoom_hex": "00AA",
                    "pan_signed": 0x1234,
                    "tilt_signed": 0x5678,
                    "transport": "sony-udp",
                },
            ),
        ) as mock_inquire:
            status, body = self.srv.get("/api/position/0")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["pan_hex"], "1234")
        self.assertEqual(data["tilt_hex"], "5678")
        self.assertEqual(data["zoom_hex"], "00AA")
        expected_port = server.DEFAULT_SETTINGS["cameras"][0]["port"]
        expected_visca_addr = server.DEFAULT_SETTINGS["cameras"][0]["viscaAddr"]
        mock_inquire.assert_called_once_with(
            "10.0.0.9", expected_port, expected_visca_addr
        )

    # ── position recording on capture ──────────────────────────────────────────

    _MOCK_POSITION = {
        "pan": 0x1234,
        "tilt": 0x5678,
        "zoom": 0x00AA,
        "pan_hex": "1234",
        "tilt_hex": "5678",
        "zoom_hex": "00AA",
        "pan_signed": 0x1234,
        "tilt_signed": 0x5678,
        "transport": "sony-udp",
    }

    def _settings_with_camera_ip(self, ip="10.0.0.9"):
        settings = dict(server.DEFAULT_SETTINGS)
        settings["cameras"] = [dict(server.DEFAULT_SETTINGS["cameras"][0], ip=ip)]
        return settings

    def test_post_image_records_position_when_camera_configured(self):
        server.write_settings(self._settings_with_camera_ip())
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20

        with patch(
            "server.inquire_visca_absolute_position",
            return_value=(True, self._MOCK_POSITION),
        ):
            status, body = self.srv.post("/api/image/0/3", fake_jpeg, "image/jpeg")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["position"]["pan_hex"], "1234")
        self.assertEqual(data["position"]["tilt_hex"], "5678")
        self.assertEqual(data["position"]["zoom_hex"], "00AA")

        # Position is persisted in settings
        saved = server.load_settings()
        self.assertEqual(saved["positions"]["0:3"]["pan_hex"], "1234")

    def test_post_image_position_null_when_no_camera_ip(self):
        # DEFAULT_SETTINGS cameras have ip="" — position recording now required before saving image
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20
        status, body = self.srv.post("/api/image/0/3", fake_jpeg, "image/jpeg")
        self.assertEqual(status, 400)
        data = json.loads(body)
        self.assertFalse(data["ok"])
        self.assertIn("could not record camera position", data.get("error", "").lower())
        # Verify image file was not written
        status_img, _ = self.srv.get("/api/image/0/3")
        self.assertEqual(status_img, 404)

    def test_post_image_position_null_when_inquiry_fails(self):
        """
        Ensure uploading an image fails and no file is stored when VISCA position inquiry fails.
        
        Mocks `inquire_visca_absolute_position` to fail, posts a JPEG to the image upload endpoint for camera 0 preset 3, and asserts the server responds with HTTP 400, `ok == False`, an error message mentioning inability to record camera position, and that the image is not present afterwards.
        """
        server.write_settings(self._settings_with_camera_ip())
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20

        with patch(
            "server.inquire_visca_absolute_position",
            return_value=(False, "No VISCA response"),
        ):
            status, body = self.srv.post("/api/image/0/3", fake_jpeg, "image/jpeg")

        self.assertEqual(status, 400)
        data = json.loads(body)
        self.assertFalse(data["ok"])
        self.assertIn("could not record camera position", data.get("error", "").lower())
        # Verify image file was not written
        status_img, _ = self.srv.get("/api/image/0/3")
        self.assertEqual(status_img, 404)

    def test_delete_image_clears_stored_position(self):
        """
        Verifies that deleting an uploaded image removes the stored VISCA position entry for that camera:preset.
        
        Writes settings with a configured camera IP, uploads a fake JPEG while mocking a successful VISCA inquiry so a position is recorded, confirms the position was persisted under "positions" with key "0:5", then deletes the image via the API and asserts the "0:5" entry is removed from stored settings.
        """
        server.write_settings(self._settings_with_camera_ip())
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20

        with patch(
            "server.inquire_visca_absolute_position",
            return_value=(True, self._MOCK_POSITION),
        ):
            self.srv.post("/api/image/0/5", fake_jpeg, "image/jpeg")

        # Confirm position was saved
        self.assertEqual(
            server.load_settings()["positions"].get("0:5", {}).get("pan_hex"), "1234"
        )

        # Delete image
        status, body = self.srv.delete("/api/image/0/5")
        self.assertEqual(status, 200)

        # Position should be cleared
        saved = server.load_settings()
        self.assertNotIn("0:5", saved.get("positions", {}))

    # ── GET /api/image/{cam}/{preset}/position ─────────────────────────────────

    def test_get_image_position_no_data_returns_404(self):
        status, body = self.srv.get("/api/image/0/5/position")
        self.assertEqual(status, 404)
        data = json.loads(body)
        self.assertFalse(data["ok"])

    def test_get_image_position_returns_stored_data(self):
        server.write_settings(self._settings_with_camera_ip())
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20
        with patch(
            "server.inquire_visca_absolute_position",
            return_value=(True, self._MOCK_POSITION),
        ):
            self.srv.post("/api/image/0/5", fake_jpeg, "image/jpeg")

        status, body = self.srv.get("/api/image/0/5/position")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["pan_hex"], "1234")
        self.assertEqual(data["tilt_hex"], "5678")
        self.assertEqual(data["zoom_hex"], "00AA")

    # ── 404 paths ──────────────────────────────────────────────────────────────

    def test_unknown_get_returns_404(self):
        status, _ = self.srv.get("/api/nonexistent")
        self.assertEqual(status, 404)

    def test_static_path_traversal_returns_403(self):
        status, _ = self.srv.get("/../server.py")
        self.assertEqual(status, 403)

    def test_unknown_delete_returns_404(self):
        status, _ = self.srv.delete("/api/nonexistent")
        self.assertEqual(status, 404)

    def test_unknown_post_returns_404(self):
        status, _ = self.srv.post("/api/nonexistent", b"{}")
        self.assertEqual(status, 404)


# ── _normalize_recall_wait_mode ───────────────────────────────────────────────


class TestNormalizeRecallWaitMode(unittest.TestCase):
    def test_returns_settle_for_none(self):
        self.assertEqual(server._normalize_recall_wait_mode(None), "settle")

    def test_returns_settle_for_empty_string(self):
        self.assertEqual(server._normalize_recall_wait_mode(""), "settle")

    def test_returns_settle_for_unknown_string(self):
        self.assertEqual(server._normalize_recall_wait_mode("bogus"), "settle")

    def test_returns_settle_for_settle(self):
        self.assertEqual(server._normalize_recall_wait_mode("settle"), "settle")

    def test_returns_dwell_for_dwell(self):
        self.assertEqual(server._normalize_recall_wait_mode("dwell"), "dwell")

    def test_returns_confirm_for_confirm(self):
        self.assertEqual(server._normalize_recall_wait_mode("confirm"), "confirm")

    def test_returns_autocut_for_autocut(self):
        self.assertEqual(server._normalize_recall_wait_mode("autocut"), "autocut")

    def test_case_sensitive_rejects_uppercase(self):
        # Mode matching is exact; uppercase should fall through to settle
        self.assertEqual(server._normalize_recall_wait_mode("Settle"), "settle")
        self.assertEqual(server._normalize_recall_wait_mode("AUTOCUT"), "settle")


# ── _normalize_scan_wait_mode ─────────────────────────────────────────────────


class TestNormalizeScanWaitMode(unittest.TestCase):
    def test_returns_settle_for_none(self):
        self.assertEqual(server._normalize_scan_wait_mode(None), "settle")

    def test_returns_dwell_for_dwell(self):
        self.assertEqual(server._normalize_scan_wait_mode("dwell"), "dwell")

    def test_returns_settle_for_settle(self):
        self.assertEqual(server._normalize_scan_wait_mode("settle"), "settle")

    def test_rejects_confirm_falls_back_to_settle(self):
        # Scan mode must not accept "confirm" — it would skip motion settling
        self.assertEqual(server._normalize_scan_wait_mode("confirm"), "settle")

    def test_rejects_autocut_falls_back_to_settle(self):
        # Scan mode must not accept "autocut" — it would skip motion settling
        self.assertEqual(server._normalize_scan_wait_mode("autocut"), "settle")

    def test_rejects_unknown_falls_back_to_settle(self):
        self.assertEqual(server._normalize_scan_wait_mode("unknown"), "settle")


# ── capture_usb_device ────────────────────────────────────────────────────────


class TestCaptureUsbDevice(unittest.TestCase):
    def test_macos_avfoundation_prefers_supported_ntsc_framerate_first(self):
        attempted = []

        def fake_grab(args, tmp, log_fail=True):
            attempted.append(args)
            if ["-framerate", "59.940180"] == args[4:6]:
                with open(tmp, "wb") as fh:
                    fh.write(b"jpeg-bytes")
                return True, ""
            return False, "unsupported"

        with (
            patch.object(server, "_IS_MACOS", True),
            patch.object(server, "_HAS_CV2", False),
            patch("server._ffmpeg_grab", side_effect=fake_grab),
        ):
            data = server.capture_usb_device("0")

        self.assertEqual(data, b"jpeg-bytes")
        self.assertGreaterEqual(len(attempted), 1)
        self.assertEqual(attempted[0][4:6], ["-framerate", "59.940180"])


# ── _probe_recall_command_succeeded ──────────────────────────────────────────


class TestProbeRecallCommandSucceeded(unittest.TestCase):
    def _reply(self, kind, payload=b""):
        return SimpleNamespace(kind=kind, payload=payload)

    def test_returns_true_when_no_error_and_no_replies(self):
        result = SimpleNamespace(error=None, replies=[])
        self.assertTrue(server._probe_recall_command_succeeded(result))

    def test_returns_true_with_ack_and_completion_replies(self):
        result = SimpleNamespace(
            error=None,
            replies=[
                self._reply("ack", b"\x90\x41\xff"),
                self._reply("completion", b"\x90\x51\xff"),
            ],
        )
        self.assertTrue(server._probe_recall_command_succeeded(result))

    def test_returns_false_when_error_attr_set(self):
        result = SimpleNamespace(error="socket timeout", replies=[])
        self.assertFalse(server._probe_recall_command_succeeded(result))

    def test_returns_false_when_reply_has_error_kind(self):
        result = SimpleNamespace(
            error=None,
            replies=[self._reply("error", b"\x90\x60\x02\xff")],
        )
        self.assertFalse(server._probe_recall_command_succeeded(result))

    def test_returns_false_when_error_attr_set_even_with_ack(self):
        result = SimpleNamespace(
            error="transport error",
            replies=[self._reply("ack", b"\x90\x41\xff")],
        )
        self.assertFalse(server._probe_recall_command_succeeded(result))

    def test_returns_true_with_only_ack_reply(self):
        result = SimpleNamespace(
            error=None,
            replies=[self._reply("ack", b"\x90\x41\xff")],
        )
        self.assertTrue(server._probe_recall_command_succeeded(result))


# ── _probe_autocut_ready ──────────────────────────────────────────────────────


class TestProbeAutocutReady(unittest.TestCase):
    def test_returns_true_when_settled(self):
        result = SimpleNamespace(
            error=None, replies=[], settled=True, saw_completion=False
        )
        self.assertTrue(server._probe_autocut_ready(result))

    def test_returns_true_when_saw_completion(self):
        result = SimpleNamespace(
            error=None, replies=[], settled=False, saw_completion=True
        )
        self.assertTrue(server._probe_autocut_ready(result))

    def test_returns_true_when_both_settled_and_saw_completion(self):
        result = SimpleNamespace(
            error=None, replies=[], settled=True, saw_completion=True
        )
        self.assertTrue(server._probe_autocut_ready(result))

    def test_returns_false_when_neither_settled_nor_saw_completion(self):
        result = SimpleNamespace(
            error=None, replies=[], settled=False, saw_completion=False
        )
        self.assertFalse(server._probe_autocut_ready(result))

    def test_returns_false_when_error_even_if_settled(self):
        result = SimpleNamespace(
            error="timeout", replies=[], settled=True, saw_completion=True
        )
        self.assertFalse(server._probe_autocut_ready(result))

    def test_returns_false_when_error_is_empty_string(self):
        # error=None is the only "no error" signal; empty string should still fail
        result = SimpleNamespace(
            error="", replies=[], settled=True, saw_completion=True
        )
        # Per implementation: `result.error is None` — empty string is not None
        self.assertFalse(server._probe_autocut_ready(result))


# ── _format_probe_message ─────────────────────────────────────────────────────


class TestFormatProbeMessage(unittest.TestCase):
    def _reply(self, kind, payload=b""):
        return SimpleNamespace(kind=kind, payload=payload)

    def _result(
        self,
        *,
        replies=None,
        settled=False,
        saw_completion=False,
        samples=None,
        error=None,
    ):
        return SimpleNamespace(
            replies=replies or [],
            settled=settled,
            saw_completion=saw_completion,
            samples=samples or [],
            error=error,
        )

    # confirm mode tests
    def test_confirm_no_replies_appends_command_sent(self):
        result = self._result()
        msg = server._format_probe_message(result, "confirm")
        self.assertIn("Command sent", msg)

    def test_confirm_with_ack_omits_command_sent(self):
        # When ACK is present, the "Command sent" branch is skipped (ack is not None)
        result = self._result(replies=[self._reply("ack", b"\x90\x41\xff")])
        msg = server._format_probe_message(result, "confirm")
        self.assertIn("ACK", msg)
        self.assertNotIn("Command sent", msg)

    def test_confirm_with_completion_omits_command_sent(self):
        result = self._result(replies=[self._reply("completion", b"\x90\x51\xff")])
        msg = server._format_probe_message(result, "confirm")
        self.assertIn("Completion", msg)
        self.assertNotIn("Command sent", msg)

    # autocut mode tests
    def test_autocut_saw_completion_no_settle_reports_visca_completion(self):
        result = self._result(saw_completion=True, settled=False)
        msg = server._format_probe_message(result, "autocut")
        self.assertIn("VISCA completion confirmed", msg)

    def test_autocut_neither_settled_nor_completion_reports_not_confirmed(self):
        result = self._result(saw_completion=False, settled=False)
        msg = server._format_probe_message(result, "autocut")
        self.assertIn("Motion stop was not confirmed", msg)

    def test_autocut_error_appended_to_message(self):
        result = self._result(saw_completion=False, settled=False, error="socket error")
        msg = server._format_probe_message(result, "autocut")
        self.assertIn("socket error", msg)

    def test_autocut_with_error_still_includes_not_confirmed(self):
        result = self._result(error="timeout", settled=False, saw_completion=False)
        msg = server._format_probe_message(result, "autocut")
        self.assertIn("Motion stop was not confirmed", msg)
        self.assertIn("timeout", msg)

    # dwell mode tests
    def test_dwell_appends_manual_dwell_mode(self):
        result = self._result()
        msg = server._format_probe_message(result, "dwell")
        self.assertIn("Manual dwell mode", msg)

    # settle mode tests
    def test_settle_not_settled_appends_did_not_settle(self):
        result = self._result(settled=False)
        msg = server._format_probe_message(result, "settle")
        self.assertIn("Motion did not settle in time", msg)

    def test_fallback_returns_visca_recall_completed_when_no_parts(self):
        # Unknown wait_mode with no replies and no error yields fallback message
        result = self._result()
        msg = server._format_probe_message(result, "settle")
        # settle and not settled → "Motion did not settle in time"
        self.assertIn("Motion did not settle in time", msg)


# ── DEFAULT_SETTINGS Camera 4 ─────────────────────────────────────────────────


class TestDefaultSettingsCamera4(unittest.TestCase):
    def _cam4(self):
        cams = server.DEFAULT_SETTINGS["cameras"]
        self.assertEqual(len(cams), 4, "Expected 4 cameras in DEFAULT_SETTINGS")
        return cams[3]

    def test_camera4_name(self):
        self.assertEqual(self._cam4()["name"], "Camera 4")

    def test_camera4_atem_input(self):
        self.assertEqual(self._cam4()["atemInput"], 4)

    def test_camera4_disabled_by_default(self):
        self.assertFalse(self._cam4()["enabled"])

    def test_camera4_has_all_required_keys(self):
        cam = self._cam4()
        for key in (
            "name",
            "ip",
            "port",
            "viscaAddr",
            "atemInput",
            "streamUrl",
            "usbDevice",
            "enabled",
        ):
            self.assertIn(key, cam)

    def test_auto_cut_enabled_removed_from_default_settings(self):
        self.assertNotIn("autoCutEnabled", server.DEFAULT_SETTINGS)


# ── ATEM_STATE_CONFIRM_TIMEOUT_S constant ────────────────────────────────────


class TestAtemStateConfirmTimeout(unittest.TestCase):
    def test_constant_is_2_seconds(self):
        self.assertEqual(server.ATEM_STATE_CONFIRM_TIMEOUT_S, 2.0)

    def test_constant_is_greater_than_old_value(self):
        # Previously hardcoded as 1.0; the PR increased it to 2.0 to give
        # the ATEM switcher more time to confirm state changes.
        self.assertGreater(server.ATEM_STATE_CONFIRM_TIMEOUT_S, 1.0)


# ── Additional recall_visca_preset edge cases ─────────────────────────────────


class TestRecallViscaPresetEdgeCases(unittest.TestCase):
    def _make_probe_result(
        self,
        *,
        settled=False,
        saw_completion=False,
        samples=None,
        error=None,
        replies=None,
    ):
        return SimpleNamespace(
            replies=replies or [],
            saw_completion=saw_completion,
            settled=settled,
            samples=samples or [],
            error=error,
        )

    def test_autocut_mode_accepts_settled_without_completion(self):
        probe_result = self._make_probe_result(settled=True, saw_completion=False)
        with patch("server._probe_preset", return_value=probe_result):
            payload = server.recall_visca_preset(
                "10.0.0.1", 52381, 3, 1, wait_mode="autocut"
            )
        self.assertTrue(payload["success"])
        self.assertEqual(payload["waitMode"], "autocut")

    def test_autocut_mode_fails_when_error_even_if_settled(self):
        probe_result = self._make_probe_result(
            settled=True, saw_completion=True, error="probe error"
        )
        with patch("server._probe_preset", return_value=probe_result):
            payload = server.recall_visca_preset(
                "10.0.0.1", 52381, 3, 1, wait_mode="autocut"
            )
        self.assertFalse(payload["success"])

    def test_autocut_mode_fails_when_neither_settled_nor_completion(self):
        probe_result = self._make_probe_result(settled=False, saw_completion=False)
        with patch("server._probe_preset", return_value=probe_result):
            payload = server.recall_visca_preset(
                "10.0.0.1", 52381, 3, 1, wait_mode="autocut"
            )
        self.assertFalse(payload["success"])
        self.assertIn("not confirmed", payload["message"])

    def test_confirm_mode_fails_when_reply_has_error_kind(self):
        error_reply = SimpleNamespace(kind="error", payload=b"\x90\x60\x02\xff")
        probe_result = self._make_probe_result(replies=[error_reply])
        with patch("server._probe_preset", return_value=probe_result):
            payload = server.recall_visca_preset(
                "10.0.0.1", 52381, 3, 1, wait_mode="confirm"
            )
        self.assertFalse(payload["success"])

    def test_unknown_wait_mode_normalizes_to_settle(self):
        probe_result = self._make_probe_result(settled=True)
        with patch("server._probe_preset", return_value=probe_result):
            payload = server.recall_visca_preset(
                "10.0.0.1", 52381, 1, 1, wait_mode="unknown_mode"
            )
        self.assertEqual(payload["waitMode"], "settle")
        self.assertTrue(payload["success"])

    def test_none_wait_mode_normalizes_to_settle(self):
        probe_result = self._make_probe_result(settled=True)
        with patch("server._probe_preset", return_value=probe_result):
            payload = server.recall_visca_preset(
                "10.0.0.1", 52381, 1, 1, wait_mode=None
            )
        self.assertEqual(payload["waitMode"], "settle")
        self.assertTrue(payload["success"])

    def test_payload_always_includes_wait_mode_key(self):
        for mode in ("settle", "confirm", "autocut", "dwell"):
            probe_result = self._make_probe_result(settled=True, saw_completion=True)
            with patch("server._probe_preset", return_value=probe_result):
                payload = server.recall_visca_preset(
                    "10.0.0.1", 52381, 1, 1, wait_mode=mode
                )
            self.assertIn("waitMode", payload, f"waitMode missing for mode={mode!r}")
            self.assertEqual(payload["waitMode"], mode)

    def test_dwell_mode_sets_require_settle_false(self):
        probe_result = self._make_probe_result()
        with patch("server._probe_preset", return_value=probe_result) as mock_probe:
            server.recall_visca_preset("10.0.0.1", 52381, 1, 1, wait_mode="dwell")
        self.assertFalse(mock_probe.call_args.kwargs["require_settle"])

    def test_autocut_mode_sets_require_settle_false(self):
        probe_result = self._make_probe_result(saw_completion=True)
        with patch("server._probe_preset", return_value=probe_result) as mock_probe:
            server.recall_visca_preset("10.0.0.1", 52381, 1, 1, wait_mode="autocut")
        self.assertFalse(mock_probe.call_args.kwargs["require_settle"])

    def test_settle_mode_sets_require_settle_true(self):
        probe_result = self._make_probe_result(settled=True)
        with patch("server._probe_preset", return_value=probe_result) as mock_probe:
            server.recall_visca_preset("10.0.0.1", 52381, 1, 1, wait_mode="settle")
        self.assertTrue(mock_probe.call_args.kwargs["require_settle"])


if __name__ == "__main__":
    unittest.main()
