"""Keep the production review navigable and its diagram recognizable."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "docs" / "production-review.md"


def test_review_links_and_diagram():
    text = REVIEW.read_text(encoding="utf-8")
    links = re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text)
    assert links
    for link in links:
        target = urlsplit(link)
        if not target.scheme and not target.netloc:
            assert (REVIEW.parent / unquote(target.path)).exists(), link
    diagrams = re.findall(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
    assert diagrams
    for diagram in diagrams:
        assert re.match(
            r"\s*(?:flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|pie|mindmap|timeline)\b",
            diagram,
        )
