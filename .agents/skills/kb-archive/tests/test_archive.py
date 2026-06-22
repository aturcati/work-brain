import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from archive import (
    archive_path_for,
    redirect_stub,
    strip_canonical_from_index,
    apply_archive,
    ArchiveError,
    TYPE_TO_DIR,
)


def test_type_to_dir_contract():
    assert TYPE_TO_DIR["Person"] == "people"
    assert TYPE_TO_DIR["Topic"] == "topics"
    assert len(TYPE_TO_DIR) == 9


def test_archive_path_for_returns_relative_under_archive():
    p = archive_path_for("people", "alice")
    assert p == Path("wiki/archive/people/alice.md")


def test_redirect_stub_contains_archive_pointer():
    stub = redirect_stub("Person", "alice", "people", "2026-05-23")
    assert "type: Person" in stub
    assert "slug: alice" in stub
    assert "status: archived" in stub
    assert "[[wiki/archive/people/alice]]" in stub
    assert "modified: 2026-05-23" in stub


def test_redirect_stub_has_no_empty_supersedes():
    stub = redirect_stub("Person", "alice", "people", "2026-05-23")
    assert "supersedes:" not in stub
    assert "superseded_by:" in stub


def test_strip_canonical_from_index_removes_exact_match():
    text = (
        "- [[wiki/people/alice]]\n"
        "- [[wiki/people/alice-smith]]\n"
        "- [[wiki/orgs/alice]]\n"
    )
    out = strip_canonical_from_index(text, "people", "alice")
    assert "[[wiki/people/alice]]" not in out
    assert "[[wiki/people/alice-smith]]" in out  # not stripped
    assert "[[wiki/orgs/alice]]" in out  # different type


def test_strip_canonical_from_index_handles_pipe_alias():
    text = "- [[wiki/people/alice|Alice]]\n- [[wiki/people/bob]]\n"
    out = strip_canonical_from_index(text, "people", "alice")
    assert "alice|Alice" not in out
    assert "[[wiki/people/bob]]" in out


def test_apply_archive_rejects_active_status_without_force(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nstatus: active\n---\nbody"
    )
    with pytest.raises(ArchiveError):
        apply_archive(tmp_path, "Person", "alice", dry_run=True, today="2026-05-23")


def test_apply_archive_accepts_dormant_status(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nstatus: dormant\n---\nbody"
    )
    result = apply_archive(tmp_path, "Person", "alice", dry_run=True, today="2026-05-23")
    assert not result.applied
    assert result.source_path.name == "alice.md"
    assert result.dest_path.parts[-3:] == ("archive", "people", "alice.md")


def test_apply_archive_force_overrides_status_check(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nstatus: active\n---\nbody"
    )
    result = apply_archive(tmp_path, "Person", "alice", dry_run=True, force=True, today="2026-05-23")
    assert not result.applied  # dry-run
    assert result.dest_path.parts[-3:] == ("archive", "people", "alice.md")


def test_apply_archive_rejects_missing_page(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    (tmp_path / "wiki" / "people").mkdir(parents=True)
    with pytest.raises(ArchiveError):
        apply_archive(tmp_path, "Person", "ghost", dry_run=True, today="2026-05-23")


def test_apply_archive_rejects_unknown_type(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    with pytest.raises(ArchiveError):
        apply_archive(tmp_path, "Unicorn", "alice", dry_run=True, today="2026-05-23")


def test_apply_archive_rejects_existing_dest(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "archive" / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nstatus: archived\n---\nbody"
    )
    (wiki / "archive" / "people" / "alice.md").write_text("---\n---\n")
    with pytest.raises(ArchiveError):
        apply_archive(tmp_path, "Person", "alice", dry_run=True, today="2026-05-23")


def test_apply_archive_applies_and_creates_redirect(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nstatus: dormant\n---\nbody-content"
    )
    (wiki / "index.md").write_text("- [[wiki/people/alice]]\n- [[wiki/people/bob]]\n")
    (wiki / "log.md").write_text("# log\n")

    result = apply_archive(tmp_path, "Person", "alice", dry_run=False, today="2026-05-23")
    assert result.applied

    # Archived copy at destination
    archived = wiki / "archive" / "people" / "alice.md"
    assert archived.is_file()
    assert "body-content" in archived.read_text()

    # Redirect stub at original path
    stub = (wiki / "people" / "alice.md").read_text()
    assert "status: archived" in stub
    assert "[[wiki/archive/people/alice]]" in stub
    assert "body-content" not in stub  # original body moved, not duplicated

    # Index updated
    idx = (wiki / "index.md").read_text()
    assert "[[wiki/people/alice]]" not in idx
    assert "[[wiki/people/bob]]" in idx


def test_apply_archive_writes_log_entry(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nstatus: dormant\n---\n"
    )
    (wiki / "log.md").write_text("# log\n")
    apply_archive(tmp_path, "Person", "alice", dry_run=False, today="2026-05-23")
    log_text = (wiki / "log.md").read_text()
    assert "kb-archive | Person/alice archived" in log_text


def test_apply_archive_preserves_staging_on_failure(tmp_path, monkeypatch):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nstatus: dormant\n---\n"
    )
    (wiki / "log.md").write_text("# log\n")

    import archive as archive_mod
    call_count = {"n": 0}
    real_move = archive_mod.shutil.move

    def flaky_move(src, dst):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated mid-commit failure")
        return real_move(src, dst)

    monkeypatch.setattr(archive_mod.shutil, "move", flaky_move)
    with pytest.raises(OSError):
        apply_archive(tmp_path, "Person", "alice", dry_run=False, today="2026-05-23")
    staging_dirs = list((tmp_path / ".kb-staging").glob("*"))
    assert staging_dirs, "staging dir must be preserved on commit failure"


def test_apply_archive_works_without_index_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\nstatus: dormant\n---\nbody"
    )
    (wiki / "log.md").write_text("# log\n")
    # no index.md present
    result = apply_archive(tmp_path, "Person", "alice", dry_run=False, today="2026-05-23")
    assert result.applied
    assert (wiki / "archive" / "people" / "alice.md").is_file()
    assert not (wiki / "index.md").exists()
