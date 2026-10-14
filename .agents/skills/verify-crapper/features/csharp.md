# C#

crapper scores C# methods and constructors (`.cs`). `:namespace` is the C# namespace plus the enclosing types, and a constructor is named by its class. Complexity counts `if`, `for`, `foreach`, `while`, `do`, `catch`, `?:`, each `case` and `default` label, each switch-expression arm, `&&`, `||`, `??` and `?.`, including those in a local function or a lambda. Coverage runs `dotnet test --coverlet --coverlet-output-format lcov --results-directory <root>/target/coverage/csharp` once in the project root and reads the `coverage.<number>.info` files coverlet.MTP writes there. A file in a C# test project, or under `bin/` or `obj/`, isn't scored.

## Sub-features

- `csharp-complexity` lists each method and constructor with its namespace and complexity, and gives no row to a member with no body.
- `csharp-coverage` runs `dotnet test` with coverlet.MTP, reads its `coverage.<number>.info`, and clears the results folder before each run.
- `csharp-test-projects` skips a project whose folder name has a `Test` or `Tests` part or ends in `Tests`, or whose `.csproj` marks it a test project (`IsTestProject`, `MSTest.Sdk`, or a reference to `Microsoft.NET.Test.Sdk`, `NUnit`, `xunit`, `xunit.v3`, `MSTest` or `MSTest.TestFramework`), and skips `bin/` and `obj/`. A name ending in `Test`, or a reference to `Microsoft.Testing.Platform`, doesn't make a test project.
- `csharp-no-coverlet` warns, scores 0%, and names coverlet.MTP and the MTP runner when the coverage run writes nothing.
- `csharp-existing-coverage` reads the coverage file a default run left, with `--use-existing-coverage`.

## How to get to it (user POV)

- Run `crapper` in a .NET solution folder whose test projects reference coverlet.MTP and whose global.json sets `"test": {"runner": "Microsoft.Testing.Platform"}`.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`, and its `tools:` line names a `dotnet` 10 SDK.
- The first `dotnet test` in a scratch project restores NUnit, NUnit3TestAdapter and coverlet.MTP from nuget.org, so it needs the network unless `~/.nuget/packages` already holds them.
- `T` is the transcript path for the sub-feature.

- **csharp-complexity.** `project=$($vc project csharp)`, then `$vc drive "$project" "$T" --no-coverage`. Exit code `0`. The table has `Ticker`, `Tick` and `Tock` in `Demo.Clock.Ticker`, `Spin` in `Demo.Clock.Ticker.Gear`, and `Turn` in `Demo.Clock.Dial` with complexity `19`, each with `N/A` coverage and CRAP, plus the four control rows from `csharp-test-projects`. There's no row for `IDial.Turn`. `.metrics/crap.edn` lists the same entries with `:coverage nil`. Then `$vc drive "$project" "$T" --help` lists `C# (.cs)` under Languages, the `dotnet test` coverage line, and `namespace.Class` under the uml-viewer joins.
- **csharp-coverage.** `project=$($vc project csharp)`, then `$vc stale "$project" target/coverage/csharp/coverage.1.info src/Clock/Ticker.cs`, then `$vc drive "$project" "$T"`. Exit code `0`. stderr has `+ (<project>) dotnet test --coverlet --coverlet-output-format lcov --results-directory <project>/target/coverage/csharp`. "coverage reports before" lists `coverage.1.info`; "after" lists one `target/coverage/csharp/coverage.<number>.info` and no `coverage.1.info`. The table scores `Tick` `100.0%`, `Tock` `0.0%`, and `Ticker` `50.0%`, each with a CRAP score, and `.metrics/crap.edn` agrees. Drive it a second time: "after" again lists one coverage file, with a new number.
- **csharp-test-projects.** On the `csharp` project, `$vc drive "$project" "$T" --no-coverage`. There's no row for `Wire` (`src/Clock.IntegrationTests`), `Check` (`src/Clock.Test.Unit`), `Verify` (`src/Checks`, whose `.csproj` references `xunit.v3`), `Describe` (`src/Specs`, `<IsTestProject>true</IsTestProject>`), `Poke` (`src/Probes`, `Sdk="MSTest.Sdk/3.6.1"`), `Repeat` (`src/Clock.UnitTest`, whose `.csproj` uses `Sdk="MSTest.Sdk/4.2.2"`), `Emit` (`src/Clock/obj/Generated.cs`), or the tests in `src/Clock.Tests`. `Score` in `Fixture.Contest` (`src/Contests`), `Fake` in `Fixture.Fakes` (`src/Clock.Testing`), `Relay` in `Fixture.Bridge` (`src/Clock.TestRunner.VsTest`, production code whose name ends in `Test`), and `Launch` in `Fixture.Host` (`src/Runner`, whose `.csproj` references `Microsoft.Testing.Platform`) have rows.
- **csharp-no-coverlet.** `project=$($vc project csharp-no-coverlet)`, then `$vc drive "$project" "$T"`. Exit code `0`. stderr has `C# coverage exited 5 in <project>. C# coverage will score 0%.`, and the next line names coverlet.MTP and global.json's `"test": {"runner": "Microsoft.Testing.Platform"}`. Every row scores `0.0%`, and "coverage reports after" is `(none)`.
- **csharp-existing-coverage.** After a `csharp-coverage` drive on a project, `$vc drive "$project" "$T" --use-existing-coverage`. Exit code `0`. stderr has no `dotnet test` line. The table shows the same coverage as the drive before it, and "coverage reports after" still lists that `coverage.<number>.info`.

## Gotchas

- coverlet.MTP numbers its file by the run's time (`ddMMyyHHmmssfff`), so two runs never share a name. Without `--results-directory`, it writes to `TestResults/` in the folder `dotnet test` runs in, and keeps every earlier run's file.
- Without global.json's MTP runner, `dotnet test` rejects `--coverlet` with `MSB1001: Unknown switch`, and C# scores 0%.
- The folders outside `Clock.slnx` aren't built. crapper finds their `.cs` files by walking the tree.
