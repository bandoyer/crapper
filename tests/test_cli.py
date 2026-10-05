import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from crapper.cli import HELP, GitError, _changed_files, _positionals, _take, main, parse_args, run
from crapper.discover import is_test_file, language_of


def test_language_detection():
    assert language_of("src/app/core.clj") == "clojure"
    assert language_of("src/app/core.cljc") == "clojure"
    assert language_of("Widget.java") == "java"
    assert language_of("board.go") == "go"
    assert language_of("ui/view.tsx") == "typescript"
    assert language_of("src/app.js") == "typescript"
    assert language_of("src/app.mjs") == "typescript"
    assert language_of("src/app.cjs") == "typescript"
    assert language_of("src/app.jsx") == "typescript"
    assert language_of("src/lib.rs") == "rust"
    assert language_of("src/crapper/cli.py") == "python"
    assert language_of("types.d.ts") is None
    assert language_of("notes.md") is None
    assert language_of("app.cts") == "typescript"
    assert language_of("app.test.cts") == "typescript"
    assert is_test_file("app.test.cts") is True
    assert is_test_file("app.spec.cts") is True
    assert is_test_file("app.cts") is False


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


class _Completed:
    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _git_status(root: Path, status: str):
    def fake(args, **_kwargs):
        if "rev-parse" in args:
            return _Completed(0, f"{root.resolve()}\n")
        return _Completed(0, status)

    return fake


