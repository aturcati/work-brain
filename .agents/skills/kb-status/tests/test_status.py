import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from status import (
    parse_overview_page_counts,
    parse_overview_last_ingest,
    count_inbox,
    count_quarantine,
    count_edge_proposals,
    count_log_entries,
    count_threads,
    format_dashboard,
)


# ── parse_overview_page_counts ──────────────────────────────

def test_parse_page_counts_reads_table():
    text = (
        "# overview\n\n"
        "## Page counts\n\n"
        "| Type | Count |\n"
        "|---|---|\n"
        "| Person | 31 |\n"
        "| Org | 5 |\n"
        "| Meeting | 7 |\n\n"
        "## Open action items\n0\n"
    )
    out = parse_overview_page_counts(text)
    assert out == {"Person": 31, "Org": 5, "Meeting": 7}


def test_parse_page_counts_missing_section_returns_empty():
    assert parse_overview_page_counts("# nothing here\n") == {}


def test_parse_page_counts_skips_zero_count_rows_kept():
    text = (
        "## Page counts\n\n"
        "| Type | Count |\n"
        "|---|---|\n"
        "| Project | 0 |\n"
        "| Topic | 2 |\n"
    )
    out = parse_overview_page_counts(text)
    assert out["Project"] == 0
    assert out["Topic"] == 2


# ── parse_overview_last_ingest ──────────────────────────────

def test_parse_last_ingest_reads_table():
    text = (
        "## Last ingest per channel\n\n"
        "| Channel | Last ingest |\n"
        "|---|---|\n"
        "| journal | — |\n"
        "| meetings | 2026-05-13 |\n"
    )
    out = parse_overview_last_ingest(text)
    assert out["journal"] == "—"
    assert out["meetings"] == "2026-05-13"


def test_parse_last_ingest_missing_section_returns_empty():
    assert parse_overview_last_ingest("nothing\n") == {}


# ── count_inbox ─────────────────────────────────────────────

def test_count_inbox_walks_channels(tmp_path):
    raw = tmp_path / "raw"
    (raw / "inbox" / "journal").mkdir(parents=True)
    (raw / "inbox" / "meetings").mkdir(parents=True)
    (raw / "inbox" / "journal" / "a.md").write_text("x")
    (raw / "inbox" / "journal" / "b.md").write_text("x")
    (raw / "inbox" / "meetings" / "m.md").write_text("x")
    out = count_inbox(raw)
    assert out == {"journal": 2, "meetings": 1}


