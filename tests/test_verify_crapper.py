"""The verify-crapper helper deletes and drives only its own scratch projects.

A verifier runs `cleanup` and `drive` on paths it is handed. These tests lock
the guards that keep those commands away from a real folder.
"""

import os
import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / ".agents/skills/verify-crapper/bin/verify-crapper"


def _helper(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(HELPER), *args],
        env={**os.environ, "TMPDIR": str(tmp_path / "scratch")},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def decoy(tmp_path: Path) -> Path:
    folder = tmp_path / "decoy"
    folder.mkdir()
    (folder / "keep.txt").write_text("keep", encoding="utf-8")
    (tmp_path / "scratch").mkdir()
    return folder


@pytest.fixture
def project(tmp_path: Path, decoy: Path) -> Path:
    made = _helper(tmp_path, "project", "typescript")
    assert made.returncode == 0, made.stderr
    return Path(made.stdout.strip())


def test_cleanup_removes_its_own_scratch_project(tmp_path, project):
    removed = _helper(tmp_path, "cleanup", str(project))
    assert removed.returncode == 0
    assert not project.parent.exists()


def test_cleanup_refuses_a_folder_outside_its_scratch(tmp_path, decoy):
    refused = _helper(tmp_path, "cleanup", str(decoy))
    assert refused.returncode == 1
    assert "refusing" in refused.stdout
    assert (decoy / "keep.txt").is_file()


def test_cleanup_refuses_a_path_that_climbs_out_of_its_scratch(tmp_path, project, decoy):
    refused = _helper(tmp_path, "cleanup", f"{project}/../../../decoy")
    assert refused.returncode == 1
    assert (decoy / "keep.txt").is_file()
    assert project.is_dir()


def test_cleanup_refuses_a_folder_inside_the_project(tmp_path, project):
    refused = _helper(tmp_path, "cleanup", str(project / "src"))
    assert refused.returncode == 1
    assert (project / "src" / "clock.ts").is_file()


@pytest.mark.parametrize("command", ["drive", "stale"])
def test_drive_and_stale_refuse_a_real_folder(tmp_path, decoy, command):
    if command == "stale":
        refused = _helper(tmp_path, "stale", str(decoy), "coverage/lcov.info", "keep.txt")
    else:
        refused = _helper(tmp_path, "drive", str(decoy), str(tmp_path / "t.txt"))
    assert refused.returncode == 1
    assert "refusing" in refused.stdout
    assert sorted(path.name for path in decoy.iterdir()) == ["keep.txt"]


def test_doctor_says_when_cargo_llvm_cov_cannot_run_in_a_scratch_project(tmp_path):
    """A mise shim is on PATH but has no toolchain outside a project with mise.toml."""

    fake = tmp_path / "bin"
    fake.mkdir()
    for name in ("cargo", "cargo-llvm-cov"):
        shim = fake / name
        shim.write_text(
            "#!/bin/sh\necho 'mise ERROR No version is set for shim: cargo' >&2\nexit 1\n",
            encoding="utf-8",
        )
        shim.chmod(0o755)
    (tmp_path / "scratch").mkdir()
    doctor = subprocess.run(
        [str(HELPER), "doctor"],
        env={**os.environ, "TMPDIR": str(tmp_path / "scratch"), "PATH": f"{fake}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert "cargo llvm-cov fails in a scratch project" in doctor.stdout
    assert list((tmp_path / "scratch").glob("crapper-verify.*")) == []
