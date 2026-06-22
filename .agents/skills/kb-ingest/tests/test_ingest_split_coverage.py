import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
BASELINE = Path(__file__).parent / "baseline_steps.json"
CHANNELS = ["journal", "meetings", "clippings", "docs", "emails", "chats"]
SHARED = [
    "phases/lock-dedup.md",
    "phases/edge-extraction.md",
    "phases/move-state-cleanup.md",
    "phases/reindex-log.md",
]


def norm(label: str) -> str:
    label = re.sub(r"\(.*?\)", "", label)
    return re.sub(r"\s+", " ", label).strip().lower()


def steps(text: str) -> set:
    return {norm(m) for m in re.findall(r"- \[ \] \*\*(.+?)\*\*", text)}


def steps_for(channel: str) -> set:
    out = set()
    for f in SHARED:
        out |= steps((SKILL_DIR / f).read_text())
    out |= steps((SKILL_DIR / "channels" / f"{channel}.md").read_text())
    return out


def test_no_step_dropped():
    baseline = json.loads(BASELINE.read_text())
    for ch in CHANNELS:
        have = steps_for(ch)
        missing = set(baseline[ch]) - have
        assert not missing, f"{ch}: split dropped steps {sorted(missing)}"
