# Threshold

`crapper --threshold <number>` exits 2 when the worst CRAP score is strictly above the number. The table and snapshot are still written.

## Sub-features

- `threshold-exceeded` exits 2 and names both scores.
- `threshold-met` exits 0 when no score is above the number.

## How to get to it (user POV)

- Run `crapper --threshold <number>` from the project root.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `project=$($vc project typescript)`. `T` is the transcript path for the feature.

- **threshold-exceeded.** Run `$vc drive "$project" "$T" --threshold 0.5`. Exit code `2`. stderr ends with `CRAP threshold exceeded: 1.0 > 0.5`.
- **threshold-met.** Run `$vc drive "$project" "$T" --threshold 1`. Exit code `0`, and stderr has no `threshold exceeded` line.

## Gotchas

- The comparison is strictly greater than: a score equal to the threshold passes.
