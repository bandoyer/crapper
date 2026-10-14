"""Find source files and decide which language each one is written in."""

import os
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

EXTENSIONS = {
    ".clj": "clojure",
    ".cljc": "clojure",
    ".cljs": "clojure",
    ".bb": "clojure",
    ".java": "java",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".mjs": "typescript",
    ".cjs": "typescript",
    ".rs": "rust",
    ".py": "python",
    ".cs": "csharp",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "target",
    "dist",
    "build",
    "out",
    "coverage",
    ".metrics",
    "testdata",
    "__pycache__",
    ".clj-kondo",
}

TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__"}

GO_TEST_SUFFIX = "_test.go"
CLOJURE_TEST_SUFFIXES = ("_test.clj", "_test.cljc", "_test.cljs", "_test.bb")
JS_TEST_SUFFIXES = (
    ".test.ts",
    ".spec.ts",
    ".test.tsx",
    ".spec.tsx",
    ".test.mts",
    ".spec.mts",
    ".test.cts",
    ".spec.cts",
    ".test.js",
    ".spec.js",
    ".test.jsx",
    ".spec.jsx",
    ".test.mjs",
    ".spec.mjs",
    ".test.cjs",
    ".spec.cjs",
)


# A C# test project's .csproj says so, uses MSTest.Sdk, or references one of
# these test frameworks: the rule skillflow #270, #271 and #272 share.
# Microsoft.Testing.Platform isn't one, since production code, such as a test
# runner, references it too. NuGet reads package IDs without regard to case.
CSHARP_TEST_PACKAGES = {"microsoft.net.test.sdk", "nunit", "xunit", "xunit.v3", "mstest", "mstest.testframework"}
CSHARP_BUILD_DIRS = {"bin", "obj"}


def language_of(path: str | Path) -> str | None:
    file_path = Path(path)
    name = file_path.name
    if name.endswith(".d.ts"):
        return None
    return EXTENSIONS.get(file_path.suffix)


@lru_cache(maxsize=None)
def _csharp_project(folder: Path) -> Path | None:
    """The nearest folder at or above `folder` that holds a .csproj."""

    if any(folder.glob("*.csproj")):
        return folder
    if folder.parent == folder:
        return None
    return _csharp_project(folder.parent)


def _marks_a_test_project(csproj: Path) -> bool:
    """Whether the .csproj sets IsTestProject, uses MSTest.Sdk, or references a test framework.

    It is read as XML, by local names, so a comment counts for nothing, quoting
    and spacing don't matter, and an old-style MSBuild namespace is fine. A
    file that can't be read as XML marks nothing; MSBuild can't load it either.
    """

    try:
        root = ET.parse(csproj).getroot()
    except (ET.ParseError, OSError):
        return False
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "IsTestProject" and (element.text or "").strip().lower() == "true":
            return True
        if tag == "PackageReference" and element.get("Include", "").strip().lower() in CSHARP_TEST_PACKAGES:
            return True
        sdks = element.get("Sdk", "") if tag == "Project" else element.get("Name", "") if tag == "Sdk" else ""
        if any(sdk.split("/")[0].strip().lower() == "mstest.sdk" for sdk in sdks.split(";")):
            return True
    return False


@lru_cache(maxsize=None)
def _is_csharp_test_project(project: Path) -> bool:
    """Whether a C# project is a test project.

    A part of its folder's name is Test or Tests (App.Tests, App.Test.Unit),
    the name ends in Tests (App.IntegrationTests), or its .csproj says so. A
    name ending in Test isn't enough: Stryker.TestRunner.VsTest is production code.
    """

    name = project.name
    if {"Test", "Tests"} & set(name.split(".")) or name.endswith("Tests"):
        return True
    return any(_marks_a_test_project(csproj) for csproj in project.glob("*.csproj"))


def _csharp_unscored(path: Path) -> bool:
    """A C# file in a test project, or in its project's bin/ or obj/ build output."""

    file_path = path.absolute()
    project = _csharp_project(file_path.parent)
    if project is None:
        return False
    inside = file_path.parent.relative_to(project).parts
    return bool(CSHARP_BUILD_DIRS.intersection(inside)) or _is_csharp_test_project(project)


def is_test_file(path: str | Path) -> bool:
    """Whether `path` is test code, which crapper doesn't score.

    A C# file in a test project counts, and so does one in its project's
    bin/ or obj/, which hold build output, not source.
    """

    file_path = Path(path)
    name = file_path.name
    if name.endswith(GO_TEST_SUFFIX):
        return True
    if name.endswith(CLOJURE_TEST_SUFFIXES):
        return True
    if name.endswith(JS_TEST_SUFFIXES):
        return True
    if name == "conftest.py":
        return True
    if name.endswith("_test.py") or (name.startswith("test_") and name.endswith(".py")):
        return True
    if file_path.suffix == ".cs" and _csharp_unscored(file_path):
        return True
    return any(part in TEST_DIRS for part in file_path.parts)


def _walk(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames if name not in SKIP_DIRS and name not in TEST_DIRS
        ]
        for name in filenames:
            path = Path(dirpath) / name
            if language_of(path) is None or is_test_file(path):
                continue
            found.append(path)
    return found


def iter_source_files(roots: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        for path in _walk(root):
            files.add(path.resolve())
    return sorted(files, key=lambda path: path.as_posix())
