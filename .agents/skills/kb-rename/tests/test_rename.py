import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from rename import (
    wikilink_pattern,
    rewrite_wikilinks_in_text,
    find_referring_files,
    build_renamed_frontmatter,
    TYPE_TO_DIR,
)


def test_wikilink_pattern_matches_plain():
    p = wikilink_pattern("people", "alice")
    assert p.search("see [[wiki/people/alice]]")


def test_wikilink_pattern_matches_pipe_alias():
    p = wikilink_pattern("people", "alice")
    assert p.search("[[wiki/people/alice|Alice Smith]]")


def test_wikilink_pattern_does_not_match_different_slug():
    p = wikilink_pattern("people", "alice")
    assert p.search("[[wiki/people/alice-smith]]") is None


def test_wikilink_pattern_does_not_match_different_type():
    p = wikilink_pattern("people", "alice")
    assert p.search("[[wiki/orgs/alice]]") is None


def test_wikilink_pattern_ignores_raw_paths():
    p = wikilink_pattern("meetings", "2026-05-11-foo")
    assert p.search("[[raw/meetings/2026/05/2026-05-11-foo.md]]") is None


def test_rewrite_wikilinks_replaces_all_occurrences():
    text = "body [[wiki/people/alice]] more [[wiki/people/alice|Alice]] end"
    new, n = rewrite_wikilinks_in_text(text, "people", "alice", "alice-smith")
    assert "[[wiki/people/alice-smith]]" in new
    assert "[[wiki/people/alice-smith|Alice]]" in new
    assert "alice]]" not in new.replace("alice-smith", "")
    assert n == 2


def test_rewrite_wikilinks_zero_when_no_match():
    text = "no links here"
    new, n = rewrite_wikilinks_in_text(text, "people", "alice", "alice-smith")
    assert new == text
    assert n == 0


def test_rewrite_wikilinks_preserves_other_links():
    text = "[[wiki/people/alice]] and [[wiki/orgs/acme]]"
    new, _ = rewrite_wikilinks_in_text(text, "people", "alice", "alice-smith")
    assert "[[wiki/orgs/acme]]" in new


def test_find_referring_files(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "orgs").mkdir()
    (wiki / "people" / "alice.md").write_text("---\nslug: alice\n---\nbody")
    (wiki / "orgs" / "acme.md").write_text("members: [\"[[wiki/people/alice]]\"]")
    (wiki / "people" / "bob.md").write_text("knows [[wiki/people/alice|Alice]]")
    (wiki / "people" / "carol.md").write_text("no links")

    refs = find_referring_files(wiki, "people", "alice")
    names = sorted(r.name for r in refs)
    # alice.md itself excluded
    assert "alice.md" not in names
    assert "acme.md" in names
    assert "bob.md" in names
    assert "carol.md" not in names


def test_find_referring_files_skips_tofile(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "tofile").mkdir()
    (wiki / "people" / "alice.md").write_text("---\nslug: alice\n---\n")
    (wiki / "tofile" / "stub.md").write_text("[[wiki/people/alice]]")

    refs = find_referring_files(wiki, "people", "alice")
    assert all("tofile" not in str(r) for r in refs)


def test_build_renamed_frontmatter_adds_old_slug_to_aliases():
    fm = {"type": "Person", "slug": "alice", "aliases": ["Alice Smith"]}
    out = build_renamed_frontmatter(fm, "alice-smith-acme", "alice", "Alice")
    assert out["slug"] == "alice-smith-acme"
    assert "alice" in out["aliases"]
    assert "Alice Smith" in out["aliases"]


def test_build_renamed_frontmatter_no_duplicate_alias():
    fm = {"type": "Person", "slug": "alice", "aliases": ["alice"]}
    out = build_renamed_frontmatter(fm, "alice-smith", "alice", "Alice")
    # ensure alias list is deduped
    assert out["aliases"].count("alice") == 1


def test_build_renamed_frontmatter_creates_aliases_when_missing():
    fm = {"type": "Person", "slug": "alice"}
    out = build_renamed_frontmatter(fm, "alice-smith", "alice", "Alice")
    assert "alice" in out["aliases"]


def test_type_to_dir_contract():
    assert TYPE_TO_DIR["Person"] == "people"
    assert TYPE_TO_DIR["Org"] == "orgs"
    assert TYPE_TO_DIR["Decision"] == "decisions"
    assert len(TYPE_TO_DIR) == 9


def test_end_to_end_rename_dry_run(tmp_path):
    # Build minimal vault
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "orgs").mkdir()
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\naliases:\n  - Alice Smith\n---\nbio"
    )
    (wiki / "orgs" / "acme.md").write_text(
        "---\ntype: Org\nslug: acme\n---\nMembers: [[wiki/people/alice]]"
    )
    (wiki / "log.md").write_text("# log\n")

    from rename import apply_rename
    result = apply_rename(tmp_path, "Person", "alice", "alice-smith", dry_run=True)
    assert result.referring_files
    assert any("acme.md" in str(p) for p in result.referring_files)
    # Dry-run must NOT have written:
    assert (wiki / "people" / "alice.md").exists()
    assert not (wiki / "people" / "alice-smith.md").exists()
    text = (wiki / "orgs" / "acme.md").read_text()
    assert "[[wiki/people/alice]]" in text


def test_end_to_end_rename_apply(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "orgs").mkdir()
    (wiki / "people" / "alice.md").write_text(
        "---\ntype: Person\nslug: alice\naliases: []\n---\nbio"
    )
    (wiki / "orgs" / "acme.md").write_text(
        "---\ntype: Org\nslug: acme\nmembers:\n  - \"[[wiki/people/alice]]\"\n---\n"
    )
    (wiki / "log.md").write_text("# log\n")

    from rename import apply_rename
    result = apply_rename(tmp_path, "Person", "alice", "alice-smith", dry_run=False)
    assert not (wiki / "people" / "alice.md").exists()
    assert (wiki / "people" / "alice-smith.md").exists()
    new_text = (wiki / "people" / "alice-smith.md").read_text()
    assert "slug: alice-smith" in new_text
    assert "alice" in new_text  # in aliases
    referring = (wiki / "orgs" / "acme.md").read_text()
    assert "[[wiki/people/alice-smith]]" in referring
    assert "[[wiki/people/alice]]" not in referring
    assert result.applied


def test_rename_rejects_conflicting_new_slug(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# fake")
    wiki = tmp_path / "wiki"
    (wiki / "people").mkdir(parents=True)
    (wiki / "people" / "alice.md").write_text("---\ntype: Person\nslug: alice\n---\n")
    (wiki / "people" / "bob.md").write_text("---\ntype: Person\nslug: bob\n---\n")

    from rename import apply_rename, RenameError
    with pytest.raises(RenameError):
        apply_rename(tmp_path, "Person", "alice", "bob", dry_run=True)
