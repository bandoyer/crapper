# Score with existing coverage

`crapper --use-existing-coverage` reads the coverage reports already on disk and runs no coverage command. Nothing on disk is deleted.

## Sub-features

- `existing-read` scores a function from a report an earlier run left.
- `existing-keep` leaves that report in place.

## How to get to it (user POV)

- Run `crapper --use-existing-coverage` from the project root.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `project=$($vc project typescript-failing)` and `$vc stale "$project" coverage/lcov.info src/clock.ts`. `T` is the transcript path for the feature.

- **existing-read.** Run `$vc drive "$project" "$T" --use-existing-coverage`. Exit code `0`. stdout has no `> coverage` lines from npm, and the row reads `tick  clock  1 100.0%  1.0`.
- **existing-keep.** In the same transcript, reports after lists `./coverage/lcov.info` with the same two-days-ago time as reports before.

## Gotchas

- The `typescript-failing` fixture proves no coverage command ran: if one had, stderr would show `npm run coverage` and its exit 1.
