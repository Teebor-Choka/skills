"""Checks for the depth dial (#46), package isolation (#43) and the `:improve` report (#45).

Run: python3 -m pytest engineering/design/skills/architect/tests
"""
import importlib.util
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint = _load("lint")

DEPTH_OK = """## Decomposition depth
**Dialed rung:** components · **Scope:** the billing service · **Given by:** the user, this invocation
## Acceptance by rung
| Rung | Acceptance criteria (ATDD) |
|------|----------------------------|
| interfaces | The API returns 402 on an unpaid invoice. |
| modules | The ledger module rejects a negative amount. |
| components | The tax component rounds half-even. |
"""


def depth_errs(text):
    errs = []
    lint.check_depth(text, errs)
    return errs


# --- #46 depth dial -------------------------------------------------------------------------

def test_depth_with_acceptance_at_every_traversed_rung_passes():
    assert depth_errs(DEPTH_OK) == []


def test_missing_depth_section_fails():
    assert any("E9" in e for e in depth_errs("## Block index\n"))


def test_unknown_rung_fails():
    assert depth_errs(DEPTH_OK.replace("components ·", "layers ·", 1))


def test_default_picked_silently_fails():
    assert depth_errs(DEPTH_OK.replace("the user, this invocation", "default"))


def test_leaf_only_acceptance_fails():
    text = DEPTH_OK.replace("| interfaces | The API returns 402 on an unpaid invoice. |\n", "")
    assert any("interfaces" in e for e in depth_errs(text))


def test_rung_below_the_dialed_one_is_not_required():
    text = DEPTH_OK.replace("components ·", "modules ·", 1).replace(
        "| components | The tax component rounds half-even. |\n", "")
    assert depth_errs(text) == []


def test_empty_acceptance_cell_fails():
    text = DEPTH_OK.replace("The ledger module rejects a negative amount.", " ")
    assert any("modules" in e for e in depth_errs(text))


def test_acceptance_for_a_rung_deeper_than_the_dialed_one_fails():
    extra = DEPTH_OK + "| functions | The parser rejects empty input. |\n"
    assert any("functions" in e and "deeper" in e for e in depth_errs(extra))


resolve_input = _load("resolve_input")


@pytest.mark.parametrize("depth,want", [
    ("interfaces", ["interfaces"]),
    ("modules", ["interfaces", "modules"]),
    ("components", ["interfaces", "modules", "components"]),
    ("functions", ["interfaces", "modules", "components", "functions"]),
])
def test_traversed_rungs_run_from_interfaces_down_to_and_including_the_dialed_one(depth, want):
    assert resolve_input.traversed(depth) == want


def test_traversed_rejects_an_unknown_rung_and_has_no_default():
    for bad in ("layers", "", None):
        with pytest.raises(ValueError):
            resolve_input.traversed(bad)


def test_traversed_is_case_insensitive():
    assert resolve_input.traversed("Modules") == ["interfaces", "modules"]


# --- #43 isolation --------------------------------------------------------------------------

def spec(rows, extra=""):
    head = "## Block index\n| # | Block | Runs on | Depends on | Write-set | Satisfies |\n|---|---|---|---|---|---|\n"
    return head + "\n".join(rows) + "\n" + extra


def ws(text):
    errs, warns = [], []
    lint.check_write_sets(text, errs, warns)
    return errs, warns


def test_disjoint_write_sets_pass():
    errs, _ = ws(spec(["| 1 | a | x | - | src/a | R1 |", "| 2 | b | x | - | src/b | R1 |"]))
    assert errs == []


def test_shared_write_set_without_edge_or_channel_fails():
    errs, _ = ws(spec(["| 1 | a | x | - | src/a | R1 |", "| 2 | b | x | - | src/a | R1 |"]))
    assert any("E10" in e for e in errs)


def test_shared_write_set_ordered_by_an_edge_passes():
    errs, _ = ws(spec(["| 1 | a | x | - | src/a | R1 |", "| 2 | b | x | 1 | src/a | R1 |"]))
    assert errs == []


def test_shared_write_set_ordered_transitively_passes():
    errs, _ = ws(spec(["| 1 | a | x | - | src/a | R1 |", "| 2 | b | x | 1 | src/b | R1 |",
                       "| 3 | c | x | 2 | src/a | R1 |"]))
    assert errs == []


def test_shared_write_set_with_channel_marker_in_both_passes():
    extra = "## Block 1: a\n**Coordination channel:** thread-ab\n## Block 2: b\n**Coordination channel:** thread-ab\n"
    errs, _ = ws(spec(["| 1 | a | x | - | src/a | R1 |", "| 2 | b | x | - | src/a | R1 |"], extra))
    assert errs == []


