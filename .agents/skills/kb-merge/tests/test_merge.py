import sys
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from merge import (
    merge_frontmatter,
    merge_body,
    redirect_stub,
    apply_merge,
    count_dropped_sections,
    MergeError,
)


def test_merge_frontmatter_unions_aliases():
    p = {"type": "Person", "slug": "alice-smith", "aliases": ["Alice"]}
    s = {"type": "Person", "slug": "alice", "aliases": ["Al"]}
    out = merge_frontmatter(p, s, "alice-smith", "alice", "2026-05-23")
    assert "Alice" in out["aliases"]
    assert "Al" in out["aliases"]
    assert "alice" in out["aliases"]


def test_merge_frontmatter_keeps_primary_slug():
    p = {"type": "Person", "slug": "alice-smith"}
    s = {"type": "Person", "slug": "alice"}
    out = merge_frontmatter(p, s, "alice-smith", "alice", "2026-05-23")
    assert out["slug"] == "alice-smith"


def test_merge_frontmatter_unions_edge_lists_dedup():
    p = {"type": "Person", "slug": "a", "works_at": ["[[wiki/orgs/acme]]"]}
    s = {"type": "Person", "slug": "b", "works_at": ["[[wiki/orgs/acme]]", "[[wiki/orgs/openai]]"]}
    out = merge_frontmatter(p, s, "a", "b", "2026-05-23")
    assert sorted(out["works_at"]) == sorted(["[[wiki/orgs/acme]]", "[[wiki/orgs/openai]]"])


def test_merge_frontmatter_drops_self_reference_to_secondary():
    p = {"type": "Person", "slug": "alice-smith"}
    s = {"type": "Person", "slug": "alice", "related": ["[[wiki/people/alice-smith]]"]}
    out = merge_frontmatter(p, s, "alice-smith", "alice", "2026-05-23")
    assert "[[wiki/people/alice-smith]]" not in (out.get("related") or [])


def test_merge_frontmatter_updates_modified():
    p = {"type": "Person", "slug": "a", "modified": "2025-01-01"}
    s = {"type": "Person", "slug": "b"}
    out = merge_frontmatter(p, s, "a", "b", "2026-05-23")
    assert out["modified"] == "2026-05-23"


def test_merge_body_appends_unique_sections():
    primary = "Bio.\n\n## Background\nA.\n"
    secondary = "Bio.\n\n## Background\nB.\n\n## Education\nC.\n"
    out = merge_body(primary, secondary, "alice")
    assert "## Background" in out
    assert "## Education" in out
    assert "From merged page" in out


def test_merge_body_no_duplicate_when_secondary_empty():
    out = merge_body("primary body\n", "", "alice")
    assert "primary body" in out
    assert "From merged page" not in out


def test_redirect_stub_contains_pointer():
    stub = redirect_stub("Person", "alice", "alice-smith", "people", "2026-05-23")
    assert "[[wiki/people/alice-smith]]" in stub
    assert "slug: alice" in stub
    assert "status: merged" in stub
    assert "superseded_by" in stub


def test_apply_merge_dry_run_does_not_write(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\naliases: []\n---\nbio-a"
    )
    (wiki / "people" / "alice-smith.md").write_text(
        "---\ntype: Person\nslug: alice-smith\naliases: []\n---\nbio-as"
    )
    (wiki / "log.md").write_text("# log\n")

    result = apply_merge(tmp_path, "Person", "alice-smith", "alice", dry_run=True, today="2026-05-23")
    text_alice = (wiki / "people" / "alice.md").read_text()
    assert "bio-a" in text_alice  # untouched
    assert not result.applied


