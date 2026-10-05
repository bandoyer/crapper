# Install with the lowest dependencies

`pyproject.toml` declares a lowest version for each dependency, such as `tree-sitter-language-pack>=1.12.5`. A user whose environment holds exactly those versions must get a working crapper. The `test (3.11, minimum)` row in `.github/workflows/ci.yml` runs the test suite this way; this recipe drives the CLI.

## Sub-features

- `install-minimum` crapper, run with every direct dependency at its declared lowest version on Python 3.11, parses and scores a function in each tree-sitter language.

## How to get to it (user POV)

- Install the dependencies at their lowest allowed versions, then run `crapper` in a project.

## Driving it with verify-crapper

Preconditions:

- `uv` is installed. It fetches Python 3.11 if the machine lacks it, and needs network access once.
- `project=$($vc project languages)`. `T` is the transcript path for the feature.

- **install-minimum.** From the repo root, build the environment outside the checkout, record what it holds, and run crapper from it:

  ```bash
  env=$(mktemp -d)
  uv venv --python 3.11 "$env/venv"
  VIRTUAL_ENV="$env/venv" uv pip install --resolution lowest-direct -r pyproject.toml
  $vc exec "$project" "$T" env VIRTUAL_ENV="$env/venv" uv pip freeze
  $vc exec "$project" "$T" env PYTHONPATH="$PWD/src" "$env/venv/bin/python" -m crapper --no-coverage
  ```

  Pass: the first transcript block lists `tree-sitter==` and `tree-sitter-language-pack==` at the floors in `pyproject.toml`. The second exits `0`, its table has five rows (`a` in `J`, `crate::r`, `p`, and `t`, and `A` in `p`), its `.metrics/crap.edn` has five entries, and stderr has no `Traceback`. Remove `$env` afterwards.

## Gotchas

- This recipe runs crapper through `exec`, not `drive`. `drive` runs `./crapper`, which always uses the checkout's `.venv` with current dependencies, so it can't test the floors.
- `-r pyproject.toml` installs only the dependencies, and `PYTHONPATH` runs this checkout's `src`, so nothing is written inside the checkout.
- The language pack downloads each grammar on first parse and caches it per pack version under `~/.cache/tree-sitter-language-pack/v<version>`.