def test_project_snapshot_is_readable_as_crap4clj_edn(tmp_path):
    _write(
        tmp_path,
        "src/demo/core.clj",
        "(ns demo.core)\n\n(defn choose [x]\n  (if x 1 0))\n",
    )
    _write(
        tmp_path,
        "src/demo/Board.java",
        "package demo;\npublic class Board {\n  public int place(int x) {\n    if (x > 0 && ready) return 1;\n    return 0;\n  }\n}\n",
    )
    _write(
        tmp_path,
        "board.go",
        "package demo\n\nfunc Place(x int) int {\n\tif x > 0 {\n\t\treturn x\n\t}\n\treturn 0\n}\n",
    )
    _write(
        tmp_path,
        "src/ui/view.ts",
        "export function view(ok: boolean): number {\n  return ok ? 1 : 0;\n}\n",
    )
    _write(tmp_path, "Cargo.toml", '[package]\nname = "demo"\nversion = "0.1.0"\n')
    _write(
        tmp_path,
        "src/lib.rs",
        "pub fn open(ok: bool) -> i32 { if ok { 1 } else { 0 } }\n",
    )
    _write(tmp_path, "src/demo/core_test.clj", "(ns demo.core-test)\n(defn should-skip [] 1)\n")
    _write(tmp_path, "board_test.go", "package demo\nfunc TestPlace(t *testing.T) {}\n")

    code = run(["--root", str(tmp_path), "--no-coverage"])
    assert code == 0
    text = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ':namespace "demo.core"' in text
    assert ':name "choose"' in text
    assert ':namespace "demo.Board"' in text
    assert ':name "place"' in text
    assert ':namespace "demo"' in text and ':name "Place"' in text
    assert ':namespace "ui.view"' in text
    assert ':namespace "demo"' in text and ':name "open"' in text
    assert "should-skip" not in text
    assert "TestPlace" not in text

    reader = subprocess.run(
        [
            "bb",
            "-e",
            (
                "(require '[clojure.edn :as edn])"
                "(let [data (edn/read-string (slurp *in*))]"
                " (doseq [entry (:entries data)]"
                "   (println (:namespace entry) (:name entry)"
                "            (:complexity entry) (pr-str (:coverage entry)))))"
            ),
        ],
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    assert reader.returncode == 0, reader.stderr
    assert "demo.core choose 2 nil" in reader.stdout
    assert "demo.Board place 3 nil" in reader.stdout


def test_existing_coverage_feeds_the_snapshot(tmp_path):
    _write(
        tmp_path,
        "src/demo/core.clj",
        "(ns demo.core)\n\n(defn choose [x]\n  (if x 1 0))\n",
    )
    lcov = tmp_path / "target" / "coverage" / "lcov.info"
    lcov.parent.mkdir(parents=True)
    lcov.write_text(
        "SF:src/demo/core.clj\nDA:3,1\nDA:4,1\nend_of_record\n",
        encoding="utf-8",
    )
    code = run(
        ["--root", str(tmp_path), "--use-existing-coverage", "src/demo/core.clj"]
    )
    assert code == 0
    text = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ":coverage 100.0" in text
    assert ":crap 2.0" in text


def test_threshold_exits_when_the_worst_score_is_too_high(tmp_path):
    _write(tmp_path, "src/demo/core.clj", "(ns demo.core)\n\n(defn choose [x]\n  (if x 1 0))\n")
    lcov = tmp_path / "target" / "coverage" / "lcov.info"
    lcov.parent.mkdir(parents=True)
    lcov.write_text("SF:src/demo/core.clj\nDA:3,0\nDA:4,0\nend_of_record\n", encoding="utf-8")
    code = run(
        [
            "--root",
            str(tmp_path),
            "--use-existing-coverage",
            "--threshold",
            "1",
        ]
    )
    assert code == 2


def test_help_and_unknown_option(capsys):
    assert run(["--help"]) == 0
    help_text = capsys.readouterr().out
    assert "uml-viewer" in help_text
    assert ".clj-kondo" in help_text
    assert ".test.cts" in help_text
    assert run(["--not-an-option"]) == 1
    assert run(["--root"]) == 1
    assert run(["--threshold", "nope"]) == 1
    assert run(["--no-coverage", "--coverage-command", "true"]) == 1


def test_selects_directories_filters_and_changed_files(tmp_path, monkeypatch, capsys):
    _write(tmp_path, "src/demo/core.clj", "(ns demo.core)\n\n(defn choose [x]\n  (if x 1 0))\n")
    _write(tmp_path, "notes.md", "not source\n")
    assert run(["--root", str(tmp_path), "--no-coverage", "--source-root", "src"]) == 0
    assert run(["--root", str(tmp_path), "--no-coverage", "src"]) == 0
    assert run(["--root", str(tmp_path), "--no-coverage", "src/demo/core.clj", "core"]) == 0
    assert run(["--root", str(tmp_path), "--no-coverage", "notes.md"]) == 0
    assert "No source files" in capsys.readouterr().out

    monkeypatch.setattr(
        "crapper.cli.subprocess.run",
        _git_status(tmp_path, " M src/demo/core.clj\0"),
    )
    assert run(["--root", str(tmp_path), "--no-coverage", "--changed"]) == 0
    assert ':name "choose"' in (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")

    monkeypatch.setattr(
        "crapper.cli.subprocess.run",
        lambda *_args, **_kwargs: _Completed(128, "", "fatal: not a git repository"),
    )
    assert run(["--root", str(tmp_path), "--no-coverage", "--changed"]) == 128
    captured = capsys.readouterr()
    assert "not a git repository" in captured.err
    assert "No source files" not in captured.out
    assert ':name "choose"' in (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")


def test_run_asks_for_coverage_when_it_is_enabled(tmp_path, monkeypatch):
    _write(tmp_path, "src/demo/core.clj", "(ns demo.core)\n\n(defn choose [x]\n  x)\n")
    called = []
    monkeypatch.setattr("crapper.cli.run_coverage", lambda *args: called.append(args))
    assert run(["--root", str(tmp_path), "--coverage-command", "true"]) == 0
    assert called


def test_empty_option_value_is_rejected():
    with pytest.raises(ValueError, match="requires a value"):
        _take(["ok", "--opt", ""], 1, "--opt")
    with pytest.raises(ValueError, match="requires a value"):
        _take(["--opt", "-1"], 0, "--opt")


def test_parse_args_reads_the_process_arguments_after_the_program(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["crapper", "--threshold", "5"])
    options = parse_args()
    assert options.threshold == 5.0
    assert options.positionals == []
    assert options.action == "analyze"


def test_every_number_option_in_the_help_rejects_values_that_are_not_finite():
    numbers = re.findall(r"^  (--[\w-]+) <number>", HELP, re.MULTILINE)
    assert "--threshold" in numbers
    largest_finite, past_it = "1.79769313486231580793e308", "1.79769313486231580794e308"
    for option in numbers:
        for value in ["nan", "inf", "+inf", "1e309", past_it, "abc"]:
            options = parse_args([option, value])
            assert options.exit_code == 1, (option, value)
            assert options.message.startswith(f"{option} requires a finite number\n"), (option, value)
    assert parse_args(["--threshold", "0"]).threshold == 0.0
    assert parse_args(["--threshold", largest_finite]).threshold == float(largest_finite)


def test_flags_that_only_store_a_boolean():
    assert parse_args(["--use-existing-coverage"]).use_existing_coverage is True
    assert parse_args(["--changed"]).changed is True
    assert parse_args(["--no-coverage"]).no_coverage is True
    conflict = parse_args(["--no-coverage", "--coverage-command", "true"])
    assert conflict.exit_code == 1


def test_changed_files_follow_git_status(tmp_path, monkeypatch, capsys):
    seen = {}
    named = tmp_path / "x"
    named.write_text("x", encoding="utf-8")
    keep = tmp_path / "sources" / "keep.py"
    keep.parent.mkdir()
    keep.write_text("x = 1\n", encoding="utf-8")

    def fake(args, **kwargs):
        seen["args"] = args
        seen.update(kwargs)
        if "rev-parse" in args:
            return _Completed(0, f"{tmp_path.resolve()}\n")
        return _Completed(0, " M x\0?? sources/keep.py\0")

    monkeypatch.setattr("crapper.cli.subprocess.run", fake)
    found = _changed_files(tmp_path)
    assert seen["check"] is False
    assert seen["capture_output"] is True
    assert seen["text"] is True
    assert seen["encoding"] == "utf-8"
    assert "-z" in seen["args"]
    assert "--no-renames" in seen["args"]
    assert "--untracked-files=all" in seen["args"]
    assert found == [named.resolve(), keep.resolve()]

    monkeypatch.setattr(
        "crapper.cli.subprocess.run",
        lambda *_a, **_k: _Completed(1, "", "git failed"),
    )
    with pytest.raises(GitError, match="git failed") as failed:
        _changed_files(tmp_path)
    assert failed.value.code == 1
    assert capsys.readouterr().err == ""

    monkeypatch.setattr(
        "crapper.cli.subprocess.run",
        lambda *_a, **_k: _Completed(128, "", ""),
    )
    with pytest.raises(GitError, match="git status failed") as silent:
        _changed_files(tmp_path)
    assert silent.value.code == 128


def test_relative_paths_are_resolved_under_the_project_root(tmp_path):
    _write(tmp_path, "src/demo/core.clj", "(ns demo.core)\n\n(defn choose [x]\n  (if x 1 0))\n")
    existing, filters = _positionals(tmp_path, ["src/demo/core.clj"])
    assert existing == [(tmp_path / "src/demo/core.clj").resolve()]
    assert filters == []
    assert run(["--root", str(tmp_path), "--no-coverage", "src/demo/core.clj"]) == 0
    text = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ':name "choose"' in text
    assert "parse_args" not in text


def test_changed_selection_ignores_files_git_did_not_name(tmp_path, monkeypatch, capsys):
    _write(tmp_path, "src/kept.clj", "(ns demo.kept)\n\n(defn kept [] 1)\n")
    _write(tmp_path, "src/other.clj", "(ns demo.other)\n\n(defn other [] 1)\n")

    monkeypatch.setattr(
        "crapper.cli.subprocess.run",
        _git_status(tmp_path, "?? src/kept.clj\0"),
    )
    assert run(["--root", str(tmp_path), "--no-coverage", "--changed"]) == 0
    text = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ':name "kept"' in text
    assert "other" not in text
    assert "No source files" not in capsys.readouterr().out


def test_threshold_equal_to_the_score_is_allowed(tmp_path):
    _write(tmp_path, "src/demo/core.clj", "(ns demo.core)\n\n(defn choose [] 1)\n")
    lcov = tmp_path / "target" / "coverage" / "lcov.info"
    lcov.parent.mkdir(parents=True)
    lcov.write_text("SF:src/demo/core.clj\nDA:1,1\nDA:3,1\nend_of_record\n", encoding="utf-8")
    code = run(
        ["--root", str(tmp_path), "--use-existing-coverage", "--threshold", "1", "src/demo/core.clj"]
    )
    assert code == 0


def test_threshold_with_no_scores_does_not_call_max_on_an_empty_list(tmp_path):
    _write(tmp_path, "src/demo/core.clj", "(ns demo.core)\n\n(defn choose [] 1)\n")
    assert run(["--root", str(tmp_path), "--no-coverage", "--threshold", "1"]) == 0


def test_a_failed_coverage_command_ignores_a_stale_report(tmp_path, monkeypatch):
    _write(tmp_path, "src/demo/core.clj", "(ns demo.core)\n\n(defn choose [x]\n  (if x 1 0))\n")
    lcov = tmp_path / "target" / "coverage" / "lcov.info"
    lcov.parent.mkdir(parents=True)
    lcov.write_text("SF:src/demo/core.clj\nDA:3,1\nDA:4,1\nend_of_record\n", encoding="utf-8")
    monkeypatch.setattr("crapper.cli.run_coverage", lambda *_args, **_kwargs: 3)
    code = run(
        ["--root", str(tmp_path), "--coverage-command", "exit 3", "src/demo/core.clj"]
    )
    assert code == 0
    text = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ":coverage 0.0" in text
    assert ":crap 6.0" in text

    monkeypatch.setattr("crapper.cli.run_coverage", lambda *_args, **_kwargs: 0)
    assert run(
        ["--root", str(tmp_path), "--coverage-command", "true", "src/demo/core.clj"]
    ) == 0
    text = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ":coverage 100.0" in text


_TS_PROJECT = {
    "package.json": '{"scripts": {"coverage": "vitest run --coverage"}}\n',
    "src/clock.ts": "export function tick(): number { return 1 }\n",
}
_PY_PROJECT = {
    "pyproject.toml": "[project]\nname = 'clock'\n",
    "src/clock.py": "def tick():\n    return 1\n",
}
_RS_PROJECT = {
    "Cargo.toml": "[package]\nname = 'clock'\n",
    "src/lib.rs": "pub fn tick() -> i32 { 1 }\n",
}


def _use_real_coverage(monkeypatch, shell, which=lambda _name: None):
    """Run the real collectors with commands and tool lookup faked at the process boundary."""

    from crapper import runners

    monkeypatch.setattr("crapper.cli.run_coverage", runners.run_coverage)
    monkeypatch.setattr("crapper.cli.collect_coverage", runners.collect_coverage)
    monkeypatch.setattr("crapper.runners.run_shell", shell)
    monkeypatch.setattr("crapper.runners.shutil.which", which)


@pytest.mark.parametrize(
    ("project", "stale", "source", "exit_code", "which"),
    [
        pytest.param(_TS_PROJECT, "coverage/lcov.info", "src/clock.ts", 1, None, id="ts-script-fails"),
        pytest.param(_TS_PROJECT, "coverage/lcov.info", "src/clock.ts", 0, None, id="ts-script-writes-nothing"),
        pytest.param(
            {**_TS_PROJECT, "package.json": '{"scripts": {}}\n'},
            "target/coverage/typescript/lcov.info",
            "src/clock.ts",
            0,
            None,
            id="ts-no-test-script",
        ),
        pytest.param(
            _PY_PROJECT, "target/coverage/python/lcov.info", "src/clock.py", 1, None, id="python-coverage-missing"
        ),
        pytest.param(
            _RS_PROJECT,
            "target/coverage/rust/lcov.info",
            "src/lib.rs",
            1,
            "cargo-llvm-cov",
            id="rust-llvm-cov-fails",
        ),
        pytest.param(_RS_PROJECT, "target/coverage/rust/lcov.info", "src/lib.rs", 127, None, id="rust-no-tool"),
    ],
)
def test_a_report_this_run_did_not_write_scores_zero(
    tmp_path, monkeypatch, project, stale, source, exit_code, which
):
    for relative, text in project.items():
        _write(tmp_path, relative, text)
    _write(tmp_path, stale, f"SF:{source}\nDA:1,1\nLF:1\nLH:1\nend_of_record\n")
    _use_real_coverage(
        monkeypatch,
        lambda _command, _cwd: exit_code,
        lambda name: which if name == which else None,
    )
    assert run(["--root", str(tmp_path)]) == 0
    text = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ':name "tick"' in text
    assert ":coverage 0.0, :crap 2.0" in text


def test_a_report_this_run_wrote_is_read(tmp_path, monkeypatch):
    for relative, text in _TS_PROJECT.items():
        _write(tmp_path, relative, text)
    _write(tmp_path, "coverage/lcov.info", "SF:src/clock.ts\nDA:1,0\nLF:1\nLH:0\nend_of_record\n")

    def coverage_script(command, cwd):
        assert command == ["npm", "run", "coverage"]
        _write(cwd, "coverage/lcov.info", "SF:src/clock.ts\nDA:1,1\nLF:1\nLH:1\nend_of_record\n")
        return 0

    _use_real_coverage(monkeypatch, coverage_script)
    assert run(["--root", str(tmp_path)]) == 0
    text = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ":coverage 100.0, :crap 1.0" in text


_JACOCO = (
    '<report name="demo"><package name="demo"><class name="demo/Clock">'
    '<method name="tick" desc="()I" line="4"><counter type="INSTRUCTION" missed="0" covered="2"/>'
    "</method></class></package></report>\n"
)
_TWO_FN_LIB = "pub fn tick() -> i32 {\n    1\n}\n\npub fn tock() -> i32 {\n    2\n}\n"
_GO_TICK = "package clock\n\nfunc Tick() int {\n\treturn 1\n}\n"
_JAVA_TICK = "package demo;\n\npublic class Clock {\n    public int tick() {\n        return 1;\n    }\n}\n"


def _fake_tools(command, cwd):
    """Each coverage tool, writing its report where its command line says. Every test hits."""

    cwd = Path(cwd)
    if command[:2] == ["cargo", "llvm-cov"]:
        source = cwd / "src" / "lib.rs"
        lines = "".join(f"DA:{line},{int(line < 4)}\n" for line in (1, 2, 3, 5, 6, 7))
        Path(command[-1]).write_text(f"SF:{source}\n{lines}end_of_record\n", encoding="utf-8")
    elif command[:2] == ["go", "test"]:
        module = (cwd / "go.mod").read_text(encoding="utf-8").split()[1]
        profile = Path(command[-1].split("=", 1)[1])
        profile.write_text(f"mode: set\n{module}/clock.go:3.17,5.2 1 1\n", encoding="utf-8")
    elif command[0] == "mvn":
        _write(cwd, "target/site/jacoco/jacoco.xml", _JACOCO)
    elif command == ["npm", "run", "coverage"]:
        _write(cwd, "coverage/lcov.info", "SF:src/clock.ts\nDA:1,1\nend_of_record\n")
    elif command[1:4] == ["-m", "coverage", "run"]:
        Path(command[4].split("=", 1)[1]).touch()
    elif command[1:4] == ["-m", "coverage", "lcov"]:
        hit = int((cwd / "test_core.py").is_file())
        Path(command[-1]).write_text(f"SF:src/core.py\nDA:1,{hit}\nDA:2,{hit}\nend_of_record\n", encoding="utf-8")
    return 0


_RUST_LEFTOVER = {
    "Cargo.toml": "[package]\nname = 'clock'\n",
    "src/lib.rs": _TWO_FN_LIB,
    "coverage/lcov.info": "SF:src/lib.rs\nDA:5,1\nDA:6,1\nDA:7,1\nend_of_record\n",
}


@pytest.mark.parametrize(
    ("project", "llvm_cov", "want"),
    [
        pytest.param(_RUST_LEFTOVER, True, {"tick": 100.0, "tock": 0.0}, id="rust-leftover"),
        pytest.param(_RUST_LEFTOVER, False, {"tick": 0.0, "tock": 0.0}, id="rust-no-report"),
        pytest.param(
            {
                "one/pyproject.toml": "[project]\nname = 'one'\n",
                "one/src/core.py": "def left():\n    return 1\n",
                "one/test_core.py": "",
                "two/pyproject.toml": "[project]\nname = 'two'\n",
                "two/src/core.py": "def right():\n    return 2\n",
            },
            True,
            {"left": 100.0, "right": 0.0},
            id="python-two-pkgs",
        ),
        pytest.param(
            {
                "a/b/pyproject.toml": "[project]\nname = 'b'\n",
                "a/b/src/core.py": "def left():\n    return 1\n",
                "a__b/pyproject.toml": "[project]\nname = 'a__b'\n",
                "a__b/src/core.py": "def right():\n    return 2\n",
                "a__b/test_core.py": "",
            },
            True,
            {"left": 0.0, "right": 100.0},
            id="python-lookalike-folders",
        ),
        pytest.param(
            {
                "packages/app/package.json": '{"scripts": {"coverage": "sh coverage.sh"}}\n',
                "packages/app/src/clock.ts": "export function tick(): number { return 1 }\n",
            },
            True,
            {"tick": 100.0},
            id="ts-nested-pkg",
        ),
        pytest.param(
            {"a/b/c/go.mod": "module example.com/repo/a/b/c\n\ngo 1.21\n", "a/b/c/clock.go": _GO_TICK},
            True,
            {"Tick": 100.0},
            id="go-deep-module",
        ),
        pytest.param(
            {"clock.go": _GO_TICK, "coverage.out": "mode: set\nexample.com/clock/clock.go:3.17,5.2 1 1\n"},
            True,
            {"Tick": 0.0},
            id="go-no-module",
        ),
        pytest.param(
            {"a/b/c/pom.xml": "<project/>\n", "a/b/c/src/main/java/demo/Clock.java": _JAVA_TICK},
            True,
            {"tick": 100.0},
            id="java-deep-module",
        ),
        pytest.param(
            {"src/main/java/demo/Clock.java": _JAVA_TICK, "target/site/jacoco/jacoco.xml": _JACOCO},
            True,
            {"tick": 0.0},
            id="java-no-pom",
        ),
    ],
)
def test_a_default_run_reads_only_the_reports_its_collectors_wrote(tmp_path, monkeypatch, project, llvm_cov, want):
    for relative, text in project.items():
        _write(tmp_path, relative, text)
    _use_real_coverage(
        monkeypatch, _fake_tools, lambda name: name if llvm_cov and name == "cargo-llvm-cov" else None
    )
    monkeypatch.chdir(tmp_path)
    assert run(["--root", str(tmp_path)]) == 0
    assert _snapshot_scores(tmp_path) == want
    for relative in project:
        assert (tmp_path / relative).is_file(), f"{relative} was deleted"


def _snapshot_scores(root: Path) -> dict[str, float]:
    text = (root / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    return {name: float(value) for name, value in re.findall(r':name "(\w+)".*?:coverage ([\d.]+)', text)}


_PY_CLOCK = "def tick():\n    return 1\n\n\ndef tock():\n    return 2\n"
_PY_TEST_TICK = "\n\ndef test_tick():\n    assert tick() == 1\n"
_PY_ROOT_TESTS = "[tool.pytest.ini_options]\ntestpaths = ['.']\n"


@pytest.mark.parametrize(
    ("project", "want"),
    [
        pytest.param(
            {
                "pyproject.toml": _PY_ROOT_TESTS,
                "demo.py": _PY_CLOCK,
                "extra.py": "def unused():\n    return 3\n",
                "test_demo.py": "from demo import tick" + _PY_TEST_TICK,
            },
            {"tick": 100.0, "tock": 50.0, "unused": 0.0},
            id="flat",
        ),
        pytest.param(
            {
                "pyproject.toml": _PY_ROOT_TESTS,
                "demo.py": _PY_CLOCK,
                "gears/__init__.py": "",
                "gears/spin.py": "def spin():\n    return 3\n",
                "test_both.py": "from demo import tick\nfrom gears.spin import spin"
                + _PY_TEST_TICK
                + "\n\ndef test_spin():\n    assert spin() == 3\n",
            },
            {"tick": 100.0, "tock": 50.0, "spin": 100.0},
            id="mixed",
        ),
        pytest.param(
            {
                "pyproject.toml": _PY_ROOT_TESTS,
                "make-report.py": _PY_CLOCK,
                "test_report.py": "import importlib.util\n\n"
                'spec = importlib.util.spec_from_file_location("make_report", "make-report.py")\n'
                "report = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(report)\n"
                "tick = report.tick" + _PY_TEST_TICK,
            },
            {"tick": 100.0, "tock": 50.0},
            id="script",
        ),
        pytest.param(
            {
                "pyproject.toml": "[tool.pytest.ini_options]\npythonpath = ['src']\n",
                "src/demo.py": _PY_CLOCK,
                "tests/test_demo.py": "from demo import tick" + _PY_TEST_TICK,
            },
            {"tick": 100.0, "tock": 50.0},
            id="src",
        ),
        pytest.param(
            {
                "pyproject.toml": "[tool.pytest.ini_options]\npythonpath = ['.']\n",
                "clock/__init__.py": "",
                "clock/hands.py": _PY_CLOCK,
                "tests/test_clock.py": "from clock.hands import tick" + _PY_TEST_TICK,
            },
            {"tick": 100.0, "tock": 50.0},
            id="package",
        ),
        pytest.param(
            {
                "pyproject.toml": "[tool.pytest.ini_options]\npythonpath = ['a,b']\n",
                "a,b/demo.py": _PY_CLOCK,
                "tests/test_demo.py": "from demo import tick" + _PY_TEST_TICK,
            },
            {"tick": 100.0, "tock": 50.0},
            id="comma-folder",
        ),
    ],
)
def test_a_default_run_measures_python_in_each_layout(tmp_path, monkeypatch, project, want):
    """Real coverage.py decides what --source means: a file at the root is measured (#3)."""

    from crapper import runners

    for relative, text in project.items():
        _write(tmp_path, relative, text)
    _write(tmp_path, ".venv/bin/python", f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    (tmp_path / ".venv" / "bin" / "python").chmod(0o755)
    _use_real_coverage(monkeypatch, runners.run_shell, shutil.which)
    monkeypatch.chdir(tmp_path)
    assert run(["--root", str(tmp_path)]) == 0
    assert _snapshot_scores(tmp_path) == want


_SPLIT_LIB = (
    "pub fn tick() -> i32 {\n    1\n}\n\n"
    "pub fn tock() -> i32 {\n    2\n}\n\n"
    "pub fn idle() -> i32 {\n    3\n}\n\n"
    "pub fn pick(flag: bool) -> i32 {\n    if flag { 1 } else { 2 }\n}\n"
)


def _llvm_cov_record(source: Path, tick: int, tock: int, taken: tuple[str, str]) -> str:
    """One LCOV record shaped like cargo-llvm-cov's: absolute SF, DA for every line, --branch BRDA."""

    hits = {1: tick, 2: tick, 3: tick, 5: tock, 6: tock, 7: tock, 9: 0, 10: 0, 11: 0, 13: 1, 14: 1, 15: 1}
    lines = [f"SF:{source}"]
    lines += [f"DA:{line},{hit}" for line, hit in hits.items()]
    lines += [f"BRDA:14,0,0,{taken[0]}", f"BRDA:14,0,1,{taken[1]}", "end_of_record"]
    return "\n".join(lines) + "\n"


def _scores_from_split_runs(root: Path, placement: str, unit: str, integration: str) -> dict[str, float]:
    _write(root, "Cargo.toml", "[package]\nname = 'clock'\n")
    _write(root, "src/lib.rs", _SPLIT_LIB)
    if placement == "one-report":
        _write(root, "target/coverage/rust/lcov.info", unit + integration)
    else:
        _write(root, "target/coverage/rust/unit/lcov.info", unit)
        _write(root, "target/coverage/rust/integration/lcov.info", integration)
    assert run(["--root", str(root), "--use-existing-coverage"]) == 0
    return _snapshot_scores(root)


@pytest.mark.parametrize("placement", ["one-report", "two-reports"])
def test_records_for_the_same_file_combine(tmp_path, placement):
    source = (tmp_path / "src" / "lib.rs").resolve()
    unit = _llvm_cov_record(source, tick=0, tock=1, taken=("1", "0"))
    integration = _llvm_cov_record(source, tick=1, tock=0, taken=("0", "1"))
    scores = _scores_from_split_runs(tmp_path, placement, unit, integration)
    assert scores == {"tick": 100.0, "tock": 100.0, "idle": 0.0, "pick": 100.0}


@pytest.mark.parametrize("placement", ["one-report", "two-reports"])
def test_a_branch_taken_in_one_record_and_unreached_in_the_other_counts_once(tmp_path, placement):
    source = (tmp_path / "src" / "lib.rs").resolve()
    unit = _llvm_cov_record(source, tick=0, tock=1, taken=("1", "-"))
    integration = _llvm_cov_record(source, tick=1, tock=0, taken=("-", "1"))
    scores = _scores_from_split_runs(tmp_path, placement, unit, integration)
    assert scores["pick"] == 100.0


def _commit_all(root: Path) -> None:
    git = ["git", "-C", str(root)]
    subprocess.run([*git, "init"], check=True, capture_output=True)
    subprocess.run([*git, "config", "user.email", "t@example.com"], check=True)
    subprocess.run([*git, "config", "user.name", "t"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-m", "init"], check=True, capture_output=True)


def test_changed_files_from_a_real_git_status(tmp_path):
    keep = tmp_path / "keep.go"
    keep.write_text("package demo\nfunc Keep() int { return 1 }\n", encoding="utf-8")
    _commit_all(tmp_path)
    keep.unlink()
    cafe = tmp_path / "café.go"
    cafe.write_text("package demo\nfunc Cafe() int { return 1 }\n", encoding="utf-8")
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (fresh / "new.go").write_text("package demo\nfunc New() int { return 1 }\n", encoding="utf-8")

    assert run(["--root", str(tmp_path), "--no-coverage", "--changed"]) == 0
    text = (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ':name "Cafe"' in text
    assert ':name "New"' in text
    assert "Keep" not in text

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "inside.go").write_text("package pkg\nfunc Inside() int { return 1 }\n", encoding="utf-8")
    (tmp_path / "outside.go").write_text(
        "package demo\nfunc Outside() int { return 1 }\n",
        encoding="utf-8",
    )
    assert run(["--root", str(pkg), "--no-coverage", "--changed"]) == 0
    nested = (pkg / ".metrics" / "crap.edn").read_text(encoding="utf-8")
    assert ':name "Inside"' in nested
    assert "Outside" not in nested
    assert "Cafe" not in nested
    assert "New" not in nested


def test_changed_outside_a_repository_returns_gits_status(tmp_path, capsys):
    _write(tmp_path, "src/app.py", "def run():\n    return 1\n")
    code = run(["--root", str(tmp_path), "--no-coverage", "--changed"])
    assert code != 0
    captured = capsys.readouterr()
    assert "No source files" not in captured.out
    assert captured.err.strip()


OLD_SNAPSHOT = '{:entries [\n  {:name "alpha", :namespace "app", :complexity 1, :coverage nil, :crap nil}\n]}\n'


@pytest.mark.parametrize(
    "args",
    [[], ["no-such-path"], ["--changed"]],
    ids=["full", "filter", "changed"],
)
def test_a_run_with_no_source_files_empties_the_snapshot(tmp_path, capsys, args):
    _write(tmp_path, "src/app.py", "def alpha(xs):\n    return xs\n")
    _commit_all(tmp_path)
    if not args:
        (tmp_path / "src/app.py").unlink()
    _write(tmp_path, ".metrics/crap.edn", OLD_SNAPSHOT)
    assert run(["--root", str(tmp_path), *args]) == 0
    assert capsys.readouterr().out == "No source files to analyze.\n"
    assert (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8") == "{:entries []}\n"


# A stand-in for the Clojure CLI: it writes the arguments the launcher gave it.
FAKE_CLOJURE = '#!/bin/sh\nprintf "%s\\n" "$@" > "$UML_ARGS.tmp" && mv "$UML_ARGS.tmp" "$UML_ARGS"\n'


def _launch_uml(tmp_path, args, examples=(), viewer="uml viewer"):
    """Run a copy of ./uml from `tmp_path/my project`, with a fake clojure and no zsh on PATH."""
    project = tmp_path / "my project"
    project.mkdir()
    shutil.copy(Path(__file__).resolve().parents[1] / "uml", project / "uml")
    for name in examples:
        _write(project, f"examples/{name}", "{}\n")
    _write(tmp_path, "bin/clojure", FAKE_CLOJURE)
    (tmp_path / "bin" / "clojure").chmod(0o755)
    (tmp_path / "uml viewer").mkdir()
    return subprocess.run(
        ["./uml", *args],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin",
            "UML_VIEWER_ROOT": str(tmp_path / viewer),
            "UML_ARGS": str(tmp_path / "clojure-args"),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def _viewer_args(tmp_path):
    """The launcher starts clojure in the background, so wait for its arguments."""
    args_file = tmp_path / "clojure-args"
    deadline = time.monotonic() + 10
    while not args_file.exists():
        assert time.monotonic() < deadline, "the launcher never started clojure"
        time.sleep(0.05)
    args = args_file.read_text(encoding="utf-8").splitlines()
    assert f':local/root "{tmp_path / "uml viewer"}"' in args[args.index("-Sdeps") + 1]
    return args[args.index("uml-viewer.main.uml-viewer") + 1 :]


def test_uml_loader_rejects_a_missing_viewer(tmp_path):
    completed = _launch_uml(tmp_path, [], viewer="missing")
    assert completed.returncode == 1
    assert "uml-viewer checkout not found" in completed.stderr


def test_uml_loader_prints_its_usage(tmp_path):
    completed = _launch_uml(tmp_path, ["--help"])
    assert completed.returncode == 0
    assert completed.stderr.startswith("usage: ./uml [--restart]\n")


@pytest.mark.parametrize(
    ("examples", "chosen"),
    [
        (["a.edn", "my project.edn"], ["examples/my project.edn"]),
        (["a.policy.edn", "b.edn", "c.edn"], ["examples/b.edn"]),
        (["a.policy.edn"], []),
        ([], []),
        (["a\\c.edn"], ["examples/a\\c.edn"]),
    ],
    ids=["own-name", "skips-policy", "only-policy", "no-examples", "backslash"],
)
def test_uml_loader_restarts_the_viewer_on_an_example(tmp_path, examples, chosen):
    completed = _launch_uml(tmp_path, ["--restart"], examples)
    assert completed.returncode == 0, completed.stderr
    assert re.fullmatch(r"UML viewer started \(pid \d+\)\. Log: uml-viewer-log\.txt\n", completed.stdout)
    assert _viewer_args(tmp_path) == ["--restart", *chosen]
    log = (tmp_path / "my project" / "uml-viewer-log.txt").read_text(encoding="utf-8")
    assert log.splitlines()[0].endswith(" ".join(["starting uml-viewer --restart", *chosen]))


def test_uml_loader_passes_other_arguments_to_the_viewer(tmp_path):
    completed = _launch_uml(tmp_path, ["diagram.edn", "two words"])
    assert completed.returncode == 0, completed.stderr
    assert _viewer_args(tmp_path) == ["diagram.edn", "two words"]


def test_main_exits_with_the_status(monkeypatch):
    monkeypatch.setattr("crapper.cli.run", lambda _argv=None: 4)
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 4
    else:
        raise AssertionError("main did not exit")
