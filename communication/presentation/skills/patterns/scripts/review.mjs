#!/usr/bin/env node
// Review runner: ingest a deck (via the deck-io leaf) → run deterministic checks
// → score → assemble the report object. LLM-tier checks are emitted as `llm_jobs`
// for the host agent to evaluate (no API calls here); safe-fixes are LISTED in
// `fixes_available` (application is Phase 1b in deck-io emit).
//   node review.mjs <deck.pptx|deck.pdf> [--plan deck.plan.yaml] [--json]
import fs from "node:fs";
import { ingest } from "../../../deck-io/scripts/ingest.mjs";
import { REGISTRY } from "./registry.mjs";
import * as det from "./checks/deterministic.mjs";
import { buildJob } from "./checks/llm_rubrics.mjs";
import { score } from "./score.mjs";
import { renderReport } from "./report.mjs";

export async function review(file, { plan = null } = {}) {
  const deck = await ingest(file);
  if (plan) deck.plan = plan; // review.mjs owns the plan sidecar, not deck-io

  const reproducible = [];
  const llm_jobs = [];
  const unscoreable = [];
  const fixes = [];

  for (const row of REGISTRY) {
    if (row.tier === "llm") {
      llm_jobs.push(buildJob(row, deck));
      continue;
    }
    if (row.tier === "unscoreable") {
      unscoreable.push({
        id: row.id,
        name: row.name,
        note: "pure live-delivery behavior — not scoreable from a deck",
      });
      continue;
    }
    let res;
    if (row.tier === "deterministic") {
      res =
        row.check && det[row.check]
          ? det[row.check](deck)
          : {
              status: "skip",
              reason: "check not yet implemented",
              evidence: [],
            };
    } else if (row.tier === "animation") {
      if (deck.source.capabilities.animation !== true)
        res = {
          status: "skip",
          reason: "animation not observable from source",
          evidence: [],
        };
      else
        res =
          row.check && det[row.check]
            ? det[row.check](deck)
            : {
                status: "skip",
                reason: "animation check pending (Phase 2)",
                evidence: [],
              };
    } else if (row.tier === "plan-presence") {
      if (!deck.plan) {
        res = {
          status: "skip",
          reason: "no plan sidecar (<deck>.plan.yaml)",
          evidence: [],
        };
      } else {
        const v = deck.plan[row.planField];
        const has = v != null && v !== "";
        res = has
          ? { status: "pass", evidence: [{ field: row.planField }] }
          : {
              status: "info",
              note: `consider recording ${row.planField} in the plan`,
              evidence: [{ field: row.planField }],
            };
      }
    } else {
      res = {
        status: "skip",
        reason: `unhandled tier ${row.tier}`,
        evidence: [],
      };
    }
    reproducible.push({
      id: row.id,
      name: row.name,
      type: row.type,
      tier: row.tier,
      file: row.file,
      ...res,
    });
    if (res.status === "fail" && row.fixOp)
      fixes.push({
        id: row.id,
        op: row.fixOp,
        slides: [
          ...new Set((res.evidence || []).map((e) => e.slide).filter(Boolean)),
        ],
      });
  }

  const headline = score(reproducible);
  return {
    deck: {
      path: deck.source.path,
      format: deck.source.format,
      slideCount: deck.meta.slideCount,
    },
    headline,
    reproducible,
    llm_jobs,
    unscoreable,
    fixes_available: fixes,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const argv = process.argv.slice(2);
  const file = argv.find((a) => !a.startsWith("--"));
  const json = argv.includes("--json");
  if (!file) {
    console.error(
      "usage: review <deck.pptx|deck.pdf> [--plan deck.plan.yaml] [--json]",
    );
    process.exit(1);
  }
  let plan = null;
  const pi = argv.indexOf("--plan");
  if (pi >= 0 && argv[pi + 1]) {
    const yaml = (await import("js-yaml")).default;
    plan = yaml.load(fs.readFileSync(argv[pi + 1], "utf8"));
  }
  const result = await review(file, { plan });
  console.log(json ? JSON.stringify(result, null, 2) : renderReport(result));
  if (
    argv.includes("--fix") &&
    result.fixes_available.length &&
    result.deck.format === "pptx"
  ) {
    const { emit } = await import("../../../deck-io/scripts/emit.mjs");
    const out = await emit(file, result.fixes_available);
    console.error(
      `\napplied ${result.fixes_available.length} fix op(s) → ${out}`,
    );
  }
  process.exit(result.headline.band === "red" ? 1 : 0);
}
