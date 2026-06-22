import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from match import find_matching_meeting


def test_exact_match(tmp_path):
    (tmp_path / "2026-05-11-status-review.md").write_text("---\n---\n")
    result = find_matching_meeting("2026-05-11-status-review", tmp_path)
    assert result == tmp_path / "2026-05-11-status-review.md"


def test_no_date_prefix_fallback(tmp_path):
    # Same date, different title = different meeting. Only exact slug or
    # hex-suffix-stripped slug may match (AGENTS.md: provider slug suffixes).
    (tmp_path / "2026-05-11-status-review.md").write_text("---\n---\n")
    result = find_matching_meeting("2026-05-11-different-title", tmp_path)
    assert result is None


def test_hex_suffix_stripped(tmp_path):
    (tmp_path / "2026-05-11-status-review.md").write_text("---\n---\n")
    result = find_matching_meeting("2026-05-11-status-review-3e5f75", tmp_path)
    assert result == tmp_path / "2026-05-11-status-review.md"


def test_no_match_returns_none(tmp_path):
    result = find_matching_meeting("2026-05-11-status-review", tmp_path)
    assert result is None


def test_exact_preferred_over_date_prefix(tmp_path):
    (tmp_path / "2026-05-11-status-review.md").write_text("---\n---\n")
    (tmp_path / "2026-05-11-other-meeting.md").write_text("---\n---\n")
    result = find_matching_meeting("2026-05-11-status-review", tmp_path)
    assert result == tmp_path / "2026-05-11-status-review.md"
