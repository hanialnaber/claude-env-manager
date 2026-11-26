"""End-to-end checks of the local server's security rules. Fake values only."""

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_env_manager import server  # noqa: E402


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["CLAUDE_CONFIG_DIR"] = str(Path(cls.tmp.name) / "cfg")
        cls.project = Path(cls.tmp.name) / "repo"
        cls.project.mkdir()
        cls.state = server.State(cls.project)
        cls.port_ref = {"port": 0}
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(cls.state, cls.port_ref))
        cls.port_ref["port"] = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmp.cleanup()

    def req(self, path, body=None, token=True, host=None, method="POST"):
        c = http.client.HTTPConnection("127.0.0.1", self.port_ref["port"])
        headers = {"Host": host or f"127.0.0.1:{self.port_ref['port']}", "Content-Type": "application/json"}
        if token:
            headers["X-CEM-Token"] = self.state.token
        c.request(method, path, body=json.dumps(body or {}) if method == "POST" else None, headers=headers)
        r = c.getresponse()
        data = r.read()
        return r.status, data, dict(r.getheaders())

    def test_needs_token(self):
        status, _, _ = self.req("/api/state", token=False)
        self.assertEqual(status, 403)

    def test_rejects_foreign_host(self):
        status, _, _ = self.req("/api/state", host="evil.example:80")
        self.assertEqual(status, 421)

    def test_round_trip_and_no_value_in_state(self):
        status, _, _ = self.req("/api/set", {"scope": "local", "name": "FAL_KEY", "value": "fake-value-xyz"})
        self.assertEqual(status, 200)
        status, data, headers = self.req("/api/state")
        self.assertEqual(status, 200)
        self.assertNotIn(b"fake-value-xyz", data)
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        status, data, _ = self.req("/api/check", {"name": "FAL_KEY"})
        out = json.loads(data)
        self.assertTrue(out["present"])
        self.assertEqual(out["source"], "local")
        self.assertNotIn(b"fake-value-xyz", data)
        status, data, _ = self.req("/api/reveal", {"scope": "local", "name": "FAL_KEY"})
        self.assertEqual(json.loads(data)["value"], "fake-value-xyz")

    def test_static_and_traversal(self):
        status, data, headers = self.req("/", method="GET", token=False)
        self.assertEqual(status, 200)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        status, _, _ = self.req("/../core.py", method="GET", token=False)
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