def test_count_inbox_missing_inbox_returns_empty(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    assert count_inbox(raw) == {}


def test_count_inbox_ignores_non_md_files(tmp_path):
    raw = tmp_path / "raw"
    (raw / "inbox" / "journal").mkdir(parents=True)
    (raw / "inbox" / "journal" / "a.md").write_text("x")
    (raw / "inbox" / "journal" / "b.txt").write_text("x")
    out = count_inbox(raw)
    assert out == {"journal": 1}


# ── count_quarantine ────────────────────────────────────────

def test_count_quarantine_returns_count(tmp_path):
    q = tmp_path / "raw" / "quarantine"
    q.mkdir(parents=True)
    (q / "a.md").write_text("x")
    (q / "b.md").write_text("x")
    assert count_quarantine(tmp_path / "raw") == 2


def test_count_quarantine_missing_returns_zero(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    assert count_quarantine(raw) == 0


# ── count_edge_proposals ────────────────────────────────────

def test_count_edge_proposals_counts_tuple_lines(tmp_path):
    edges = tmp_path / "edges.md"
    edges.write_text(
        "# edges\n\n"
        "## 2026-05-13 14:30 · raw/foo.md\n"
        "- (a, attended, m, 0.9, \"e\")\n"
        "- (b, attended, m, 0.9, \"e\")\n\n"
        "## 2026-05-13 15:00 · raw/bar.md\n"
        "- (c, attended, m2, 0.9, \"x\")\n"
    )
    assert count_edge_proposals(edges) == 3


def test_count_edge_proposals_ignores_format_template(tmp_path):
    edges = tmp_path / "edges.md"
    edges.write_text(
        "# edges\n\n"
        "Format per ingest:\n"
        "- (subject_slug, predicate, object_slug, confidence, evidence_quote)\n\n"
        "## 2026-05-13 14:30 · raw/foo.md\n"
        "- (a, attended, m, 0.9, \"e\")\n"
    )
    assert count_edge_proposals(edges) == 1


def test_count_edge_proposals_missing_file_returns_zero(tmp_path):
    assert count_edge_proposals(tmp_path / "missing.md") == 0


# ── count_log_entries ───────────────────────────────────────

def test_count_log_entries_counts_h2_brackets(tmp_path):
    log = tmp_path / "log.md"
    log.write_text(
        "# log\n\n"
        "## [2026-05-11 00:00] kb-init | scaffold\n"
        "## [2026-05-12 00:00] kb-graph project | ok\n"
        "## not a log entry\n"
        "Some prose ## [bogus]\n"
    )
    assert count_log_entries(log) == 2


def test_count_log_entries_missing_returns_zero(tmp_path):
    assert count_log_entries(tmp_path / "missing.md") == 0


# ── count_threads ───────────────────────────────────────────

def test_count_threads_counts_md_files(tmp_path):
    threads = tmp_path / "wiki" / "threads"
    threads.mkdir(parents=True)
    (threads / "a.md").write_text("x")
    (threads / "b.md").write_text("x")
    assert count_threads(threads) == 2


def test_count_threads_missing_returns_zero(tmp_path):
    assert count_threads(tmp_path / "wiki" / "threads") == 0


# ── format_dashboard ────────────────────────────────────────

def test_format_dashboard_has_all_sections():
    now = datetime(2026, 5, 23, 17, 0, tzinfo=timezone.utc)
    out = format_dashboard(
        now=now,
        overview_age_hours=2.5,
        page_counts={"Person": 31, "Meeting": 7},
        last_ingest={"journal": "—", "meetings": "2026-05-13"},
        inbox={"journal": 0, "meetings": 0},
        quarantine=0,
        edges=1,
        log_entries=25,
        threads=0,
    )
    assert "work-brain status" in out
    assert "2026-05-23 17:00" in out
    assert "Person=31" in out
    assert "Meeting=7" in out
    assert "journal=0" in out
    assert "Quarantine:" in out
    assert "Edges inbox:" in out
    assert "rotation threshold: 500" in out
    assert "rotation threshold: 1000" in out
    assert "Last ingest:" in out
    assert "meetings=2026-05-13" in out
    assert "Open threads: 0" in out


def test_format_dashboard_zero_threads():
    now = datetime(2026, 5, 23, 17, 0, tzinfo=timezone.utc)
    out = format_dashboard(
        now=now, overview_age_hours=None, page_counts={}, last_ingest={}, inbox={},
        quarantine=0, edges=0, log_entries=0, threads=0,
    )
    assert "Open threads: 0" in out


def test_count_quarantine_excludes_error_sidecars(tmp_path):
    q = tmp_path / "raw" / "quarantine"
    q.mkdir(parents=True)
    (q / "foo.md").write_text("x")
    (q / "foo.error.md").write_text("err")
    (q / "bar.md").write_text("x")
    (q / "bar.error.md").write_text("err")
    # 4 files on disk but 2 incidents
    assert count_quarantine(tmp_path / "raw") == 2


def test_format_dashboard_overview_age_shown():
    now = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
    out = format_dashboard(
        now=now, overview_age_hours=2.5, page_counts={}, last_ingest={}, inbox={},
        quarantine=0, edges=0, log_entries=0, threads=0,
    )
    assert "2.5h old" in out


def test_format_dashboard_overview_missing():
    now = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
    out = format_dashboard(
        now=now, overview_age_hours=None, page_counts={}, last_ingest={}, inbox={},
        quarantine=0, edges=0, log_entries=0, threads=0,
    )
    assert "missing — run /kb-lint" in out
