# Complexity only

`crapper --no-coverage` scores complexity only. Coverage and CRAP are `N/A` in the table and `nil` in the snapshot. No coverage command runs.

## Sub-features

- `no-coverage-na` prints `N/A` for coverage and CRAP.

## How to get to it (user POV)

- Run `crapper --no-coverage` from the project root.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `project=$($vc project typescript)`. `T` is the transcript path for the feature.

- **no-coverage-na.** Run `$vc drive "$project" "$T" --no-coverage`. Exit code `0`. The row reads `tick  clock  1   N/A  N/A`, and `.metrics/crap.edn` has `:coverage nil, :crap nil`. stderr has no `npm run coverage` line.

## Gotchas

- `--no-coverage` with `--coverage-command` is a usage error and exits `1`.
