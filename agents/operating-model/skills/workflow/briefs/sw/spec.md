# Specify the item

Role: lead.

Turn the aligned brief into a specification that matches schemas/org/item.json.

## Rules

- Write each criterion as behaviour: when an event happens, the system does X, provided Y.
- Fill all five categories: valid inputs, expected outputs, failure definition, performance, dependency behaviour.
- State what is out of scope.
- Give every criterion a unique id.

## Output

Output one JSON object that validates against schemas/org/item.json. The spec-check script runs on it.