def test_channel_marker_in_one_block_only_fails():
    extra = "## Block 1: a\n**Coordination channel:** thread-ab\n## Block 2: b\n"
    errs, _ = ws(spec(["| 1 | a | x | - | src/a | R1 |", "| 2 | b | x | - | src/a | R1 |"], extra))
    assert errs


def test_missing_write_set_column_warns():
    errs, warns = ws("## Block index\n| # | Block | Depends on |\n|---|---|---|\n| 1 | a | - |\n")
    assert errs == [] and any("W3" in w for w in warns)


def test_overlapping_path_prefixes_count_as_shared():
    errs, _ = ws(spec(["| 1 | a | x | - | src/a | R1 |", "| 2 | b | x | - | src/a/deep | R1 |"]))
    assert any("E10" in e for e in errs)


def test_placeholder_channel_marker_does_not_count():
    for v in ("none", "-", ""):
        extra = f"## Block 1: a\n**Coordination channel:** {v}\n**Satisfies:** R\n## Block 2: b\n**Coordination channel:** {v}\n**Satisfies:** R\n"
        errs, _ = ws(spec(["| 1 | a | x | - | src/a | R1 |", "| 2 | b | x | - | src/a | R1 |"], extra))
        assert errs, v


def test_dependency_cycle_does_not_excuse_a_shared_write_set():
    errs, _ = ws(spec(["| 1 | a | x | 2 | src/a | R1 |", "| 2 | b | x | 1 | src/a | R1 |"]))
    assert any("cycle" in e for e in errs)


def test_backticked_and_space_separated_write_sets_are_compared():
    errs, _ = ws(spec(["| 1 | a | x | - | `src/a` | R1 |", "| 2 | b | x | - | `src/b` `src/a/deep` | R1 |"]))
    assert any("E10" in e for e in errs)


def test_no_write_marker_is_not_an_overlap():
    errs, _ = ws(spec(["| 1 | a | x | - | none | R1 |", "| 2 | b | x | - | n/a | R1 |"]))
    assert errs == []


def test_block_index_heading_is_case_insensitive():
    errs, _ = ws(spec(["| 1 | a | x | - | src/a | R1 |", "| 2 | b | x | - | src/a | R1 |"]).replace("Block index", "Block Index"))
    assert errs


def test_depth_given_by_must_name_the_user():
    assert depth_errs(DEPTH_OK.replace("the user, this invocation", "the architect"))


def test_depth_scope_is_required():
    assert any("scope" in e for e in depth_errs(DEPTH_OK.replace("**Scope:** the billing service · ", "")))


def test_dash_is_not_acceptance():
    assert any("modules" in e for e in depth_errs(DEPTH_OK.replace("The ledger module rejects a negative amount.", "n/a")))


def test_direct_read_that_only_says_no_graph_fails():
    assert improve_errs(report([row(1, "yes")], box(1), grounding="direct read; no code graph available"))


def test_graph_claim_that_negates_the_graph_fails():
    assert improve_errs(report([row(1, "yes")], box(1), grounding="no code graph, read the files"))


# --- #45 improve report ---------------------------------------------------------------------

def box(n):
    return (f"### Box {n}: deepen module {n}\n**Acceptance:** the interface of module {n} has one entry point.\n"
            "**Invariant:** keep components and libraries deep with tiny interfaces.\n")


def report(rows, boxes, cap=2, grounding="code graph (codebase-memory)", result="Findings below.", tail=""):
    table = "| # | Finding | Kind | Importance | Scope | Impact | Emitted |\n|---|---|---|---|---|---|---|\n" + "\n".join(rows)
    return (f"# r\n**Target:** the billing subtree\n**Grounding:** {grounding}\n"
            f"**Output location:** one GitHub issue per box\n**Box cap:** {cap}\n"
            f"## Result\n{result}\n## Boxes\n{boxes}\n## All findings\n{table}\n## Not emitted\n{tail}\n")


def row(n, emitted):
    return f"| {n} | f{n} | shallow | high | m | m | {emitted} |"


def improve_errs(text):
    errs = []
    lint.check_improve(text, errs)
    return errs


def test_clean_report_within_cap_passes():
    assert improve_errs(report([row(1, "yes"), row(2, "yes")], box(1) + box(2))) == []


def test_nothing_found_must_say_so_and_emit_nothing():
    text = report([], "", result="Nothing worth deepening in this target.")
    assert improve_errs(text) == []


def test_nothing_found_padded_with_a_box_fails():
    text = report([], box(1), result="Nothing worth deepening in this target.")
    assert improve_errs(text)


def test_boxes_over_cap_fail():
    rows = [row(1, "yes"), row(2, "yes"), row(3, "yes")]
    assert any("cap" in e for e in improve_errs(report(rows, box(1) + box(2) + box(3), cap=2)))


def test_non_numeric_cap_fails():
    assert any("cap" in e for e in improve_errs(report([row(1, "yes")], box(1), cap="few")))