def test_apply_merge_applies_and_redirects(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "orgs").mkdir()
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\naliases: [Al]\nworks_at:\n  - \"[[wiki/orgs/acme]]\"\n---\n## Notes\nA\n"
    )
    (wiki / "people" / "alice-smith.md").write_text(
        "---\ntype: Person\nslug: alice-smith\naliases: []\n---\nprimary body\n"
    )
    (wiki / "orgs" / "acme.md").write_text(
        "---\ntype: Org\nslug: acme\nmembers:\n  - \"[[wiki/people/alice]]\"\n---\n"
    )
    (wiki / "log.md").write_text("# log\n")

    result = apply_merge(tmp_path, "Person", "alice-smith", "alice", dry_run=False, today="2026-05-23")
    assert result.applied
    # Primary updated
    primary_text = (wiki / "people" / "alice-smith.md").read_text()
    assert "primary body" in primary_text
    assert "[[wiki/orgs/acme]]" in primary_text  # works_at unioned
    assert "alice" in primary_text  # secondary slug in aliases
    assert "## Notes" in primary_text  # body section appended
    # Secondary became redirect stub
    sec_text = (wiki / "people" / "alice.md").read_text()
    assert "merged" in sec_text
    assert "[[wiki/people/alice-smith]]" in sec_text
    # External references rewritten
    org_text = (wiki / "orgs" / "acme.md").read_text()
    assert "[[wiki/people/alice-smith]]" in org_text
    assert "[[wiki/people/alice]]" not in org_text


def test_apply_merge_rejects_different_types(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "orgs").mkdir()
    (wiki / "people" / "x.md").write_text("---\ntype: Person\nslug: x\n---\n")
    (wiki / "orgs" / "y.md").write_text("---\ntype: Org\nslug: y\n---\n")

    with pytest.raises(MergeError):
        apply_merge(tmp_path, "Person", "x", "y", dry_run=True, today="2026-05-23")


def test_apply_merge_rejects_same_slug(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "a.md").write_text("---\ntype: Person\nslug: a\n---\n")

    with pytest.raises(MergeError):
        apply_merge(tmp_path, "Person", "a", "a", dry_run=True, today="2026-05-23")


def test_count_dropped_sections_detects_collisions():
    primary = "## Notes\nP-notes\n\n## Other\nP-other\n"
    secondary = "## Notes\nS-notes\n\n## Unique\nS-unique\n"
    assert count_dropped_sections(primary, secondary) == 1


def test_count_dropped_sections_empty_secondary():
    assert count_dropped_sections("## A\n", "") == 0


def test_redirect_stub_no_empty_supersedes():
    stub = redirect_stub("Person", "alice", "alice-smith", "people", "2026-05-23")
    assert "supersedes:" not in stub
    assert "superseded_by:" in stub


def test_apply_merge_writes_log_entry(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "p.md").write_text("---\ntype: Person\nslug: p\n---\n")
    (wiki / "people" / "s.md").write_text("---\ntype: Person\nslug: s\n---\n")
    (wiki / "log.md").write_text("# log\n")
    apply_merge(tmp_path, "Person", "p", "s", dry_run=False, today="2026-05-23")
    log_text = (wiki / "log.md").read_text()
    assert "kb-merge | s → p" in log_text


def test_apply_merge_preserves_staging_on_failure(tmp_path, monkeypatch):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "p.md").write_text("---\ntype: Person\nslug: p\n---\n")
    (wiki / "people" / "s.md").write_text("---\ntype: Person\nslug: s\n---\n")
    (wiki / "log.md").write_text("# log\n")

    import merge as merge_mod
    call_count = {"n": 0}
    real_move = merge_mod.shutil.move

    def flaky_move(src, dst):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated mid-commit failure")
        return real_move(src, dst)

    monkeypatch.setattr(merge_mod.shutil, "move", flaky_move)
    with pytest.raises(OSError):
        apply_merge(tmp_path, "Person", "p", "s", dry_run=False, today="2026-05-23")
    staging_dirs = list((tmp_path / ".kb-staging").glob("*"))
    assert staging_dirs, "staging dir must be preserved on commit failure"
