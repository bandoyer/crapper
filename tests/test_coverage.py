import pytest

from crapper.analyze import analyze_files
from crapper.coverage import (
    CoverageBundle,
    Report,
    go_percent,
    load_bundle,
    parse_form_coverage,
    parse_go_profile,
    parse_jacoco_index,
    parse_lcov,
)
from crapper.model import Function


def function(**kwargs):
    defaults = dict(
        name="choose",
        namespace="demo.core",
        complexity=2,
        start_line=3,
        end_line=5,
        path="src/demo/core.clj",
        language="clojure",
        jacoco_class=None,
    )
    defaults.update(kwargs)
    return Function(**defaults)


def test_cloverage_form_counts_and_lcov_lines():
    html = '<span class="pc" title="1 out of 2 forms covered">   4&nbsp;&nbsp;(if x 1)</span>'
    assert parse_form_coverage(html) == {4: (1, 2)}
    lcov = "SF:src/demo/core.clj\nDA:3,1\nDA:4,0\nDA:9,3\nend_of_record\n"
    parsed = parse_lcov(lcov)
    bundle = CoverageBundle(lcov=parsed, form_html={"src/demo/core.clj": {4: (1, 2)}})
    # Form HTML wins over LCOV for Clojure, matching crap4clj.
    assert bundle.percent_for(function(start_line=3, end_line=5)) == 50.0


def test_lcov_percentage_when_there_is_no_html():
    lcov = parse_lcov("SF:src/demo/core.clj\nDA:3,1\nDA:4,0\nend_of_record\n")
    bundle = CoverageBundle(lcov=lcov)
    assert bundle.percent_for(function(start_line=3, end_line=4)) == 50.0
    assert bundle.percent_for(function(path="src/missing.clj")) is None


def test_lcov_branch_records_override_line_hits():
    text = "SF:src/demo/app.ts\nDA:2,1\nDA:3,1\nBRDA:3,0,0,1\nBRDA:3,0,1,-\nend_of_record\n"
    parsed = parse_lcov(text)
    assert parsed["src/demo/app.ts"][2] == (1, 1)
    assert parsed["src/demo/app.ts"].branches[3] == (1, 2)
    bundle = CoverageBundle(lcov=parsed)
    scored = function(
        path="src/demo/app.ts",
        language="typescript",
        start_line=2,
        end_line=3,
        namespace="demo.app",
    )
    assert bundle.percent_for(scored) == 50.0


def test_a_branchless_span_keeps_line_coverage():
    text = "SF:src/demo/app.ts\nDA:2,1\nDA:3,0\nBRDA:8,0,0,1\nBRDA:8,0,1,0\nend_of_record\n"
    bundle = CoverageBundle(lcov=parse_lcov(text))
    scored = function(path="src/demo/app.ts", language="typescript", start_line=2, end_line=3)
    assert bundle.percent_for(scored) == 50.0


def test_go_profile_matches_crap4go_statement_ranges():
    profile = parse_go_profile(
        "mode: set\ngithub.com/acme/demo/board.go:4.1,6.2 2 1\ngithub.com/acme/demo/board.go:8.1,9.2 1 0\n"
    )
    assert go_percent(profile, "board.go", 4, 6) == 100.0
    assert go_percent(profile, "board.go", 8, 9) == 0.0
    assert go_percent(profile, "other.go", 1, 3) is None


def test_jacoco_instruction_coverage_joins_on_class_and_method():
    xml = """<?xml version="1.0"?>
    <report>
      <package>
        <class name="demo/pkg/Board">
          <method name="place" line="4">
            <counter type="INSTRUCTION" missed="1" covered="3"/>
          </method>
        </class>
        <class name="demo/pkg/Board$Inner">
          <method name="tick" line="9">
            <counter type="INSTRUCTION" missed="0" covered="2"/>
          </method>
        </class>
      </package>
    </report>
    """
    bundle = CoverageBundle(jacoco=parse_jacoco_index(xml))
    outer = function(
        name="place",
        namespace="demo.pkg.Board",
        language="java",
        jacoco_class="demo.pkg.Board",
        start_line=4,
        path="src/demo/pkg/Board.java",
    )
    inner = function(
        name="tick",
        namespace="demo.pkg.Board.Inner",
        language="java",
        jacoco_class="demo.pkg.Board$Inner",
        start_line=9,
        path="src/demo/pkg/Board.java",
    )
    assert bundle.percent_for(outer) == 75.0
    assert bundle.percent_for(inner) == 100.0


