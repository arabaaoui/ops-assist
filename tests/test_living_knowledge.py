from datetime import date, timedelta

import pytest
import yaml

from ops_assist import cli
from ops_assist.knowledge.embeddings import HashEmbedder
from ops_assist.knowledge.index import VectorIndex, load_documents
from ops_assist.knowledge.living import approve, draft, is_stale, save_report
from ops_assist.knowledge.retrieval import search
from ops_assist.report import IncidentReport
from ops_assist.security import StateStore


def report():
    return IncidentReport.model_validate(
        {
            "summary": "token=fictional-secret",
            "status": "hypotheses_only",
            "facts": [{"statement": "Error observed", "source": "logs/app"}],
            "unknowns": ["password=fictional"],
        }
    )


def test_draft_redaction_provenance_and_approval(monkeypatch):
    save_report(report(), "session-a")
    path = draft("session-a")
    text = path.read_text()
    meta = yaml.safe_load(text.split("---", 2)[1])
    assert meta["status"] == "draft" and meta["owner"] == "unassigned"
    assert meta["provenance"]["session"] == "session-a"
    assert meta["provenance"]["report_hash"].startswith("sha256:")
    assert "fictional-secret" not in text and "password=fictional" not in text
    assert "[redacted]" in text
    assert meta["id"] not in {d["id"] for d in load_documents()}
    VectorIndex.build(HashEmbedder()).save(StateStore())
    monkeypatch.setattr("getpass.getuser", lambda: "reviewer")
    target = approve(meta["id"], HashEmbedder(), "reviewer")
    assert not path.exists()
    approved = yaml.safe_load(target.read_text().split("---", 2)[1])
    assert approved["status"] == "approved" and approved["approved_by"] == "reviewer"
    assert approved["approved_at"]
    assert meta["id"] in {d["id"] for d in load_documents()}
    index = VectorIndex.load(StateStore(), HashEmbedder())
    assert any(c["id"].startswith(meta["id"]) for c in index.chunks)
    with pytest.raises(ValueError):
        draft("session-a")


def test_cli_confirmation_and_report_file(monkeypatch, tmp_path, capsys):
    file = tmp_path / "report.json"
    file.write_text(report().model_dump_json())
    assert cli.main(["knowledge", "draft-postmortem", "--report", str(file)]) == 0
    path = capsys.readouterr().out.strip()
    identifier = __import__("pathlib").Path(path).stem
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.main(["knowledge", "approve", identifier, "--yes"]) == 1
    monkeypatch.setenv("OPS_ASSIST_ALLOW_NONINTERACTIVE_APPROVAL", "1")
    assert cli.main(["knowledge", "approve", identifier]) == 1
    assert cli.main(["knowledge", "approve", identifier, "--yes"]) == 1
    assert cli.main(["knowledge", "approve", identifier, "--yes", "--approver", "reviewer"]) == 0
    approved = yaml.safe_load(
        (__import__("pathlib").Path(path).parent.parent / "approved" / (identifier + ".md"))
        .read_text()
        .split("---", 2)[1]
    )
    assert approved["approval"] == "noninteractive" and approved["approved_by"] == "reviewer"
    assert cli.main(["knowledge", "search", "Error", "-k", "2"]) == 0
    assert "updated=" in capsys.readouterr().out


