"""The repository stays shareable: no term from a private list may appear in it.

The list itself is not in the repository (it would leak what it protects): CI reads
it from the FORBIDDEN_TERMS secret, one regex per line. On a push to main and on pull
requests from this repository, CI sets REQUIRE_FORBIDDEN_TERMS=true, so a missing
secret fails the build instead of silently skipping the check. Pull requests from
forks get no secrets: there the test skips and says so. Matches report the pattern's
number, never the pattern, because CI logs are public.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def tracked_files(root: Path) -> list[Path]:
    """Files under version control, plus new files not ignored; never .env or .venv."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout
    return [root / p for p in out.decode().split("\0") if p]


def scan(root: Path, files: list[Path], patterns: list[re.Pattern]) -> list[str]:
    """Return 'file: pattern #n' for every match in a file's path or content."""
    hits = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        text = rel + "\n" + f.read_text(encoding="utf-8", errors="ignore")
        hits += [f"{rel}: pattern #{i}" for i, p in enumerate(patterns, 1) if p.search(text)]
    return hits


def compile_terms(raw: str) -> list[re.Pattern]:
    return [re.compile(line.strip(), re.I) for line in raw.splitlines() if line.strip()]


def test_no_forbidden_term_in_the_repository():
    raw = os.environ.get("FORBIDDEN_TERMS", "").strip()
    if not raw:
        if os.environ.get("REQUIRE_FORBIDDEN_TERMS", "").lower() == "true":
            pytest.fail("FORBIDDEN_TERMS is required here but is empty: configure the CI secret")
        pytest.skip("FORBIDDEN_TERMS not set")
    files = [f for f in tracked_files(ROOT) if f.is_file()]
    assert len(files) > 20, f"only {len(files)} files to scan: the scan would prove nothing"
    hits = scan(ROOT, files, compile_terms(raw))
    assert not hits, hits


def test_the_scanner_finds_a_planted_term_in_content_and_names(tmp_path):
    (tmp_path / "ok.txt").write_text("nothing to see")
    (tmp_path / "leak.txt").write_text("written by Acme Corp")
    (tmp_path / "acme-notes.md").write_text("clean")
    patterns = compile_terms("acme\r\n  \n")  # CRLF and blank lines are tolerated
    files = sorted(tmp_path.iterdir())
    assert scan(tmp_path, files, patterns) == ["acme-notes.md: pattern #1", "leak.txt: pattern #1"]
