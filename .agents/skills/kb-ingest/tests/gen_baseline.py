# /// script
# requires-python = ">=3.9,<3.14"
# dependencies = []
# ///
"""Extract the per-channel checklist-step inventory from the CURRENT (pre-split)
SKILL.md and freeze it as the coverage oracle. Run once, before splitting."""
import json
import re
from pathlib import Path

SKILL = Path(__file__).parent.parent / "SKILL.md"
OUT = Path(__file__).parent / "baseline_steps.json"
CHANNELS = ["journal", "meetings", "clippings", "docs", "emails", "chats"]


def norm(label: str) -> str:
    # Drop parenthetical qualifiers (path-specific notes) so "uses inbox path"
    # and "uses FINAL path" collapse to the same step identity.
    label = re.sub(r"\(.*?\)", "", label)
    return re.sub(r"\s+", " ", label).strip().lower()


def steps(text: str) -> list:
    return [norm(m) for m in re.findall(r"- \[ \] \*\*(.+?)\*\*", text)]


def main() -> None:
    text = SKILL.read_text()
    blocks = {}
    for ch in CHANNELS:
        m = re.search(
            rf"## {ch.capitalize()} channel checklist\n(.*?)(?=\n## )",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        assert m, f"channel block not found: {ch}"
        blocks[ch] = sorted(set(steps(m.group(1))))
    OUT.write_text(json.dumps(blocks, indent=2, ensure_ascii=False))
    for ch in CHANNELS:
        print(f"{ch}: {len(blocks[ch])} unique steps")


if __name__ == "__main__":
    main()
