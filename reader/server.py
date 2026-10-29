"""Local server for the FM26 Moneyball tool.

    python server.py            then open http://127.0.0.1:8626

GET /                 the tool
GET /api/status       is the game running, which build, in-game date
GET /api/players      every player with minutes (?scope=competitive|league|all|cups|continental,
                      ?all=1 to also include players with no minutes yet (profile only),
                      ?rescan=1 to rebuild the player list)

Listens on 127.0.0.1 only. Reads the game's memory read-only.
"""
import json
import os
import random
import struct
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from export import to_row
from fm26 import SCOPES, Game
from sanity import KNOWN_BUILDS, check

PORT = 8626
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_NAME = "FM26 Moneyball.html"


def page_path() -> str:
    """The tool page: bundled inside the exe, else next to the reader folder."""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), PAGE_NAME)
    return os.path.join(HERE, "..", PAGE_NAME)


PAGE = page_path()


class Live:
    """One attached Game, re-created when the game restarts or the save changes."""

    def __init__(self):
        self.g: Game | None = None
        self.lock = threading.Lock()

    def _attach(self):
        if self.g:
            try:
                self.g.close()
            except OSError:
                pass
        self.g = Game()

    def _healthy(self) -> bool:
        """Cached player addresses still point at players (same process, same save)?"""
        g = self.g
        if not g or g._players is None:
            return False
        try:
            if g.p.read(g.build.module.base, 2) != b"MZ":
                return False
            sample = random.sample(g._players, min(200, len(g._players)))
            ok = sum(g.p.u64(a) == g.player_vt and g.p.u32(a + 0x0C) == g.p.u32(a + 0x10) for a in sample)
            return ok >= 0.98 * len(sample)
        except (OSError, struct.error, TypeError):
            return False

    def status(self):
        with self.lock:
            try:
                if not self.g:
                    self._attach()
                return {"ok": True, "pid": self.g.p.pid, "build": self.g.build.id,
                        "build_known": self.g.build.id in KNOWN_BUILDS}
            except Exception as e:  # game not running, access denied, unknown build
                self.g = None
                return {"ok": False, "error": str(e)}

    def players(self, scope: str, rescan: bool, everyone: bool = False):
        with self.lock:
            t0 = time.time()
            for attempt in range(2):
                try:
                    if not self.g:
                        self._attach()
                    if rescan or not self._healthy():
                        self.g.players(refresh=True)
                    today, raw = self.g.read_all(scope, require_minutes=not everyone)
                    rows = [to_row(r) for r in raw]
                    rows.sort(key=lambda r: not r.get("Mins"))  # full rows first: the page reads columns from row 0
                    played = sum(1 for r in rows if r.get("Mins"))
                    warnings = check(rows, self.g.build.id)
                    return {"ok": True, "build": self.g.build.id, "warnings": warnings,
                            "date": today.isoformat() if today else None,
                            "scope": scope, "players": len(self.g.players()), "count": len(rows),
                            "played": played, "everyone": everyone,
                            "seconds": round(time.time() - t0, 1), "rows": rows}
                except Exception as e:
                    traceback.print_exc()
                    self.g = None  # re-attach once (game restarted?)
                    if attempt:
                        return {"ok": False, "error": str(e)}


LIVE = Live()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s  %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # allow the page when opened straight from disk (file:// sends Origin: null), nothing else
        if self.headers.get("Origin") == "null":
            self.send_header("Access-Control-Allow-Origin", "null")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            try:
                with open(PAGE, "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(404, b"FM26 Moneyball.html not found next to the reader folder", "text/plain")
        elif u.path == "/api/status":
            self._json(LIVE.status())
        elif u.path == "/api/players":
            scope = q.get("scope", ["competitive"])[0]
            if scope not in SCOPES:
                return self._json({"ok": False, "error": f"unknown scope {scope}"}, 400)
            res = LIVE.players(scope, q.get("rescan", ["0"])[0] == "1", q.get("all", ["0"])[0] == "1")
            self._json(res, 200 if res.get("ok") else 503)
        else:
            self._send(404, b"not found", "text/plain")


class Server(ThreadingHTTPServer):
    # Windows lets a second process bind the same port when SO_REUSEADDR is set, and an old copy
    # then keeps answering with old code. Refuse instead, so only one reader ever runs.
    allow_reuse_address = False


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else PORT
    url = f"http://127.0.0.1:{port}/"
    try:
        srv = Server(("127.0.0.1", port), Handler)
    except OSError:
        print(f"The reader is already running at {url} - close its other window first if you updated it.")
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        sys.exit(1)
    print(f"FM26 Moneyball running at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
