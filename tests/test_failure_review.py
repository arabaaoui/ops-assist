"""The failure review must remain usable as a local evidence map."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "docs" / "failure-review.md"


def test_failure_review_links_and_owner():
    text = REVIEW.read_text(encoding="utf-8")
    links = re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text)
    assert links
    for link in links:
        target = urlsplit(link)
        if not target.scheme and not target.netloc:
            assert (REVIEW.parent / unquote(target.path)).exists(), link
    assert re.search(r"(?m)^Owner: _{5,}\s*$", text)
    for heading in (
        "Unclear need",
        "Missing data",
        "No validation",
        "Uncontrolled cost",
        "No owner",
    ):
        assert f"## {heading}" in text
