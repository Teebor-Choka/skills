// LLM-tier rubrics. These are NOT evaluated by the script — the runner emits a
// `llm_job` per row for the host agent (Claude) to judge against the slide text +
// notes it can already read. Verdicts are advisory and never enter the headline.
// One terse criterion per pattern; the agent returns {verdict, rationale, slideRefs}.
export const RUBRICS = {
  "abstract-attorney":
    "Does the delivered content match what the abstract / opening slide promises (no bait-and-switch)?",
  "narrative-arc":
    "Do the slides form a story (setup → tension → resolution), not a flat topic list?",
  triad:
    "Is the talk built around ~3 central ideas/acts, rather than a scattered dozen?",
  talklet:
    "Is the material composed of self-contained ~15–20 min segments that could stand alone?",
  "brain-breaks":
    "Are there deliberate re-engagement beats (demo, story, question) roughly every 10–20 min?",
  "cave-painting":
    "If a zoomable single-canvas (Prezi-style) structure is used, does it aid comprehension rather than disorient?",
  "unifying-visual-theme":
    "Is there one consistent visual theme tying the slides together (not a mishmash)?",
  "leet-grammars":
    "Is insider slang used to bond with this audience appropriately, not to alienate?",
  celery:
    "Is there real substance, or lots of chewing (filler) for little nutritional payoff?",
  "alienating-artifact":
    "Is any risqué/edgy content present that could disenfranchise part of the audience?",
  "analog-noise":
    "Do imperfection / hand-drawn touches add believable interest, used purposefully?",
  foreshadowing:
    "Is an idea seeded early and paid off later (a deliberate setup/callback)?",
  "greek-chorus":
    "Are seeded voices/personas used to interject perspective effectively?",
  "peer-review":
    "Is the copy clean — grammar, complete thoughts, active voice — as if peer-reviewed?",
  "borrowed-shoes":
    "Does the deck read as the speaker's own, or like someone else's talk being delivered?",
  "tower-of-babble":
    "Is jargon/TLA density pitched to the audience, or does unexplained technospeak obscure meaning?",
  "lipstick-on-a-pig":
    "Is there substantive insight, or attractive slides masking thin content?",
  entertainment:
    "Is entertainment seasoned in to serve the message, not drown it?",
  mentor:
    "Does the deck guide the audience like a tutor (scaffolded), rather than lecture over them?",
};

export function buildJob(row, deck) {
  return {
    id: row.id,
    name: row.name,
    type: row.type,
    tier: "llm",
    file: row.file,
    rubric:
      RUBRICS[row.id] ||
      `Does the deck exhibit "${row.name}"? See references/${row.file}.`,
    inputs: {
      titles: deck.slides.map((s) => s.title),
      slideTexts: deck.slides.map((s) =>
        s.paragraphs
          .map((p) => p.text)
          .join(" ")
          .trim(),
      ),
      notes: deck.slides.map((s) => s.notes),
    },
    scale: "conforms | partial | violates | na",
    output_contract: "return { verdict, rationale, slideRefs: [] }",
  };
}
