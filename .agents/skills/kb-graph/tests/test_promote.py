import textwrap
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from promote import Edge, parse_edges_md


def make_edges_md(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "edges.md"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_parse_edges_md_basic(tmp_path):
    p = make_edges_md(tmp_path, """
        ## 2026-05-11 13:40 · raw/inbox/journal/foo.md
        - (source-a, cites, org-b, 0.95, "org-b mentioned in source-a")
        - (source-a, related, topic-c, 0.70, "topic-c referenced")
    """)
    edges = parse_edges_md(p)
    assert len(edges) == 2
    e = edges[0]
    assert e.subject == "source-a"
    assert e.predicate == "cites"
    assert e.object_ == "org-b"
    assert e.confidence == 0.95
    assert e.evidence == "org-b mentioned in source-a"
    assert e.timestamp == "2026-05-11 13:40"
    assert e.source_path == "raw/inbox/journal/foo.md"


def test_parse_edges_md_multiple_sections(tmp_path):
    p = make_edges_md(tmp_path, """
        ## 2026-05-10 09:00 · raw/meetings/foo.md
        - (person-a, attended, meeting-x, 0.99, "present at meeting")

        ## 2026-05-11 13:40 · raw/inbox/journal/bar.md
        - (org-b, related, topic-c, 0.80, "org-b works on topic-c")
    """)
    edges = parse_edges_md(p)
    assert len(edges) == 2
    assert edges[0].timestamp == "2026-05-10 09:00"
    assert edges[1].timestamp == "2026-05-11 13:40"


def test_parse_edges_md_ignores_non_edge_lines(tmp_path):
    p = make_edges_md(tmp_path, """
        # header comment
        Some prose line.
        ## 2026-05-11 13:40 · raw/foo.md
        - (a, cites, b, 0.9, "evidence")
        <!-- rotation comment -->
    """)
    edges = parse_edges_md(p)
    assert len(edges) == 1


from promote import build_canonical_map


def make_wiki_page(wiki_dir: Path, subdir: str, slug: str, ntype: str) -> Path:
    d = wiki_dir / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{slug}.md"
    p.write_text(
        f"---\ntype: {ntype}\nslug: {slug}\nstatus: active\n---\nBody.\n",
        encoding="utf-8",
    )
    return p


def test_build_canonical_map_finds_canonical_pages(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "orgs", "openai", "Org")
    make_wiki_page(wiki, "sources", "my-source", "Source")
    result = build_canonical_map(wiki)
    assert "openai" in result
    assert result["openai"][0] == "Org"
    assert "my-source" in result


def test_build_canonical_map_excludes_tofile(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "tofile", "stub-slug", "Org")
    result = build_canonical_map(wiki)
    assert "stub-slug" not in result


def test_build_canonical_map_excludes_inbox(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "_inbox", "inbox-slug", "Topic")
    result = build_canonical_map(wiki)
    assert "inbox-slug" not in result


from promote import filter_promotable, format_dry_run_report


def _edge(subject, predicate, object_, confidence=0.90):
    return Edge(
        subject=subject, predicate=predicate, object_=object_,
        confidence=confidence, evidence="test evidence",
        timestamp="2026-05-13 10:00", source_path="raw/foo.md",
        raw_line=f"- ({subject}, {predicate}, {object_}, {confidence}, \"test evidence\")",
    )


def test_filter_promotable_passes_high_confidence(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "sources", "src-a", "Source")
    make_wiki_page(wiki, "orgs", "org-b", "Org")
    cmap = build_canonical_map(wiki)
    edges = [_edge("src-a", "cites", "org-b", 0.95)]
    result = filter_promotable(edges, cmap, threshold=0.7)
    assert len(result) == 1


def test_filter_promotable_rejects_below_threshold(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "sources", "src-a", "Source")
    make_wiki_page(wiki, "orgs", "org-b", "Org")
    cmap = build_canonical_map(wiki)
    edges = [_edge("src-a", "cites", "org-b", 0.60)]
    result = filter_promotable(edges, cmap, threshold=0.7)
    assert result == []


def test_filter_promotable_rejects_unresolved_subject(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "orgs", "org-b", "Org")
    cmap = build_canonical_map(wiki)
    edges = [_edge("missing-subject", "cites", "org-b", 0.95)]
    result = filter_promotable(edges, cmap, threshold=0.7)
    assert result == []


def test_filter_promotable_rejects_unresolved_object(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "sources", "src-a", "Source")
    cmap = build_canonical_map(wiki)
    edges = [_edge("src-a", "cites", "missing-object", 0.95)]
    result = filter_promotable(edges, cmap, threshold=0.7)
    assert result == []


def test_format_dry_run_report_contains_key_info(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "sources", "src-a", "Source")
    make_wiki_page(wiki, "orgs", "org-b", "Org")
    cmap = build_canonical_map(wiki)
    edges = [_edge("src-a", "cites", "org-b", 0.95)]
    promotable = filter_promotable(edges, cmap, threshold=0.7)
    report = format_dry_run_report(promotable, cmap)
    assert "src-a" in report
    assert "cites" in report
    assert "org-b" in report
    assert "[[wiki/orgs/org-b]]" in report


from promote import apply_promotions


def test_apply_adds_wikilink_to_frontmatter(tmp_path):
    wiki = tmp_path / "wiki"
    src_page = make_wiki_page(wiki, "sources", "src-a", "Source")
    make_wiki_page(wiki, "orgs", "org-b", "Org")
    cmap = build_canonical_map(wiki)
    edges_md = make_edges_md(tmp_path, """
        ## 2026-05-13 10:00 · raw/foo.md
        - (src-a, cites, org-b, 0.95, "test evidence")
    """)
    log = tmp_path / "log.md"
    log.write_text("", encoding="utf-8")

    all_edges = parse_edges_md(edges_md)
    promotable = filter_promotable(all_edges, cmap, threshold=0.7)
    apply_promotions(promotable, cmap, edges_md, log)

    updated = src_page.read_text(encoding="utf-8")
    assert "[[wiki/orgs/org-b]]" in updated


def test_apply_removes_promoted_lines_from_edges_md(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "sources", "src-a", "Source")
    make_wiki_page(wiki, "orgs", "org-b", "Org")
    cmap = build_canonical_map(wiki)
    edges_md = make_edges_md(tmp_path, """
        ## 2026-05-13 10:00 · raw/foo.md
        - (src-a, cites, org-b, 0.95, "test evidence")
        - (src-a, cites, missing-org, 0.95, "unresolvable")
    """)
    log = tmp_path / "log.md"
    log.write_text("", encoding="utf-8")

    all_edges = parse_edges_md(edges_md)
    promotable = filter_promotable(all_edges, cmap, threshold=0.7)
    apply_promotions(promotable, cmap, edges_md, log)

    remaining = edges_md.read_text()
    assert "org-b" not in remaining       # promoted → removed
    assert "missing-org" in remaining     # unresolvable → kept


def test_apply_is_idempotent(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "sources", "src-a", "Source")
    make_wiki_page(wiki, "orgs", "org-b", "Org")
    cmap = build_canonical_map(wiki)
    edges_md = make_edges_md(tmp_path, """
        ## 2026-05-13 10:00 · raw/foo.md
        - (src-a, cites, org-b, 0.95, "test evidence")
    """)
    log = tmp_path / "log.md"
    log.write_text("", encoding="utf-8")

    all_edges = parse_edges_md(edges_md)
    promotable = filter_promotable(all_edges, cmap, threshold=0.7)
    apply_promotions(promotable, cmap, edges_md, log)
    # run again on now-empty edges_md
    all_edges2 = parse_edges_md(edges_md)
    promotable2 = filter_promotable(all_edges2, cmap, threshold=0.7)
    apply_promotions(promotable2, cmap, edges_md, log)

    src_page = wiki / "sources" / "src-a.md"
    updated = src_page.read_text()
    assert updated.count("[[wiki/orgs/org-b]]") == 1


def test_apply_appends_to_log(tmp_path):
    wiki = tmp_path / "wiki"
    make_wiki_page(wiki, "sources", "src-a", "Source")
    make_wiki_page(wiki, "orgs", "org-b", "Org")
    cmap = build_canonical_map(wiki)
    edges_md = make_edges_md(tmp_path, """
        ## 2026-05-13 10:00 · raw/foo.md
        - (src-a, cites, org-b, 0.95, "test evidence")
    """)
    log = tmp_path / "log.md"
    log.write_text("", encoding="utf-8")

    all_edges = parse_edges_md(edges_md)
    promotable = filter_promotable(all_edges, cmap, threshold=0.7)
    apply_promotions(promotable, cmap, edges_md, log)

    log_text = log.read_text()
    assert "kb-graph promote" in log_text
    assert "1 edge" in log_text


def test_apply_preserves_flow_style_frontmatter(tmp_path):
    """ruamel.yaml must not reflow existing flow-style YAML lists on write."""
    wiki = tmp_path / "wiki"
    (wiki / "sources").mkdir(parents=True)
    src_page = wiki / "sources" / "src-a.md"
    # Write a page with flow-style lists — exactly as vault pages look
    src_page.write_text(
        '---\ntype: Source\nslug: src-a\nstatus: active\n'
        'aliases: ["My Source"]\ntags: [research, ai]\n---\nBody text.\n',
        encoding="utf-8",
    )
    make_wiki_page(wiki, "orgs", "org-b", "Org")
    cmap = build_canonical_map(wiki)
    edges_md = make_edges_md(tmp_path, """
        ## 2026-05-13 10:00 · raw/foo.md
        - (src-a, cites, org-b, 0.95, "test evidence")
    """)
    log = tmp_path / "log.md"
    log.write_text("", encoding="utf-8")

    all_edges = parse_edges_md(edges_md)
    promotable = filter_promotable(all_edges, cmap, threshold=0.7)
    apply_promotions(promotable, cmap, edges_md, log)

    updated = src_page.read_text(encoding="utf-8")
    # Flow-style lists must be preserved, not reflowed to block style
    assert 'aliases: ["My Source"]' in updated
    assert "tags: [research, ai]" in updated
    # The new edge was added
    assert "[[wiki/orgs/org-b]]" in updated
    # Body is intact
    assert "Body text." in updated
