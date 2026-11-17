"""Keep CI gates and publication permissions explicit."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_ci_gates_and_publication():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert workflow["on"]["push"]["branches"] == ["main"]
    # Only release tags publish an image, not the etape-NN step tags.
    assert workflow["on"]["push"]["tags"] == ["v*"]
    assert "pull_request" in workflow["on"]
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    gates = {"lint", "tests", "contract-tests", "offline-evals", "redteam"}
    assert set(jobs) == gates | {"image"}
    image = jobs["image"]
    assert set(image["needs"]) == gates
    assert image["permissions"] == {"contents": "read", "packages": "write", "id-token": "write"}
    assert all("permissions" not in jobs[name] for name in gates)
    for job in jobs.values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"])
    commands = {name: "\n".join(s.get("run", "") for s in jobs[name]["steps"]) for name in gates}
    assert "ruff check ." in commands["lint"] and "ruff format --check ." in commands["lint"]
    assert "pytest -q" in commands["tests"]
    assert "tests/test_replay.py tests/test_live_sources.py" in commands["contract-tests"]
    assert "eval check-reports tests/fixtures/evaluation/passing" in commands["offline-evals"]
    assert "redteam --fast" in commands["redteam"]
    scan = next(s for s in jobs["tests"]["steps"] if "pytest -q" in s.get("run", ""))
    assert scan["env"]["FORBIDDEN_TERMS"] == "${{ secrets.FORBIDDEN_TERMS }}"
    assert "github.event_name" in scan["env"]["REQUIRE_FORBIDDEN_TERMS"]
    steps = image["steps"]
    build = next(s for s in steps if s.get("id") == "build")
    tag_condition = "startsWith(github.ref, 'refs/tags/v')"
    assert build["with"]["push"] == "${{ " + tag_condition + " }}"
    for fragment in ("docker/login-action@", "sigstore/cosign-installer@"):
        assert next(s for s in steps if fragment in s.get("uses", ""))["if"] == tag_condition
    sign = next(s for s in steps if "cosign sign" in s.get("run", ""))
    assert sign["if"] == tag_condition and "${IMAGE}@${DIGEST}" in sign["run"]
    assert sign["env"]["DIGEST"] == "${{ steps.build.outputs.digest }}"


def test_container_is_pinned_and_non_root():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert (
        "python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
        in dockerfile
    )
    assert (
        "ghcr.io/astral-sh/uv:0.9@sha256:538e0b39736e7feae937a65983e49d2ab75e1559d35041f9878b7b7e51de91e4"
        in dockerfile
    )
    assert "COPY --from=uv /uv /usr/local/bin/uv" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER app" in dockerfile and 'ENTRYPOINT ["ops-assist"]' in dockerfile
