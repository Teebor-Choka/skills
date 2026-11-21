"""Tests for cost.py: dollars from cost-state segments and from deduped per-message usage."""
import json

import pytest

from helpers import asst_text, at, load, write

cost = load("cost.py")

PRICES = {"claude-sonnet": {"in": 3.0, "out": 15.0, "cache_write": 3.75, "cache_read": 0.30}}
MODEL = "claude-sonnet-4-5"


def usage(inp=0, out=0, cw=0, cr=0):
    return {"input_tokens": inp, "output_tokens": out,
            "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}


def msg(msg_id, u, model=MODEL, ts="2026-03-04T10:00:00Z"):
    return at(asst_text("x", msg_id=msg_id, model=model, usage=u), ts)


def test_usage_is_priced_per_token_class(tmp_path):
    rows = [msg("m1", usage(1_000_000, 1_000_000, 1_000_000, 1_000_000))]
    r = cost.cost_of([write(tmp_path, rows)], prices=PRICES)
    assert r["usage_usd"] == pytest.approx(3.0 + 15.0 + 3.75 + 0.30)


def test_a_message_logged_once_per_content_block_is_priced_once(tmp_path):
    rows = [msg("m1", usage(1_000_000)), msg("m1", usage(1_000_000)), msg("m1", usage(1_000_000))]
    r = cost.cost_of([write(tmp_path, rows)], prices=PRICES)
    assert r["usage_usd"] == pytest.approx(3.0)
    assert r["messages"] == 1


def test_a_continuation_that_repeats_a_message_does_not_double_count(tmp_path):
    a = write(tmp_path, [msg("m1", usage(1_000_000))], name="a.jsonl")
    b = write(tmp_path, [msg("m1", usage(1_000_000)), msg("m2", usage(1_000_000))], name="b.jsonl")
    assert cost.cost_of([a, b], prices=PRICES)["usage_usd"] == pytest.approx(6.0)


def test_unknown_model_warns_and_costs_nothing(tmp_path):
    rows = [msg("m1", usage(1_000_000), model="mystery-model-9")]
    r = cost.cost_of([write(tmp_path, rows)], prices=PRICES)
    assert r["usage_usd"] == 0
    assert any("mystery-model-9" in w for w in r["warnings"])


def test_default_price_table_knows_the_three_model_families(tmp_path):
    for fam in ("claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"):
        r = cost.cost_of([write(tmp_path, [msg("m", usage(1000), model=fam)], name=fam + ".jsonl")])
        assert r["warnings"] == [] and r["usage_usd"] > 0


def test_cost_state_sums_segments_across_resets(tmp_path):
    rows = [{"type": "cost-state", "totalCostUsd": v} for v in (1.0, 2.5, 0.5, 1.2)]
    r = cost.cost_of([write(tmp_path, rows)], prices=PRICES)
    assert r["cost_state_usd"] == pytest.approx(3.7)  # 2.5 before the reset + 1.2 after


def test_no_cost_state_reports_none_not_zero(tmp_path):
    r = cost.cost_of([write(tmp_path, [msg("m1", usage(10))])], prices=PRICES)
    assert r["cost_state_usd"] is None


def test_window_applies_to_usage_by_event_time(tmp_path):
    rows = [msg("old", usage(1_000_000), ts="2026-01-01T00:00:00Z"),
            msg("new", usage(1_000_000), ts="2026-03-04T00:00:00Z")]
    r = cost.cost_of([write(tmp_path, rows)], prices=PRICES, since="2026-02-01")
    assert r["usage_usd"] == pytest.approx(3.0)


def test_cli_prints_both_figures_as_json(tmp_path, capsys):
    write(tmp_path, [msg("m1", usage(1_000_000))])
    assert cost.main([str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {"usage_usd", "cost_state_usd", "warnings", "by_model"} <= set(out)


def test_cost_state_key_spelled_totalCostUSD_is_read(tmp_path):
    rows = [{"type": "cost-state", "totalCostUSD": v} for v in (1.0, 2.5)]
    assert cost.cost_of([write(tmp_path, rows)], prices=PRICES)["cost_state_usd"] == pytest.approx(2.5)
