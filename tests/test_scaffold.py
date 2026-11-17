import os
import subprocess
import sys

import pytest

from ops_assist import cli


@pytest.mark.parametrize("name", ["", "../oops", "Bad", "a-b", "class", "a" * 65])
def test_invalid_names_do_not_create_destination(tmp_path, name, capsys):
    target = tmp_path / "agent"
    assert cli.main(["new-agent", name, "--dir", str(target)]) == 1
    assert "NAME" in capsys.readouterr().err
    assert not target.exists()


def test_existing_destination_is_protected(tmp_path, capsys):
    target = tmp_path / "agent"
    target.mkdir()
    (target / "keep").write_text("preserve")
    assert cli.main(["new-agent", "example", "--dir", str(target)]) == 1
    assert "empty" in capsys.readouterr().err
    assert (target / "keep").read_text() == "preserve"
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    assert cli.main(["new-agent", "example", "--dir", str(link)]) == 1
    assert (target / "keep").read_text() == "preserve"


def test_generate_and_run_tests_offline(tmp_path, capsys):
    target = tmp_path / "agent"
    target.mkdir()
    assert cli.main(["new-agent", "example_agent", "--dir", str(target)]) == 0
    assert "Created agent example_agent" in capsys.readouterr().out
    assert (target / "SKILL.md").read_text().startswith("---")
    assert "example_agent" in (target / "README.md").read_text()
    assert "OPS_ASSIST_REPOSITORY" in (target / ".github/workflows/ci.yml").read_text()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(target)
    env["OPS_ASSIST_TEST_ASYNC_TICK"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
