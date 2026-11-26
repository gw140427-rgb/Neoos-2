"""Tests for the Podroid VPS panel: slots, isolation flags, TTL and the terminal."""
import http.client
import json
import re
import subprocess
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import podroid_vps_server

TOKEN = "t" * 40
AUTH = {"Authorization": "Bearer " + TOKEN}


def done(cmd, stdout="", stderr="", code=0):
    return subprocess.CompletedProcess(cmd, code, stdout, stderr)


def row(
    cid="aaaabbbbcccc",
    name="guest-one",
    state="running",
    image="alpine:latest",
    ports="0.0.0.0:8101->80/tcp",
    labels="neoos.managed=guest,neoos.expires_at=2000000000",
):
    return [cid, name, state, image, "2 minutes ago", "Up 2 minutes", ports, labels]


class FakeDocker:
    """Stands in for `subprocess.run`, so no Docker is needed to test."""

    def __init__(self, rows=None, stats=None, exec_code=0, exec_out="ok\n", exec_err="", exec_error=None):
        self.rows = [list(item) for item in (rows or [])]
        self.stats = stats or {}
        self.exec_code = exec_code
        self.exec_out = exec_out
        self.exec_err = exec_err
        self.exec_error = exec_error
        self.calls = []
        self.fail_on = set()

    def __call__(self, cmd, **kwargs):
        if kwargs.get("shell"):
            raise AssertionError("docker must never run through a shell")
        if cmd[0] != "docker":
            raise AssertionError("unexpected binary: %s" % cmd[0])
        self.calls.append(list(cmd))
        verb = cmd[1]
        if verb in self.fail_on:
            raise subprocess.CalledProcessError(1, cmd, output="", stderr="boom")
        if verb == "ps":
            return done(cmd, "\n".join("|".join(item) for item in self.rows))
        if verb == "stats":
            lines = ["%s|%s|%s" % (cid, value["cpu"], value["mem"]) for cid, value in self.stats.items()]
            return done(cmd, "\n".join(lines))
        if verb == "run":
            name = cmd[cmd.index("--name") + 1]
            mapping = cmd[cmd.index("-p") + 1]
            labels = ",".join(cmd[index + 1] for index, item in enumerate(cmd) if item == "--label")
            image = next((part for part in cmd if part in set(podroid_vps_server.OS_IMAGES.values())), "alpine:latest")
            host_port = mapping.split(":")[-2]
            self.rows.append(
                [
                    "c0ffee123456",
                    name,
                    "running",
                    image,
                    "1 second ago",
                    "Up 1 second",
                    "127.0.0.1:%s->80/tcp" % host_port,
                    labels,
                ]
            )
            return done(cmd, "c0ffee1234567890\n")
        if verb in {"start", "stop", "restart", "pause", "unpause"}:
            target = cmd[2]
            states = {
                "start": "running", "restart": "running", "unpause": "running",
                "stop": "exited", "pause": "paused",
            }
            for item in self.rows:
                if item[1] == target:
                    item[2] = states[verb]
            return done(cmd)
        if verb == "logs":
            return done(cmd, "guest started\\n")
        if verb == "rm":
            target = cmd[-1]
            self.rows = [item for item in self.rows if item[1] != target]
            return done(cmd)
        if verb == "exec":
            if self.exec_error:
                raise self.exec_error
            return done(cmd, self.exec_out, self.exec_err, self.exec_code)
        raise AssertionError("unexpected docker verb: %s" % verb)


class PodroidPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), podroid_vps_server.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.server.server_address
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method="GET", path="/api/instances", body=None, headers=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
        payload = json.dumps(body).encode() if body is not None else None
        merged = dict(headers or {})
        if payload is not None:
            merged.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=payload, headers=merged)
        response = conn.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        conn.close()
        return result

    def panel(self, fake, token=TOKEN, max_containers=4):
        return mock.patch.multiple(
            podroid_vps_server,
            TOKEN=token,
            MAX_CONTAINERS=max_containers,
            subprocess=mock.Mock(run=fake, SubprocessError=subprocess.SubprocessError,
                                 CompletedProcess=subprocess.CompletedProcess,
                                 CalledProcessError=subprocess.CalledProcessError,
                                 TimeoutExpired=subprocess.TimeoutExpired),
        )

    def authed(self, method="GET", path="/api/instances", body=None, headers=None):
        merged = dict(headers or {})
        merged.update(AUTH)
        return merged

    # -- health & auth ------------------------------------------------------
    def test_health_is_public_and_minimal(self):
        status, _, body = self.request(path="/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok", "provider": "podroid"})

    def test_listing_requires_the_bearer_token(self):
        fake = FakeDocker([row()])
        with self.panel(fake):
            for token in (None, "wrong-token"):
                headers = {"Authorization": "Bearer " + token} if token else {}
                status, _, body = self.request(headers=headers)
                self.assertEqual(status, 401, token)
                self.assertEqual(json.loads(body)["error"], "unauthorized")
            self.assertEqual(fake.calls, [])
            status, _, _ = self.request(headers=AUTH)
        self.assertEqual(status, 200)

    def test_missing_token_fails_closed_even_on_private_networks(self):
        fake = FakeDocker([row()])
        with self.panel(fake, token=""):
            status, _, body = self.request()
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["error"], "server_token_not_configured")
        self.assertEqual(fake.calls, [])

    # -- listing ------------------------------------------------------------
    def test_listing_merges_stats_ports_and_capacity(self):
        fake = FakeDocker(
            rows=[row(), row(cid="ddddeeeeffff", name="box", ports="", labels="")],
            stats={"aaaabbbbcccc": {"cpu": "2.34%", "mem": "12MiB / 256MiB"}},
        )
        with self.panel(fake):
            status, _, body = self.request(headers=AUTH)
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["capacity"], {"used": 1, "max": 4})
        self.assertEqual(payload["containers"], 2)
        first, second = payload["instances"]
        self.assertEqual(first["cpu"], "2.34%")
        self.assertEqual(first["mem"], "12MiB / 256MiB")
        self.assertEqual(first["ports"], "8101->80/tcp")
        self.assertFalse(first["protected"])
        self.assertTrue(first["isReal"])
        self.assertEqual(second["cpu"], "—")
        self.assertTrue(second["protected"])
        self.assertIn("stats", " ".join(call[1] for call in fake.calls))

    def test_listing_survives_a_stats_failure(self):
        fake = FakeDocker([row()], stats={"aaaabbbbcccc": {"cpu": "1%", "mem": "8MiB / 256MiB"}})
        fake.fail_on = {"stats"}
        with self.panel(fake):
            status, _, body = self.request(headers=AUTH)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["instances"][0]["cpu"], "—")

    def test_docker_unavailable_is_a_clean_503_or_500(self):
        fake = FakeDocker([row()])
        fake.fail_on = {"ps"}
        with self.panel(fake):
            status, _, body = self.request(headers=AUTH)
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body)["error"], "docker_error")

    # -- creation -----------------------------------------------------------
    def test_create_applies_isolation_limits_labels_and_a_port(self):
        fake = FakeDocker()
        with self.panel(fake):
            status, _, body = self.request(
                "POST",
                "/api/instances",
                {"name": "guest-two", "os": "alpine", "instance_type": "t3.micro", "volume_gb": 8},
                headers=self.authed(),
            )
        payload = json.loads(body)
        self.assertEqual(status, 202, body)
        self.assertEqual(payload["instance"]["name"], "guest-two")
        self.assertEqual(payload["instance"]["ports"], "8101->80/tcp")
        self.assertEqual(payload["capacity"], {"used": 1, "max": 4})
        run = [call for call in fake.calls if call[1] == "run"][0]
        for flag in (
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory=256m",
            "--cpus=0.5",
            "--pids-limit=64",
        ):
            self.assertIn(flag, run, flag)
        self.assertEqual(run[run.index("-p") + 1], "127.0.0.1:8101:80")
        self.assertIn("neoos.managed=guest", run)
        expires = [item for item in run if item.startswith("neoos.expires_at=")][0]
        self.assertAlmostEqual(int(expires.split("=", 1)[1]), int(time.time()) + 1800, delta=5)

    def test_create_picks_the_next_free_port(self):
        fake = FakeDocker([row(ports="0.0.0.0:8101->80/tcp")])
        with self.panel(fake):
            status, _, body = self.request(
                "POST", "/api/instances", {"name": "guest-two", "os": "debian"}, headers=self.authed()
            )
        self.assertEqual(status, 202, body)
        run = [call for call in fake.calls if call[1] == "run"][0]
        self.assertEqual(run[run.index("-p") + 1], "127.0.0.1:8102:80")

    def test_full_capacity_returns_429(self):
        rows = [row(cid="id000000000%d" % index, name="guest-%d" % index, ports="") for index in range(4)]
        fake = FakeDocker(rows)
        with self.panel(fake):
            status, _, body = self.request(
                "POST", "/api/instances", {"name": "guest-five", "os": "ubuntu"}, headers=self.authed()
            )
        payload = json.loads(body)
        self.assertEqual(status, 429)
        self.assertEqual(payload["error"], "capacity_full")
        self.assertEqual(payload["message"], "현재 서버 슬롯이 가득 찼습니다. 잠시 후 다시 시도해 주세요.")
        self.assertFalse([call for call in fake.calls if call[1] == "run"])

    def test_create_rejects_bad_names_and_images(self):
        fake = FakeDocker()
        cases = [
            ({"name": "-rm-rf", "os": "alpine"}, 400, "invalid_name"),
            ({"name": "x", "os": "alpine"}, 400, "invalid_name"),
            ({"name": "ok_name", "os": "windows"}, 400, "unsupported_os"),
        ]
        with self.panel(fake):
            for body, code, error in cases:
                status, _, payload = self.request(
                    "POST", "/api/instances", body, headers=self.authed()
                )
                self.assertEqual(status, code, body)
                self.assertEqual(json.loads(payload)["error"], error, body)
        self.assertFalse([call for call in fake.calls if call[1] == "run"])

    # -- lifecycle ----------------------------------------------------------
    def test_start_stop_reboot_pause_and_resume_on_a_guest(self):
        fake = FakeDocker([row()])
        with self.panel(fake):
            for action, verb in (
                ("start", "start"), ("stop", "stop"), ("reboot", "restart"),
                ("pause", "pause"), ("unpause", "unpause")
            ):
                status, _, body = self.request(
                    "POST", "/api/instances/aaaabbbbcccc/%s" % action, {}, headers=self.authed()
                )
                self.assertEqual(status, 202, action)
                self.assertEqual(json.loads(body)["action"], action)
        verbs = [call[1] for call in fake.calls]
        self.assertEqual(verbs, ["ps", "start", "ps", "stop", "ps", "restart", "ps", "pause", "ps", "unpause"])

    def test_unmanaged_and_prefix_containers_cannot_be_started_stopped_or_rebooted(self):
        fake = FakeDocker([row(name="box", labels=""), row(name="user-vps-7", labels="neoos.managed=guest")])
        with self.panel(fake):
            for name in ("box", "user-vps-7"):
                for action in ("start", "stop", "reboot"):
                    status, _, body = self.request(
                        "POST", "/api/instances/%s/%s" % (name, action), {}, headers=self.authed()
                    )
                    self.assertEqual(status, 403, (name, action))
                    self.assertEqual(json.loads(body)["error"], "protected_container")
        self.assertFalse([call for call in fake.calls if call[1] in {"start", "stop", "restart"}])

    def test_delete_refuses_protected_and_removes_guests(self):
        fake = FakeDocker(
            [
                row(name="box", labels="neoos.managed=guest"),      # protected by name
                row(cid="111122223333", name="legacy", labels=""),   # not ours
                row(cid="444455556666", name="guest-two"),
            ]
        )
        with self.panel(fake):
            for name in ("box", "legacy"):
                status, _, body = self.request("DELETE", "/api/instances/%s" % name, headers=AUTH)
                self.assertEqual(status, 403, name)
                self.assertEqual(json.loads(body)["error"], "protected_container")
            status, _, _ = self.request("DELETE", "/api/instances/guest-two", headers=AUTH)
            self.assertEqual(status, 202)
        self.assertIn(["docker", "rm", "-f", "guest-two"], fake.calls)

    def test_unknown_actions_and_paths_are_blocked(self):
        fake = FakeDocker([row()])
        with self.panel(fake):
            for path, code in (
                ("/api/instances/aaaabbbbcccc/kill", 404),
                ("/api/instances/aaaabbbbcccc", 405),
                ("/nope", 404),
            ):
                status, _, body = self.request("POST", path, {}, headers=self.authed())
                self.assertEqual(status, code, path)
                if code == 404:
                    self.assertEqual(json.loads(body)["error"], "not_found")
            status, _, _ = self.request("PUT", "/api/instances/aaaabbbbcccc/stop", headers=self.authed())
            self.assertEqual(status, 405)
        self.assertFalse([call for call in fake.calls if call[1] in {"kill", "restart"}])

    # -- web terminal -------------------------------------------------------
    def test_exec_returns_output_and_exit_code(self):
        fake = FakeDocker([row()], exec_code=0, exec_out="Linux podroid\n", exec_err="")
        with self.panel(fake):
            status, _, body = self.request(
                "POST", "/api/instances/aaaabbbbcccc/exec", {"cmd": "uname -a"}, headers=self.authed()
            )
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["stdout"], "Linux podroid\n")
        self.assertEqual(payload["exit_code"], 0)
        self.assertEqual(payload["stderr"], "")
        exec_call = [call for call in fake.calls if call[1] == "exec"][0]
        self.assertEqual(exec_call, ["docker", "exec", "guest-one", "sh", "-c", "uname -a"])

    def test_exec_reports_a_non_zero_exit(self):
        error = subprocess.CalledProcessError(127, "docker", output="", stderr="sh: nope: not found\n")
        fake = FakeDocker([row()], exec_error=error)
        with self.panel(fake):
            status, _, body = self.request(
                "POST", "/api/instances/aaaabbbbcccc/exec", {"cmd": "nope"}, headers=self.authed()
            )
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["exit_code"], 127)
        self.assertIn("not found", payload["stderr"])

    def test_exec_timeout_is_a_504(self):
        error = subprocess.TimeoutExpired("docker", 10, output="partial\n")
        fake = FakeDocker([row()], exec_error=error)
        with self.panel(fake):
            status, _, body = self.request(
                "POST", "/api/instances/aaaabbbbcccc/exec", {"cmd": "sleep 60"}, headers=self.authed()
            )
        payload = json.loads(body)
        self.assertEqual(status, 504)
        self.assertEqual(payload["error"], "exec_timeout")
        self.assertEqual(payload["stdout"], "partial\n")

    def test_exec_output_is_capped(self):
        fake = FakeDocker([row()], exec_out="x" * 20000)
        with self.panel(fake):
            status, _, body = self.request(
                "POST", "/api/instances/aaaabbbbcccc/exec", {"cmd": "cat big"}, headers=self.authed()
            )
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(payload["truncated"])
        self.assertLessEqual(len(payload["stdout"]), 8192 + 40)

    def test_exec_rejects_empty_or_stopped(self):
        fake = FakeDocker([row(state="exited")])
        with self.panel(fake):
            status, _, body = self.request(
                "POST", "/api/instances/aaaabbbbcccc/exec", {"cmd": "   "}, headers=self.authed()
            )
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)["error"], "invalid_command")
            status, _, body = self.request(
                "POST", "/api/instances/aaaabbbbcccc/exec", {"cmd": "ls"}, headers=self.authed()
            )
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["error"], "container_not_running")

    def test_exec_needs_the_token(self):
        fake = FakeDocker([row()])
        with self.panel(fake):
            status, _, _ = self.request("POST", "/api/instances/aaaabbbbcccc/exec", {"cmd": "ls"})
        self.assertEqual(status, 401)
        self.assertFalse([call for call in fake.calls if call[1] == "exec"])

    def test_exec_cannot_reach_unmanaged_containers(self):
        fake = FakeDocker([row(name="box", labels="")])
        with self.panel(fake):
            status, _, body = self.request(
                "POST", "/api/instances/box/exec", {"cmd": "id"}, headers=self.authed()
            )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "protected_container")
        self.assertFalse([call for call in fake.calls if call[1] == "exec"])

    def test_guest_logs_are_available_but_system_logs_are_protected(self):
        fake = FakeDocker([row(), row(name="box", labels="")])
        with self.panel(fake):
            status, _, body = self.request("GET", "/api/instances/guest-one/logs", headers=AUTH)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["logs"], "guest started\\n")
            status, _, body = self.request("GET", "/api/instances/box/logs", headers=AUTH)
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "protected_container")

    # -- TTL ----------------------------------------------------------------
    def test_cleanup_removes_only_expired_guests(self):
        now = 1_000_000
        fake = FakeDocker(
            [
                row(cid="expired00001", name="old-guest", labels="neoos.managed=guest,neoos.expires_at=999990"),
                row(cid="fresh0000001", name="new-guest", labels="neoos.managed=guest,neoos.expires_at=1000600"),
                row(cid="legacy000001", name="legacy", labels=""),
                row(cid="box000000001", name="box", labels="neoos.managed=guest,neoos.expires_at=1"),
                row(cid="prefix000001", name="user-vps-2", labels="neoos.managed=guest,neoos.expires_at=1"),
            ]
        )
        with self.panel(fake):
            removed = podroid_vps_server.cleanup_expired_containers(now=now)
        self.assertEqual(removed, ["old-guest"])
        removals = [call for call in fake.calls if call[1] == "rm"]
        self.assertEqual(removals, [["docker", "rm", "-f", "old-guest"]])

    def test_cleanup_survives_a_docker_failure(self):
        fake = FakeDocker()
        fake.fail_on = {"ps"}
        with self.panel(fake):
            self.assertEqual(podroid_vps_server.cleanup_expired_containers(now=time.time()), [])

    def test_listing_reports_ttl_left(self):
        now = int(time.time())
        fake = FakeDocker([row(labels="neoos.managed=guest,neoos.expires_at=%d" % (now + 600))])
        with self.panel(fake):
            status, _, body = self.request(headers=AUTH)
        instance = json.loads(body)["instances"][0]
        self.assertEqual(status, 200)
        self.assertEqual(instance["managed"], "guest")
        self.assertGreater(instance["ttl_seconds"], 500)
        self.assertLessEqual(instance["ttl_seconds"], 600)

    # -- CORS ---------------------------------------------------------------
    def test_cors_echoes_vercel_and_local_origins_only(self):
        fake = FakeDocker([row()])
        with self.panel(fake):
            for origin in ("https://neoos-2.vercel.app", "http://localhost:3000", "http://127.0.0.1:5500"):
                status, headers, _ = self.request(headers=dict(AUTH, Origin=origin))
                self.assertEqual(status, 200, origin)
                self.assertEqual(headers.get("Access-Control-Allow-Origin"), origin)
                self.assertEqual(headers.get("Vary"), "Origin")
            status, headers, _ = self.request(headers=dict(AUTH, Origin="https://evil.example"))
            self.assertEqual(status, 200)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            status, headers, _ = self.request("OPTIONS", headers={"Origin": "https://evil.example"})
            self.assertEqual(status, 403)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            status, headers, _ = self.request("OPTIONS", headers={"Origin": "http://localhost:8080"})
            self.assertEqual(status, 204)
            self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://localhost:8080")

    # -- source guardrails --------------------------------------------------
    def test_source_never_uses_a_shell(self):
        source = Path(podroid_vps_server.__file__).read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("eval(", source)
        self.assertIsNone(re.search(r"/api/instances/.*\$\{", source))
        self.assertIn("--cap-drop=ALL", source)
        self.assertIn("no-new-privileges", source)
        self.assertIn("capacity_full", source)
        self.assertIn("neoos.managed=guest", source)


if __name__ == "__main__":
    unittest.main()