def test_tail_is_listed_and_not_emitted():
    rows = [row(1, "yes"), row(2, "yes"), row(3, "no")]
    text = report(rows, box(1) + box(2), tail="- f3 (below the cap)")
    assert improve_errs(text) == []


def test_tail_must_name_every_finding_below_the_cap():
    rows = [row(1, "yes"), row(2, "no"), row(3, "no")]
    errs = improve_errs(report(rows, box(1), tail="- f2 (below the cap)"))
    assert any("I7" in e and "f3" in e for e in errs)


def test_tail_naming_every_finding_below_the_cap_passes():
    rows = [row(1, "yes"), row(2, "no"), row(3, "no")]
    assert improve_errs(report(rows, box(1), tail="- f2\n- f3")) == []


def test_tail_without_a_note_fails():
    rows = [row(1, "yes"), row(2, "yes"), row(3, "no")]
    assert improve_errs(report(rows, box(1) + box(2), tail=""))


def test_emitted_rows_must_be_the_top_ranked():
    rows = [row(1, "no"), row(2, "yes"), row(3, "yes")]
    assert improve_errs(report(rows, box(2) + box(3), tail="- f1"))


def test_box_without_the_invariant_fails():
    text = report([row(1, "yes")], "### Box 1: x\n**Acceptance:** y\n")
    assert any("invariant" in e.lower() for e in improve_errs(text))


def test_direct_read_without_warning_fails():
    text = report([row(1, "yes")], box(1), grounding="direct read of the code")
    assert improve_errs(text)


def test_direct_read_with_warning_passes():
    text = report([row(1, "yes")], box(1), grounding="direct read; WARNING: no code index available")
    assert improve_errs(text) == []


def test_unstated_target_fails():
    text = report([row(1, "yes")], box(1)).replace("**Target:** the billing subtree\n", "")
    assert any("Target" in e for e in improve_errs(text))


def test_unstated_output_location_fails():
    text = report([row(1, "yes")], box(1)).replace("**Output location:** one GitHub issue per box\n", "")
    assert any("Output location" in e for e in improve_errs(text))


# --- scaffold + cross-references ------------------------------------------------------------

def test_scaffolded_full_spec_declares_depth_write_set_and_channel(tmp_path):
    subprocess.run([sys.executable, str(SKILL / "scripts" / "scaffold.py"), "--slug", "t",
                    "--title", "T", "--dir", str(tmp_path / "p"), "--tier", "small",
                    "--depth", "modules", "--scope", "svc"], check=True,
                   capture_output=True)
    text = (tmp_path / "p" / "t-spec.md").read_text()
    for needle in ("Decomposition depth", "Acceptance by rung", "Write-set", "Coordination channel"):
        assert needle in text, needle


def test_scaffold_emits_an_improve_report_that_lints_clean_once_filled(tmp_path):
    subprocess.run([sys.executable, str(SKILL / "scripts" / "scaffold.py"), "--slug", "t",
                    "--title", "T", "--dir", str(tmp_path / "i"), "--improve",
                    "--target", "src/billing"], check=True,
                   capture_output=True)
    path = tmp_path / "i" / "improve-report.md"
    out = subprocess.run([sys.executable, str(SKILL / "scripts" / "lint.py"), str(path), "--improve"],
                         capture_output=True, text=True)
    assert out.returncode == 1 and "E3" in out.stdout  # unfilled scaffold is rejected


@pytest.mark.parametrize("name", ["depth-dial.md", "improve.md"])
def test_depth_and_improve_docs_cross_reference_each_other(name):
    text = (SKILL / "references" / name).read_text()
    other = "improve.md" if name == "depth-dial.md" else "depth-dial.md"
    assert other in text


def test_improve_doc_names_the_report_and_the_boundary():
    text = (SKILL / "references" / "improve.md").read_text()
    for needle in ("improve-report.md", "code-quality", "never edits", "Box cap", "Conjoined methods"):
        assert needle in text, needle


def test_decompose_filing_guard_for_packages():
    guide = (SKILL.parent / "decompose" / "references" / "filing.md").read_text()
    for needle in ("Blocked by", "Blocks", "never opens", "work.tracker"):
        assert needle in guide, needle


# --- non-interactive input resolution -------------------------------------------------------

import json
import os

SCAFFOLD = SKILL / "scripts" / "scaffold.py"


def stub_loader(tmp_path, policy):
    """A policy loader stand-in: `--get KEY` prints policy[KEY], else the real loader's 'None'."""
    path = tmp_path / "loader.py"
    path.write_text("import json, os, sys\nk = sys.argv[sys.argv.index('--get') + 1]\n"
                    f"print(json.loads({json.dumps(json.dumps(policy))}).get(k, 'None'))\n")
    return str(path)


