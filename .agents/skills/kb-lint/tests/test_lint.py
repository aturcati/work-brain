import sys
import datetime
import json
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lint import (
    parse_wikilinks,
    build_link_graph,
    collect_pages,
    check_orphans,
    check_broken_links,
    check_schema_violations,
    check_stale_last_verified,
    check_contradictions,
    check_bloated_pages,
    check_log_rotation,
    check_edges_rotation,
    check_raw_drift,
    check_decision_sources,
    check_person_works_at,
    check_stale_action_items,
    check_unprocessed_journal,
    write_lint_report,
    write_overview,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_page(slug, node_type, fm_extra=None, body=""):
    fm = {"type": node_type, "slug": slug}
    if fm_extra:
        fm.update(fm_extra)
    return {"path": Path(f"wiki/{node_type.lower()}s/{slug}.md"),
            "type": node_type, "slug": slug, "fm": fm, "body": body}


# ── parse_wikilinks ────────────────────────────────────────────────────────

def test_parse_wikilinks_extracts_links():
    text = '["[[wiki/people/foo]]", "[[wiki/orgs/bar]]"]'
    result = parse_wikilinks(text)
    assert "wiki/people/foo" in result
    assert "wiki/orgs/bar" in result


def test_parse_wikilinks_strips_md_extension():
    text = "[[wiki/people/foo.md]]"
    result = parse_wikilinks(text)
    assert result == ["wiki/people/foo"]


def test_parse_wikilinks_body_link():
    text = "See [[wiki/meetings/2026-05-11-status-review]] for details."
    result = parse_wikilinks(text)
    assert result == ["wiki/meetings/2026-05-11-status-review"]


def test_parse_wikilinks_empty():
    assert parse_wikilinks("no links here") == []


# ── build_link_graph ──────────────────────────────────────────────────────

def test_build_link_graph_inbound():
    pages = [
        _make_page("foo", "Person"),
        _make_page("bar", "Person",
                   fm_extra={"sources": ["[[wiki/people/foo]]"]}),
    ]
    graph = build_link_graph(pages)
    assert "bar" in graph["foo"]   # bar links to foo
    assert len(graph["bar"]) == 0  # nothing links to bar


def test_build_link_graph_body_link():
    pages = [
        _make_page("target", "Topic"),
        _make_page("src", "Topic", body="See [[wiki/topics/target]]."),
    ]
    graph = build_link_graph(pages)
    assert "src" in graph["target"]


# ── check_orphans ─────────────────────────────────────────────────────────

def test_check_orphans_detects_isolated_page():
    pages = [
        _make_page("foo", "Person"),
        _make_page("bar", "Person",
                   fm_extra={"sources": ["[[wiki/people/foo]]"]}),
    ]
    graph = build_link_graph(pages)
    findings = check_orphans(pages, graph)
    # bar has no inbound links → orphan
    assert any("bar" in f["path"] for f in findings)
    # foo is cited by bar → not orphan
    assert not any("foo" in f["path"] for f in findings)


def test_check_orphans_skips_source_type():
    pages = [_make_page("some-source", "Source")]
    graph = build_link_graph(pages)
    findings = check_orphans(pages, graph)
    assert len(findings) == 0


# ── check_broken_links ────────────────────────────────────────────────────

def test_check_broken_links_detects_missing_target(tmp_path):
    wiki = tmp_path / "wiki" / "people"
    wiki.mkdir(parents=True)
    page = {
        "path": wiki / "foo.md",
        "type": "Person", "slug": "foo",
        "fm": {"sources": ["[[wiki/people/nonexistent]]"]},
        "body": "",
    }
    findings = check_broken_links([page], tmp_path)
    assert len(findings) == 1
    assert "nonexistent" in findings[0]["message"]


def test_check_broken_links_ok_when_target_exists(tmp_path):
    wiki = tmp_path / "wiki" / "people"
    wiki.mkdir(parents=True)
    target = wiki / "bar.md"
    target.write_text("---\ntype: Person\nslug: bar\n---\n")
    page = {
        "path": wiki / "foo.md",
        "type": "Person", "slug": "foo",
        "fm": {"sources": ["[[wiki/people/bar]]"]},
        "body": "",
    }
    findings = check_broken_links([page], tmp_path)
    assert len(findings) == 0


# ── check_schema_violations ───────────────────────────────────────────────

def test_check_schema_violations_unknown_key():
    pages = [_make_page("foo", "Person", fm_extra={"unknown_key": "value"})]
    findings = check_schema_violations(pages)
    assert len(findings) == 1
    assert "unknown_key" in findings[0]["message"]


def test_check_schema_violations_unknown_type():
    pages = [{"path": Path("wiki/widgets/foo.md"), "type": "Widget", "slug": "foo",
              "fm": {"type": "Widget", "slug": "foo"}, "body": ""}]
    findings = check_schema_violations(pages)
    assert len(findings) == 1
    assert "Widget" in findings[0]["message"]


def test_check_schema_violations_parse_error():
    pages = [{"path": Path("wiki/people/foo.md"), "type": "", "slug": "",
              "fm": None, "body": ""}]
    findings = check_schema_violations(pages)
    assert len(findings) == 1
    assert "parse error" in findings[0]["message"].lower()


def test_check_schema_violations_clean_page():
    pages = [_make_page("foo", "Person",
                        fm_extra={"aliases": ["Foo Bar"], "status": "active"})]
    findings = check_schema_violations(pages)
    assert len(findings) == 0


# ── check_stale_last_verified ─────────────────────────────────────────────

def test_check_stale_last_verified_flags_old_page():
    today = datetime.date(2026, 5, 13)
    pages = [_make_page("foo", "Person", fm_extra={"last_verified": "2026-01-01"})]
    # 132 days ago > 90 → stale
    findings = check_stale_last_verified(pages, today)
    assert len(findings) == 1


def test_check_stale_last_verified_recent_ok():
    today = datetime.date(2026, 5, 13)
    pages = [_make_page("foo", "Person", fm_extra={"last_verified": "2026-04-01"})]
    # 42 days ago < 90 → ok
    findings = check_stale_last_verified(pages, today)
    assert len(findings) == 0


def test_check_stale_last_verified_missing_field_ok():
    today = datetime.date(2026, 5, 13)
    pages = [_make_page("foo", "Meeting")]  # Meeting has no last_verified
    findings = check_stale_last_verified(pages, today)
    assert len(findings) == 0


# ── check_contradictions ──────────────────────────────────────────────────

def test_check_contradictions_one_sided():
    pages = [
        _make_page("foo", "Topic",
                   fm_extra={"contradicts": ["[[wiki/topics/bar]]"]}),
        _make_page("bar", "Topic"),  # no reverse contradicts
    ]
    findings = check_contradictions(pages)
    assert len(findings) == 1
    assert "bar" in findings[0]["message"]


def test_check_contradictions_symmetric_ok():
    pages = [
        _make_page("foo", "Topic",
                   fm_extra={"contradicts": ["[[wiki/topics/bar]]"]}),
        _make_page("bar", "Topic",
                   fm_extra={"contradicts": ["[[wiki/topics/foo]]"]}),
    ]
    findings = check_contradictions(pages)
    assert len(findings) == 0


def test_check_contradictions_no_contradicts_ok():
    pages = [_make_page("foo", "Topic"), _make_page("bar", "Topic")]
    findings = check_contradictions(pages)
    assert len(findings) == 0


# ── check_bloated_pages ───────────────────────────────────────────────────

def test_check_bloated_pages_flags_large():
    # 1601 words × 5 chars = 8005 chars / 4 = ~2001 tokens > 2000
    large_body = "word " * 1601
    pages = [_make_page("big", "Topic", body=large_body)]
    findings = check_bloated_pages(pages)
    assert len(findings) == 1


def test_check_bloated_pages_ok():
    pages = [_make_page("small", "Topic", body="word " * 100)]
    findings = check_bloated_pages(pages)
    assert len(findings) == 0


def test_check_bloated_pages_skips_artifact():
    large_body = "word " * 1601
    pages = [_make_page("transcript", "Artifact", body=large_body)]
    findings = check_bloated_pages(pages)
    assert len(findings) == 0


# ── check_log_rotation ────────────────────────────────────────────────────

def test_check_log_rotation_triggers_on_line_count(tmp_path):
    log = tmp_path / "wiki" / "log.md"
    log.parent.mkdir(parents=True)
    log.write_text("\n".join(f"## line {i}" for i in range(1001)) + "\n")
    findings = check_log_rotation(log)
    assert len(findings) == 1
    assert "1001" in findings[0]["message"]


def test_check_log_rotation_triggers_on_size(tmp_path):
    log = tmp_path / "log.md"
    # Write ≤1000 lines but >1MB — 10 lines of 120KB each
    line = "x" * 120_000 + "\n"  # ~120KB per line
    log.write_text(line * 10, encoding="utf-8")
    findings = check_log_rotation(log)
    assert len(findings) == 1
    assert "KB" in findings[0]["message"]
    assert "1MB" in findings[0]["message"]


def test_check_log_rotation_ok(tmp_path):
    log = tmp_path / "wiki" / "log.md"
    log.parent.mkdir(parents=True)
    log.write_text("## entry 1\n## entry 2\n")
    findings = check_log_rotation(log)
    assert len(findings) == 0


def test_check_log_rotation_missing_file(tmp_path):
    log = tmp_path / "wiki" / "log.md"
    findings = check_log_rotation(log)
    assert len(findings) == 0


# ── check_edges_rotation ──────────────────────────────────────────────────

def test_check_edges_rotation_triggers_on_entries(tmp_path):
    edges = tmp_path / "wiki" / "_inbox" / "edges.md"
    edges.parent.mkdir(parents=True)
    lines = "\n".join(f"- (foo, related, bar{i}, 0.9, 'e')" for i in range(501))
    edges.write_text(lines + "\n")
    findings = check_edges_rotation(edges)
    assert len(findings) == 1
    assert "501" in findings[0]["message"]


def test_check_edges_rotation_missing_file(tmp_path):
    findings = check_edges_rotation(tmp_path / "edges.md")
    assert findings == []


def test_check_edges_rotation_triggers_on_size(tmp_path):
    edges = tmp_path / "edges.md"
    # ≤500 entry lines but >500KB — pad lines with long content
    lines = [f"- (a, b, c)  {'x' * 6000}\n" for _ in range(100)]  # 100 entries, ~600KB total
    edges.write_text("".join(lines), encoding="utf-8")
    findings = check_edges_rotation(edges)
    assert len(findings) == 1
    assert "KB" in findings[0]["message"]


def test_check_edges_rotation_ok(tmp_path):
    edges = tmp_path / "wiki" / "_inbox" / "edges.md"
    edges.parent.mkdir(parents=True)
    edges.write_text("- (foo, related, bar, 0.9, 'e')\n")
    findings = check_edges_rotation(edges)
    assert len(findings) == 0


# ── check_raw_drift ───────────────────────────────────────────────────────

def test_check_raw_drift_flags_modified_file(tmp_path):
    raw = tmp_path / "raw" / "journal" / "2026" / "04" / "note.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("content")
    # State says ingested far in the past; file mtime is now (recent)
    state = {
        "raw/journal/2026/04/note.md": {
            "sha256": "abc", "status": "done",
            "ts": "2026-01-01T00:00:00+00:00",
        }
    }
    state_path = tmp_path / "raw" / ".ingest-state.json"
    state_path.write_text(json.dumps(state))
    findings = check_raw_drift(tmp_path, state_path)
    assert len(findings) == 1
    assert "note.md" in findings[0]["path"]


def test_check_raw_drift_missing_state(tmp_path):
    findings = check_raw_drift(tmp_path / "vault", tmp_path / "state.json")
    assert findings == []


def test_check_raw_drift_ok_when_file_unchanged(tmp_path):
    raw = tmp_path / "raw" / "journal" / "2026" / "04" / "note.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("content")
    mtime = os.path.getmtime(raw)
    # State timestamp is AFTER the file's mtime → no drift
    future_ts = datetime.datetime.fromtimestamp(
        mtime + 10, tz=datetime.timezone.utc
    ).isoformat()
    state = {
        "raw/journal/2026/04/note.md": {
            "sha256": "abc", "status": "done", "ts": future_ts,
        }
    }
    state_path = tmp_path / "raw" / ".ingest-state.json"
    state_path.write_text(json.dumps(state))
    findings = check_raw_drift(tmp_path, state_path)
    assert len(findings) == 0


# ── check_decision_sources ────────────────────────────────────────────────

def test_check_decision_sources_flags_empty():
    pages = [_make_page("2026-01-foo", "Decision", fm_extra={"sources": []})]
    findings = check_decision_sources(pages)
    assert len(findings) == 1


def test_check_decision_sources_ok():
    pages = [_make_page("2026-01-foo", "Decision",
                        fm_extra={"sources": ["[[wiki/sources/bar]]"]})]
    findings = check_decision_sources(pages)
    assert len(findings) == 0


def test_check_decision_sources_missing_key():
    pages = [_make_page("2026-01-foo", "Decision")]  # no sources key
    findings = check_decision_sources(pages)
    assert len(findings) == 1


# ── check_person_works_at ─────────────────────────────────────────────────

def test_check_person_works_at_flags_empty():
    pages = [_make_page("alice", "Person", fm_extra={"works_at": []})]
    findings = check_person_works_at(pages)
    assert len(findings) == 1


def test_check_person_works_at_ok():
    pages = [_make_page("alice", "Person",
                        fm_extra={"works_at": ["[[wiki/orgs/acme]]"]})]
    findings = check_person_works_at(pages)
    assert len(findings) == 0


def test_check_person_works_at_missing_key():
    pages = [_make_page("alice", "Person")]  # no works_at key
    findings = check_person_works_at(pages)
    assert len(findings) == 1


def test_check_person_works_at_allows_external_person_without_works_at():
    pages = [
        _make_page(
            "erin-lee98",
            "Person",
            fm_extra={"tags": ["external"], "sources": ["[[raw/meetings/example]]"]},
        )
    ]
    findings = check_person_works_at(pages)
    assert findings == []


def test_check_person_works_at_still_flags_internal_person_without_works_at():
    pages = [_make_page("alice-smith", "Person", fm_extra={"tags": []})]
    findings = check_person_works_at(pages)
    assert len(findings) == 1
    assert "no works_at" in findings[0]["message"]


def test_check_person_works_at_flags_mapping_tags_even_if_external_key():
    pages = [_make_page("alice-smith", "Person", fm_extra={"tags": {"external": True}})]
    findings = check_person_works_at(pages)
    assert len(findings) == 1
    assert "no works_at" in findings[0]["message"]


def test_check_person_works_at_flags_non_string_external_tag():
    pages = [_make_page("alice-smith", "Person", fm_extra={"tags": [123]})]
    findings = check_person_works_at(pages)
    assert len(findings) == 1
    assert "no works_at" in findings[0]["message"]


# ── check_stale_action_items ──────────────────────────────────────────────

def test_check_stale_action_items_flags_old_checkbox():
    today = datetime.date(2026, 5, 13)
    pages = [_make_page("proj", "Project",
                        fm_extra={"modified": "2026-01-01"},
                        body="## Tasks\n- [ ] Do something\n")]
    findings = check_stale_action_items(pages, today)
    assert len(findings) == 1


def test_check_stale_action_items_recent_ok():
    today = datetime.date(2026, 5, 13)
    pages = [_make_page("proj", "Project",
                        fm_extra={"modified": "2026-05-01"},
                        body="## Tasks\n- [ ] Do something\n")]
    findings = check_stale_action_items(pages, today)
    assert len(findings) == 0


def test_check_stale_action_items_no_checkboxes_ok():
    today = datetime.date(2026, 5, 13)
    pages = [_make_page("proj", "Project",
                        fm_extra={"modified": "2026-01-01"},
                        body="## Tasks\n- [x] Done\n")]
    findings = check_stale_action_items(pages, today)
    assert len(findings) == 0


# ── check_unprocessed_journal ─────────────────────────────────────────────

def test_check_unprocessed_journal_flags_inbox_backlog(tmp_path):
    inbox = tmp_path / "raw" / "inbox" / "journal"
    inbox.mkdir(parents=True)
    f = inbox / "old-note.md"
    f.write_text("---\ncaptured_at: 2026-01-01\n---\ncontent")
    state_path = tmp_path / "raw" / ".ingest-state.json"
    state_path.write_text("{}")
    today = datetime.date(2026, 5, 13)  # 132 days after 2026-01-01
    findings = check_unprocessed_journal(tmp_path, state_path, today)
    assert len(findings) == 1
    assert "old-note" in findings[0]["path"]


def test_check_unprocessed_journal_recent_inbox_ok(tmp_path):
    inbox = tmp_path / "raw" / "inbox" / "journal"
    inbox.mkdir(parents=True)
    f = inbox / "new-note.md"
    f.write_text("---\ncaptured_at: 2026-05-10\n---\ncontent")
    state_path = tmp_path / "raw" / ".ingest-state.json"
    state_path.write_text("{}")
    today = datetime.date(2026, 5, 13)  # 3 days ago < 30 → ok
    findings = check_unprocessed_journal(tmp_path, state_path, today)
    assert len(findings) == 0


# ── write_lint_report ─────────────────────────────────────────────────────

def test_write_lint_report_creates_file(tmp_path):
    findings = [
        {"check": "orphans", "path": "wiki/people/foo.md", "message": "orphan"},
        {"check": "broken_links", "path": "wiki/people/bar.md", "message": "broken [[x]]"},
    ]
    write_lint_report(findings, tmp_path)
    report = (tmp_path / "views" / "lint-report.md").read_text()
    assert "## Orphans" in report
    assert "orphan" in report
    assert "## Broken links" in report
    assert "_No issues._" in report  # section with no findings


def test_write_lint_report_empty_shows_no_issues(tmp_path):
    (tmp_path / "views").mkdir()
    write_lint_report([], tmp_path)
    report = (tmp_path / "views" / "lint-report.md").read_text()
    assert report.count("_No issues._") == 14  # all 14 sections empty


def test_write_overview_creates_file(tmp_path):
    (tmp_path / "wiki").mkdir()
    state_path = tmp_path / "raw" / ".ingest-state.json"
    state_path.parent.mkdir(parents=True)
    state = {
        "raw/meetings/2026/05/foo.md": {
            "sha256": "abc", "status": "done",
            "ts": "2026-05-13T10:00:00+00:00",
        }
    }
    state_path.write_text(json.dumps(state))
    pages = [_make_page("foo", "Person"), _make_page("bar", "Meeting")]
    today = datetime.date(2026, 5, 13)
    write_overview(pages, tmp_path, state_path, today)
    overview = (tmp_path / "wiki" / "overview.md").read_text()
    assert "| Person | 1 |" in overview
    assert "| Meeting | 1 |" in overview
    assert "meetings" in overview


# --- duplicate stubs (tofile slug already canonical) ---

def test_duplicate_stub_flagged(tmp_path):
    from lint import check_duplicate_stubs
    wiki = tmp_path / "wiki"
    (wiki / "tofile").mkdir(parents=True)
    (wiki / "people").mkdir()
    (wiki / "tofile" / "jane-doe.md").write_text("---\ntype: Person\nslug: jane-doe\n---\nstub\n")
    (wiki / "people" / "jane-doe.md").write_text("---\ntype: Person\nslug: jane-doe\n---\ncanonical\n")
    findings = check_duplicate_stubs(wiki)
    assert len(findings) == 1
    assert findings[0]["check"] == "duplicate_stubs"
    assert "jane-doe" in findings[0]["path"]


def test_non_duplicate_stub_not_flagged(tmp_path):
    from lint import check_duplicate_stubs
    wiki = tmp_path / "wiki"
    (wiki / "tofile").mkdir(parents=True)
    (wiki / "people").mkdir()
    (wiki / "tofile" / "new-entity.md").write_text("---\ntype: Person\nslug: new-entity\n---\nstub\n")
    findings = check_duplicate_stubs(wiki)
    assert findings == []


# --- decision date field ---

def test_decision_without_date_flagged():
    from lint import check_decision_date
    pages = [{"path": "wiki/decisions/x.md", "type": "Decision", "slug": "x",
              "fm": {"type": "Decision", "slug": "x"}, "body": ""}]
    findings = check_decision_date(pages)
    assert len(findings) == 1 and findings[0]["check"] == "decision_date"


def test_decision_with_date_ok():
    from lint import check_decision_date
    pages = [{"path": "wiki/decisions/x.md", "type": "Decision", "slug": "x",
              "fm": {"type": "Decision", "slug": "x", "date": "2026-06-08"}, "body": ""}]
    assert check_decision_date(pages) == []


def test_non_decision_without_date_ok():
    from lint import check_decision_date
    pages = [{"path": "wiki/topics/y.md", "type": "Topic", "slug": "y",
              "fm": {"type": "Topic", "slug": "y"}, "body": ""}]
    assert check_decision_date(pages) == []
