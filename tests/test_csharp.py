from pathlib import Path

from crapper.discover import is_test_file, iter_source_files, language_of
from crapper.languages.csharp import functions_in_source


def _rows(source: str) -> list[tuple[str, str, int]]:
    return [
        (method.namespace, method.name, method.complexity)
        for method in functions_in_source(source, "src/Clock/Ticker.cs")
    ]


def test_names_methods_and_constructors_by_namespace_and_type():
    source = """
    namespace Demo.Clock;

    public class Ticker<T> where T : class
    {
        static Ticker() { }
        public Ticker(int start) { this.start = start; }
        public int Tick(int n) { return n; }
        public int Tock(int n) => n;
        public Gear Make() => new Gear(1);
        T IClock.Get<T>() => default;

        public record struct Gear(int Teeth)
        {
            public int Spin() => Teeth;
        }
    }
    """
    assert _rows(source) == [
        ("Demo.Clock.Ticker", "Ticker", 1),
        ("Demo.Clock.Ticker", "Ticker", 1),
        ("Demo.Clock.Ticker", "Tick", 1),
        ("Demo.Clock.Ticker", "Tock", 1),
        ("Demo.Clock.Ticker", "Make", 1),
        ("Demo.Clock.Ticker", "Get", 1),
        ("Demo.Clock.Ticker.Gear", "Spin", 1),
    ]


def test_reads_block_namespaces_nested_in_each_other():
    source = """
    namespace Demo
    {
        namespace Clock.Parts
        {
            struct Dial { int Turn() { return 1; } }
            interface IFace { void Show() { } }
        }
    }
    class Loose { void Run() { } }
    """
    assert _rows(source) == [
        ("Demo.Clock.Parts.Dial", "Turn", 1),
        ("Demo.Clock.Parts.IFace", "Show", 1),
        ("Loose", "Run", 1),
    ]


def test_a_member_with_no_body_has_no_row():
    source = """
    namespace Demo;
    public interface IDial { int Turn(); }
    public abstract partial class Face
    {
        public abstract int Show();
        partial void Hook();
        [System.Runtime.InteropServices.DllImport("x")] static extern int Native();
        public Face() { }
    }
    """
    assert _rows(source) == [("Demo.Face", "Face", 1)]


def test_a_byte_order_mark_and_crlf_line_ends_change_nothing():
    """Visual Studio writes C# with a UTF-8 byte order mark and CRLF line ends."""

    source = "namespace Demo;\nclass Board\n{\n    int Place(int x)\n    {\n        return x > 0 ? x : 0;\n    }\n}\n"
    plain = functions_in_source(source, "src/Board.cs")
    marked = functions_in_source("\ufeff" + source.replace("\n", "\r\n"), "src/Board.cs")
    assert [(f.namespace, f.name, f.complexity, f.start_line, f.end_line) for f in marked] == [
        (f.namespace, f.name, f.complexity, f.start_line, f.end_line) for f in plain
    ] == [("Demo.Board", "Place", 2, 4, 7)]


def test_a_function_spans_its_lines():
    source = "namespace Demo;\nclass Board\n{\n    int Place(int x)\n    {\n        return x;\n    }\n}\n"
    [place] = functions_in_source(source, "src/Board.cs")
    assert (place.start_line, place.end_line) == (4, 7)
    assert (place.path, place.language) == ("src/Board.cs", "csharp")


def _complexity(body: str) -> int:
    source = f"class Sample {{ int Run(int[] xs, string? s, bool a, bool b) {{ {body} }} }}"
    [method] = functions_in_source(source, "Sample.cs")
    return method.complexity


def test_each_decision_adds_one():
    assert _complexity("return 1;") == 1
    assert _complexity("if (a) { } else if (b) { } else { } return 1;") == 3
    assert _complexity("for (var i = 0; i < 2; i++) { } return 1;") == 2
    assert _complexity("foreach (var x in xs) { } return 1;") == 2
    assert _complexity("while (a) { } return 1;") == 2
    assert _complexity("do { } while (a); return 1;") == 2
    assert _complexity("try { } catch (System.IO.IOException e) when (a) { } catch { } return 1;") == 3
    assert _complexity("return a ? 1 : 2;") == 2
    assert _complexity("return a && b || !a ? 1 : 0;") == 4
    assert _complexity("return s?.Length ?? 0;") == 3
    assert _complexity("return s?.Trim()?.Length ?? xs?[0] ?? 0;") == 6


def test_each_case_label_and_switch_arm_adds_one():
    switch = "switch (xs.Length) { case 1: case 2: return 1; case 3 when a: return 3; default: return 0; }"
    assert _complexity(switch) == 5
    assert _complexity("return xs.Length switch { 0 => 0, 1 => 1, _ => 2 };") == 4


def test_guards_patterns_and_null_assignment_are_not_decisions():
    assert _complexity("if (xs is [] or [_]) { } s ??= \"x\"; return 1;") == 2
    assert _complexity("int d = default; return default(int) + (a == default ? 1 : d);") == 2


def test_local_functions_and_lambdas_count_toward_their_member():
    body = (
        "int Half(int v) => v > 1 ? v / 2 : v;"
        " System.Func<int, int> twice = v => v < 0 ? 0 : v * 2;"
        " return Half(twice(1));"
    )
    assert _complexity(body) == 3


def test_keywords_in_comments_and_strings_are_not_decisions():
    body = 'var t = "if && || ?? ?. case default catch"; // if && || ?? case\n /* switch ? : */ return 1;'
    assert _complexity(body) == 1


