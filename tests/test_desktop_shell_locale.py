"""Desktop shell locale mapping for Claude's zh-Hans / zh-Hant catalogs."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patcher", ROOT / "scripts/patch_claude_zh_cn.py")
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

REQUEST = "window.electronIntl?.requestLocaleChange?.(e.locale);"


def make_app(root: Path, source: str = REQUEST) -> Path:
    app = root / "Claude.app"
    assets = app / patcher.FRONTEND_ASSETS_REL
    assets.mkdir(parents=True)
    (assets / "shared-locale.js").write_text(source, encoding="utf-8")
    return app


class DesktopShellLocaleTests(unittest.TestCase):
    def test_shell_locale_mapping(self):
        self.assertEqual(patcher.desktop_shell_locale("zh-CN"), "zh-Hans")
        self.assertEqual(patcher.desktop_shell_locale("zh-TW"), "zh-Hant")
        self.assertEqual(patcher.desktop_shell_locale("zh-HK"), "zh-Hant")
        self.assertEqual(patcher.desktop_shell_locale("en-US"), "en-US")

    def test_request_is_mapped_and_valid_javascript(self):
        updated, count = patcher.replace_shell_locale_request(REQUEST)
        self.assertEqual(count, 1)
        self.assertIn('l==="zh-CN"?"zh-Hans"', updated)
        self.assertIn('l==="zh-TW"||l==="zh-HK"?"zh-Hant"', updated)
        self.assertEqual(patcher.replace_shell_locale_request(updated), (updated, 0))
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "check.js"
            script.write_text(updated, encoding="utf-8")
            subprocess.run(["node", "--check", str(script)], check=True, capture_output=True)

    def test_other_calls_are_untouched(self):
        source = "window.electronIntl?.requestOther?.(e.locale);"
        self.assertEqual(patcher.replace_shell_locale_request(source), (source, 0))

    def test_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(Path(tmp))
            asset = app / patcher.FRONTEND_ASSETS_REL / "shared-locale.js"
            patcher.patch_desktop_shell_locale(app, "zh-CN")
            first = asset.read_text(encoding="utf-8")
            self.assertIn('"zh-Hans"', first)
            patcher.patch_desktop_shell_locale(app, "zh-TW")
            self.assertEqual(asset.read_text(encoding="utf-8"), first)

    def test_missing_request_warns_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(Path(tmp), "const noRequest = 1;")
            asset = app / patcher.FRONTEND_ASSETS_REL / "shared-locale.js"
            before = asset.read_bytes()
            with patch.object(patcher, "log") as log:
                patcher.patch_desktop_shell_locale(app, "zh-CN")
                self.assertIn("WARNING", log.call_args.args[0])
            self.assertEqual(asset.read_bytes(), before)

    def test_official_locale_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(Path(tmp))
            asset = app / patcher.FRONTEND_ASSETS_REL / "shared-locale.js"
            before = asset.read_bytes()
            patcher.patch_desktop_shell_locale(app, "en-US")
            self.assertEqual(asset.read_bytes(), before)

    @unittest.skipUnless(sys.platform == "darwin", "macOS user config layout")
    def test_user_config_uses_shell_catalog_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home / "Library/Application Support/Claude/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"locale": "zh-CN", "keep": 1}), encoding="utf-8")
            with patch.dict(os.environ, {"SUDO_UID": "", "SUDO_GID": ""}):
                patcher.set_user_locale(home, "zh-TW")
            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(data, {"locale": "zh-Hant", "keep": 1})

    @unittest.skipUnless(sys.platform == "darwin", "macOS user config layout")
    def test_restore_still_writes_english(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home / "Library/Application Support/Claude/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"locale": "zh-Hans"}), encoding="utf-8")
            with patch.dict(os.environ, {"SUDO_UID": "", "SUDO_GID": ""}):
                patcher.set_user_locale(home, "en-US")
            self.assertEqual(json.loads(config.read_text(encoding="utf-8"))["locale"], "en-US")


if __name__ == "__main__":
    unittest.main()
