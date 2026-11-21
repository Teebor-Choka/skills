// Render the deterministic half of a review as human-readable markdown. The host
// agent folds its LLM-tier rubric verdicts in as a separate advisory section.
export function renderReport(r) {
  const L = [];
  L.push(`# Presentation review — ${r.deck.path}`);
  L.push("");
  L.push(
    `CONFORMANCE ${r.headline.score}% (${r.headline.band}) — ${r.deck.slideCount} slides, ${r.headline.applicable} deck checks scored (plan checklist + advisories below)`,
  );
  L.push("");
  const shown = r.reproducible.filter((c) => c.status !== "skip");
  for (const c of shown) {
    const detail =
      c.evidence && c.evidence.length
        ? "  " + JSON.stringify(c.evidence)
        : c.note
          ? "  " + c.note
          : "";
    L.push(
      `  ${c.status.toUpperCase().padEnd(5)} ${c.name} (${c.type}) — references/${c.file}${detail}`,
    );
  }
  const skipped = r.reproducible.length - shown.length;
  if (skipped)
    L.push(
      `  … ${skipped} skipped (pending tiers / no plan / source-unavailable)`,
    );
  if (r.fixes_available.length) {
    L.push("");
    L.push(
      "Fixes available (pptx): " +
        r.fixes_available.map((f) => `${f.op}[${f.id}]`).join(", "),
    );
  }
  if (r.llm_jobs.length) {
    L.push("");
    L.push(
      `+ ${r.llm_jobs.length} advisory LLM-tier checks for the agent to evaluate (not in headline).`,
    );
  }
  if (r.unscoreable.length)
    L.push(
      `+ ${r.unscoreable.length} live-delivery patterns not scoreable from a deck.`,
    );
  return L.join("\n");
}
