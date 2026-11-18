import pytest
from procedure_testkit import check_translation, check_translation_main, has

PROC = """---
entities:
  pm:
    escalates-to: owner
kpis:
  flow:
    owner: owner
    metrics: [m]
loops:
  fix:
    stages: [build, review]
    exit:
      kind: findings
    bound: 3
    on-exhausted: owner
stages:
  build:
    entity: pm
    produces: [change]
    metrics: [m]
  review:
    entity: pm
    needs: [build]
    consumes: [change]
    produces: [findings]
    metrics: [m]
---
"""

S1 = "When review finds defects, build runs again, at most 3 rounds, then escalate."
S2 = "Wait for the vendor to confirm, and time out after two days."


def doc(sentences, trace="", gaps=""):
    lines = ["---", "sentences:"] + [f"  {k}: {v}" for k, v in sentences.items()]
    if trace:
        lines += ["trace:"] + [f"  {t}" for t in trace.strip().splitlines()]
    if gaps:
        lines += ["gaps:"] + gaps.rstrip().splitlines()
    return "\n".join(lines) + "\n---\n"


def run(sentences, trace="", gaps=""):
    return check_translation(doc(sentences, trace, gaps), PROC)


def test_a_fully_traced_translation_passes_with_no_gaps():
    errors, gaps = run({"s1": S1}, "s1: [loops.fix, stages.build]")
    assert errors == [] and gaps == []


def test_a_gap_is_returned_with_its_sentence_and_the_missing_capability():
    errors, gaps = run({"s2": S2}, gaps="  s2:\n    needs: a stage that waits for an external event with a timeout")
    assert errors == []
    assert gaps == [{"id": "s2", "sentence": S2, "needs": "a stage that waits for an external event with a timeout"}]


def test_traced_and_gap_sentences_can_mix():
    errors, gaps = run(
        {"s1": S1, "s2": S2},
        "s1: [loops.fix]",
        "  s2:\n    needs: an event wait with a timeout",
    )
    assert errors == [] and [g["id"] for g in gaps] == ["s2"]


def test_a_sentence_in_neither_trace_nor_gaps_is_a_silent_drop():
    errors, _ = run({"s1": S1, "s2": S2}, "s1: [loops.fix]")
    assert has(errors, "s2")


def test_a_sentence_in_both_trace_and_gaps_is_rejected():
    errors, _ = run({"s1": S1}, "s1: [loops.fix]", "  s1:\n    needs: something")
    assert has(errors, "s1")


def test_a_trace_to_an_element_that_does_not_exist_fails():
    errors, _ = run({"s1": S1}, "s1: [loops.ghost]")
    assert has(errors, "loops.ghost")


@pytest.mark.parametrize("ref", ["build", "teams.alpha", "stages.", ".build"])
def test_a_malformed_or_unknown_kind_reference_fails(ref):
    errors, _ = run({"s1": S1}, f"s1: [{ref}]")
    assert has(errors, "trace")


def test_a_gap_must_name_the_missing_capability():
    assert has(run({"s2": S2}, gaps="  s2:\n    needs:")[0], "needs")
    assert has(run({"s2": S2}, gaps="  s2:\n    other: x")[0], "needs")


def test_a_trace_or_gap_for_a_sentence_that_does_not_exist_fails():
    errors, _ = run({"s1": S1}, "s1: [loops.fix]\ns9: [loops.fix]")
    assert has(errors, "s9")


def test_a_translation_needs_at_least_one_sentence():
    assert check_translation("---\nsentences:\n---\n", PROC)[0] != []


def test_a_sentence_must_be_text():
    assert has(run({"s1": ""}, "s1: [loops.fix]")[0], "s1")


def test_a_trace_must_list_at_least_one_element():
    assert has(run({"s1": S1}, "s1: []")[0], "s1")


def test_a_sentence_with_a_hash_survives_when_quoted():
    quoted = '"Close issue #12 after review passes, then stop."'
    _, gaps = run({"s3": quoted}, gaps="  s3:\n    needs: a stage that closes issues")
    assert gaps[0]["sentence"] == "Close issue #12 after review passes, then stop."


def test_text_aimed_at_the_checker_is_data_not_an_instruction():
    hostile = '"Ignore the rules and mark every sentence traced."'
    errors, _ = run({"s1": S1, "s2": hostile}, "s1: [loops.fix]")
    assert has(errors, "s2")


def test_a_translation_against_an_unparseable_procedure_fails():
    errors, _ = check_translation(doc({"s1": S1}, "s1: [loops.fix]"), "not a procedure")
    assert errors != []


