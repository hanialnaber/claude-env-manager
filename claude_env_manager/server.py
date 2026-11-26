"""Local-only web server for the UI.

Security model (see README):
- Binds to 127.0.0.1 only.
- Every API call needs a random per-run token sent in a custom header. The
  token reaches the page in the URL fragment, which browsers never send to
  servers, and the page drops it from the address bar on load.
- The Host header must be 127.0.0.1/localhost on our port (blocks DNS rebinding).
- No CORS headers, so other websites can't read responses or send the header.
- No request logging, no telemetry, no outbound network calls.
- API responses are sent with Cache-Control: no-store.
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from . import __version__, core

UI_DIR = Path(__file__).parent / "ui"
MAX_BODY = 256 * 1024


class State:
    def __init__(self, project: Optional[Path]):
        self.project = project.resolve() if project else None
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()


def _project_from(body_or_query: dict, state: State) -> Optional[Path]:
    raw = body_or_query.get("project")
    if raw is None:
        return state.project
    raw = str(raw).strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_dir():
        raise core.SettingsError("That project folder doesn't exist.")
    return p.resolve()


def _scope_json(s: core.Scope) -> dict:
    is_shell = s.id == "shell"
    return {
        "id": s.id,
        "label": s.label,
        "path": str(s.path) if s.path else None,
        "writable": s.writable,
        "exists": s.exists,
        "description": s.description,
        "warning": s.warning,
        "error": s.error,
        "vars": [
            {
                "name": n,
                "masked": core.mask(v),
                "length": len(v),
                "secret": core.is_secret_name(n),
                "notes": [] if is_shell else core.name_notes(n, s.id),
            }
            for n, v in sorted(s.env.items(), key=lambda kv: kv[0].lower())
        ],
    }


def _res_json(r: core.Resolution) -> dict:
    return {
        "name": r.name,
        "present": r.present,
        "source": r.source,
        "length": r.length,
        "shadowed": r.shadowed,
        "secret": r.secret,
    }


def make_handler(state: State, port_ref: dict):
    class Handler(BaseHTTPRequestHandler):
        server_version = "claude-env-manager"
        sys_version = ""

        def log_message(self, *args):  # never log requests (paths or bodies)
            return

        # ---- helpers -------------------------------------------------
        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            port = port_ref["port"]
            return host in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _send(self, code: int, body: bytes, ctype: str, extra: Optional[dict] = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                "style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict):
            self._send(code, json.dumps(obj).encode(), "application/json; charset=utf-8")

        def _authed(self) -> bool:
            got = self.headers.get("X-CEM-Token", "")
            return hmac.compare_digest(got.encode(), state.token.encode())

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise core.SettingsError("Request too large.")
            if (self.headers.get("Content-Type") or "").split(";")[0] != "application/json":
                raise core.SettingsError("Expected JSON.")
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw or b"{}")
            if not isinstance(data, dict):
                raise core.SettingsError("Expected a JSON object.")
            return data

        # ---- routes --------------------------------------------------
        def do_GET(self):
            if not self._host_ok():
                return self._send(421, b"Misdirected request", "text/plain")
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                path = "/index.html"
            if path.startswith("/api/"):
                return self._json(405, {"error": "Use POST."})
            target = (UI_DIR / path.lstrip("/")).resolve()
            if UI_DIR.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"Not found", "text/plain")
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, target.read_bytes(), ctype)

        def do_POST(self):
            if not self._host_ok():
                return self._send(421, b"Misdirected request", "text/plain")
            if not self._authed():
                return self._json(403, {"error": "Missing or wrong session token. Open the link printed in your terminal."})
            route = self.path.split("?", 1)[0]
            try:
                body = self._body()
                with state.lock:
                    result = self._dispatch(route, body)
                self._json(200, result)
            except core.SettingsError as exc:
                self._json(400, {"error": str(exc)})
            except json.JSONDecodeError:
                self._json(400, {"error": "Bad JSON."})
            except OSError as exc:
                # Path and reason only; never values.
                self._json(500, {"error": f"Couldn't write the file: {exc.strerror or 'OS error'}."})

        def _dispatch(self, route: str, body: dict) -> dict:
            project = _project_from(body, state)
            if route == "/api/state":
                scopes = core.build_scopes(project)
                return {
                    "version": __version__,
                    "project": str(project) if project else "",
                    "scopes": [_scope_json(s) for s in scopes],
                    "effective": [_res_json(r) for r in core.effective(scopes)],
                }
            if route == "/api/set":
                name = str(body.get("name", "")).strip()
                value = body.get("value", "")
                scope_id = str(body.get("scope", ""))
                path = core.set_var(scope_id, name, value, project)
                return {"ok": True, "path": str(path), "notes": core.name_notes(name, scope_id)}
            if route == "/api/delete":
                path = core.delete_var(str(body.get("scope", "")), str(body.get("name", "")), project)
                return {"ok": True, "path": str(path)}
            if route == "/api/reveal":
                scopes = core.build_scopes(project)
                return {"value": core.reveal_value(scopes, str(body.get("scope", "")), str(body.get("name", "")))}
            if route == "/api/check":
                name = str(body.get("name", "")).strip()
                core.validate_name(name)
                scopes = core.build_scopes(project)
                r = core.resolve(scopes, name)
                out = _res_json(r)
                out["notes"] = core.name_notes(name, r.source)
                out["snippet"] = core.check_snippet(name)
                return out
            if route == "/api/export":
                names = body.get("names") or []
                if not isinstance(names, list) or not names:
                    raise core.SettingsError("Pick at least one variable.")
                scopes = core.build_scopes(project)
                return {"dotenv": core.export_dotenv(scopes, [str(n) for n in names])}
            if route == "/api/quit":
                httpd = port_ref.get("httpd")
                if httpd is not None:
                    threading.Thread(target=httpd.shutdown, daemon=True).start()
                return {"ok": True}
            if route == "/api/snippet":
                return {"snippet": core.check_snippet(str(body.get("name", "")).strip())}
            raise core.SettingsError("Unknown action.")

    return Handler


def _say(msg: str) -> None:
    # Windowed desktop builds may have no console; never fail on output.
    try:
        print(msg, flush=True)
    except Exception:
        pass


def serve(project: Optional[Path], port: int = 0, open_browser: bool = True) -> None:
    state = State(project)
    port_ref = {"port": port}
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state, port_ref))
    port_ref["port"] = httpd.server_address[1]
    port_ref["httpd"] = httpd
    url = f"http://127.0.0.1:{port_ref['port']}/#token={state.token}"
    _say("Claude Env Manager is running on this machine only.")
    _say(f"Open: {url}")
    _say("Press Ctrl+C (or Quit in the app) to stop. Nothing is sent anywhere, and nothing is logged.")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        _say("Stopped.")
