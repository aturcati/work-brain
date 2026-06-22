import subprocess
import sys
from pathlib import Path

MOVE_PY = str(Path(__file__).parent.parent / "move_file.py")


def make_vault(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md")
    inbox = tmp_path / "raw" / "inbox" / "journal"
    inbox.mkdir(parents=True)
    return inbox


def run_move(src, channel, date):
    return subprocess.run(
        [sys.executable, MOVE_PY, "--src", str(src),
         "--channel", channel, "--date", date],
        capture_output=True, text=True,
    )


def test_move_partitions_by_date(tmp_path):
    inbox = make_vault(tmp_path)
    src = inbox / "note.md"
    src.write_text("body")
    r = run_move(src, "journal", "2026-06-11")
    assert r.returncode == 0
    dest = tmp_path / "raw" / "journal" / "2026" / "06" / "note.md"
    assert dest.exists() and not src.exists()
    assert str(dest) in r.stdout


def test_move_collision_refuses_overwrite(tmp_path):
    inbox = make_vault(tmp_path)
    dest = tmp_path / "raw" / "journal" / "2026" / "06" / "note.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("existing")
    src = inbox / "note.md"
    src.write_text("new content")
    r = run_move(src, "journal", "2026-06-11")
    assert r.returncode != 0
    assert dest.read_text() == "existing"  # never overwritten
    assert src.exists()  # source untouched


def test_move_rejects_bad_date(tmp_path):
    inbox = make_vault(tmp_path)
    src = inbox / "note.md"
    src.write_text("body")
    r = run_move(src, "journal", "June 2026")
    assert r.returncode != 0
    assert src.exists()


def test_move_missing_source_fails(tmp_path):
    make_vault(tmp_path)
    r = run_move(tmp_path / "raw" / "inbox" / "journal" / "ghost.md",
                 "journal", "2026-06-11")
    assert r.returncode != 0