def scaffold(tmp_path, *args, policy=None):
    cmd = [sys.executable, str(SCAFFOLD), "--slug", "t", "--title", "T", "--dir", str(tmp_path / "out"),
           "--policy-loader", stub_loader(tmp_path, policy or {}), *args]
    out = subprocess.run(cmd, capture_output=True, text=True)
    return out, (tmp_path / "out")


def result(out):
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_missing_depth_halts_with_needs_input_and_writes_nothing(tmp_path):
    out, root = scaffold(tmp_path, "--tier", "small", "--scope", "svc")
    assert out.returncode == 3
    res = result(out)
    assert res["status"] == "needs-input"
    miss = {m["field"]: m for m in res["missing"]}
    assert set(miss) == {"depth"}
    assert miss["depth"]["arg"] == "--depth" and miss["depth"]["policy_key"] == "architect.depth"
    assert not root.exists()


def test_missing_depth_and_scope_are_both_named(tmp_path):
    out, root = scaffold(tmp_path, "--tier", "full")
    assert {m["field"] for m in result(out)["missing"]} == {"depth", "scope"}
    assert not root.exists()


def test_depth_from_an_arg_proceeds(tmp_path):
    out, root = scaffold(tmp_path, "--tier", "small", "--depth", "modules", "--scope", "svc")
    assert out.returncode == 0
    spec = (root / "t-spec.md").read_text()
    assert "**Dialed rung:** modules" in spec and "`--depth`" in spec
    errs = []
    lint.check_depth(spec.replace("FILL-IN", "x"), errs)
    assert errs == []


def test_depth_from_policy_proceeds(tmp_path):
    out, root = scaffold(tmp_path, "--tier", "small", policy={"architect.depth": "components",
                                                                  "architect.scope": "svc"})
    assert out.returncode == 0
    assert "architect.depth" in (root / "t-spec.md").read_text()


def test_an_arg_beats_policy(tmp_path):
    out, root = scaffold(tmp_path, "--tier", "small", "--depth", "interfaces",
                         policy={"architect.depth": "functions", "architect.scope": "s"})
    assert "**Dialed rung:** interfaces" in (root / "t-spec.md").read_text()


def test_an_unknown_rung_halts(tmp_path):
    out, root = scaffold(tmp_path, "--tier", "small", "--depth", "layers", "--scope", "svc")
    assert out.returncode == 3 and not root.exists()
    assert result(out)["missing"][0]["field"] == "depth"


def test_interactive_channel_asks_instead_of_halting(tmp_path):
    out, root = scaffold(tmp_path, "--tier", "small", "--interactive")
    assert out.returncode == 4 and result(out)["status"] == "ask" and not root.exists()


def test_the_note_tier_needs_no_depth(tmp_path):
    out, _ = scaffold(tmp_path, "--tier", "note")
    assert out.returncode == 0


def test_improve_missing_target_halts_naming_only_the_target(tmp_path):
    out, root = scaffold(tmp_path, "--improve")
    assert out.returncode == 3
    miss = result(out)["missing"]
    assert [m["field"] for m in miss] == ["target"]
    assert miss[0]["arg"] == "--target" and miss[0]["policy_key"] == "architect.improve-target"
    assert not root.exists()


def test_improve_defaults_are_stated_and_written_into_the_report(tmp_path):
    out, root = scaffold(tmp_path, "--improve", "--target", "src/billing")
    assert out.returncode == 0
    text = (root / "improve-report.md").read_text()
    assert "**Box cap:** 5" in text and "default" in text
    assert "github issues" in text.lower() and "work.tracker" in text
    assert "src/billing" in text


def test_improve_output_and_cap_come_from_policy(tmp_path):
    out, root = scaffold(tmp_path, "--improve", policy={"architect.improve-target": "lib", "work.tracker": "beads",
                                                       "architect.box-cap": "3"})
    text = (root / "improve-report.md").read_text()
    assert "**Box cap:** 3" in text and "beads" in text and "lib" in text


def test_improve_non_numeric_cap_halts(tmp_path):
    out, root = scaffold(tmp_path, "--improve", "--target", "x", "--cap", "many")
    assert out.returncode == 3 and result(out)["missing"][0]["field"] == "cap" and not root.exists()


def test_e9_message_points_to_the_arg_and_policy_key_not_a_question():
    msgs = " ".join(depth_errs("## Block index\n"))
    assert "--depth" in msgs and "architect.depth" in msgs and "ask the user" not in msgs.lower()


@pytest.mark.parametrize("name", ["SKILL.md", "references/depth-dial.md", "references/improve.md"])
def test_docs_state_the_two_path_rule(name):
    text = (SKILL / name).read_text()
    assert "needs-input" in text, name
    assert "ask the user" not in text.lower() and "**ask**" not in text, name
