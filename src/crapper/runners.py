"""Run each language's coverage tool, and list the reports it wrote for the loader.

Failures are reported and do not stop analysis. A language with no coverage
tool, or a failed run that wrote no report, scores its functions at 0%. A
failed run's report is still read, and its `Report.code` says the run failed.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from crapper.coverage import Report
from crapper.discover import is_test_file, language_of

_MAVEN = [
    "mvn",
    "-q",
    "org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent",
    "test",
    "org.jacoco:jacoco-maven-plugin:0.8.12:report",
]


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def _ran(language: str, module: Path, code: int, paths: list[Path]) -> list[Report]:
    """The reports at `paths` from a coverage run in `module` that exited `code`.

    A failed run that wrote a report has that report read, so the warning
    names it rather than claiming the language scores 0%.
    """

    if code != 0:
        written = [str(path) for path in paths if path.is_file()]
        if written:
            shown = written[0] + (f" and {len(written) - 1} more" if len(written) > 1 else "")
            _warn(
                f"{language} coverage exited {code} in {module}, but wrote {shown}. "
                "That coverage is read, and may miss lines the failed run never reached."
            )
        else:
            _warn(f"{language} coverage exited {code} in {module}. {language} coverage will score 0%.")
    return [Report(path, module, code) for path in paths]


def _show(command: str | list[str]) -> str:
    if isinstance(command, str):
        return command
    return " ".join(shlex.quote(part) for part in command)


def run_shell(command: str | list[str], cwd: Path) -> int:
    """Run a coverage command.

    A list is an argument vector and does not go through a shell, so a path
    with spaces or metacharacters stays one argument. A string is a command
    the user typed in `--coverage-command` and runs in a shell.
    """

    _warn(f"+ ({cwd}) {_show(command)}")
    try:
        if isinstance(command, str):
            completed = subprocess.run(command, cwd=cwd, shell=True)
        else:
            completed = subprocess.run(list(command), cwd=cwd)
    except OSError as exc:
        _warn(f"Coverage command failed to start: {exc}")
        return 127
    return completed.returncode


def _nearest(start: Path, marker: str, stop: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    stop = stop.resolve()
    while True:
        if (current / marker).is_file():
            return current
        if current == stop or current.parent == current:
            return None
        current = current.parent


def _clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


_COVERAGE_DIRS = {"typescript", "rust", "go", "python"}


def _outside_language_dirs(coverage: Path, path: Path) -> bool:
    relative = path.relative_to(coverage)
    if path.name in _COVERAGE_DIRS:
        return False
    return not _COVERAGE_DIRS.intersection(relative.parts)


def _cloverage_html(coverage: Path) -> list[Path]:
    """Cloverage's HTML under `coverage`, outside the other languages' folders."""

    return sorted(path for path in coverage.rglob("*.html") if _outside_language_dirs(coverage, path))


def _remove_cloverage_html(coverage: Path) -> None:
    for path in _cloverage_html(coverage):
        path.unlink()


def _remove_empty_dirs(coverage: Path) -> None:
    directories = [path for path in coverage.rglob("*") if path.is_dir()]
    for path in sorted(directories, reverse=True):
        if not _outside_language_dirs(coverage, path):
            continue
        try:
            path.rmdir()
        except OSError:
            continue


def _clean_clojure(root: Path) -> None:
    """Remove Cloverage's HTML and top-level lcov without touching other reports.

    Other languages keep their directories. Files that are not Cloverage HTML
    stay, including anything a project keeps under target/coverage itself.
    """

    coverage = root / "target" / "coverage"
    if not coverage.is_dir():
        return
    lcov = coverage / "lcov.info"
    if lcov.is_file():
        lcov.unlink()
    _remove_cloverage_html(coverage)
    _remove_empty_dirs(coverage)


_VITEST_CONFIGS = (
    "vitest.config.ts",
    "vitest.config.mts",
    "vitest.config.cts",
    "vitest.config.js",
    "vitest.config.mjs",
    "vitest.config.cjs",
)


class PackageJsonError(Exception):
    """package.json is present and cannot be read as an object."""


def _package_json(package: Path) -> dict | None:
    path = package / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackageJsonError(f"{path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise PackageJsonError(f"{path}: expected a JSON object")
    return data


def _uses_vitest(package: Path, scripts: dict) -> bool:
    if "vitest" in str(scripts.get("test", "")):
        return True
    return any((package / name).is_file() for name in _VITEST_CONFIGS)


def _vitest_version(package: Path) -> str | None:
    installed = package / "node_modules" / "vitest" / "package.json"
    if installed.is_file():
        try:
            data = json.loads(installed.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _warn(f"{installed}: {exc.msg}")
            data = None
        if isinstance(data, dict) and isinstance(data.get("version"), str):
            return data["version"]
    return None


def _manifest_snapshot(package: Path) -> dict[Path, bytes | None]:
    snapshot: dict[Path, bytes | None] = {}
    for name in ("package.json", "package-lock.json", "npm-shrinkwrap.json"):
        path = package / name
        snapshot[path] = path.read_bytes() if path.is_file() else None
    return snapshot


def _restore_manifests(snapshot: dict[Path, bytes | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            if path.is_file():
                path.unlink()
        elif not path.is_file() or path.read_bytes() != content:
            path.write_bytes(content)


def _ensure_vitest_coverage(package: Path) -> bool:
    """Vitest collects coverage itself. c8 never sees its worker processes."""

    if (package / "node_modules" / "@vitest" / "coverage-v8").is_dir():
        return True
    version = _vitest_version(package)
    spec = f"@vitest/coverage-v8@{version}" if version else "@vitest/coverage-v8"
    _warn(
        f"Installing {spec} so Vitest can write LCOV. "
        "package.json and the lockfile are restored afterward."
    )
    snapshot = _manifest_snapshot(package)
    try:
        code = run_shell(
            ["npm", "install", "--no-save", "--no-package-lock", spec],
            package,
        )
    finally:
        _restore_manifests(snapshot)
    ready = code == 0 and (package / "node_modules" / "@vitest" / "coverage-v8").is_dir()
    if not ready:
        _warn("Vitest's coverage provider is missing. TypeScript coverage will score 0%.")
    return ready


def typescript_packages(root: Path, files: list[Path]) -> list[Path]:
    packages: set[Path] = set()
    root = root.resolve()
    for file in files:
        if language_of(file) != "typescript":
            continue
        package = _nearest(file, "package.json", root)
        if package is not None:
            packages.add(package.resolve())
    return sorted(packages)


def typescript_command(
    package: Path, files: list[Path], report_dir: Path
) -> list[str] | None:
    """Argument vector that writes LCOV into `report_dir`, or None when there is no test script."""

    data = _package_json(package)
    if data is None:
        return None
    scripts = data.get("scripts") or {}
    if not isinstance(scripts, dict):
        scripts = {}
    if "coverage" in scripts:
        return ["npm", "run", "coverage"]
    if _uses_vitest(package, scripts):
        return _vitest_coverage_command(package, files, report_dir)
    if "test" not in scripts:
        return None
    return [
        "npx",
        "--yes",
        "c8",
        "--reporter=lcov",
        "--reports-dir",
        str(report_dir),
        "npm",
        "test",
    ]


def _vitest_includes(package: Path, files: list[Path]) -> list[str]:
    includes: list[str] = []
    package = package.resolve()
    for file in files:
        if language_of(file) != "typescript" or is_test_file(file):
            continue
        try:
            relative = Path(file).resolve().relative_to(package)
        except ValueError:
            continue
        includes.append(relative.as_posix())
    return includes


def _vitest_coverage_command(package: Path, files: list[Path], report_dir: Path) -> list[str]:
    binary = package / "node_modules" / ".bin" / "vitest"
    if binary.is_file():
        command = [str(binary)]
    else:
        command = ["npx", "vitest"]
    command.extend(
        [
            "run",
            "--coverage",
            "--coverage.reporter=lcov",
            f"--coverage.reportsDirectory={report_dir}",
            "--coverage.reportOnFailure=true",
        ]
    )
    for include in _vitest_includes(package, files):
        command.append(f"--coverage.include={include}")
    return command


def _coverage_report(root: Path, module: Path, language: str) -> Path:
    """`target/coverage/<language>/<module folder>/lcov.info`, one folder per module."""

    root = root.resolve()
    return root / "target" / "coverage" / language / module.resolve().relative_to(root) / "lcov.info"


def rust_modules(root: Path, files: list[Path]) -> list[Path]:
    root = root.resolve()
    return [
        module.resolve()
        for module in _modules_with(files, ".rs", "Cargo.toml", root)
    ]


def _rust_kind() -> str | None:
    if shutil.which("cargo-llvm-cov"):
        return "llvm-cov"
    if shutil.which("cargo-tarpaulin"):
        return "tarpaulin"
    _warn("Neither cargo-llvm-cov nor cargo-tarpaulin is installed. Installing cargo-llvm-cov.")
    if shutil.which("rustup"):
        code = run_shell(["rustup", "component", "add", "llvm-tools-preview"], Path.home())
        if code != 0:
            _warn("rustup component add llvm-tools-preview failed.")
    code = run_shell(["cargo", "install", "cargo-llvm-cov", "--locked"], Path.home())
    if code == 0 and shutil.which("cargo-llvm-cov"):
        return "llvm-cov"
    _warn("Rust coverage will score 0%.")
    return None


_PYTHON_MARKERS = ("pyproject.toml", "setup.cfg", "setup.py", "pytest.ini", "tox.ini")


def python_roots(root: Path, files: list[Path]) -> list[Path]:
    found: set[Path] = set()
    root = root.resolve()
    for file in files:
        if Path(file).suffix != ".py":
            continue
        module = None
        for marker in _PYTHON_MARKERS:
            module = _nearest(Path(file), marker, root)
            if module is not None:
                break
        found.add((module or root).resolve())
    return sorted(found)


def _python_executable(package: Path) -> str:
    for relative in (".venv/bin/python", "venv/bin/python"):
        candidate = package / relative
        if candidate.is_file():
            return str(candidate)
    return "python3"


def uses_pytest(package: Path) -> bool:
    if (package / "pytest.ini").is_file() or (package / "conftest.py").is_file():
        return True
    for name in ("pyproject.toml", "setup.cfg", "tox.ini"):
        path = package / name
        if path.is_file() and "pytest" in path.read_text(encoding="utf-8", errors="replace"):
            return True
    return False


def python_sources(package: Path, files: list[Path]) -> str:
    """Directories coverage.py should report even when a file was never imported.

    coverage.py reads a `--source` value as a directory, or else as an
    importable module name, so a file directly in `package` adds `.`, never
    its file name (#3). coverage.py also splits the list on commas, so a
    folder with a comma in its name is reached through `.` too.
    """

    tops: set[str] = set()
    package = package.resolve()
    for file in files:
        path = Path(file)
        if path.suffix != ".py" or is_test_file(path):
            continue
        try:
            relative = path.resolve().relative_to(package)
        except ValueError:
            continue
        top = relative.parts[0]
        tops.add(top if len(relative.parts) > 1 and "," not in top else ".")
    return ",".join(sorted(tops))


def python_coverage_commands(
    py: str, kind: str, data_file: Path, report: Path, source: str
) -> tuple[list[str], list[str]]:
    run = [py, "-m", "coverage", "run", f"--data-file={data_file}"]
    if source:
        run.append(f"--source={source}")
    if kind == "pytest":
        run.extend(["-m", "pytest"])
    else:
        run.extend(["-m", "unittest", "discover", "-s", "."])
    lcov = [py, "-m", "coverage", "lcov", f"--data-file={data_file}", "-o", str(report)]
    return run, lcov


def _ensure_python_module(py: str, package: Path, module: str) -> bool:
    if run_shell([py, "-c", f"import {module}"], package) == 0:
        return True
    _warn(
        f"Installing {module} for Python coverage. "
        "The project requirements are left unchanged."
    )
    code = run_shell(
        [py, "-m", "pip", "install", "--disable-pip-version-check", module],
        package,
    )
    return code == 0


def rust_coverage_command(kind: str, report: Path) -> list[str]:
    if kind == "llvm-cov":
        return ["cargo", "llvm-cov", "--lcov", "--output-path", str(report)]
    return ["cargo", "tarpaulin", "--out", "Lcov", "--output-dir", str(report.parent)]


def _languages_in(files: list[Path]) -> set[str]:
    found = set()
    for file in files:
        language = language_of(file)
        if language:
            found.add(language)
    return found


def _modules_with(files: list[Path], suffix: str, marker: str, root: Path) -> list[Path]:
    modules: set[Path] = set()
    for file in files:
        if Path(file).suffix != suffix:
            continue
        module = _nearest(file, marker, root)
        if module is not None:
            modules.add(module)
    return sorted(modules)


def _cover_clojure(root: Path) -> list[Report]:
    if not (root / "deps.edn").is_file() and not (root / "bb.edn").is_file():
        _warn("No deps.edn or bb.edn; skipping Clojure coverage.")
        return []
    code = run_shell(["clj", "-M:cov", "--lcov"], root)
    if code != 0:
        _warn("clj -M:cov --lcov failed; retrying without --lcov.")
        _clean_clojure(root)
        code = run_shell(["clj", "-M:cov"], root)
    coverage = root / "target" / "coverage"
    return _ran("Clojure", root, code, [coverage / "lcov.info", *_cloverage_html(coverage)])


def _cover_java(root: Path, files: list[Path]) -> list[Report]:
    modules = _modules_with(files, ".java", "pom.xml", root)
    if not modules:
        _warn("No pom.xml; skipping Java coverage.")
        return []
    reports = []
    for module in modules:
        report = module / "target" / "site" / "jacoco" / "jacoco.xml"
        _clean_dir(report.parent)
        exec_file = module / "target" / "jacoco.exec"
        if exec_file.exists():
            exec_file.unlink()
        reports += _ran("Java", module, run_shell(_MAVEN, module), [report])
    return reports


def _cover_go(root: Path, files: list[Path]) -> list[Report]:
    modules = _modules_with(files, ".go", "go.mod", root)
    if not modules:
        _warn("No go.mod; skipping Go coverage.")
        return []
    reports = []
    for module in modules:
        profile = module / "target" / "coverage" / "go" / "coverage.out"
        profile.parent.mkdir(parents=True, exist_ok=True)
        if profile.exists():
            profile.unlink()
        code = run_shell(["go", "test", "./...", f"-coverprofile={profile}"], module)
        reports += _ran("Go", module, code, [profile])
    return reports


def _prepare_report(report: Path) -> None:
    if report.parent.exists():
        shutil.rmtree(report.parent)
    report.parent.mkdir(parents=True, exist_ok=True)


def _remove_lcov(folder: Path) -> None:
    """Remove `coverage/**/lcov.info` under `folder`, where a package's own coverage script writes."""

    for path in folder.glob("coverage/**/lcov.info"):
        path.unlink()


def _cover_typescript(root: Path, files: list[Path]) -> list[Report]:
    packages = typescript_packages(root, files)
    if not packages:
        _warn("No package.json; skipping TypeScript coverage.")
        return []
    reports = []
    for package in packages:
        report = _coverage_report(root, package, "typescript")
        try:
            command = typescript_command(package, files, report.parent)
        except PackageJsonError as exc:
            _warn(str(exc))
            continue
        if command is None:
            _warn(f"No package.json test script in {package}; skipping TypeScript coverage.")
            continue
        if _needs_vitest_provider(command) and not _ensure_vitest_coverage(package):
            continue
        _prepare_report(report)
        _remove_lcov(package)
        code = run_shell(command, package)
        reports += _ran("TypeScript", package, code, [report, *package.glob("coverage/**/lcov.info")])
    return reports


def _needs_vitest_provider(command: list[str]) -> bool:
    if command[:3] == ["npm", "run", "coverage"]:
        return False
    return any(Path(part).name == "vitest" for part in command)


def _python_kind(py: str, package: Path) -> str:
    if not uses_pytest(package):
        return "unittest"
    if _ensure_python_module(py, package, "pytest"):
        return "pytest"
    _warn(f"pytest is missing in {package}. Falling back to unittest.")
    return "unittest"


def _record_python_lcov(
    package: Path, code: int, data_file: Path, lcov_cmd: str | list[str]
) -> int:
    """Write the LCOV report from the tests' coverage data; return the status its report carries.

    That is the tests' status `code`, or else `coverage lcov`'s.
    """

    if not data_file.exists():
        return code
    lcov_code = run_shell(lcov_cmd, package)
    if lcov_code != 0:
        _warn(f"coverage lcov exited {lcov_code} in {package}.")
    return code or lcov_code


def _cover_python(root: Path, files: list[Path]) -> list[Report]:
    reports = []
    for package in python_roots(root, files):
        report = _coverage_report(root, package, "python")
        py = _python_executable(package)
        if not _ensure_python_module(py, package, "coverage"):
            _warn(f"coverage is missing in {package}. Python coverage will score 0%.")
            continue
        report.parent.mkdir(parents=True, exist_ok=True)
        data_file = report.parent / ".coverage"
        run_cmd, lcov_cmd = python_coverage_commands(
            py, _python_kind(py, package), data_file, report, python_sources(package, files)
        )
        code = _record_python_lcov(package, run_shell(run_cmd, package), data_file, lcov_cmd)
        reports += _ran("Python", package, code, [report])
    return reports


def _cover_rust(root: Path, files: list[Path]) -> list[Report]:
    modules = rust_modules(root, files)
    if not modules:
        _warn("No Cargo.toml; skipping Rust coverage.")
        return []
    kind = _rust_kind()
    if kind is None:
        return []
    reports = []
    for module in modules:
        report = _coverage_report(root, module, "rust")
        report.parent.mkdir(parents=True, exist_ok=True)
        code = run_shell(rust_coverage_command(kind, report), module)
        reports += _ran("Rust", module, code, [report])
    return reports


def _clear_reports(root: Path, languages: set[str]) -> None:
    """Remove the reports crapper's collectors write for these languages.

    The loader reads every report on disk. Clearing first means a collector
    that fails, writes nothing, or finds no tool leaves no earlier run's
    report behind to be read as this run's coverage.
    """

    for language in languages & {"typescript", "python", "rust"}:
        _clean_dir(root / "target" / "coverage" / language)
    if "typescript" in languages:
        _remove_lcov(root)
    if "clojure" in languages:
        _clean_clojure(root)


def collect_coverage(root: Path, files: list[Path]) -> list[Report]:
    """Run each language's coverage tool and return the reports this run wrote.

    Each collector clears its report paths before it runs, so a path that
    exists afterward holds this run's report. Each report's `code` is the exit
    status of the run that wrote it. A failed run is reported: its language
    scores 0% when it wrote nothing, and its report, when it wrote one, comes
    back with a non-zero `code`, so a caller can refuse it.
    """

    root = root.resolve()
    languages = _languages_in(files)
    _clear_reports(root, languages)
    reports: list[Report] = []
    if "clojure" in languages:
        reports += _cover_clojure(root)
    if "java" in languages:
        reports += _cover_java(root, files)
    if "go" in languages:
        reports += _cover_go(root, files)
    if "typescript" in languages:
        reports += _cover_typescript(root, files)
    if "python" in languages:
        reports += _cover_python(root, files)
    if "rust" in languages:
        reports += _cover_rust(root, files)
    return [report for report in reports if report.path.is_file()]


def run_coverage(root: Path, files: list[Path], command: str | None) -> int:
    """Generate coverage reports for the languages present in `files`, or run `command`.

    Returns the custom command's status. A non-zero status means the caller
    must not read reports already on disk. Per-language runs return 0 (see
    `collect_coverage`, which also lists the reports they wrote).
    """

    if command:
        code = run_shell(command, root.resolve())
        if code != 0:
            _warn(
                f"Coverage command exited {code}. "
                "Reports already on disk will not be read."
            )
        return code
    collect_coverage(root, files)
    return 0
