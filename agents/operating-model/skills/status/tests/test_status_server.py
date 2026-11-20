"""The server, started in-process on a free loopback port: what it serves, what it refuses, and the ingest endpoint."""

import http.client
import json
import shutil
import threading

import pytest

from status_testlib import FIXTURE, fixture_argv, load

pytest.importorskip("yaml", reason="the server generates the data with gen.py, which needs PyYAML")


@pytest.fixture
def site(tmp_path):
    data_dir = tmp_path / "state"
    (data_dir / "ingest").mkdir(parents=True)
    shutil.copy(FIXTURE / "ingest.jsonl", data_dir / "ingest" / "events.jsonl")
    (data_dir / "secret.txt").write_text("not for the web\n")
    assert load("gen").main(fixture_argv(data_dir)) == 0
    serve = load("serve")
    srv = serve.make_server(serve.parse(fixture_argv(data_dir) + ["--port", "0"]))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    srv.data_dir = data_dir
    yield srv
    srv.shutdown()
    srv.server_close()


def request(srv, method, path, body=None, headers=None, host=None):
    port = srv.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    c.putheader("Host", host or "127.0.0.1:%d" % port)
    for k, v in (headers or {}).items():
        c.putheader(k, v)
    if body is not None:
        c.putheader("Content-Length", str(len(body)))
    c.endheaders()
    if body is not None:
        c.send(body)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


def test_binds_loopback_only(site):
    assert site.server_address[0] == "127.0.0.1"


@pytest.mark.parametrize("path,code", [
    ("/", 200), ("/index.html", 200), ("/css/site.css", 200), ("/js/app.js", 200), ("/fonts/atkinson-next-var.ttf", 200),
    ("/data/data.js", 200), ("/data/org.json", 200), ("/api/live", 200),
    ("/css/", 404), ("/data", 404), ("/data/", 404), ("/serve.py", 404), ("/scripts/serve.py", 404),
    ("/../scripts/serve.py", 404), ("/%2e%2e/scripts/serve.py", 404), ("/..%2fscripts%2fserve.py", 404),
    ("/%2e%2e/%2e%2e/etc/passwd", 404), ("/.git/config", 404), ("/data/../secret.txt", 404),
    ("/data/%2e%2e/secret.txt", 404), ("/secret.txt", 404), ("/ingest/events.jsonl", 404),
    ("/data/../ingest/events.jsonl", 404), ("/data/meta.json.tmp", 404),
])
def test_serves_assets_and_data_only(site, path, code):
    st, _ = request(site, "GET", path)
    assert st == code


def test_index_is_the_page_shell(site):
    st, body = request(site, "GET", "/")
    assert st == 200 and b"<title>Organization</title>" in body


@pytest.mark.parametrize("headers,host", [
    ({}, "evil.example:8765"), ({}, "127.0.0.1:1"), ({"Sec-Fetch-Site": "cross-site"}, None),
    ({"Sec-Fetch-Site": "same-site"}, None), ({"Origin": "http://evil.example"}, None),
])
def test_foreign_requests_are_refused(site, headers, host):
    st, _ = request(site, "GET", "/data/data.js", headers=headers, host=host)
    assert st == 403


def test_the_bound_port_is_the_allowed_host(site):
    port = site.server_address[1]
    st, _ = request(site, "GET", "/", host="localhost:%d" % port, headers={"Origin": "http://localhost:%d" % port})
    assert st == 200


JSON = {"Content-Type": "application/json"}


def log_size(site):
    return (site.data_dir / "ingest" / "events.jsonl").stat().st_size


@pytest.mark.parametrize("body,headers,code", [
    (json.dumps({"unit": "U1", "state": "nope"}).encode(), JSON, 400),
    (json.dumps({"unit": "U1", "state": "building", "x": 1}).encode(), JSON, 400),
    (b"{nope", JSON, 400),
    (json.dumps({"unit": "U1", "state": "building", "text": "a" * 5000}).encode(), JSON, 413),
    (json.dumps({"unit": "U1", "state": "building"}).encode(), {"Content-Type": "text/plain"}, 415),
    (json.dumps({"unit": "U1", "state": "building"}).encode(), dict(JSON, **{"Sec-Fetch-Site": "cross-site"}), 403),
    (json.dumps({"unit": "U1", "state": "building"}).encode(), dict(JSON, Origin="http://evil.example"), 403),
])
def test_refused_reports_leave_the_log_unchanged(site, body, headers, code):
    before = log_size(site)
    st, _ = request(site, "POST", "/api/ingest", body=body, headers=headers)
    assert st == code
    assert log_size(site) == before


def test_post_without_length_is_refused(site):
    st, _ = request(site, "POST", "/api/ingest", headers=JSON)
    assert st == 411


def test_post_elsewhere_is_not_found(site):
    st, _ = request(site, "POST", "/api/refresh", body=b"{}", headers=JSON)
    assert st == 404


def test_good_report_is_stored_in_the_data_dir_log(site):
    st, body = request(site, "POST", "/api/ingest", body=json.dumps({"unit": "U30", "state": "building"}).encode(), headers=JSON)
    assert st == 201
    line = json.loads(body)
    assert line["unit"] == "U30" and line["src"] == "http"
    ingest = load("ingest")
    st = ingest.read(site.data_dir / "ingest" / "events.jsonl")
    assert st["events"][-1]["unit"] == "U30" and not st["broken"]


def test_rate_cap_answers_429(site):
    site.app.bucket = load("serve").Bucket(1, 3600)
    body = json.dumps({"unit": "U31", "state": "queued"}).encode()
    assert request(site, "POST", "/api/ingest", body=body, headers=JSON)[0] == 201
    assert request(site, "POST", "/api/ingest", body=body, headers=JSON)[0] == 429


def test_deeply_nested_json_is_a_bad_request(site):
    body = b"[" * 2000 + b"]" * 2000
    st, _ = request(site, "POST", "/api/ingest", body=body, headers=JSON)
    assert st == 400


def test_head_on_the_event_stream_is_refused(site):
    st, _ = request(site, "HEAD", "/api/events")
    assert st == 405


def test_a_symlink_in_the_data_folder_is_not_followed(site):
    out = site.data_dir / "data"
    (out / "live.json").unlink()
    (out / "live.json").symlink_to(site.data_dir / "secret.txt")
    st, _ = request(site, "GET", "/data/live.json")
    assert st == 404