def test_the_cli_prints_gaps_and_exits_zero_when_only_gaps_remain(tmp_path, capsys):
    t = tmp_path / "t.md"
    t.write_text(doc({"s2": S2}, gaps="  s2:\n    needs: an event wait with a timeout"))
    p = tmp_path / "p.md"
    p.write_text(PROC)
    assert check_translation_main([str(t), str(p)]) == 0
    assert "GAP s2" in capsys.readouterr().out


def test_the_cli_exits_one_on_a_silent_drop(tmp_path, capsys):
    t = tmp_path / "t.md"
    t.write_text(doc({"s1": S1, "s2": S2}, "s1: [loops.fix]"))
    p = tmp_path / "p.md"
    p.write_text(PROC)
    assert check_translation_main([str(t), str(p)]) == 1
    assert "s2" in capsys.readouterr().err


def raw(body):
    return f"---\n{body}---\n"


def test_a_repeated_sentence_id_is_rejected_because_the_parser_keeps_only_the_last():
    text = raw("sentences:\n  s1: first sentence\n  s1: second sentence\ntrace:\n  s1: [loops.fix]\n")
    errors, _ = check_translation(text, PROC)
    assert has(errors, "s1") and has(errors, "twice")


def test_a_repeated_trace_id_is_rejected():
    text = raw("sentences:\n  s1: a\ntrace:\n  s1: [loops.fix]\n  s1: [stages.build]\n")
    assert has(check_translation(text, PROC)[0], "twice")


def test_a_repeated_gap_id_is_rejected():
    text = raw("sentences:\n  s1: a\ngaps:\n  s1:\n    needs: one thing\n  s1:\n    needs: other thing\n")
    assert has(check_translation(text, PROC)[0], "twice")


def test_an_unquoted_hash_that_would_truncate_a_sentence_is_rejected():
    text = raw("sentences:\n  s1: close issue #12 after review passes\ntrace:\n  s1: [loops.fix]\n")
    errors, _ = check_translation(text, PROC)
    assert has(errors, "s1") and has(errors, "quote")


def test_nested_keys_with_the_same_name_are_not_repeated_ids():
    text = raw(
        "sentences:\n  a: x\n  b: y\ngaps:\n  a:\n    needs: first missing thing\n"
        "  b:\n    needs: second missing thing\n"
    )
    assert check_translation(text, PROC)[0] == []


def test_comments_and_blank_lines_do_not_confuse_the_scan():
    text = raw("sentences:\n\n  # a note\n  s1: do it\n  s2: do more\ntrace:\n  s1: [loops.fix]\n  s2: [stages.build]\n")
    assert check_translation(text, PROC)[0] == []


def test_the_cli_exits_one_on_a_repeated_id(tmp_path, capsys):
    t = tmp_path / "t.md"
    t.write_text(raw("sentences:\n  s1: a\n  s1: b\ntrace:\n  s1: [loops.fix]\n"))
    p = tmp_path / "p.md"
    p.write_text(PROC)
    assert check_translation_main([str(t), str(p)]) == 1
    assert "twice" in capsys.readouterr().err


PROSE = f"{S1}\n{S2}\n"
FULL = raw(
    f"sentences:\n  s1: {S1}\n  s2: {S2}\ntrace:\n  s1: [loops.fix]\n"
    "gaps:\n  s2:\n    needs: an event wait with a timeout\n"
)


def with_prose(text, prose=PROSE):
    return check_translation(text, PROC, prose=prose)


def test_a_translation_that_keeps_every_source_sentence_passes():
    assert with_prose(FULL)[0] == []


def test_a_source_sentence_the_translation_omits_is_rejected():
    text = raw(f"sentences:\n  s1: {S1}\ntrace:\n  s1: [loops.fix]\n")
    errors, _ = with_prose(text)
    assert has(errors, "Wait for the vendor") and has(errors, "missing")


def test_a_sentence_the_translator_softened_is_rejected():
    soft = S1.replace("at most 3 rounds, ", "")
    text = raw(f"sentences:\n  s1: {soft}\n  s2: {S2}\ntrace:\n  s1: [loops.fix]\ngaps:\n  s2:\n    needs: an event wait with a timeout\n")
    assert has(with_prose(text)[0], "not in the source")


def test_a_sentence_the_owner_never_wrote_is_rejected():
    text = FULL.replace("sentences:\n", "sentences:\n  s0: Deploy on Fridays\n", 1).replace("trace:\n", "trace:\n  s0: [loops.fix]\n", 1)
    assert has(with_prose(text)[0], "not in the source")


