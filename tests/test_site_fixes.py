"""Regression checks for the restored, always-working NeoOS site."""
import re
import shutil
import subprocess
import tempfile
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def read(relative):
    return (DOCS / relative).read_text(encoding="utf-8")


def inline_scripts(html):
    pattern = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.S)
    return [m.group("body") for m in pattern.finditer(html) if "src=" not in m.group("attrs")]


class NoMaintenanceLockTests(unittest.TestCase):
    def test_no_page_can_be_blocked_by_a_local_maintenance_flag(self):
        for page in ("index.html", "cloud/index.html", "editor/index.html", "bean-jail/index.html"):
            html = read(page)
            self.assertNotIn("neoos_cloud_service", html, page)
            self.assertNotIn("서버 운영이 일시 종료되었습니다", html, page)
            self.assertNotIn("portalMaintenanceOverlay", html, page)
            self.assertNotIn("maintenanceOverlay", html, page)

    def test_cloud_console_has_no_fake_read_only_gate(self):
        html = read("cloud/index.html")
        self.assertNotIn("CONTROL_ACTIONS_ENABLED", html)
        self.assertNotIn("보안 점검 중 · 배포 일시 중지", html)
        self.assertNotIn("제어 기능은 임시 비활성화", html)
        self.assertIn("const MAX_INSTANCES=4;", html)
        self.assertIn("btn.disabled=full;", html)
        self.assertIn("$('server-name').disabled=false;", html)


class WorkingCloudEngineTests(unittest.TestCase):
    def setUp(self):
        self.html = read("cloud/index.html")

    def test_every_instance_action_is_enabled(self):
        for snippet in (
            "addBtn('💻 터미널','',function(){openWebTerminal(inst);},runable",
            "addBtn('ℹ️ 연결 정보','ghost',function(){openTerminal(inst);},!locked",
            "addBtn('🔄 재부팅','',function(){rebootInstance(inst);},!locked",
            "addBtn('▶️ 시작','',function(){startInstance(inst);},!locked",
            "addBtn('⏹️ 중지','',function(){stopInstance(inst,false);},!locked",
            "addBtn('🗑️ 삭제','danger',function(){terminateInstance(inst);},!locked",
        ):
            self.assertIn(snippet, self.html)

    def test_actions_do_not_require_a_fake_password_gate(self):
        for action in ("rebootInstance", "stopInstance", "startInstance", "terminateInstance", "openWebTerminal"):
            block = re.search(r"function %s\(.*?\n\}" % action, self.html, re.S)
            self.assertIsNotNone(block, action)
            self.assertNotIn("requireAdmin(", block.group(0), action)

    def test_local_engine_implements_real_state_transitions(self):
        for snippet in (
            "async function apiFetch(path,options)",
            "function backendAvailable(result)",
            "function newLocalInstance(payload)",
            "function localStateChange(inst,action)",
            "async function sendAction(inst,action,extra)",
            "function localShell(cmd,inst)",
            "saveInstances(instances)",
            "window.addEventListener('storage'",
        ):
            self.assertIn(snippet, self.html)

    def test_local_terminal_has_a_useful_command_set(self):
        for command in ("help", "whoami", "uname", "ls", "cat", "echo", "df", "free", "ask"):
            self.assertIn("head==='%s'" % command, self.html)

    def test_token_is_never_sent_to_a_foreign_endpoint(self):
        self.assertIn("if(token&&(!base||base===location.origin))", self.html)
        self.assertIn("if(url&&!/^https:\\/\\/[^\\s/]+/i.test(url))", self.html)

    def test_stats_are_not_hardcoded_fake_numbers(self):
        self.assertNotIn("$119.03", self.html)
        self.assertIn('id="credits-value"', self.html)


class GatewayHardeningTests(unittest.TestCase):
    def test_gateway_handles_cors_options_validation_and_content_type(self):
        for path in ("api/instances.js", "docs/api/instances.js"):
            source = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("function cors(res)", source, path)
            self.assertIn("function validCreateBody(text)", source, path)
            self.assertIn("if (method === 'OPTIONS')", source, path)
            self.assertIn("unsupported_media_type", source, path)
            self.assertNotIn("headers['Content-Type'] = (req.headers", source, path)

    def test_root_and_deployed_gateway_match(self):
        self.assertEqual(
            (ROOT / "api/instances.js").read_text(encoding="utf-8"),
            (DOCS / "api/instances.js").read_text(encoding="utf-8"),
        )


class ScriptSyntaxTests(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node") or shutil.which("nodejs")

    def test_inline_scripts_parse(self):
        if not self.node:
            self.skipTest("node is not installed")
        for page in ("index.html", "cloud/index.html", "editor/index.html", "bean-jail/index.html"):
            for index, script in enumerate(inline_scripts(read(page))):
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as handle:
                    handle.write(script)
                    path = handle.name
                try:
                    result = subprocess.run([self.node, "--check", path], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, "%s script %d: %s" % (page, index, result.stderr))
                finally:
                    os.unlink(path)


if __name__ == "__main__":
    unittest.main()
