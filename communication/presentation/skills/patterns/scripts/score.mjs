// Headline conformance = reproducible checks only (pass/fail). 'skip' (capability
// unavailable), 'na' (not applicable), and 'info' are excluded so the trend line
// stays trustworthy. LLM-tier verdicts are advisory and never enter this number.
// Headline = artifact-derived ANTIPATTERN avoidance: deterministic/animation deck
// checks of type AP (pass = not violated, fail = violated). Patterns (P) are
// advisory technique-usage notes (present→pass, absent→info) and never enter the
// number, so it can't be inflated by using techniques or listing plan fields — it
// reflects "how many antipatterns is this deck committing."
const SCORED_TIERS = new Set(["deterministic", "animation"]);
export function score(results) {
  const applicable = results.filter(
    (r) =>
      SCORED_TIERS.has(r.tier) &&
      r.type === "AP" &&
      (r.status === "pass" || r.status === "fail"),
  );
  const pass = applicable.filter((r) => r.status === "pass").length;
  const total = applicable.length;
  const pct = total ? Math.round((100 * pass) / total) : 100;
  const band = pct >= 80 ? "green" : pct >= 50 ? "yellow" : "red";
  const tierStats = (t) => {
    const g = results.filter((r) => r.tier === t);
    return {
      pass: g.filter((r) => r.status === "pass").length,
      fail: g.filter((r) => r.status === "fail").length,
      skip: g.filter((r) => r.status === "skip").length,
    };
  };
  return {
    score: pct,
    band,
    applicable: total,
    tiers: {
      deterministic: tierStats("deterministic"),
      "plan-presence": tierStats("plan-presence"),
      animation: tierStats("animation"),
    },
  };
}