def _project(folder: Path, csproj: str = '<Project Sdk="Microsoft.NET.Sdk" />') -> Path:
    """A C# project in `folder`, with `csproj` as its .csproj, and one source file. Returns the file."""

    folder.mkdir(parents=True)
    (folder / f"{folder.name}.csproj").write_text(csproj, encoding="utf-8")
    source = folder / "Code.cs"
    source.write_text("class Code { void Run() { } }\n", encoding="utf-8")
    return source.resolve()


def _references(package: str) -> str:
    return f'<Project><ItemGroup><PackageReference Include="{package}" Version="1.0.0" /></ItemGroup></Project>'


def test_a_cs_file_is_csharp():
    assert language_of("src/Clock/Ticker.cs") == "csharp"


def test_files_in_a_test_project_are_not_scored(tmp_path):
    tests = [
        _project(tmp_path / "Clock.Tests"),
        _project(tmp_path / "Clock.Test.Unit"),
        _project(tmp_path / "Clock.IntegrationTests"),
        _project(tmp_path / "Clock.UnitTest", '<Project Sdk="MSTest.Sdk/4.2.2"></Project>'),
        _project(tmp_path / "Tests"),
        _project(tmp_path / "Specs", "<Project><PropertyGroup><IsTestProject> true </IsTestProject></PropertyGroup></Project>"),
        _project(tmp_path / "Sdk", _references("Microsoft.NET.Test.Sdk")),
        _project(tmp_path / "Nunit", _references("NUnit")),
        _project(tmp_path / "Xunit", _references("xunit.v3")),
        _project(tmp_path / "Xunit2", _references("xunit")),
        _project(tmp_path / "Mstest", _references("MSTest.TestFramework")),
        _project(tmp_path / "Meta", _references("MSTest")),
        _project(tmp_path / "Probes", '<Project Sdk="MSTest.Sdk/3.6.1"></Project>'),
        _project(tmp_path / "Sampler", '<Project Sdk="MSTest.Sdk"></Project>'),
    ]
    deeper = tmp_path / "Clock.Tests" / "Fakes" / "Clock.cs"
    deeper.parent.mkdir()
    deeper.write_text("class Clock { }\n", encoding="utf-8")
    for source in [*tests, deeper]:
        assert is_test_file(source) is True, source
    assert iter_source_files([tmp_path]) == []


def test_a_csproj_is_read_as_xml(tmp_path):
    """Review round 1: quoting, spacing and an old-style namespace don't hide a test project, and a comment doesn't make one."""

    legacy = (
        '<Project ToolsVersion="15.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'
        '<ItemGroup><PackageReference Include="MSTest.TestFramework"><Version>3.0.0</Version></PackageReference>'
        "</ItemGroup></Project>"
    )
    tests = [
        _project(tmp_path / "Quoted", "<Project><ItemGroup><PackageReference Include='xunit.v3' /></ItemGroup></Project>"),
        _project(tmp_path / "Spaced", '<Project><ItemGroup><PackageReference Include = "NUnit" /></ItemGroup></Project>'),
        _project(tmp_path / "Legacy", legacy),
        _project(tmp_path / "SdkQuoted", "<Project Sdk='MSTest.Sdk/4.2.2'></Project>"),
        _project(tmp_path / "SdkElement", '<Project><Sdk Name="MSTest.Sdk" Version="3.6.1" /></Project>'),
    ]
    scored = [
        _project(tmp_path / "Commented", '<Project><!-- <PackageReference Include="NUnit" /> '
                 "<IsTestProject>true</IsTestProject> --></Project>"),
        _project(tmp_path / "Broken", '<Project><ItemGroup><PackageReference Include="NUnit"'),
    ]
    for source in tests:
        assert is_test_file(source) is True, source
    for source in scored:
        assert is_test_file(source) is False, source


def test_files_in_other_projects_and_in_no_project_are_scored(tmp_path):
    scored = [
        _project(tmp_path / "Contests"),
        _project(tmp_path / "Clock.Testing"),
        _project(tmp_path / "Clock", "<Project><PropertyGroup><IsTestProject>false</IsTestProject></PropertyGroup></Project>"),
        _project(tmp_path / "Lite", _references("NUnitLite")),
        _project(tmp_path / "Stryker.TestRunner.VsTest"),
        _project(tmp_path / "Tools.UnitTest"),
        _project(tmp_path / "Runner", _references("Microsoft.Testing.Platform")),
        _project(tmp_path / "Hooks", _references("Microsoft.Testing.Platform.MSBuild")),
        _project(tmp_path / "Asserts", _references("xunit.assert")),
        _project(tmp_path / "Bench", '<Project Sdk="MSTest.Sdk.Extras"></Project>'),
    ]
    loose = tmp_path / "scripts" / "Build.cs"
    loose.parent.mkdir()
    loose.write_text("class Build { }\n", encoding="utf-8")
    for source in [*scored, loose]:
        assert is_test_file(source) is False, source
    assert iter_source_files([tmp_path]) == sorted([*scored, loose.resolve()], key=Path.as_posix)


def test_a_projects_build_output_is_not_scored(tmp_path):
    source = _project(tmp_path / "src" / "Clock")
    for folder in ("obj/Debug/net10.0", "bin/Debug"):
        generated = source.parent / folder / "Generated.cs"
        generated.parent.mkdir(parents=True)
        generated.write_text("class Generated { void Emit() { } }\n", encoding="utf-8")
    tool = _project(tmp_path / "obj" / "Tool")
    script = tmp_path / "web" / "bin" / "cli.js"
    script.parent.mkdir(parents=True)
    script.write_text("export function run() { return 1 }\n", encoding="utf-8")
    assert iter_source_files([tmp_path]) == [tool, source, script.resolve()]
