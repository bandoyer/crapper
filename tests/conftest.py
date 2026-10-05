"""Keep a mutant from launching coverage against the project under test.

`run()` falls through into `run_coverage` or `collect_coverage` when a mutant
skips the help return. That would delete `target/coverage` and recurse into
this suite. The stubs return None, so a default run in a test reads the
reports the test put on disk.
"""

import pytest


@pytest.fixture(autouse=True)
def do_not_launch_project_coverage(monkeypatch):
    monkeypatch.setattr("crapper.cli.run_coverage", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("crapper.cli.collect_coverage", lambda *_args, **_kwargs: None)
