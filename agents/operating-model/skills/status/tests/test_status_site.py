"""Generate the site from the fixture, then run check.py's checks and the node render test on it."""

import json
import shutil
import subprocess

import pytest

from status_testlib import ASSETS, FIXTURE, TESTS, fixture_argv, load

pytest.importorskip("yaml", reason="gen.py reads the workflow YAML with PyYAML")


def generate(tmp_path, **kw):
    data_dir = tmp_path / "state"
    (data_dir / "ingest").mkdir(parents=True)
    if kw.pop("ingest", True):
        shutil.copy(FIXTURE / "ingest.jsonl", data_dir / "ingest" / "events.jsonl")
    gen = load("gen")
    assert gen.main(fixture_argv(data_dir, **kw)) == 0
    return data_dir / "data"


def read(out, part):
    return json.loads((out / (part + ".json")).read_text())


@pytest.fixture
def check():
    c = load("check")
    c.fails.clear()
    c.notes.clear()
    yield c
    c.fails.clear()
    c.notes.clear()


def test_full_fixture_passes_the_data_checks(tmp_path, check):
    out = generate(tmp_path)
    check.data_checks(out)
    assert check.fails == []
    dec = read(out, "decisions")
    assert [d["title"] for d in dec["items"] if d["open"]] == ["Fixture decision"]
    assert "the fixture decision needs an answer" in dec["owner_html"]
    units = {u["id"]: u for u in read(out, "build")["units"]}
    assert {"U3", "U4", "U13b", "U19", "U20", "U21", "U22"} <= set(units)
    assert units["U4"]["state"] == "failed" and units["U4"]["state_src"] == "ingest"
    assert units["U3"]["items"] == ["tdd-unit"]
    runs = read(out, "live")["runs"]
    assert [r["workflow"] for r in runs] == ["tdd-unit"]


def test_without_a_work_package_the_site_still_builds(tmp_path, check):
    out = generate(tmp_path, work_package=False)
    check.data_checks(out)
    assert check.fails == []
    dec = read(out, "decisions")
    assert dec["items"] == [] and dec["log"] == [] and dec["owner_html"] == ""
    units = read(out, "build")["units"]
    assert sorted(u["id"] for u in units) == ["U20", "U21", "U22", "U4"]
    assert all(u["src"] == "ingest" for u in units)
    meta = read(out, "meta")
    assert meta["gh"] == "off"


def test_with_nothing_but_the_org_root_the_site_still_builds(tmp_path, check):
    out = generate(tmp_path, work_package=False, ledger=False, ingest=False)
    check.data_checks(out)
    assert check.fails == []
    assert read(out, "build")["units"] == []
    assert read(out, "live")["runs"] == []
    assert read(out, "workflows")


def test_generated_data_names_no_home_path(tmp_path):
    out = generate(tmp_path)
    blob = (out / "data.js").read_text()
    assert str(tmp_path) not in blob.replace(str(tmp_path / "state"), "")
    for p in (out / "meta.json", out / "build.json"):
        assert "/Users/" not in p.read_text()


def test_static_and_contrast_checks_pass(check):
    check.static_checks(ASSETS)
    check.contrast_checks(ASSETS)
    assert check.fails == []


def test_ingest_checks_pass(check):
    check.ingest_checks()
    assert check.fails == []


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not on PATH; the render test needs it (add nodejs to run it)")
@pytest.mark.parametrize("kw", [{}, {"work_package": False}, {"work_package": False, "ledger": False, "ingest": False}],
                         ids=["full", "no-work-package", "org-root-only"])
def test_render_every_route(tmp_path, kw):
    out = generate(tmp_path, **kw)
    p = subprocess.run([NODE, str(TESTS / "render.test.js"), str(out / "data.js")], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, (p.stdout + p.stderr)[-4000:]
    assert "PASS" in p.stdout