def test_jacoco_skips_methods_without_an_instruction_counter():
    xml = """<report>
      <class name="demo/pkg/Board">
        <method name="skip" line="2">
          <counter type="LINE" missed="1" covered="0"/>
        </method>
        <method name="bad" line="nope">
          <counter type="INSTRUCTION" missed="1" covered="1"/>
        </method>
        <counter type="INSTRUCTION" missed="0" covered="1"/>
      </class>
    </report>"""
    found = parse_jacoco_index(xml)
    assert list(found) == ["demo.pkg.Board#bad"]
    assert found["demo.pkg.Board#bad"][0].line == 0


def test_missing_go_profile_is_na():
    assert go_percent(None, "board.go", 1, 3) is None


def test_load_bundle_merges_each_report(tmp_path):
    lcov = tmp_path / "target" / "coverage" / "lcov.info"
    lcov.parent.mkdir(parents=True)
    lcov.write_text("SF:src/demo/core.clj\nDA:3,1\nDA:4,0\nend_of_record\n", encoding="utf-8")
    go = tmp_path / "target" / "coverage" / "go" / "coverage.out"
    go.parent.mkdir(parents=True)
    go.write_text("mode: set\nboard.go:1.1,2.2 1 1\n", encoding="utf-8")
    jacoco = tmp_path / "target" / "site" / "jacoco" / "jacoco.xml"
    jacoco.parent.mkdir(parents=True)
    jacoco.write_text(
        '<report><class name="demo/Board"><method name="place" line="4">'
        '<counter type="INSTRUCTION" missed="0" covered="1"/></method></class></report>',
        encoding="utf-8",
    )
    html = tmp_path / "target" / "coverage" / "src" / "demo" / "core.clj.html"
    html.parent.mkdir(parents=True)
    html.write_text(
        '<span title="1 out of 2 forms covered">   4&nbsp;&nbsp;(if x 1)</span>',
        encoding="utf-8",
    )
    (tmp_path / "target" / "coverage" / "index.html").write_text("<html></html>", encoding="utf-8")
    bundle = load_bundle(tmp_path)
    assert bundle.percent_for(function(start_line=3, end_line=4)) == 50.0
    assert bundle.go_profile is not None
    assert bundle.jacoco is not None


def test_combined_records_keep_the_line_and_branch_shapes(tmp_path):
    report = tmp_path / "coverage" / "lcov.info"
    report.parent.mkdir(parents=True)
    report.write_text(
        "SF:src/app.ts\nDA:2,1\nDA:3,0\nBRDA:3,0,0,1\nBRDA:3,0,1,0\nend_of_record\n"
        "SF:src/app.ts\nDA:2,0\nDA:3,4\nBRDA:3,0,0,0\nBRDA:3,0,1,2\nend_of_record\n",
        encoding="utf-8",
    )
    record = load_bundle(tmp_path).lcov["src/app.ts"]
    assert dict(record) == {2: (1, 1), 3: (1, 1)}
    assert record.branches == {3: (2, 2)}


def test_load_bundle_with_only_a_root_reads_every_report_on_disk_as_written(tmp_path):
    """mutator and --use-existing-coverage call `load_bundle(root)`: every report, `SF:` kept as written."""

    absolute = (tmp_path / "src" / "lib.rs").resolve().as_posix()
    files = {
        "coverage/lcov.info": "SF:src/lib.rs\nDA:5,1\nend_of_record\n",
        "target/coverage/rust/lcov.info": f"SF:{absolute}\nDA:1,1\nend_of_record\n",
        "coverage.out": "mode: set\nexample.com/clock/clock.go:3.17,5.2 1 1\n",
        "a/b/target/site/jacoco/jacoco.xml": (
            '<report><class name="demo/Clock"><method name="tick" line="4">'
            '<counter type="INSTRUCTION" missed="0" covered="1"/></method></class></report>'
        ),
    }
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    bundle = load_bundle(tmp_path)
    assert {key: dict(lines) for key, lines in bundle.lcov.items()} == {
        "src/lib.rs": {5: (1, 1)},
        absolute: {1: (1, 1)},
    }
    assert list(bundle.go_profile) == ["example.com/clock/clock.go"]
    assert list(bundle.jacoco) == ["demo.Clock#tick"]


