"""Run each language's coverage tool, then leave the reports for the loader.

Failures are reported and do not stop analysis. A language with no coverage
tool, or a failed run, scores its functions at 0%.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from crapper.discover import is_test_file, language_of

_MAVEN = (
    "mvn -q "
    "org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent "
    "test "
    "org.jacoco:jacoco-maven-plugin:0.8.12:report"
)


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def run_shell(command: str, cwd: Path) -> int:
    _warn(f"+ ({cwd}) {command}")
    try:
        completed = subprocess.run(command, cwd=cwd, shell=True)
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


def _clean_clojure(root: Path) -> None:
    coverage = root / "target" / "coverage"
    if not coverage.is_dir():
        return
    keep = {"typescript", "rust", "go", "python"}
    for path in coverage.iterdir():
        if path.name in keep:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


_VITEST_CONFIGS = (
    "vitest.config.ts",
    "vitest.config.mts",
    "vitest.config.cts",
    "vitest.config.js",
    "vitest.config.mjs",
    "vitest.config.cjs",
)


def _package_json(package: Path) -> dict | None:
    path = package / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _uses_vitest(package: Path, scripts: dict) -> bool:
    if "vitest" in str(scripts.get("test", "")):
        return True
    return any((package / name).is_file() for name in _VITEST_CONFIGS)


def _vitest_version(package: Path) -> str | None:
    installed = package / "node_modules" / "vitest" / "package.json"
    if installed.is_file():
        try:
            data = json.loads(installed.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
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
    code = run_shell(f"npm install --no-save --no-package-lock {spec}", package)
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


def typescript_command(package: Path, files: list[Path], report_dir: Path) -> str | None:
    """Shell command that writes LCOV into `report_dir`, or None when there is no test script."""

    data = _package_json(package)
    if data is None:
        return None
    scripts = data.get("scripts") or {}
    if not isinstance(scripts, dict):
        scripts = {}
    if "coverage" in scripts:
        return "npm run coverage"
    quoted_dir = shlex.quote(str(report_dir))
    if _uses_vitest(package, scripts):
        return _vitest_coverage_command(package, files, quoted_dir)
    if "test" not in scripts:
        return None
    return f"npx --yes c8 --reporter=lcov --reports-dir {quoted_dir} npm test"


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
        includes.append(shlex.quote(relative.as_posix()))
    return includes


def _vitest_coverage_command(package: Path, files: list[Path], quoted_dir: str) -> str:
    binary = package / "node_modules" / ".bin" / "vitest"
    runner = shlex.quote(str(binary)) if binary.is_file() else "npx vitest"
    flags = [
        "--coverage",
        "--coverage.reporter=lcov",
        f"--coverage.reportsDirectory={quoted_dir}",
        "--coverage.reportOnFailure=true",
    ]
    for include in _vitest_includes(package, files):
        flags.append(f"--coverage.include={include}")
    return f"{runner} run " + " ".join(flags)


def _coverage_report(root: Path, module: Path, language: str) -> Path:
    root = root.resolve()
    module = module.resolve()
    if module == root:
        return root / "target" / "coverage" / language / "lcov.info"
    slug = module.relative_to(root).as_posix().replace("/", "__")
    return root / "target" / "coverage" / language / slug / "lcov.info"


def rust_modules(root: Path, files: list[Path]) -> list[Path]:
    modules: set[Path] = set()
    root = root.resolve()
    for file in files:
        if Path(file).suffix != ".rs":
            continue
        module = _nearest(file, "Cargo.toml", root)
        if module is not None:
            modules.add(module.resolve())
    return sorted(modules)


def _rust_kind() -> str | None:
    if shutil.which("cargo-llvm-cov"):
        return "llvm-cov"
    if shutil.which("cargo-tarpaulin"):
        return "tarpaulin"
    _warn("Neither cargo-llvm-cov nor cargo-tarpaulin is installed. Installing cargo-llvm-cov.")
    if shutil.which("rustup"):
        code = run_shell("rustup component add llvm-tools-preview", Path.home())
        if code != 0:
            _warn("rustup component add llvm-tools-preview failed.")
    code = run_shell("cargo install cargo-llvm-cov --locked", Path.home())
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
            return shlex.quote(str(candidate))
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
    """Directories coverage.py should report even when a file was never imported."""

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
        tops.add(relative.parts[0])
    return ",".join(sorted(tops))


def python_coverage_commands(
    py: str, kind: str, data_file: Path, report: Path, source: str
) -> tuple[str, str]:
    data = shlex.quote(str(data_file))
    out = shlex.quote(str(report))
    source_flag = f" --source={shlex.quote(source)}" if source else ""
    if kind == "pytest":
        module = "pytest"
    else:
        module = "unittest discover -s ."
    run = f"{py} -m coverage run --data-file={data}{source_flag} -m {module}"
    lcov = f"{py} -m coverage lcov --data-file={data} -o {out}"
    return run, lcov


def _ensure_python_module(py: str, package: Path, module: str) -> bool:
    probe = f"{py} -c {shlex.quote('import ' + module)}"
    if run_shell(probe, package) == 0:
        return True
    _warn(
        f"Installing {module} for Python coverage. "
        "The project requirements are left unchanged."
    )
    code = run_shell(
        f"{py} -m pip install --disable-pip-version-check {module}",
        package,
    )
    return code == 0


def rust_coverage_command(kind: str, report: Path) -> str:
    if kind == "llvm-cov":
        return f"cargo llvm-cov --lcov --output-path {shlex.quote(str(report))}"
    return f"cargo tarpaulin --out Lcov --output-dir {shlex.quote(str(report.parent))}"


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


def _cover_clojure(root: Path) -> None:
    if not (root / "deps.edn").is_file() and not (root / "bb.edn").is_file():
        _warn("No deps.edn or bb.edn; skipping Clojure coverage.")
        return
    _clean_clojure(root)
    code = run_shell("clj -M:cov --lcov", root)
    if code != 0:
        _warn("clj -M:cov --lcov failed; retrying without --lcov.")
        code = run_shell("clj -M:cov", root)
    if code != 0:
        _warn(f"Clojure coverage exited {code}. Clojure coverage will score 0%.")


def _cover_java(root: Path, files: list[Path]) -> None:
    modules = _modules_with(files, ".java", "pom.xml", root)
    if not modules:
        _warn("No pom.xml; skipping Java coverage.")
        return
    for module in modules:
        _clean_dir(module / "target" / "site" / "jacoco")
        exec_file = module / "target" / "jacoco.exec"
        if exec_file.exists():
            exec_file.unlink()
        code = run_shell(_MAVEN, module)
        if code != 0:
            _warn(f"Java coverage exited {code} in {module}. Java coverage will score 0%.")


def _cover_go(root: Path, files: list[Path]) -> None:
    modules = _modules_with(files, ".go", "go.mod", root)
    if not modules:
        _warn("No go.mod; skipping Go coverage.")
        return
    for module in modules:
        profile = module / "target" / "coverage" / "go" / "coverage.out"
        profile.parent.mkdir(parents=True, exist_ok=True)
        if profile.exists():
            profile.unlink()
        code = run_shell(f"go test ./... -coverprofile={profile}", module)
        if code != 0:
            _warn(f"Go coverage exited {code} in {module}. Go coverage will score 0%.")


def _prepare_report(report: Path) -> None:
    if report.parent.exists():
        shutil.rmtree(report.parent)
    report.parent.mkdir(parents=True, exist_ok=True)


def _cover_typescript(root: Path, files: list[Path]) -> None:
    packages = typescript_packages(root, files)
    if not packages:
        _warn("No package.json; skipping TypeScript coverage.")
        return
    for package in packages:
        report = _coverage_report(root, package, "typescript")
        command = typescript_command(package, files, report.parent)
        if command is None:
            _warn(f"No package.json test script in {package}; skipping TypeScript coverage.")
            continue
        if _needs_vitest_provider(command) and not _ensure_vitest_coverage(package):
            continue
        _prepare_report(report)
        code = run_shell(command, package)
        if code != 0:
            _warn(f"TypeScript coverage exited {code} in {package}. TypeScript coverage will score 0%.")


def _needs_vitest_provider(command: str) -> bool:
    return command != "npm run coverage" and "vitest" in command


def _python_kind(py: str, package: Path) -> str:
    if not uses_pytest(package):
        return "unittest"
    if _ensure_python_module(py, package, "pytest"):
        return "pytest"
    _warn(f"pytest is missing in {package}. Falling back to unittest.")
    return "unittest"


def _record_python_lcov(package: Path, code: int, data_file: Path, lcov_cmd: str) -> None:
    if not data_file.exists():
        if code != 0:
            _warn(f"Python coverage exited {code} in {package}. Python coverage will score 0%.")
        return
    lcov_code = run_shell(lcov_cmd, package)
    if lcov_code != 0:
        _warn(f"coverage lcov exited {lcov_code} in {package}. Python coverage will score 0%.")
    elif code != 0:
        _warn(f"Python tests exited {code} in {package}. Coverage was still recorded.")


def _cover_python(root: Path, files: list[Path]) -> None:
    for package in python_roots(root, files):
        report = _coverage_report(root, package, "python")
        py = _python_executable(package)
        if not _ensure_python_module(py, package, "coverage"):
            _warn(f"coverage is missing in {package}. Python coverage will score 0%.")
            continue
        report.parent.mkdir(parents=True, exist_ok=True)
        data_file = report.parent / ".coverage"
        report.unlink(missing_ok=True)
        data_file.unlink(missing_ok=True)
        run_cmd, lcov_cmd = python_coverage_commands(
            py, _python_kind(py, package), data_file, report, python_sources(package, files)
        )
        _record_python_lcov(package, run_shell(run_cmd, package), data_file, lcov_cmd)


def _cover_rust(root: Path, files: list[Path]) -> None:
    modules = rust_modules(root, files)
    if not modules:
        _warn("No Cargo.toml; skipping Rust coverage.")
        return
    kind = _rust_kind()
    if kind is None:
        return
    for module in modules:
        report = _coverage_report(root, module, "rust")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.unlink(missing_ok=True)
        code = run_shell(rust_coverage_command(kind, report), module)
        if code != 0:
            _warn(f"Rust coverage exited {code} in {module}. Rust coverage will score 0%.")


def run_coverage(root: Path, files: list[Path], command: str | None) -> None:
    """Generate coverage reports for the languages present in `files`."""

    root = root.resolve()
    if command:
        code = run_shell(command, root)
        if code != 0:
            _warn(f"Coverage command exited {code}. Coverage may score 0%.")
        return

    languages = _languages_in(files)
    if "clojure" in languages:
        _cover_clojure(root)
    if "java" in languages:
        _cover_java(root, files)
    if "go" in languages:
        _cover_go(root, files)
    if "typescript" in languages:
        _cover_typescript(root, files)
    if "python" in languages:
        _cover_python(root, files)
    if "rust" in languages:
        _cover_rust(root, files)
