# Threshold

`crapper --threshold <number>` exits 2 when the worst CRAP score is strictly above the number. The table and snapshot are still written.

## Sub-features

- `threshold-exceeded` exits 2 and names both scores.
- `threshold-met` exits 0 when no score is above the number.
- `threshold-not-finite` rejects a threshold that is not a finite number, such as `nan`, `inf`, or `1e309`: a usage error before any analysis.

## How to get to it (user POV)

- Run `crapper --threshold <number>` from the project root.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `project=$($vc project typescript)`. `T` is the transcript path for the feature.

- **threshold-exceeded.** Run `$vc drive "$project" "$T" --threshold 0.5`. Exit code `2`. stderr ends with `CRAP threshold exceeded: 1.0 > 0.5`.
- **threshold-met.** Run `$vc drive "$project" "$T" --threshold 1`. Exit code `0`, and stderr has no `threshold exceeded` line.
- **threshold-not-finite.** On a new project, run `$vc drive "$project" "$T" --threshold <v>` for each of `nan`, `inf`, and `1e309`. Each: exit code `1`, stderr starts with `--threshold requires a finite number` followed by the help, stdout has no table, and the transcript shows no `.metrics/crap.edn`.

## Gotchas

- The comparison is strictly greater than: a score equal to the threshold passes.
- `0` is a valid threshold: every CRAP score is at least 1.0, so any scored function exceeds it.
- `1e309` is past the largest float, so `float()` reads it as infinity. No score is above NaN or infinity, which is why they are rejected (#11).
