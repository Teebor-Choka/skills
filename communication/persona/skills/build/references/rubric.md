# Judge rubric

The judge scores the generated message against the original, with TRAIN exemplars of the same
channel and band beside it. Each dimension gets 0 to 5 and one line of reason. The reason names a
feature (a habit, a length, a word class), never quotes the original.

| Dimension     | Question                                                                                          |
| ------------- | ------------------------------------------------------------------------------------------------- |
| `voice`       | Would someone who knows this person believe they wrote it? Word choice, rhythm, idiolect.         |
| `length`      | Is the length right for this person in this channel and band? A one-liner stays a one-liner.      |
| `register`    | Formality, casing and politeness right for this audience and channel.                             |
| `habit`       | Openers, closers, punctuation, emoji, signature phrases, at this person's rate, not more.         |
| `temperament` | Directness, hedging, humor, and the reaction (to news, a request, praise, disagreement) fit them. |

Scale, for every dimension:

| Score | Meaning                                                   |
| ----- | --------------------------------------------------------- |
| 5     | Indistinguishable from the person on this dimension.      |
| 4     | Close; one minor slip a careful reader might notice.      |
| 3     | Recognisably theirs, with a clear slip.                   |
| 2     | Generic: could be anyone; the person's marks are missing. |
| 1     | Wrong for this person: a habit they never show.           |
| 0     | Missing, unparseable, or caricature (habits overdone).    |

A mean of 3.5 (the default pass floor) means the dimensions sit between "recognisably theirs"
and "close". Caricature scores low on purpose: a message that stacks every signature phrase is a
worse imitation than a plain one.

## Identification

Before scoring, a separate blind call sees the exemplars, the point and the two messages as A and
B, and answers which one the person wrote, as JSON: `{"original": "A", "why": "..."}`.