def test_a_listed_report_resolves_a_relative_source_against_its_module(tmp_path):
    report = tmp_path / "target" / "coverage" / "python" / "one" / "lcov.info"
    report.parent.mkdir(parents=True)
    report.write_text(
        "SF:src/core.py\nDA:1,1\nend_of_record\nSF:/elsewhere/x.py\nDA:2,1\nend_of_record\n",
        encoding="utf-8",
    )
    bundle = load_bundle(tmp_path, [Report(report, tmp_path / "one")])
    assert sorted(bundle.lcov) == sorted(
        [(tmp_path / "one" / "src" / "core.py").resolve().as_posix(), "/elsewhere/x.py"]
    )


# Two crates with the same src/lib.rs layout. The first function is on lines
# 1-3 and the second on lines 5-7; the LCOV hits say which one a test called.
TWO_FUNCTIONS = "pub fn {0}() -> i32 {{\n    1\n}}\n\npub fn {1}() -> i32 {{\n    2\n}}\n"


def _crate(folder, first, second, hit_first):
    source = folder / "src" / "lib.rs"
    source.parent.mkdir(parents=True)
    source.write_text(TWO_FUNCTIONS.format(first, second), encoding="utf-8")
    hits = [(line, int((line < 4) == hit_first)) for line in (1, 2, 3, 5, 6, 7)]
    record = "".join(f"DA:{line},{hit}\n" for line, hit in hits)
    return source, f"SF:{source.resolve().as_posix()}\n{record}end_of_record\n"


@pytest.mark.parametrize("layout", ["run-from-a-member-crate", "report-names-a-sibling-crate"])
def test_a_source_is_matched_to_its_report_under_the_root_not_the_current_folder(
    tmp_path, monkeypatch, layout
):
    """#31: cargo-llvm-cov's absolute SF: keys match a source by its path under --root.

    run-from-a-member-crate: the workspace root is the package clock, and the
    user stands in its member crate gears/, whose src/lib.rs would be gears'
    own key if resolved against the current folder.
    report-names-a-sibling-crate: `cargo llvm-cov --workspace` in clock/ also
    names its sibling gears/src/lib.rs at the same depth; only clock is scored.
    """

    workspace = tmp_path / "ws"
    if layout == "run-from-a-member-crate":
        root, gears, here = workspace, workspace / "gears", workspace / "gears"
    else:
        root, gears, here = workspace / "clock", workspace / "gears", workspace
    clock_source, clock_record = _crate(root, "tick", "tock", hit_first=True)
    gears_source, gears_record = _crate(gears, "idle", "spin", hit_first=False)
    report = root / "target" / "coverage" / "rust" / "lcov.info"
    report.parent.mkdir(parents=True)
    report.write_text(clock_record + gears_record, encoding="utf-8")
    scored = [clock_source, gears_source] if gears.is_relative_to(root) else [clock_source]
    monkeypatch.chdir(here)

    entries = analyze_files(scored, root, load_bundle(root, [Report(report, root)]))

    want = {"tick": 100.0, "tock": 0.0}
    if len(scored) == 2:
        want |= {"idle": 0.0, "spin": 100.0}
    assert {entry.name: entry.coverage for entry in entries} == want


def test_without_a_root_a_source_has_no_absolute_candidate():
    """A bundle that was never bound to a root doesn't guess one: `pkg/src/lib.rs` doesn't take `pkg/lib.rs`."""

    bundle = CoverageBundle(lcov={"pkg/lib.rs": {1: (1, 1)}})
    assert bundle.percent_for(function(path="pkg/src/lib.rs", start_line=1, end_line=1)) is None
