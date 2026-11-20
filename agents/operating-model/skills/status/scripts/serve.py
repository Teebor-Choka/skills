#!/usr/bin/env python3
"""Serve the organization site on http://127.0.0.1:8765/ (loopback only). Standard library only.

  python3 site/serve.py                       (rungs of an org-root change need PyYAML:
  uv run -q --with pyyaml python site/serve.py  use this form to get them)

GET /                 index.html
GET /<file>           a file under site/ with a known extension; no listing, no dotfiles, no path outside site/
GET /api/refresh      regenerate data/*.json (gen.py) unless the data is under 25 s old; returns meta.json
GET /api/live         the live snapshot: runs read from the ledgers in live-sources.json
GET /api/events       server-sent events: one `run` message per new ledger entry, polled every 0.5 s, and a
                      `build` message after the ingest log grew and the data was generated again
POST /api/ingest      one unit state report (see ingest.py): JSON object, Content-Type application/json, at most
                      4096 bytes, same Host, Origin and Sec-Fetch-Site rules as GET, at most 30 a minute;
                      appended to site/ingest/events.jsonl. 201 with the stored line, 400 bad record, 403 foreign
                      request, 409 broken chain, 411 no length, 413 too large, 415 not JSON, 429 too many
"""
import http.server
import json
import os
import queue
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

SITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SITE))
import live  # noqa: E402
import ingest  # noqa: E402

HOST, PORT = "127.0.0.1", 8765
HOSTS = {"127.0.0.1:%d" % PORT, "localhost:%d" % PORT}
FRESH = 25
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".json": "application/json", ".svg": "image/svg+xml", ".ttf": "font/ttf", ".woff2": "font/woff2",
         ".png": "image/png", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}
HIDDEN = {"serve.py", "gen.py", "check.py", "live.py", "live-sources.json", "ingest.py", "emit.py", "events.jsonl"}
ORIGINS = {"http://" + h for h in HOSTS}
RATE = (30, 60.0)  # ingest: at most 30 reports per 60 s, from every client together


class Refresher:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_err = None

    def meta(self):
        try:
            return json.loads((SITE / "data/meta.json").read_text())
        except (OSError, ValueError):
            return {}

    def age(self):
        return time.time() - float(self.meta().get("generated") or 0)

    def run(self, force=False):
        if not force and self.age() < FRESH and self.meta().get("ingest_seq", 0) >= ingest.read()["seq"]:
            return "fresh"
        if not self.lock.acquire(blocking=False):
            return "busy"  # another tab started it; the page fetches the data again later
        try:
            uv = shutil.which("uv")
            cmd = [uv, "run", "-q", "--with", "pyyaml", "python", "gen.py"] if uv else [sys.executable, "gen.py"]
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            p = subprocess.run(cmd, cwd=SITE, capture_output=True, text=True, timeout=120, env=env)
            self.last_err = None if p.returncode == 0 else (p.stderr.strip().splitlines() or ["exit %d" % p.returncode])[-1][:300]
            return "ok" if p.returncode == 0 else "failed"
        except (OSError, subprocess.SubprocessError) as e:
            self.last_err = str(e)[:300]
            return "failed"
        finally:
            self.lock.release()


class Hub:
    """One poller thread for the ledgers; each event-stream client gets a queue."""

    def __init__(self):
        self.live = live.Live()
        self.lock = threading.Lock()
        self.clients = []
        self.ingest_sig = self.sig()
        with self.lock:
            self.live.poll()
        threading.Thread(target=self.loop, daemon=True).start()
        threading.Thread(target=self.build_loop, daemon=True).start()

    @staticmethod
    def sig():
        try:
            st = ingest.log_path().stat()
            return (st.st_size, st.st_mtime)
        except OSError:
            return None

    def push(self, m):
        for q in list(self.clients):
            try:
                q.put_nowait(m)
            except queue.Full:
                pass

    def build_loop(self):
        """The ingest log grew (a POST, or emit.py writing the file directly): generate the data again, then tell the pages."""
        while True:
            time.sleep(0.5)
            sig = self.sig()
            if sig == self.ingest_sig:
                continue
            res = REFRESH.run(force=True)
            if res == "busy":
                continue  # a refresh is running; it may predate the new line, so try again
            self.ingest_sig = sig
            meta = REFRESH.meta()
            self.push({"build": {"seq": meta.get("ingest_seq"), "hash": meta.get("hash"), "refresh": res}})

    def loop(self):
        while True:
            time.sleep(0.5)
            try:
                with self.lock:
                    evs = self.live.poll()
                    runs = {r.id: r for r in self.live.runs.values()}
                    msgs = []
                    for ev in evs:
                        r = runs[ev["run"]]
                        m = {"event": ev, "run": r.snapshot(events=20) if r.workflow else None}
                        if ev.get("kind") == "org.metric":
                            m["metrics"] = self.live.metrics()
                        msgs.append(m)
            except Exception as e:  # noqa: BLE001  a bad ledger must not stop the stream
                msgs = [{"error": str(e)[:300]}]
            for m in msgs:
                self.push(m)

    def snapshot(self):
        with self.lock:
            return self.live.snapshot()