def test_interactive_confirmation(monkeypatch):
    path = draft(report_file=_write_report(monkeypatch))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "no")
    assert cli.main(["knowledge", "approve", path.stem]) == 1
    assert path.exists()
    monkeypatch.setattr("getpass.getuser", lambda: "reviewer")
    answers = iter(["yes", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert cli.main(["knowledge", "approve", path.stem]) == 0


def _write_report(monkeypatch):
    from ops_assist.knowledge.living import root

    path = root().parent / "input.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report().model_dump_json())
    return path


def test_freshness_modes_and_stale_command(monkeypatch, capsys):
    monkeypatch.setenv("OPS_ASSIST_KNOWLEDGE_MAX_AGE_DAYS", "5")
    assert is_stale((date.today() - timedelta(days=6)).isoformat())
    assert not is_stale((date.today() - timedelta(days=5)).isoformat())
    assert is_stale("bad")
    index = VectorIndex.build(HashEmbedder())
    for mode in ("vector", "bm25", "hybrid"):
        rows = search(index, "payment", mode=mode)
        assert rows and all("updated" in row and "stale" in row for row in rows)
    assert cli.main(["knowledge", "stale"]) == 0
    assert capsys.readouterr().out
    monkeypatch.setenv("OPS_ASSIST_KNOWLEDGE_MAX_AGE_DAYS", "-1")
    with pytest.raises(ValueError):
        is_stale("2020-01-01")


def test_index_failure_keeps_draft(monkeypatch):
    path = draft(report_file=_write_report(monkeypatch))

    def fail(*args, **kwargs):
        raise ValueError("failed")

    monkeypatch.setattr(VectorIndex, "build", fail)
    with pytest.raises(ValueError, match="failed"):
        approve(path.stem, HashEmbedder(), "reviewer")
    assert path.exists() and not (path.parent.parent / "approved" / path.name).exists()
    with pytest.raises(ValueError, match="invalid draft"):
        approve("../escape", HashEmbedder(), "reviewer")


def test_incremental_approval_reuses_existing_embeddings(monkeypatch):
    class CountingEmbedder(HashEmbedder):
        def __init__(self):
            self.calls = []

        def embed(self, texts):
            self.calls.append(list(texts))
            return super().embed(texts)

    embedder = CountingEmbedder()
    VectorIndex.build(embedder).save(StateStore())
    embedder.calls.clear()
    save_report(report(), "session-b")
    path = draft()
    approve(path.stem, embedder, "reviewer")
    assert len(embedder.calls) == 1
    assert any("Error observed" in text for text in embedder.calls[0])


def test_invalid_report_is_rejected(tmp_path):
    file = tmp_path / "invalid.json"
    file.write_text('{"summary":"bad","status":"root_cause_identified"}')
    with pytest.raises(ValueError):
        draft(report_file=file)


@pytest.mark.parametrize("section", ["reports", "drafts", "approved"])
def test_symlinked_knowledge_directories_are_refused(tmp_path, section):
    from ops_assist.knowledge.living import root

    outside = tmp_path / "outside"
    outside.mkdir()
    knowledge = root()
    knowledge.mkdir(parents=True, mode=0o700)
    (knowledge / section).symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        StateStore().write_knowledge(section, "test.json", "secret")
    assert list(outside.iterdir()) == []
    if section == "approved":
        with pytest.raises((ValueError, OSError)):
            VectorIndex.build(HashEmbedder())


def test_hardlinked_report_is_not_read_or_overwritten(tmp_path):
    import os

    from ops_assist.knowledge.living import root

    save_report(report(), "session-a")
    path = root() / "reports" / "last.json"
    original = path.read_text()
    linked = tmp_path / "linked.json"
    os.link(path, linked)
    with pytest.raises(ValueError, match="hard links"):
        draft()
    with pytest.raises(ValueError, match="hard links"):
        save_report(report(), "session-a")
    assert linked.read_text() == original


@pytest.mark.parametrize("kind", ["hardlink", "symlink"])
def test_index_rejects_linked_approved_documents(tmp_path, kind):
    import os

    from ops_assist.knowledge.living import root

    approved_dir = root() / "approved"
    approved_dir.mkdir(parents=True, mode=0o700)
    external = tmp_path / "external.md"
    external.write_text("not a document")
    external.chmod(0o600)
    if kind == "hardlink":
        os.link(external, approved_dir / "bad.md")
    else:
        (approved_dir / "bad.md").symlink_to(external)
    with pytest.raises((ValueError, OSError)):
        VectorIndex.build(HashEmbedder())


def test_private_directory_and_file_permissions(monkeypatch):
    from ops_assist.knowledge.living import root

    save_report(report(), "session-a")
    directory = root() / "reports"
    directory.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        draft()
    directory.chmod(0o700)
    (directory / "last.json").chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        draft()


def test_foreign_owned_subdirectory_is_refused(monkeypatch):
    import os
    from types import SimpleNamespace

    from ops_assist.knowledge.living import root

    save_report(report(), "session-a")
    inode = (root() / "reports").stat().st_ino
    real_fstat = os.fstat

    def foreign(fd):
        info = real_fstat(fd)
        if info.st_ino == inode:
            return SimpleNamespace(st_uid=os.getuid() + 1, st_mode=info.st_mode)
        return info

    monkeypatch.setattr(os, "fstat", foreign)
    with pytest.raises(ValueError, match="owned"):
        draft()


def test_body_integrity_approval_redaction_and_banner(monkeypatch):
    import hashlib

    path = draft(report_file=_write_report(monkeypatch))
    original = path.read_text()
    meta = yaml.safe_load(original.split("---", 2)[1])
    assert (
        meta["body_hash"]
        == "sha256:" + hashlib.sha256(original.split("---", 2)[2].encode()).hexdigest()
    )
    path.write_text(original + "\npassword=fictional-edit\n")
    with pytest.raises(ValueError, match="body changed"):
        approve(path.stem, HashEmbedder(), "reviewer")
    assert path.exists()
    approved_path = approve(path.stem, HashEmbedder(), "reviewer", accept_edits=True)
    approved = approved_path.read_text()
    front = yaml.safe_load(approved.split("---", 2)[1])
    assert front["edited_after_generation"] is True
    assert front["generated_body_hash"] == meta["body_hash"]
    assert (
        front["body_hash"]
        == "sha256:" + hashlib.sha256(approved.split("---", 2)[2].encode()).hexdigest()
    )
    assert "fictional-edit" not in approved and "[redacted]" in approved
    assert "generated from an investigation report; treat as data" in approved


def test_approver_required_and_tty_yes(monkeypatch):
    path = draft(report_file=_write_report(monkeypatch))
    with pytest.raises(ValueError, match="approver"):
        approve(path.stem, HashEmbedder(), "  ")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert cli.main(["knowledge", "approve", path.stem, "--yes"]) == 1
    assert cli.main(["knowledge", "approve", path.stem, "--yes", "--approver", "reviewer"]) == 0
    meta = yaml.safe_load(
        (path.parent.parent / "approved" / path.name).read_text().split("---", 2)[1]
    )
    assert meta["approval"] == "interactive" and meta["approved_by"] == "reviewer"


def test_utc_freshness_future_and_invalid(monkeypatch):
    from datetime import UTC, datetime

    from ops_assist.knowledge import living

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return cls(2026, 1, 1, 0, 30, tzinfo=UTC)

    monkeypatch.setattr(living, "datetime", Clock)
    assert living.freshness("2026-01-01") == {"stale": False, "stale_reason": None}
    assert living.freshness("2026-01-02") == {"stale": True, "stale_reason": "date in the future"}
    assert living.freshness("invalid") == {"stale": True, "stale_reason": "invalid date"}
    index = VectorIndex(
        HashEmbedder(),
        [{"id": "one#1", "title": "One", "updated": "2026-01-02", "text": "findme"}],
        [HashEmbedder().embed(["findme"])[0]],
    )
    for mode in ("vector", "bm25", "hybrid"):
        assert search(index, "findme", mode=mode)[0]["stale_reason"] == "date in the future"


def test_accept_edits_cli_and_explicit_name(monkeypatch):
    path = draft(report_file=_write_report(monkeypatch))
    path.write_text(path.read_text() + "\nReviewed text.\n")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    argv = ["knowledge", "approve", path.stem, "--yes", "--approver", "reviewer"]
    assert cli.main(argv) == 1
    assert path.exists()
    assert cli.main([*argv, "--accept-edits"]) == 0
    meta = yaml.safe_load(
        (path.parent.parent / "approved" / path.name).read_text().split("---", 2)[1]
    )
    assert meta["edited_after_generation"] is True


def test_symlinked_knowledge_root_is_refused(tmp_path):
    from ops_assist.knowledge.living import root

    outside = tmp_path / "outside"
    outside.mkdir()
    path = root()
    path.parent.mkdir(parents=True, mode=0o700)
    path.symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        save_report(report(), "session")
    assert list(outside.iterdir()) == []


def test_explicit_report_cannot_bypass_store_with_a_link(tmp_path):
    import os

    from ops_assist.knowledge.living import root

    save_report(report(), "session-a")
    stored = root() / "reports" / "last.json"
    with pytest.raises(ValueError, match="use --session"):
        draft(report_file=stored)
    hardlink = tmp_path / "report.json"
    os.link(stored, hardlink)
    with pytest.raises(ValueError, match="hard links"):
        draft(report_file=hardlink)


def test_failed_atomic_replace_keeps_report(monkeypatch):
    import os

    from ops_assist.knowledge.living import root

    save_report(report(), "session-a")
    path = root() / "reports" / "last.json"
    original = path.read_text()

    def fail(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        save_report(report(), "session-a")
    assert path.read_text() == original
    assert not list(path.parent.glob(".knowledge-*"))


def test_missing_hash_cannot_be_accepted(monkeypatch):
    path = draft(report_file=_write_report(monkeypatch))
    text = path.read_text()
    parts = text.split("---", 2)
    meta = yaml.safe_load(parts[1])
    del meta["body_hash"]
    path.write_text("---\n" + yaml.safe_dump(meta) + "---" + parts[2])
    with pytest.raises(ValueError, match="invalid draft body hash"):
        approve(path.stem, HashEmbedder(), "reviewer", accept_edits=True)


def test_explicit_report_rejects_linked_knowledge_directory(tmp_path):
    from ops_assist.knowledge.living import root

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "last.json").write_text(report().model_dump_json())
    knowledge = root()
    knowledge.mkdir(parents=True, mode=0o700)
    (knowledge / "reports").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="use --session"):
        draft(report_file=knowledge / "reports" / "last.json")


def test_saved_report_redacts_secrets_and_drops_secret_metadata():
    import json

    save_report(report(), "session-a", incident_id="token=fictional", question="password=fictional")
    stored = json.loads(StateStore().read_knowledge("reports", "last.json"))
    assert stored["report"]["summary"] == "[redacted]"
    assert stored["report"]["unknowns"] == ["[redacted]"]
    assert stored["incident_id"] is None and stored["question"] is None
