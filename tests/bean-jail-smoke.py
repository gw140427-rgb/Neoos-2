#!/usr/bin/env python3
"""Static smoke checks for the Bean Jail Survival single-file web game."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "docs" / "bean-jail" / "index.html"
HOME = ROOT / "docs" / "index.html"

class GameParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.actions = set()
        self.buy_items = set()
        self.use_items = set()
        self.scripts = []
        self._in_script = False
        self._script_data = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "button":
            if "data-action" in attrs:
                self.actions.add(attrs["data-action"])
            if "data-buy" in attrs:
                self.buy_items.add(attrs["data-buy"])
            if "data-use" in attrs:
                self.use_items.add(attrs["data-use"])
        if tag == "script" and "src" not in attrs:
            self._in_script = True
            self._script_data = []

    def handle_data(self, data):
        if self._in_script:
            self._script_data.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_script:
            self.scripts.append("".join(self._script_data))
            self._in_script = False
            self._script_data = []

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def main():
    require(GAME.is_file(), "Game HTML file is missing.")
    require(HOME.is_file(), "Landing page is missing.")
    html = GAME.read_text(encoding="utf-8")
    home_html = HOME.read_text(encoding="utf-8")
    parser = GameParser()
    parser.feed(html)
    parser.close()

    require('lang="ko"' in html, "Korean document language is missing.")
    require('name="viewport"' in html, "Mobile viewport configuration is missing.")
    require({"eat", "work", "exercise", "read", "clean", "talk", "rest", "shop"} <= parser.actions,
            "One or more main action buttons are missing.")
    require(parser.buy_items == {"snack", "book", "kit"}, "Store purchase buttons are incomplete.")
    require(parser.use_items == {"snack", "book", "kit"}, "Inventory use buttons are incomplete.")
    required_ids = {"dayLine", "turnLine", "moneyLine", "eventCard", "eventChoices",
                    "shopCard", "inventory", "log", "ending", "restart", "resetGame"}
    require(required_ids <= parser.ids, "One or more required UI elements are missing.")
    require('const SAVE_KEY=' in html and 'JSON.parse' in html and 'localStorage' in html,
            "Local save/load implementation is missing.")
    require("brawl:{title:" in html and "콩돌이와 두부" in html,
            "Gang-underlings event is missing.")
    require('id="bean-jail-game-link"' in home_html and 'href="./bean-jail/"' in home_html,
            "Landing page does not link to the game.")
    require(len(parser.scripts) == 1, f"Expected one inline game script; found {len(parser.scripts)}.")
    script = parser.scripts[0]
    require("function validState" in script and "function finishTurnIfNeeded" in script,
            "State validation or turn progression code is missing.")

    # Parse-check the browser script without running browser-only APIs.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as tmp:
            tmp.write(script)
            temp_path = tmp.name
        result = subprocess.run(["node", "--check", temp_path], capture_output=True, text=True)
        if result.returncode:
            sys.stderr.write(result.stdout + result.stderr)
            raise AssertionError("Inline JavaScript failed Node syntax validation.")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    print("PASS: game file, Korean/mobile metadata, actions, store, event, save UI, landing link, and JavaScript syntax.")

if __name__ == "__main__":
    main()