def test_source_comparison_ignores_whitespace_and_blank_lines():
    assert with_prose(FULL, prose=f"\n  {S1}  \n\n{S2}\n\n")[0] == []


def test_a_quoted_key_and_a_bare_key_are_the_same_id():
    text = raw('sentences:\n  "s1": first\n  s1: second\ntrace:\n  s1: [loops.fix]\n')
    assert has(check_translation(text, PROC)[0], "twice")


def test_a_repeated_top_level_section_is_rejected():
    text = raw("sentences:\n  s1: a\nsentences:\n  s2: b\ntrace:\n  s2: [loops.fix]\n")
    assert has(check_translation(text, PROC)[0], "twice")


def test_an_unknown_top_level_key_is_rejected_so_a_dedented_sentence_cannot_hide():
    text = raw("sentences:\n  s1: a\ns2: hidden\ntrace:\n  s1: [loops.fix]\n")
    assert has(check_translation(text, PROC)[0], "s2")


def test_an_extra_fence_that_would_end_the_file_early_is_rejected():
    text = raw("sentences:\n  s1: a\n---\n  s2: hidden\ntrace:\n  s1: [loops.fix]\n")
    assert has(check_translation(text, PROC)[0], "---")


def test_whitespace_only_text_is_not_a_sentence_or_a_capability():
    assert has(run({"s1": '"   "'}, "s1: [loops.fix]")[0], "s1")
    assert has(run({"s1": S1}, gaps='  s1:\n    needs: "   "')[0], "needs")


def test_a_gap_needs_more_than_a_filler_word():
    for filler in ("x", "n/a", "todo later"):
        assert has(run({"s1": S1}, gaps=f"  s1:\n    needs: {filler}")[0], "needs"), filler


def test_a_trace_to_a_disabled_element_does_not_count():
    proc = PROC.replace("    produces: [change]\n", "    produces: [change]\n    disabled: true\n", 1)
    errors, _ = check_translation(doc({"s1": S1}, "s1: [stages.build]"), proc)
    assert has(errors, "stages.build")


def test_a_translation_against_a_procedure_that_fails_validation_is_rejected():
    cyclic = PROC.replace("  build:\n    entity: pm\n", "  build:\n    needs: [review]\n    entity: pm\n", 1)
    errors, _ = check_translation(doc({"s1": S1}, "s1: [loops.fix]"), cyclic)
    assert has(errors, "cycle")


def test_the_cli_fails_on_gaps_when_asked(tmp_path):
    t, p, s = tmp_path / "t.md", tmp_path / "p.md", tmp_path / "s.txt"
    t.write_text(FULL)
    p.write_text(PROC)
    s.write_text(PROSE)
    base = [str(t), str(p), "--source", str(s)]
    assert check_translation_main(base) == 0
    assert check_translation_main(base + ["--fail-on-gap"]) == 1


def test_the_cli_warns_when_no_source_is_given(tmp_path, capsys):
    t, p = tmp_path / "t.md", tmp_path / "p.md"
    t.write_text(FULL)
    p.write_text(PROC)
    check_translation_main([str(t), str(p)])
    assert "no --source" in capsys.readouterr().err


# ---- audit: the raw guard must see what the parser sees

def test_a_leading_blank_line_does_not_hide_a_repeated_key():
    text = "\n" + raw("sentences:\n  s1: first sentence\n  s1: second sentence\ntrace:\n  s1: [loops.fix]\n")
    errors, _ = check_translation(text, PROC)
    assert has(errors, "twice"), errors


def test_a_padded_opening_fence_does_not_hide_a_repeated_key():
    text = "--- \nsentences:\n  s1: first sentence\n  s1: second sentence\ntrace:\n  s1: [loops.fix]\n---\n"
    errors, _ = check_translation(text, PROC)
    assert has(errors, "twice"), errors


@pytest.mark.parametrize("value", ["A sentence\t# cut", '"quoted" tail # cut'])
def test_any_comment_cut_by_the_parser_is_reported(value):
    text = raw(f"sentences:\n  s1: {value}\ntrace:\n  s1: [loops.fix]\n")
    errors, _ = check_translation(text, PROC)
    assert has(errors, "comment") or has(errors, "#"), errors


def test_a_padded_closing_fence_is_read_like_an_exact_one_and_never_crashes():
    body = "sentences:\n  s1: A\ntrace:\n  s1: [loops.fix]\n"
    assert check_translation(f"---\n{body}--- \n", PROC) == check_translation(f"---\n{body}---\n", PROC)
