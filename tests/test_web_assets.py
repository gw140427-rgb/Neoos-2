"""Static checks for the NeoOS web apps: portal, cloud console, editor, game routes."""
import json
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


def node_binary():
    for name in ("node", "nodejs"):
        found = shutil.which(name)
        if found:
            return found
    local = Path.home() / ".local" / "bin" / "node"
    if local.exists():
        return str(local)
    return None


def inline_scripts(html):
    pattern = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.S)
    return [m.group("body") for m in pattern.finditer(html) if "src=" not in m.group("attrs")]


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.html = read("index.html")

    def test_portal_links_the_three_apps(self):
        for path in ("/cloud", "/editor", "/game"):
            self.assertIn('href="%s"' % path, self.html)

    def test_portal_is_a_clean_three_card_hub(self):
        self.assertIn("NeoOS Cloud", self.html)
        self.assertIn("CapCut Studio", self.html)
        self.assertIn("콩밥 먹기", self.html)
        self.assertEqual(self.html.count('class="app '), 3)

    def test_removed_legacy_sections(self):
        lowered = self.html.lower()
        self.assertNotIn("mcaddon", lowered)
        self.assertNotIn("마인크래프트", self.html)
        self.assertNotIn("jszip", lowered)
        self.assertNotIn("podroid", lowered)
        self.assertNotIn("aws ec2", lowered)

    def test_dark_theme_is_declared(self):
        self.assertIn('name="viewport"', self.html)
        self.assertIn("color-scheme:dark", self.html)


class CloudConsoleTests(unittest.TestCase):
    def setUp(self):
        self.html = read("cloud/index.html")

    def test_identity_and_navigation(self):
        self.assertIn("<title>NeoOS Cloud", self.html)
        self.assertIn("독립형 AI 샌드박스", self.html)
        for path in ('"/cloud"', '"/editor"', '"/game"'):
            self.assertIn(path, self.html)
        self.assertNotIn("Podroid", self.html)
        self.assertNotIn("AWS EC2", self.html)

    def test_admin_gate_default_password_and_session_memory(self):
        self.assertIn("DEFAULT_PASSWORD='neoos2026!'", self.html)
        self.assertIn("sessionStorage.setItem(KEYS.admin", self.html)
        self.assertIn('id="gateInput"', self.html)
        self.assertIn("passwordMatches", self.html)

    def test_maintenance_mode_overlay(self):
        self.assertIn('id="maintenanceOverlay"', self.html)
        self.assertIn("서버가 종료되었습니다.", self.html)
        self.assertIn("관리자(개발자)가 점검을 위해 서비스를 일시 중지했습니다.", self.html)
        self.assertIn("개발자 로그인", self.html)
        self.assertIn("localStorage.setItem(KEYS.service", self.html)
        self.assertIn('id="svcOn"', self.html)
        self.assertIn('id="svcOff"', self.html)

    def test_credit_guardrails_and_expiry(self):
        self.assertIn("MAX_INSTANCES=2", self.html)
        self.assertIn("TTL_MS=24*60*60*1000", self.html)
        self.assertIn("24시간", self.html)
        self.assertIn("만료", self.html)
        self.assertIn("t3.micro", self.html)

    def test_ask_cli_and_railway_quickstart(self):
        self.assertIn("https://raw.githubusercontent.com/gw140427-rgb/ask-cli/main/install.sh", self.html)
        self.assertIn("ssh railway.new", self.html)
        self.assertIn("2 vCPU", self.html)
        self.assertIn("Claude Code", self.html)
        self.assertIn("data-qs=", self.html)

    def test_instances_are_viewable_but_actions_are_gated(self):
        self.assertIn("requireAdmin(", self.html)
        self.assertIn("개발자 인증", self.html)
        # every mutating instance action goes through the gate
        for action in ("rebootInstance", "stopInstance", "startInstance", "terminateInstance"):
            self.assertIn("requireAdmin(", self.html)
            self.assertIn("async function %s(" % action, self.html)

    def test_no_remote_script_tags(self):
        self.assertNotRegex(self.html, r"<script[^>]+src=")


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.html = read("editor/index.html")

    def test_capcut_studio_identity(self):
        self.assertIn("<title>NeoOS 캡컷 스튜디오", self.html)
        self.assertIn("NeoOS CapCut Studio", self.html)
        self.assertIn("color-scheme:dark", self.html)

    def test_preview_timeline_and_upload(self):
        for element_id in ("preview", "playBtn", "timeline", "fileInput", "dropZone"):
            self.assertIn('id="%s"' % element_id, self.html)
        self.assertIn("<canvas", self.html)
        self.assertIn("accept=\"video/*,image/*\"", self.html)

    def test_text_overlay_controls(self):
        self.assertIn('id="addText"', self.html)
        self.assertIn('id="textValue"', self.html)
        self.assertIn('id="textSize"', self.html)
        self.assertIn("drawTexts", self.html)

    def test_filters_and_speeds(self):
        for name in ("normal", "bw", "cyber", "vintage", "sepia"):
            self.assertIn('data-filter="%s"' % name, self.html)
        for speed in ("0.5", "1", "1.5", "2"):
            self.assertIn('data-speed="%s"' % speed, self.html)
        self.assertIn("Cyberpunk Blue", self.html)
        self.assertIn("Vintage Warm", self.html)

    def test_media_recorder_export(self):
        self.assertIn("MediaRecorder", self.html)
        self.assertIn("captureStream(30)", self.html)
        self.assertIn("video/mp4", self.html)
        self.assertIn("video/webm", self.html)
        self.assertIn("a.download", self.html)


