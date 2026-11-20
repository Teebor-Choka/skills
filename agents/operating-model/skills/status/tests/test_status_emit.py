"""emit.py: the fallback log lives in the site's data dir, and a hook run never blocks a session."""

import io
import json
import socket

from status_testlib import load


def free_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "http://127.0.0.1:%d" % port


def test_server_down_appends_to_the_data_dir_log(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ORG_INGEST", raising=False)
    emit = load("emit")
    rc = emit.main(["--unit", "U7", "--state", "review", "--data-dir", str(tmp_path), "--url", free_url()])
    assert rc == 0
    lines = (tmp_path / "ingest" / "events.jsonl").read_text().splitlines()
    assert [json.loads(x)["unit"] for x in lines] == ["U7"]
    assert json.loads(lines[0])["src"] == "file"


def test_default_data_dir_follows_xdg_state_home(tmp_path, monkeypatch):
    monkeypatch.delenv("ORG_INGEST", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    emit = load("emit")
    assert emit.main(["--unit", "U8", "--state", "queued", "--url", free_url()]) == 0
    assert (tmp_path / "org-status" / "ingest" / "events.jsonl").is_file()


def test_hook_without_a_unit_does_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"description": "no unit id here"})))
    emit = load("emit")
    assert emit.main(["--hook", "--state", "building", "--data-dir", str(tmp_path), "--url", free_url()]) == 0
    assert not (tmp_path / "ingest" / "events.jsonl").exists()


def test_hook_exits_zero_on_a_refused_report(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"description": "work on U9"})))
    emit = load("emit")
    log = tmp_path / "ingest" / "events.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("torn")
    assert emit.main(["--hook", "--state", "building", "--data-dir", str(tmp_path), "--url", free_url()]) == 0
    assert log.read_text() == "torn"
