# The uml launcher

`./uml` at the repo root starts uml-viewer, which draws the project and reads `.metrics/crap.edn`. It is a POSIX `sh` script, so it runs on a machine with no zsh. It finds the viewer checkout at `$UML_VIEWER_ROOT`, or at `../uml-viewer` next to the launcher, and starts it in the background with `clojure`, writing `uml-viewer-log.txt` beside the launcher. `--restart` also hands the viewer an example diagram from `examples/`.

## Sub-features

- `uml-missing-viewer` the viewer checkout is missing: exit 1 and `uml-viewer checkout not found at <path>` on stderr.
- `uml-help` `--help` prints the usage on stderr and exits 0.
- `uml-restart` `--restart` hands the viewer `examples/<folder name>.edn` when it exists, else the first `examples/*.edn` that isn't `*.policy.edn`, else no file.
- `uml-args` any other arguments reach the viewer unchanged.
- `uml-posix` `shellcheck --shell=sh uml` reports nothing.

## How to get to it (user POV)

- Run `./uml`, `./uml --help`, or `./uml --restart` from the folder that holds the launcher.

## Driving it with verify-crapper

The real viewer is a GUI on the JVM, so a drive puts a fake `clojure` first on `PATH`. It writes the arguments it got to `args`, one per line. The launcher runs from a copy in a folder whose name has a space, and the viewer checkout's name has one too.

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `zsh` is not installed, or the drive proves nothing about it: `command -v zsh` prints nothing, and `/bin/zsh` doesn't exist.
- `project=$($vc project typescript)`. `T` is the transcript path for the feature.
- Make the folders and the fake: `$vc exec "$project" "$T" sh -c 'mkdir -p "my project/examples" "uml viewer" bin && cp "$1" "my project/uml" && printf "%s\n" "#!/bin/sh" "printf \"%s\\\\n\" \"\$@\" > args" > bin/clojure && chmod +x bin/clojure' sh "$PWD/uml"`, from the repo root.
- `run` below is `$vc exec "$project" "$T" sh -c 'cd "my project" && PATH="$0/bin:/usr/bin:/bin" UML_VIEWER_ROOT="$0/uml viewer" ./uml "$@"' "$project"`, followed by the launcher's arguments.
- `args` below is `$vc exec "$project" "$T" sh -c 'n=0; while [ ! -f "my project/args" ] && [ $n -lt 50 ]; do sleep 0.1; n=$((n+1)); done; cat "my project/args" && rm "my project/args"'`. The launcher starts the fake in the background, so this waits for it, and it exits 1 when the fake never ran.

- **uml-missing-viewer.** Run `$vc exec "$project" "$T" sh -c 'cd "my project" && UML_VIEWER_ROOT="$0/no viewer" ./uml' "$project"`. Pass: exit `1`, and stderr says `uml-viewer checkout not found at <project>/no viewer`.
- **uml-help.** `run --help`. Pass: exit `0`, and stderr starts with `usage: ./uml [--restart]`.
- **uml-restart.** Add `examples/a.edn` and `examples/my project.edn` (`$vc exec "$project" "$T" touch "my project/examples/a.edn" "my project/examples/my project.edn"`), then `run --restart` and `args`. Pass: exit `0`, stdout `UML viewer started (pid <n>). Log: uml-viewer-log.txt`, and `args` ends with `--restart` and `examples/my project.edn`, with `<project>/uml viewer` inside the `-Sdeps` line. Then remove `my project.edn`, add `examples/0.policy.edn`, `run --restart`, and `args`: it ends with `--restart` and `examples/a.edn`. With only `0.policy.edn` left, it ends with `--restart` alone.
- **uml-args.** `run diagram.edn "two words"`, then `args`. Pass: the lines after `uml-viewer.main.uml-viewer` are `diagram.edn` and `two words`.
- **uml-posix.** `$vc exec "$project" "$T" shellcheck --shell=sh "$PWD/uml"`, from the repo root. Pass: exit `0` and no output. CI runs the same check.

## Gotchas

- The launcher writes `uml-viewer-log.txt` next to itself, so a drive of the repo's own `./uml` would write in the checkout. Drive the copy.
- `/bin/sh` is bash on some machines and dash on others. bash accepts constructs that dash rejects, so `uml-posix` is the check for those, not a passing drive.
- The transcript's coverage-report and snapshot sections don't apply to this feature; read stdout, stderr, the exit code, and `args`.
