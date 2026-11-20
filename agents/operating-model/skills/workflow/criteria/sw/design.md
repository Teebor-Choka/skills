# Criteria: design

The judge passes the work only if every rule holds. Each rule names what it is judged against.

## Pass conditions

1. The design names the modules and the public contract of each. Judged against: the design document's modules section.
2. The design shows failure behaviour at every boundary. Judged against: the design document's failure section.
3. The design reuses existing code where it can and names it. Judged against: the design document and the repository.
4. The design is no larger than the acceptance tests need. Judged against: the design document and the acceptance tests.

## On a fail

The judge reports fail and states the number of the first rule that failed and the design section at fault. The judge adds one sentence on what would make it pass. An unreadable or missing input is a fail.
