"""Run with: python3 -m unittest discover -s tests  (no dependencies). Uses fake values only."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_env_manager import core  # noqa: E402


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = root / "home" / ".claude"
        self.project = root / "repo"
        self.project.mkdir()
        self._old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.cfg)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._old
        self.tmp.cleanup()

    def scopes(self, shell=None):
        return core.build_scopes(self.project, process_env=shell or {})

    def test_set_preserves_other_keys_and_is_private(self):
        path = self.cfg / "settings.json"
        self.cfg.mkdir(parents=True)
        path.write_text(json.dumps({"model": "x", "permissions": {"allow": ["Bash(ls)"]}}))
        core.set_var("user", "FAL_KEY", "fake-123", self.project)
        data = json.loads(path.read_text())
        self.assertEqual(data["model"], "x")
        self.assertEqual(data["permissions"]["allow"], ["Bash(ls)"])
        self.assertEqual(data["env"]["FAL_KEY"], "fake-123")

    def test_new_file_is_owner_only(self):
        p = core.set_var("local", "FAL_KEY", "fake", self.project)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)

    def test_precedence_and_shadowing(self):
        core.set_var("user", "FAL_KEY", "fake-user", self.project)
        core.set_var("project", "FAL_KEY", "fake-proj", self.project)
        core.set_var("local", "FAL_KEY", "fake-local-longer", self.project)
        r = core.resolve(self.scopes({"FAL_KEY": "fake-shell"}), "FAL_KEY")
        self.assertEqual(r.source, "local")
        self.assertEqual(r.shadowed, ["project", "user", "shell"])
        self.assertEqual(r.length, len("fake-local-longer"))

    def test_settings_beat_shell(self):
        core.set_var("user", "A", "fake-settings", self.project)
        r = core.resolve(self.scopes({"A": "fake-shell"}), "A")
        self.assertEqual(r.source, "user")

    def test_shell_only_and_missing(self):
        sc = self.scopes({"ONLY_SHELL": "x"})
        self.assertEqual(core.resolve(sc, "ONLY_SHELL").source, "shell")
        self.assertFalse(core.resolve(sc, "NOPE").present)

    def test_delete_removes_empty_env(self):
        core.set_var("project", "A", "1", self.project)
        core.delete_var("project", "A", self.project)
        data = json.loads((self.project / ".claude" / "settings.json").read_text())
        self.assertNotIn("env", data)
        with self.assertRaises(core.SettingsError):
            core.delete_var("project", "A", self.project)

    def test_bad_names_and_readonly_scopes(self):
        for bad in ["", "1ABC", "A-B", "A B", "A=B"]:
            with self.assertRaises(core.SettingsError):
                core.set_var("user", bad, "v", self.project)
        for scope in ["managed", "shell", "nope"]:
            with self.assertRaises(core.SettingsError):
                core.set_var(scope, "A", "v", self.project)

    def test_invalid_json_not_overwritten_and_not_echoed(self):
        self.cfg.mkdir(parents=True)
        path = self.cfg / "settings.json"
        path.write_text('{"env": {"FAL_KEY": "fake-SECRET-VALUE"},,}')
        with self.assertRaises(core.SettingsError) as ctx:
            core.set_var("user", "B", "v", self.project)
        self.assertNotIn("fake-SECRET-VALUE", str(ctx.exception))
        self.assertIn("fake-SECRET-VALUE", path.read_text())  # untouched
        user = [s for s in self.scopes() if s.id == "user"][0]
        self.assertIsNotNone(user.error)
        self.assertNotIn("fake-SECRET-VALUE", user.error)

    def test_mask_never_leaks(self):
        for v in ["abc", "x" * 50, "sk-fake-1234567890"]:
            self.assertNotIn(v[:3], core.mask(v).replace("•", ""))

    def test_export_dotenv_quotes(self):
        core.set_var("user", "SIMPLE", "fake123", self.project)
        core.set_var("user", "SPACEY", 'has space "q"', self.project)
        out = core.export_dotenv(self.scopes(), ["SIMPLE", "SPACEY"])
        self.assertIn("SIMPLE=fake123\n", out)
        self.assertIn('SPACEY="has space \\"q\\""', out)
        with self.assertRaises(core.SettingsError):
            core.export_dotenv(self.scopes(), ["MISSING"])

    def test_notes(self):
        self.assertTrue(core.name_notes("OTEL_EXPORTER", "project"))
        self.assertFalse(core.name_notes("OTEL_EXPORTER", "user"))
        self.assertTrue(core.name_notes("CLAUDECODE", "user"))

    def test_check_snippet_never_prints_value(self):
        s = core.check_snippet("FAL_KEY")
        self.assertIn("len(v)", s)
        self.assertNotIn("print(v", s)


if __name__ == "__main__":
    unittest.main()
