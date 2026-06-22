import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from state import load_state, save_state


def test_save_and_load_roundtrip(tmp_path):
    state_file = tmp_path / ".ingest-state.json"
    save_state(state_file, {"raw/a.md": {"status": "done"}})
    assert load_state(state_file) == {"raw/a.md": {"status": "done"}}


def test_save_leaves_no_tmp_file(tmp_path):
    state_file = tmp_path / ".ingest-state.json"
    save_state(state_file, {"raw/a.md": {"status": "done"}})
    assert not state_file.with_suffix(".tmp").exists()


def test_crashed_write_preserves_existing_state(tmp_path, monkeypatch):
    """A write that dies mid-stream must not corrupt the state file."""
    state_file = tmp_path / ".ingest-state.json"
    save_state(state_file, {"raw/a.md": {"status": "done"}})

    original_write_text = Path.write_text

    def partial_write(self, data, *args, **kwargs):
        original_write_text(self, data[: len(data) // 2], *args, **kwargs)
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(Path, "write_text", partial_write)
    with pytest.raises(OSError):
        save_state(state_file, {"raw/a.md": {"status": "done"}, "raw/b.md": {"status": "done"}})
    monkeypatch.undo()

    assert load_state(state_file) == {"raw/a.md": {"status": "done"}}