class RouteRedirectTests(unittest.TestCase):
    def test_legacy_vps_routes_redirect_to_cloud(self):
        for relative in ("vps/aws.html", "vps/index.html"):
            html = read(relative)
            self.assertIn("../cloud/", html)
            self.assertIn('http-equiv="refresh"', html)

    def test_game_short_route_points_at_the_game(self):
        html = read("game/index.html")
        self.assertIn("../bean-jail/", html)

    def test_vercel_configs_match(self):
        root = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        docs = json.loads((DOCS / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(root, docs)
        rewrites = {item["source"]: item["destination"] for item in root["rewrites"]}
        self.assertEqual(rewrites["/cloud"], "/cloud/index.html")
        self.assertEqual(rewrites["/editor"], "/editor/index.html")
        self.assertEqual(rewrites["/game"], "/bean-jail/index.html")
        redirects = {item["source"]: item["destination"] for item in root["redirects"]}
        self.assertEqual(redirects["/vps/aws.html"], "/cloud")
        self.assertEqual(redirects["/vps"], "/cloud")


class BeanJailV11Tests(unittest.TestCase):
    def setUp(self):
        self.html = read("bean-jail/index.html")

    def test_v11_badge_and_changelog(self):
        self.assertIn("v1.1 양양이 에디션", self.html)
        self.assertIn("v1.1 양양이 에디션 변경점", self.html)

    def test_new_events(self):
        self.assertIn("ai_tip:{title:", self.html)
        self.assertIn("black_market:{title:", self.html)
        self.assertIn("숨겨진 폰", self.html)
        self.assertIn("특가 매점", self.html)

    def test_hidden_hacker_ending(self):
        self.assertIn("천재 해커 조기 출소", self.html)
        self.assertIn("hackerEligible", self.html)
        self.assertIn("state.flags.aiTip", self.html)

    def test_web_audio_sounds(self):
        self.assertIn("AudioContext", self.html)
        self.assertIn("createOscillator", self.html)
        self.assertIn("Sound.coin", self.html)
        self.assertIn("Sound.alert", self.html)
        self.assertIn("soundToggle", self.html)

    def test_double_tap_and_event_guards(self):
        self.assertIn("inputLockedUntil", self.html)
        self.assertIn("lockInput(", self.html)
        self.assertIn("eventReadyAt", self.html)
        self.assertIn("modal-open", self.html)
        # purchases are refused while an event modal is open
        self.assertIn("state.pendingEvent)return;", self.html)

    def test_single_inline_script(self):
        scripts = inline_scripts(self.html)
        self.assertEqual(len(scripts), 1)


class JavaScriptSyntaxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = node_binary()

    def check(self, relative):
        if not self.node:
            self.skipTest("node is not installed")
        html = read(relative)
        for index, script in enumerate(inline_scripts(html)):
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as handle:
                handle.write(script)
                path = handle.name
            try:
                result = subprocess.run([self.node, "--check", path], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, "%s script %d: %s" % (relative, index, result.stderr))
            finally:
                os.unlink(path)

    def test_portal_script(self):
        self.check("index.html")

    def test_cloud_script(self):
        self.check("cloud/index.html")

    def test_editor_script(self):
        self.check("editor/index.html")

    def test_game_script(self):
        self.check("bean-jail/index.html")


if __name__ == "__main__":
    unittest.main()
