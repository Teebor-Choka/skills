# Criteria: specification

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. Every criterion states a behaviour with an event, a result and a condition. Judged against: item.criteria[].text.
2. The five categories are filled with specific values, not placeholders. Judged against: item.valid_inputs, expected_outputs, failure_definition, performance, dependencies.
3. A reader could write a test for each criterion without asking a question. Judged against: item.criteria[].text.
4. Out-of-scope items are listed with a reason. Judged against: item.out_of_scope.
5. The ai_gap field names a specific behaviour a passing build could still get wrong. Judged against: item.ai_gap.

## On a fail

The judge reports fail and states the number of the first rule that failed and the criterion id or field at fault. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
