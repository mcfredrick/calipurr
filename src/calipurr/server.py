"""The local viewer's server. It only ever listens on this computer.

Browsers will send requests to localhost on behalf of any website, so requests
must name this server as their Host, and writes must come from its own page.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import kitten, profiles, purrflight
from .errors import Hiss, NeedsConfirmation
from .project import Project

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".stl": "model/stl",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
BUILD_TIMEOUT_S = 300
MAX_BODY_BYTES = 1_000_000


class Rebuilder:
    """Runs the user's --build command after a value changes, one run at a time."""

    def __init__(self, command: str | None, cwd: Path):
        self.argv = shlex.split(command) if command else None
        self.cwd = cwd
        self.lock = threading.Lock()
        self.pending = False
        self.running = False
        self.state: dict = {"configured": bool(command), "running": False, "ok": None, "output": ""}

    def request(self) -> None:
        if not self.argv:
            return
        with self.lock:
            self.pending = True
            if self.running:
                return
            self.running = True
            self.state["running"] = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while True:
            with self.lock:
                if not self.pending:
                    self.running = False
                    self.state["running"] = False
                    return
                self.pending = False
            try:
                done = subprocess.run(
                    self.argv, cwd=self.cwd, capture_output=True, text=True, timeout=BUILD_TIMEOUT_S
                )
                ok, output = done.returncode == 0, done.stdout + done.stderr
            except (OSError, subprocess.TimeoutExpired) as err:
                ok, output = False, str(err)
            with self.lock:
                self.state.update(ok=ok, output=output[-4000:])


class App:
    def __init__(self, project: Project, build: str | None = None):
        self.project = project
        self.rebuilder = Rebuilder(build, project.root)
        self.check_cache: dict = {}

    def state(self) -> dict:
        machines = {}
        for name in profiles.litter():
            profile = profiles.load(name)
            machines[name] = {"kind": profile["kind"], "fields": profile["fields"]}
        return {
            "project": self.project.root.name,
            "root": str(self.project.root),
            "next": self.project.next_step(),
            "lurking": self.project.lurking(),
            "handed": self.project.handed(),
            "params": self.project.params(),
            "dots": self.project.dots(),
            "files": self.project.files(),
            "kittens": kitten.kittens(self.project),
            "lives": self.project.lives(),
            "discarded": self.project.discarded(),
            "machines": machines,
            "build": self.rebuilder.state,
        }

    def check(self, file: str, machine: str | None) -> dict:
        path = self.project.resolve_file(file)
        if path.suffix.lower() != ".stl":
            raise Hiss("Pre-flight checks run on STL models")
        profile = profiles.load(machine) if machine else None
        key = (file, path.stat().st_mtime, machine, json.dumps(profile, sort_keys=True))
        if key not in self.check_cache:
            self.check_cache = {key: purrflight.run(path, machine, profile)}
        return self.check_cache[key]

    def post(self, route: str, body: dict) -> dict:
        project = self.project
        if route == "/api/params":
            value = body.get("value")
            if value in (None, ""):
                result = project.forget(body["key"])
            else:
                result = project.answer(body["key"], value, body.get("status", "measured"), body.get("note"))
            self.rebuilder.request()
            return result
        if route == "/api/bell":
            project.ring()
            return {}
        if route == "/api/dots":
            return project.add_dot(body["file"], body["position"], body.get("text", ""))
        if route == "/api/dots/edit":
            project.edit_dot(int(body["id"]), body["text"])
            return {}
        if route == "/api/dots/remove":
            project.remove_dot(int(body["id"]))
            return {}
        if route == "/api/kitten/gauge":
            return kitten.make_gauge(
                project,
                body["from"],
                body["to"],
                body["step"],
                kind=body.get("kind", "plug"),
                labels=body.get("labels", True),
                target=body.get("for"),
            )
        if route == "/api/kitten/report":
            result = kitten.report(
                project,
                body["name"],
                body["letter"],
                body["measured"],
                material=body.get("material") or None,
                machine=body.get("machine") or None,
                note=body.get("note") or None,
                confirm=bool(body.get("confirm")),
            )
            if result["for"]:
                self.rebuilder.request()
            return result
        if route == "/api/litter/discard":
            return {"file": project.discard(body["file"])}
        if route == "/api/litter/rescue":
            return {"file": project.rescue(body["file"])}
        if route == "/api/lives/restore":
            project.restore_life(str(body["id"]))
            self.rebuilder.request()
            return {}
        if route == "/api/machine/feed":
            value = body.get("value")
            return profiles.feed(body["name"], body["key"], str(value), body.get("status", "measured"), body.get("note"))
        raise Hiss(f"Unknown request {route}")


def _handler(app: App, port_holder: dict) -> type[BaseHTTPRequestHandler]:
    web = resources.files("calipurr") / "web"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002
            pass

        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # The browser left mid-download, as it does on a reload.
                pass

        def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def _allowed_hosts(self) -> set[str]:
            port = port_holder["port"]
            return {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _host_ok(self) -> bool:
            if self.headers.get("Host") in self._allowed_hosts():
                return True
            self._json({"error": "Requests must come through this computer's own address."}, HTTPStatus.FORBIDDEN)
            return False

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return
            url = urlparse(self.path)
            try:
                if url.path == "/api/state":
                    self._json(app.state())
                elif url.path == "/api/check":
                    query = parse_qs(url.query)
                    self._json(app.check(query["file"][0], query.get("machine", [None])[0]))
                elif url.path.startswith("/file/"):
                    path = app.project.resolve_file(unquote(url.path[len("/file/") :]))
                    self._send(HTTPStatus.OK, path.read_bytes(), CONTENT_TYPES[path.suffix.lower()])
                else:
                    self._static(url.path)
            except (Hiss, KeyError) as err:
                self._json({"error": str(err)}, HTTPStatus.NOT_FOUND)

        def _static(self, route: str) -> None:
            parts = [p for p in unquote(route).split("/") if p] or ["index.html"]
            if any(p.startswith(".") for p in parts):
                raise Hiss("Not found")
            target = web.joinpath(*parts)
            suffix = Path(parts[-1]).suffix
            if suffix not in CONTENT_TYPES or not target.is_file():
                raise Hiss("Not found")
            self._send(HTTPStatus.OK, target.read_bytes(), CONTENT_TYPES[suffix])

        def do_POST(self):  # noqa: N802
            if not self._host_ok():
                return
            origin = self.headers.get("Origin")
            if origin is None or origin.removeprefix("http://") not in self._allowed_hosts():
                self._json({"error": "Changes must come from Calipurr's own page."}, HTTPStatus.FORBIDDEN)
                return
            if self.headers.get_content_type() != "application/json":
                self._json({"error": "Send JSON."}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._json({"error": "That request is too large."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                self._json({"result": app.post(urlparse(self.path).path, body)})
            except NeedsConfirmation as err:
                self._json({"error": str(err), "needs_confirmation": True}, HTTPStatus.CONFLICT)
            except KeyError as err:
                self._json({"error": f"Missing {err}"}, HTTPStatus.BAD_REQUEST)
            except (Hiss, ValueError, TypeError) as err:
                self._json({"error": str(err)}, HTTPStatus.BAD_REQUEST)

    return Handler


def make_server(project: Project, port: int = 0, build: str | None = None) -> ThreadingHTTPServer:
    holder: dict = {}
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(App(project, build), holder))
    holder["port"] = server.server_address[1]
    return server
