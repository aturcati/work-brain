# /// script
# requires-python = ">=3.9,<3.14"
# dependencies = []
# ///
import json
import re
from pathlib import Path

SKILL = Path(__file__).parent.parent / "SKILL.md"
OUT = Path(__file__).parent / "baseline_steps.json"
# (exact block heading in SKILL.md  ->  provider file stem)
BLOCKS = {
    "Teams channel checklist": "teams",
    "Clippings channel checklist": "clippings",
    "Docs channel checklist": "docs",
    "Emails channel checklist": "emails-outlook",
    "Chats manual export checklist": "chats",
    "MeetGeek channel checklist": "meetgeek",
}


def norm(s):
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def steps(t):
    return [norm(m) for m in re.findall(r"- \[ \] \*\*(.+?)\*\*", t)]


def main():
    text = SKILL.read_text()
    out = {}
    for title, stem in BLOCKS.items():
        # Capture from this heading to the next top-level "## " or end-of-file.
        m = re.search(rf"## {re.escape(title)}\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
        assert m, f"block not found: {title}"
        out[stem] = sorted(set(steps(m.group(1))))
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    for k, v in out.items():
        print(f"{k}: {len(v)} steps")


if __name__ == "__main__":
    main()
