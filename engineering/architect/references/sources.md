# Sources & credits

This skill was written from scratch. It draws on the works below for their **ideas, methodology,
and a few short attributed quotes** (the Ford "laws" and Fowler's monolith-first line, quoted under
fair use). It reproduces no substantial text from any of them. Standards are used **by reference**,
not by copying: arc42 is CC BY-SA and is referenced by concept only (the §11 Risks and §12 Glossary
ideas), never quoted; MADR is MIT; the RFCs are IETF documents whose normative keywords are standard
usage. The architecture-style scorecards in `architecture-styles.md` are factual data reconstructed
from the figures in _Fundamentals of Software Architecture_ and flagged where a cell is approximate.

## Design disciplines

- John Ousterhout, _A Philosophy of Software Design_ (deep modules, information hiding, the design
  red flags, "design it twice"). https://web.stanford.edu/~ouster/cgi-bin/aposd.php
- Mark Richards & Neal Ford, _Fundamentals of Software Architecture_, 1st ed. (O'Reilly, 2020),
  ISBN 978-1492043454, and 2nd ed. (2025), ISBN 978-1098175511:
  https://www.oreilly.com/library/view/fundamentals-of-software/9781492043454/
- Neal Ford, Rebecca Parsons, Patrick Kua & Pramod Sadalage, _Building Evolutionary Architectures_,
  2nd ed. (O'Reilly, 2022), ISBN 978-1492097549 (fitness functions):
  https://www.oreilly.com/library/view/building-evolutionary-architectures/9781492097532/
- Neal Ford, Mark Richards, Pramod Sadalage & Zhamak Dehghani, _Software Architecture: The Hard
  Parts_ (O'Reilly, 2021), ISBN 978-1492086895 (architecture quantum):
  https://www.oreilly.com/library/view/software-architecture-the/9781492086888/
- Mark Richards, _Developer to Architect_ (fitness-function lessons):
  https://developertoarchitect.com/lessons/

## Architecture styles

- Style catalog and trade-off scorecards: _Fundamentals of Software Architecture_, Part II (above).
- Martin Fowler, "MonolithFirst" (2015): https://martinfowler.com/bliki/MonolithFirst.html and
  "MicroservicePremium": https://martinfowler.com/bliki/MicroservicePremium.html

## Document standards (methodology.md)

- EARS requirement syntax (Alistair Mavin): https://alistairmavin.com/ears/
- RFC 2119 / RFC 8174 (normative keywords): https://www.rfc-editor.org/rfc/rfc2119 ·
  https://www.rfc-editor.org/rfc/rfc8174
- MADR (MIT): https://adr.github.io/madr/ · Michael Nygard, "Documenting Architecture Decisions"
  (2011): https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- Gherkin / Given-When-Then (Cucumber): https://cucumber.io/docs/gherkin/reference ·
  Gojko Adzic, _Specification by Example_: https://gojko.net/books/specification-by-example/
- arc42 (CC BY-SA, referenced by concept only): https://arc42.org/overview
- C4 model (Simon Brown): https://c4model.com/
- Topological sort / Kahn: https://en.wikipedia.org/wiki/Topological_sorting · critical path method:
  https://en.wikipedia.org/wiki/Critical_path_method · Python `graphlib`:
  https://docs.python.org/3/library/graphlib.html
- Kiro spec traceability: https://kiro.dev/docs/specs/feature-specs/

## Engineering guardrails

The research/adversarial/component-under-test disciplines echo standard testing practice (ATDD,
fault injection) and are stated in the author's own words in `principles.md` and `execution.md`.
