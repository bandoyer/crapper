"""Load Cloverage, LCOV, JaCoCo, and Go coverage profiles.

Clojure prefers Cloverage's per-line form counts, then LCOV. Java uses JaCoCo
instruction counters. Go uses statement profiles. LCOV scores a function by
its BRDA branch records when it has any, and by line hits otherwise.
`percent_for` returns None when the file is absent; analysis turns that into 0%.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from crapper.model import Function

_SPAN = re.compile(
    r'<span[^>]*title="(\d+) out of (\d+) forms covered"[^>]*>\s*(\d+)&nbsp;'
)
_LCOV_DA = re.compile(r"DA:(\d+),(\d+)")
_LCOV_BRDA = re.compile(r"BRDA:(\d+),([^,]*),([^,]*),(-|\d+)")
_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)


class FileCoverage(dict):
    """Line hits for one file, plus branch hits keyed by line.

    The mapping itself is `line → (covered, total)` from `DA` records, so
    existing callers can keep indexing it. `branches` aggregates each `BRDA`
    record on that line as one branch.
    """

    def __init__(self):
        super().__init__()
        self.branches: dict[int, tuple[int, int]] = {}


def normalize_path(path: str) -> str:
    text = unquote(path).replace("\\", "/")
    if text.startswith("file:"):
        text = text[5:]
    while text.startswith("./"):
        text = text[2:]
    while "//" in text:
        text = text.replace("//", "/")
    return text


def _segments(path: str) -> list[str]:
    return [part for part in normalize_path(path).split("/") if part]


def suffix_match(path: str, suffix: str) -> bool:
    path_parts = _segments(path)
    suffix_parts = _segments(suffix)
    if not suffix_parts or len(suffix_parts) > len(path_parts):
        return False
    return path_parts[-len(suffix_parts) :] == suffix_parts


def _candidates(source_path: str) -> list[str]:
    relative = normalize_path(source_path)
    absolute = normalize_path(str(Path(source_path).resolve())) if source_path else relative
    no_src = re.sub(r"^src/", "", relative)
    absolute_no_src = re.sub(r"/src/", "/", absolute)
    values = [relative, absolute, no_src, absolute_no_src]
    found: list[str] = []
    for value in values:
        if value and value not in found:
            found.append(value)
    return found


def coverage_percent(covered: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return 100.0 * covered / total


def percent_for_range(lines: dict[int, tuple[int, int]] | None, start: int, end: int) -> float | None:
    if lines is None:
        return None
    covered = 0
    total = 0
    for line in range(start, end + 1):
        entry = lines.get(line)
        if entry is None:
            continue
        covered += entry[0]
        total += entry[1]
    if total == 0:
        return 0.0
    return coverage_percent(covered, total)


def parse_form_coverage(html: str) -> dict[int, tuple[int, int]]:
    found: dict[int, tuple[int, int]] = {}
    for covered, total, line in _SPAN.findall(html):
        total_forms = int(total)
        if total_forms <= 0:
            continue
        found[int(line)] = (int(covered), total_forms)
    return found


def _branch_hit(taken: str) -> bool:
    if taken == "-":
        return False
    try:
        return int(taken) > 0
    except ValueError:
        return False


def _add_branch(record: FileCoverage, line: int, taken: str) -> None:
    covered, total = record.branches.get(line, (0, 0))
    record.branches[line] = (covered + (1 if _branch_hit(taken) else 0), total + 1)


def parse_lcov(text: str) -> dict[str, FileCoverage]:
    out: dict[str, FileCoverage] = {}
    current_file = None
    current = FileCoverage()
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SF:"):
            if current_file is not None:
                out[current_file] = current
            current_file = line[3:]
            current = FileCoverage()
        elif line == "end_of_record":
            if current_file is not None:
                out[current_file] = current
            current_file = None
            current = FileCoverage()
        elif current_file is not None:
            match = _LCOV_DA.match(line)
            if match:
                hits = int(match.group(2))
                current[int(match.group(1))] = (1 if hits > 0 else 0, 1)
                continue
            branch = _LCOV_BRDA.match(line)
            if branch:
                _add_branch(current, int(branch.group(1)), branch.group(4))
    if current_file is not None:
        out[current_file] = current
    return out


def branch_percent(record, start: int, end: int) -> float | None:
    """Branch coverage for a function, or None when that span has no branches."""

    branches = getattr(record, "branches", None)
    if not branches:
        return None
    covered = 0
    total = 0
    for line in range(start, end + 1):
        entry = branches.get(line)
        if entry is None:
            continue
        covered += entry[0]
        total += entry[1]
    if total == 0:
        return None
    return coverage_percent(covered, total)


def parse_go_profile(text: str) -> dict[str, list[tuple[int, int, int, int]]]:
    """Map file → (start_line, end_line, statements, hits)."""

    out: dict[str, list[tuple[int, int, int, int]]] = {}
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("mode:"):
            continue
        fields = line.split()
        if len(fields) != 3 or ":" not in fields[0]:
            raise ValueError(f"invalid coverage segment on line {line_number}: {raw!r}")
        file_part, range_part = fields[0].split(":", 1)
        start_text, end_text = range_part.split(",", 1)
        start_line = int(start_text.split(".", 1)[0])
        end_line = int(end_text.split(".", 1)[0])
        statements = int(fields[1])
        hits = int(fields[2])
        out.setdefault(file_part, []).append((start_line, end_line, statements, hits))
    return out


def _profile_segments(profile, path: str):
    if profile is None:
        return None
    for candidate in _candidates(path):
        for key, value in profile.items():
            if (
                normalize_path(key) == candidate
                or suffix_match(key, candidate)
                or suffix_match(candidate, key)
            ):
                return value
    return None


def go_percent(
    profile: dict[str, list[tuple[int, int, int, int]]] | None,
    path: str,
    start: int,
    end: int,
) -> float | None:
    segments = _profile_segments(profile, path)
    if segments is None:
        return None
    total = 0
    covered = 0
    for seg_start, seg_end, statements, hits in segments:
        if seg_end < start or seg_start > end:
            continue
        total += statements
        if hits > 0:
            covered += statements
    if total == 0:
        return 0.0
    return coverage_percent(covered, total)


@dataclass
class JacocoMethod:
    missed: int
    covered: int
    line: int

    @property
    def percent(self) -> float:
        return coverage_percent(self.covered, self.missed + self.covered)


def _jacoco_from_index(classes, class_names, method_name, line) -> float | None:
    pool: list[JacocoMethod] = []
    for name in class_names:
        for method in classes.get(f"{name}#{method_name}", []):
            pool.append(method)
    if not pool:
        return None
    for method in pool:
        if method.line == line:
            return method.percent
    nearest = min(pool, key=lambda method: abs(method.line - line))
    return nearest.percent


def parse_jacoco_index(text: str) -> dict[str, list[JacocoMethod]]:
    """Key methods as `binary.class.name#method`."""

    cleaned = _DOCTYPE.sub("", text)
    root = ET.fromstring(cleaned)
    found: dict[str, list[JacocoMethod]] = {}
    for class_node in root.iter("class"):
        class_name = class_node.get("name", "").replace("/", ".")
        for method in list(class_node):
            if method.tag != "method":
                continue
            counter = next(
                (
                    child
                    for child in list(method)
                    if child.tag == "counter" and child.get("type") == "INSTRUCTION"
                ),
                None,
            )
            if counter is None:
                continue
            try:
                line = int(method.get("line") or "0")
            except ValueError:
                line = 0
            key = f"{class_name}#{method.get('name', '')}"
            found.setdefault(key, []).append(
                JacocoMethod(
                    missed=int(counter.get("missed") or "0"),
                    covered=int(counter.get("covered") or "0"),
                    line=line,
                )
            )
    return found


@dataclass
class CoverageBundle:
    lcov: dict[str, dict[int, tuple[int, int]]] = field(default_factory=dict)
    go_profile: dict[str, list[tuple[int, int, int, int]]] | None = None
    jacoco: dict[str, list[JacocoMethod]] | None = None
    form_html: dict[str, dict[int, tuple[int, int]]] = field(default_factory=dict)

    def percent_for(self, function: Function) -> float | None:
        if function.language == "java":
            names = []
            if function.jacoco_class:
                names.append(function.jacoco_class)
            if function.namespace not in names:
                names.append(function.namespace)
            return _jacoco_from_index(
                self.jacoco or {}, names, function.name, function.start_line
            )
        if function.language == "go":
            return go_percent(
                self.go_profile, function.path, function.start_line, function.end_line
            )
        html = self._html_lines(function.path)
        if html is not None:
            return percent_for_range(html, function.start_line, function.end_line)
        record = self._lcov_lines(function.path)
        if record is None:
            return None
        branched = branch_percent(record, function.start_line, function.end_line)
        if branched is not None:
            return branched
        return percent_for_range(record, function.start_line, function.end_line)

    def _html_lines(self, path: str) -> dict[int, tuple[int, int]] | None:
        return _lookup(self.form_html, path)

    def _lcov_lines(self, path: str) -> dict[int, tuple[int, int]] | None:
        return _lookup(self.lcov, path)


def _lookup(index: dict[str, dict], source_path: str):
    if not index:
        return None
    normalized = {normalize_path(key): value for key, value in index.items()}
    for candidate in _candidates(source_path):
        if candidate in normalized:
            return normalized[candidate]
    for key, value in normalized.items():
        if any(suffix_match(key, candidate) for candidate in _candidates(source_path)):
            return value
    return None


def _read(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _lcov_paths(root: Path) -> list[Path]:
    paths = [
        root / "target" / "coverage" / "lcov.info",
        root / "coverage" / "lcov.info",
        root / "target" / "coverage" / "typescript" / "lcov.info",
        root / "target" / "coverage" / "rust" / "lcov.info",
        root / "target" / "coverage" / "python" / "lcov.info",
    ]
    paths.extend(root.glob("target/coverage/**/lcov.info"))
    paths.extend(root.glob("coverage/**/lcov.info"))
    return paths


def _merge_texts(paths: list[Path]) -> list[str]:
    texts: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        text = _read(path)
        if text:
            texts.append(text)
    return texts


def _merge_lcov(root: Path) -> dict[str, dict[int, tuple[int, int]]]:
    merged: dict[str, dict[int, tuple[int, int]]] = {}
    for text in _merge_texts(_lcov_paths(root)):
        merged.update(parse_lcov(text))
    return merged


def _merge_go(root: Path) -> dict[str, list[tuple[int, int, int, int]]]:
    paths = [
        root / "target" / "coverage" / "coverage.out",
        root / "target" / "coverage" / "go" / "coverage.out",
        root / "coverage.out",
    ]
    paths.extend(root.glob("*/target/coverage/go/coverage.out"))
    paths.extend(root.glob("*/*/target/coverage/go/coverage.out"))
    merged: dict[str, list[tuple[int, int, int, int]]] = {}
    for text in _merge_texts(paths):
        for key, segments in parse_go_profile(text).items():
            merged.setdefault(key, []).extend(segments)
    return merged


def _merge_jacoco(root: Path) -> dict[str, list[JacocoMethod]]:
    paths = [root / "target" / "site" / "jacoco" / "jacoco.xml"]
    paths.extend(root.glob("*/target/site/jacoco/jacoco.xml"))
    paths.extend(root.glob("*/*/target/site/jacoco/jacoco.xml"))
    merged: dict[str, list[JacocoMethod]] = {}
    for text in _merge_texts(paths):
        for key, methods in parse_jacoco_index(text).items():
            merged.setdefault(key, []).extend(methods)
    return merged


def _merge_forms(root: Path) -> dict[str, dict[int, tuple[int, int]]]:
    coverage_dir = root / "target" / "coverage"
    found: dict[str, dict[int, tuple[int, int]]] = {}
    if not coverage_dir.is_dir():
        return found
    for html_path in coverage_dir.rglob("*.html"):
        text = _read(html_path)
        if not text or "forms covered" not in text:
            continue
        relative = html_path.relative_to(coverage_dir).as_posix()
        if relative.endswith(".html"):
            relative = relative[: -len(".html")]
        found[relative] = parse_form_coverage(text)
    return found


def load_bundle(root: Path) -> CoverageBundle:
    go_profile = _merge_go(root)
    jacoco = _merge_jacoco(root)
    return CoverageBundle(
        lcov=_merge_lcov(root),
        go_profile=go_profile or None,
        jacoco=jacoco or None,
        form_html=_merge_forms(root),
    )
