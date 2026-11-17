"""Create a minimal platform-backed agent project without network access."""

import keyword
import re
from pathlib import Path

TEMPLATES = Path(__file__).parent / "scaffold_templates"


def new_agent(name: str, directory: Path) -> None:
    """Populate an absent or empty directory with a read-only agent skeleton."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or keyword.iskeyword(name):
        raise ValueError("NAME must be a lowercase Python identifier (1–64 characters)")
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError("destination must be a real directory")
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("destination directory must be empty")
    directory.mkdir(parents=True, exist_ok=True)
    for source in TEMPLATES.rglob("*"):
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        relative = source.relative_to(TEMPLATES)
        if relative.suffix == ".tmpl":
            relative = relative.with_suffix("")
        if relative.name == "workflow.txt":
            relative = Path(".github/workflows/ci.yml")
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            source.read_text(encoding="utf-8").replace("__AGENT_NAME__", name), encoding="utf-8"
        )
