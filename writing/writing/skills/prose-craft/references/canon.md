# The canon behind the checklist

Why each rule earns its place. Read this when a fix is not obvious, or when you need to explain
a change to the author. Two sources, cited inline; full URLs in `sources.md`.

## Strunk and White: concision

_The Elements of Style_ argues one thing above all: a sentence should contain no unnecessary
words, a paragraph no unnecessary sentences, "for the same reason that a drawing should have no
unnecessary lines and a machine no unnecessary parts" (1918, Rule 13). The rules below are that
principle applied.

Rule numbers are from the public-domain 1918 edition (Strunk). "Use definite, specific,
concrete language" was added by White in the later editions and is marked as such.

- **Omit needless words** (Rule 13). The core discipline. Every word does work or it goes.
- **Use the active voice** (Rule 11). "Y Xed", not "X was done by Y". The active voice is
  shorter, and it names who acts.
- **Put statements in positive form** (Rule 12). Assert what is. "Dishonest", not "not honest".
- **Use definite, specific, concrete language** (White's addition, later editions). "A Toy
  poodle", not "an animal". The particular over the general, the tangible over the abstract.
- **Keep related words together** (Rule 16). Subject beside verb, modifier beside what it
  modifies. Distance between them is where ambiguity breeds.
- **Place the emphatic word at the end** (Rule 18). The stress position of a sentence is its
  end; put the word you want to land there.
- **Express coordinate ideas in parallel form** (Rule 15). Matched grammar signals matched
  ideas.
- **Avoid a succession of loose sentences** (Rule 14). Do not string clauses on and, but, so;
  subordinate and vary.
- **Make the paragraph the unit of composition** (Rules 9–10). One paragraph, one point,
  signaled by a topic sentence.
- **Keep to one tense in a summary** (Rule 17).
- **Do not overwrite; avoid qualifiers.** "Rather", "very", "little", "pretty" are, in White's
  phrase, "the leeches that infest the pond of prose".

## Pinker: classic style and the cognitive load of reading

_The Sense of Style_ grounds the same advice in how reading works. Three ideas do most of the
work.

### Classic style (ch. 2)

The writer directs the reader's gaze at something in the world. Prose is a window, not a
performance of the writer's own reasoning. In practice:

- **Show the reader something.** Frame each passage as pointing at a concrete thing or event,
  not as staging your thought process.
- **Cut metadiscourse.** "In this section I will argue", "it is important to note that", "as we
  shall see" talk about the text instead of the world. Delete them.
- **Drop reflexive hedging.** "Somewhat", "arguably", "in some sense" used as a shield against
  an imagined objector, not as a real statement of limits, is throat-clearing.
- **Address a competent equal.** No over-signposting, no lecturing a reader who does not need
  it.

### The curse of knowledge (ch. 3)

The single biggest cause of bad writing: the writer cannot un-know what they know, and so omits
the steps and names a novice would need. Defeat it by:

- **Naming the concrete thing.** Replace "the device", "the process", "the relevant factors"
  with what they actually are.
- **Killing nominalizations** (zombie nouns). A verb buried as a noun ("make a decision") hides
  the actor and the action; restore the verb ("decide").
- **Giving an example right after an abstraction.**
- **Spelling out the step you find too obvious to mention**, and defining jargon at first use
  or not using it.

### Syntactic architecture for working memory (ch. 4)

The reader parses a flat string of words into a tree in a limited memory. Help them:

- **Keep subject and verb close.** A long modifier stack between them forces the reader to hold
  the subject open while wading through it.
- **Put heavy, branching material at the end** (right-branching). Lead with a short subject and
  verb; hang the long stuff off the end. Deep left-branching and center-embedding (a clause
  inside a clause inside a clause) overrun memory.
- **Resolve every pronoun** to one unambiguous, recently named antecedent.
- **Prefer coordination over deep embedding.** Two sentences beat one nested monster.

### Coherence (ch. 4)

A text hangs together through arcs the reader can follow:

- **Given before new.** Start a sentence with the familiar, end with the novel. This threads
  sentences into a chain.
- **A consistent topic string.** Keep the same entity in subject position across a passage
  rather than switching what each sentence is about.
- **Explicit connectives.** State the logical relation; do not make the reader infer it.
- **The arc of coherence.** Every sentence visibly serves the point at the top of its section.

## Where craft ends and de-slopping begins

Everything above is positive construction: how to build a good sentence from intent. It would
be in this guide whether or not LLMs existed. It does not reference "AI", a banned-word list,
or a machine tell, and it must not grow one. That inventory is the `unslop` skill's job.

The line to hold:

- Craft owns the **principle** ("omit needless words", the classic-style stance against
  metadiscourse, the teaching on nominalizations and passive voice).
- `unslop` owns the **tell inventory** (specific overused tokens, the "not just X, but Y"
  antithesis, forced triads, "In conclusion" wrap-ups, emoji, sycophantic openers, the
  specific hedge phrases models overproduce, format tells like header sprawl and bolded label
  runs).

Where both touch a topic, state the principle here once and point to `unslop` for the list.
Do not copy the list into this guide.