class Bucket:
    """Rate cap for POST /api/ingest: a token bucket shared by every client."""

    def __init__(self, n, per):
        self.n, self.per, self.tokens, self.t, self.lock = n, per, float(n), time.monotonic(), threading.Lock()

    def take(self):
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.n, self.tokens + (now - self.t) * self.n / self.per)
            self.t = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True


REFRESH = Refresher()
HUB = None
BUCKET = Bucket(*RATE)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "orgsite"
    sys_version = ""

    def log_message(self, fmt, *args):
        if "/api/events" not in (self.path or ""):
            sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send(self, code, body, ctype="text/plain; charset=utf-8", extra=None):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def do_HEAD(self):
        self.do_GET()

    def foreign(self):
        """Why this request is refused as coming from elsewhere, or None."""
        if self.headers.get("Host", "") not in HOSTS:
            return "forbidden: unknown Host header\n"
        if self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            return "forbidden: request from another site\n"  # stops a foreign page reading data.js or posting
        if self.headers.get("Origin") is not None and self.headers.get("Origin") not in ORIGINS:
            return "forbidden: foreign Origin\n"
        return None

    def do_POST(self):
        bad = self.foreign()
        if bad:
            return self.send(403, bad)
        if urllib.parse.urlsplit(self.path).path != "/api/ingest":
            return self.send(404, "not found\n")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self.send(415, "Content-Type must be application/json\n")  # a cross-site form cannot send it without a preflight
        try:
            n = int(self.headers.get("Content-Length") or "")
        except ValueError:
            return self.send(411, "Content-Length required\n")
        if n < 0 or n > ingest.MAX_BODY:
            self.close_connection = True
            return self.send(413, "body larger than %d bytes\n" % ingest.MAX_BODY)
        body = self.rfile.read(n)
        if not BUCKET.take():
            return self.send(429, "too many reports, at most %d per %d s\n" % RATE, extra={"Retry-After": "5"})
        try:
            rec = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self.send(400, "body is not JSON\n")
        try:
            line = ingest.append(rec, "http")
        except ValueError as e:
            return self.send(400, "bad report: %s\n" % e)
        except ingest.ChainBroken as e:
            return self.send(409, "%s\n" % e)
        return self.send(201, json.dumps(line), "application/json")

    def do_GET(self):
        bad = self.foreign()
        if bad:
            return self.send(403, bad)
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/refresh":
            res = REFRESH.run()
            try:
                meta = json.loads((SITE / "data/meta.json").read_text())
            except (OSError, ValueError):
                meta = {}
            meta.update(refresh=res, error=REFRESH.last_err if res == "failed" else None)
            return self.send(200, json.dumps(meta), "application/json")
        if path == "/api/live":
            return self.send(200, json.dumps(HUB.snapshot(), default=str), "application/json")
        if path == "/api/events":
            return self.events()
        return self.file(path)

    def file(self, path):
        rel = urllib.parse.unquote(path)
        if rel in ("", "/"):
            rel = "/index.html"
        parts = [p for p in rel.split("/") if p]
        if any(p.startswith(".") for p in parts) or "\\" in rel or "\x00" in rel:
            return self.send(404, "not found\n")
        target = (SITE / "/".join(parts)).resolve()
        if not target.is_relative_to(SITE) or not target.is_file() or target.name in HIDDEN:
            return self.send(404, "not found\n")
        ctype = TYPES.get(target.suffix.lower())
        if not ctype:
            return self.send(404, "not found\n")
        return self.send(200, target.read_bytes(), ctype)

    def events(self):
        q = queue.Queue(maxsize=500)
        HUB.clients.append(q)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                try:
                    m = q.get(timeout=15)
                    self.wfile.write(("data: %s\n\n" % json.dumps(m, default=str)).encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            HUB.clients.remove(q)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    global HUB
    try:
        srv = Server((HOST, PORT), Handler)
    except OSError as e:
        sys.exit("serve.py: cannot listen on %s:%d (%s). Is another serve.py running?" % (HOST, PORT, e.strerror))
    HUB = Hub()
    if not (SITE / "data/meta.json").exists():
        print("generating data first ...", REFRESH.run())
    print("serving %s on http://%s:%d/ (Ctrl-C stops)" % (SITE, HOST, PORT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
